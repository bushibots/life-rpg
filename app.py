import csv
import io
import time
import os
import json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
# REMOVED: werkzeug.security imports (We are standardizing on Bcrypt)
from flask_login import login_user, logout_user, login_required, current_user
from models import User, Goal, Habit, DailyLog, Feedback, QuestHistory, Notification
from datetime import date, timedelta, datetime
from extensions import db, login_manager, migrate, csrf
from sqlalchemy import func, extract
import calendar
from flask_migrate import Migrate
from weasyprint import HTML
from models import User, Goal, Habit, DailyLog, Feedback, QuestHistory
from utils import guess_category, smart_ai_parse, get_ai_feedback, get_backlog_strategy
from flask_wtf import FlaskForm
from collections import Counter
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import google.generativeai as genai
from flask import session

load_dotenv()

os.environ['TZ'] = 'Asia/Kolkata'
try:
    time.tzset()
except AttributeError:
    pass # Windows (Local PC) skips this, Linux (Server) uses it.

# --- FORM CLASSES ---
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

# --- PRESET LIBRARY ---
PRESETS = [
    {"id": 1, "name": "50 Pushups", "category": "Physical", "attribute": "STR", "difficulty": "Medium", "is_daily": True},
    {"id": 2, "name": "Morning Run (3km)", "category": "Physical", "attribute": "STR", "difficulty": "Hard", "is_daily": True},
    {"id": 11, "name": "Read 10 Pages", "category": "Intellect", "attribute": "INT", "difficulty": "Easy", "is_daily": True},
    {"id": 12, "name": "Code for 1 Hour", "category": "Career", "attribute": "INT", "difficulty": "Hard", "is_daily": True},
    {"id": 21, "name": "Meditation (10m)", "category": "Mental Health", "attribute": "WIS", "difficulty": "Easy", "is_daily": True},
    {"id": 31, "name": "Drink 3L Water", "category": "Health", "attribute": "CON", "difficulty": "Medium", "is_daily": True},
    {"id": 41, "name": "Call Family", "category": "Social", "attribute": "CHA", "difficulty": "Medium", "is_daily": False},
]

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-dev-key')

# --- FIXED: ABSOLUTE DATABASE PATH (Crucial for PythonAnywhere) ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'rpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

bcrypt = Bcrypt(app)

db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.before_request
def check_ban():
    if current_user.is_authenticated and hasattr(current_user, 'is_banned') and current_user.is_banned:
        logout_user()
        flash("Access Denied: Account suspended.", "danger")
        return redirect(url_for('login'))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
# --- HELPER FUNCTION: Get Monthly XP ---
def get_monthly_xp(user_id):
    today = date.today()
    # Calculates total XP earned only in the current month
    total = db.session.query(func.sum(QuestHistory.xp_gained)).filter(
        QuestHistory.user_id == user_id,
        extract('year', QuestHistory.date_completed) == today.year,
        extract('month', QuestHistory.date_completed) == today.month
    ).scalar()
    return total if total else 0

with app.app_context():
    db.create_all()

# --- ROUTES ---
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()

    # 1. DAILY RESET CHECK
    if current_user.last_check_date != today:
        user_goals = Goal.query.filter_by(user_id=current_user.id).all()
        for goal in user_goals:
            for habit in goal.habits:
                if habit.is_daily and habit.completed:
                    habit.completed = False
        current_user.last_check_date = today
        db.session.commit()

    goals = Goal.query.filter_by(user_id=current_user.id).all()

    # 2. GET COMPLETED TASKS (For Vanishing Logic)
    todays_completed = [
        q.name for q in QuestHistory.query.filter_by(user_id=current_user.id, date_completed=today).all()
    ]

    # 3. SMART COLLAPSE LOGIC (The New Part)
    # We want a list of Goal IDs that have tasks due TODAY
    active_goal_ids = []
    for goal in goals:
        has_today_task = False
        for habit in goal.habits:
            # Check if task is due today and NOT completed
            if habit.target_date == today and not habit.completed:
                has_today_task = True
                break
        if has_today_task:
            active_goal_ids.append(goal.id)

    # 4. STATS & REPORT
    monthly_xp = get_monthly_xp(current_user.id)
    overdue_count = Habit.query.join(Goal).filter(
        Goal.user_id == current_user.id,
        Habit.target_date < today,
        Habit.completed == False
    ).count()

    show_report = False
    prev_month_date = today.replace(day=1) - timedelta(days=1)
    if today.day <= 7:
        has_data = QuestHistory.query.filter(
            QuestHistory.user_id == current_user.id,
            extract('month', QuestHistory.date_completed) == prev_month_date.month
        ).first()
        if has_data: show_report = True

    return render_template('dashboard.html',
                           user=current_user,
                           goals=goals,
                           overdue_count=overdue_count,
                           monthly_xp=monthly_xp,
                           show_report=show_report,
                           prev_month=prev_month_date,
                           todays_completed=todays_completed,
                           active_goal_ids=active_goal_ids) # <--- PASS THIS LIST




@app.route('/analytics')
@login_required
def analytics():
    # --- 1. HANDLE DATE SELECTION ---
    today = date.today()

    # Get params from URL (e.g., ?month=1&year=2025)
    try:
        selected_month = int(request.args.get('month', today.month))
        selected_year = int(request.args.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    show_all = request.args.get('all') == 'true'

    # --- 2. FETCH DATA ---
    query = QuestHistory.query.filter_by(user_id=current_user.id)

    if not show_all:
        # Filter by the selected month/year
        query = query.filter(
            extract('year', QuestHistory.date_completed) == selected_year,
            extract('month', QuestHistory.date_completed) == selected_month
        )
        # Determine the "Reference Date" for the graphs
        # If looking at past month, set reference to the last day of that month
        last_day = calendar.monthrange(selected_year, selected_month)[1]
        reference_date = date(selected_year, selected_month, last_day)

        # If selected month is current month, clamp reference to today (don't show future)
        if selected_year == today.year and selected_month == today.month:
            reference_date = today
    else:
        reference_date = today # For All Time, just use today as anchor

    history = query.order_by(QuestHistory.date_completed.asc()).all()

    # --- 3. PROCESS GRAPHS ---

    # A. RADAR & ATTRIBUTES
    stats = {'STR': 0, 'INT': 0, 'WIS': 0, 'CON': 0, 'CHA': 0}
    for h in history:
        if h.stat_type in stats:
            stats[h.stat_type] += h.xp_gained
    radar_data = list(stats.values())
    radar_labels = list(stats.keys())

    # B. XP MAP (For Heatmap & Line Chart)
    xp_map = {}
    for h in history:
        d_str = h.date_completed.strftime('%Y-%m-%d')
        xp_map[d_str] = xp_map.get(d_str, 0) + h.xp_gained

    # C. HEALTH SCORE (Based on the selected period's reference date)
    # We look at the 7 days leading up to the reference_date
    last_7_days_dates = [reference_date - timedelta(days=i) for i in range(7)]
    active_days = sum(1 for day in last_7_days_dates if day.strftime('%Y-%m-%d') in xp_map)
    health_score = int((active_days / 7) * 100)

    # D. LINE CHART (Cumulative for the period)
    line_labels = []
    line_data = []
    cumulative_xp = 0

    # If filtering by month, we fill in missing days to make the chart smooth
    if not show_all:
        # Create a list of ALL days in that month (up to reference date)
        start_date = date(selected_year, selected_month, 1)
        delta = (reference_date - start_date).days + 1
        sorted_dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(delta)]
    else:
        # For all time, just use the days we have data
        sorted_dates = sorted(xp_map.keys())

    for d_str in sorted_dates:
        # Add daily gain to cumulative
        gain = xp_map.get(d_str, 0)
        cumulative_xp += gain
        line_labels.append(d_str)
        line_data.append(cumulative_xp)

    if not line_data:
        line_labels = [today.strftime('%Y-%m-%d')]
        line_data = [0]

    # E. DONUT (Difficulty)
    difficulty_counts = {'Easy': 0, 'Medium': 0, 'Hard': 0, 'Epic': 0}
    for h in history:
        if h.difficulty in difficulty_counts:
            difficulty_counts[h.difficulty] += 1

    # F. BAR CHART (Last 7 Days of Selected Period)
    bar_labels = []
    bar_data = []
    for i in range(6, -1, -1):
        d = reference_date - timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        bar_labels.append(d.strftime('%a')) # Mon, Tue...
        bar_data.append(xp_map.get(d_str, 0))

    return render_template('analytics.html',
                         user=current_user,
                         radar_data=radar_data,
                         radar_labels=radar_labels,
                         heatmap_data=xp_map,
                         health_score=health_score,
                         line_labels=line_labels,
                         line_data=line_data,
                         diff_data=list(difficulty_counts.values()),
                         bar_labels=bar_labels,
                         bar_data=bar_data,
                         # Pass selection back to UI
                         selected_month=selected_month,
                         selected_year=selected_year,
                         show_all=show_all)

@app.route('/planning')
@login_required
def planning():
    goals = Goal.query.filter_by(user_id=current_user.id).all()
    scheduled = []
    for g in goals:
        for h in g.habits:
            if h.target_date and not h.completed:
                scheduled.append(h)
    scheduled.sort(key=lambda x: x.target_date)

    date_strings = [h.target_date.strftime('%Y-%m-%d') for h in scheduled]
    counts = Counter(date_strings)
    sorted_dates = sorted(counts.keys())
    chart_data = [counts[d] for d in sorted_dates]

    return render_template('planning.html',
                           user=current_user,
                           goals=goals,
                           scheduled=scheduled,
                           chart_labels=sorted_dates,
                           chart_data=chart_data)

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    goal_id = request.form.get('goal_id')
    name = request.form.get('name')
    stat_type = request.form.get('stat_type')
    difficulty = request.form.get('difficulty')
    duration = request.form.get('duration')
    date_str = request.form.get('target_date')
    description = request.form.get('description') # <--- NEW: Get the description

    xp_map = {'Easy': 10, 'Medium': 30, 'Hard': 50, 'Epic': 100}
    xp = xp_map.get(difficulty, 10)

    target_date_obj = None
    if date_str:
        try:
            target_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            target_date_obj = None

    if name and goal_id:
        new_habit = Habit(
            goal_id=int(goal_id),
            name=name,
            stat_type=stat_type,
            difficulty=difficulty,
            xp_value=xp,
            duration=int(duration) if duration else 0,
            completed=False,
            is_daily=False,
            target_date=target_date_obj,
            description=description if description else "" # <--- NEW: Save it!
        )
        db.session.add(new_habit)
        db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/operations/backlog')
@login_required
def backlog_calculator():
    return render_template('backlog_calculator.html')

@app.route('/toggle_habit/<int:habit_id>', methods=['POST']) # Changed to POST for safety
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.get(habit_id)
    if habit and habit.goal.user_id == current_user.id:
        habit.completed = not habit.completed
        today = date.today()

        if habit.completed:
            # Add XP
            current_user.total_xp += habit.xp_value
            # Update Stats
            if habit.stat_type == 'STR': current_user.str_score += habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score += habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score += habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score += habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score += habit.xp_value

            # Log History
            history_entry = QuestHistory(
                user_id=current_user.id,
                name=habit.name,
                difficulty=habit.difficulty,
                stat_type=habit.stat_type,
                xp_gained=habit.xp_value,
                date_completed=today
            )
            db.session.add(history_entry)
            action = "completed"
        else:
            # Remove XP (Undo)
            current_user.total_xp -= habit.xp_value
            # Remove Stats
            if habit.stat_type == 'STR': current_user.str_score -= habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score -= habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score -= habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score -= habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score -= habit.xp_value

            # Remove History Log
            log_to_delete = QuestHistory.query.filter_by(
                user_id=current_user.id,
                name=habit.name,
                date_completed=today
            ).order_by(QuestHistory.id.desc()).first()
            if log_to_delete:
                db.session.delete(log_to_delete)
            action = "uncompleted"

        db.session.commit()

        # Calculate new Monthly XP to update the UI instantly
        new_monthly_xp = get_monthly_xp(current_user.id)

        return jsonify({
            'success': True,
            'action': action,
            'new_total_xp': current_user.total_xp,
            'new_monthly_xp': new_monthly_xp,
            'habit_id': habit.id
        })

    return jsonify({'success': False}), 400

@app.route('/add_goal', methods=['POST'])
@login_required
def add_goal():
    name = request.form.get('name')
    if name:
        db.session.add(Goal(name=name, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_goal/<int:goal_id>')
@login_required
def delete_goal(goal_id):
    g = db.session.get(Goal, goal_id)
    if g and g.user_id == current_user.id:
        db.session.delete(g)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_habit/<int:habit_id>')
@login_required
def delete_habit(habit_id):
    h = db.session.get(Habit, habit_id)
    if h:
        # GRANT ACCESS IF: User owns it OR User is Admin
        if h.goal.user_id == current_user.id or current_user.is_admin:
            target_user_id = h.goal.user_id # Remember who we are deleting from
            db.session.delete(h)
            db.session.commit()

            # IF ADMIN ACTION: Redirect back to inspection, not dashboard
            if current_user.is_admin and target_user_id != current_user.id:
                flash(f"Moderation: Mission '{h.name}' terminated.", "warning")
                return redirect(url_for('admin_inspect', user_id=target_user_id))

    return redirect(url_for('dashboard'))

@app.route('/admin/inspect/<int:user_id>')
@login_required
def admin_inspect(user_id):
    # SECURITY CHECK: Only Admins can enter
    if not current_user.is_admin:
        flash("Unauthorized Access.", "danger")
        return redirect(url_for('dashboard'))

    target_user = db.session.get(User, user_id)
    if not target_user:
        return redirect(url_for('admin_panel'))

    # Fetch ALL active missions for this user
    habits = Habit.query.join(Goal).filter(Goal.user_id == user_id).all()

    return render_template('admin_inspect.html', target=target_user, habits=habits)

@app.route('/edit_habit', methods=['POST'])
@login_required
def edit_habit():
    h = db.session.get(Habit, request.form.get('habit_id'))
    if h and h.goal.user_id == current_user.id:
        h.name = request.form.get('name')
        h.difficulty = request.form.get('difficulty')
        h.description = request.form.get('description')
        h.is_daily = True if request.form.get('is_daily') else False

        # 1. Handle Date
        date_str = request.form.get('target_date')
        if date_str:
            h.target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            h.target_date = None

        # 2. Handle Category Change
        new_cat_name = request.form.get('category_name')
        if new_cat_name and new_cat_name != h.goal.name:
            new_goal = Goal.query.filter_by(user_id=current_user.id, name=new_cat_name).first()
            if not new_goal:
                new_goal = Goal(name=new_cat_name, user_id=current_user.id)
                db.session.add(new_goal)
                db.session.flush()
            h.goal_id = new_goal.id

        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if request.method == 'POST':
        # FIXED: Use Flask-WTF validation for cleaner handling
        if form.validate_on_submit():
            # FIXED: Ensure hashing matches Login logic
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(username=form.username.data, password=hashed_password)
            db.session.add(user)
            starter_goal = Goal(name="Starter Quests", user=user)
            db.session.add(starter_goal)
            db.session.flush()
            h1 = Habit(name="Create your first real task", difficulty="Easy", stat_type='INT', xp_value=10, goal=starter_goal)
            h2 = Habit(name="Drink a glass of water", difficulty="Easy", stat_type='CON', xp_value=10, goal=starter_goal)
            h3 = Habit(name="Visit the Focus Hub", difficulty="Easy", stat_type='WIS', xp_value=10, goal=starter_goal)
            db.session.add_all([h1, h2, h3])
            db.session.commit()
            login_user(user)
            flash('Welcome, Agent.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        # FIXED: Use bcrypt.check_password_hash instead of werkzeug
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True if request.form.get('remember') else False)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials. Access Denied.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html', user=current_user, presets=PRESETS)

@app.route('/restore_preset/<int:preset_id>')
@login_required
def restore_preset(preset_id):
    p = next((x for x in PRESETS if x['id'] == preset_id), None)
    g = Goal.query.filter_by(user_id=current_user.id, name=p['category']).first()
    if not g:
        g = Goal(name=p['category'], user_id=current_user.id)
        db.session.add(g)
        db.session.commit()
    db.session.add(Habit(name=p['name'], goal_id=g.id, difficulty=p['difficulty'], is_daily=p['is_daily'], xp_value=10, stat_type=p['attribute']))
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    if request.form.get('username'): current_user.username = request.form.get('username')
    # FIXED: Standardize profile update hashing to use Bcrypt as well
    if request.form.get('password'):
        current_user.password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
    db.session.commit()
    return redirect(url_for('settings'))

@app.route('/reset_progress')
@login_required
def reset_progress():
    current_user.total_xp = 0
    current_user.str_score = 0
    current_user.int_score = 0
    current_user.wis_score = 0
    current_user.cha_score = 0
    current_user.con_score = 0
    habits = Habit.query.join(Goal).filter(Goal.user_id == current_user.id).all()
    for h in habits:
        h.completed = False
    db.session.query(QuestHistory).filter(QuestHistory.user_id==current_user.id).delete()
    db.session.commit()
    return redirect(url_for('settings'))

@app.route('/mission_print')
@login_required
def mission_print():
    habits = Habit.query.join(Goal).filter(Goal.user_id == current_user.id).all()
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    week_labels = [(start_of_week + timedelta(days=i)).strftime('%a %d') for i in range(7)]
    return render_template('print.html', habits=habits, week_labels=week_labels, user=current_user)

@app.route('/get_reminders')
def get_reminders():
    return {"alert": False}

@app.route('/export')
@login_required
def export_data():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Task', 'Category', 'Attribute', 'XP', 'Difficulty'])
    history = QuestHistory.query.filter_by(user_id=current_user.id).order_by(QuestHistory.date_completed.desc()).all()
    for h in history:
        writer.writerow([h.date_completed, h.name, 'N/A', h.stat_type, h.xp_gained, h.difficulty])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=cosmo_tracker_export.csv"})

# --- ADMIN ROUTES ---

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access Denied: Admin privileges required.", "danger")
        return redirect(url_for('dashboard'))

    # FETCH ALL USERS FOR THE ROSTER
    users_list = User.query.all()
    total_quests = Habit.query.count()
    active_feedbacks = Feedback.query.order_by(Feedback.timestamp.desc()).all()

    return render_template('admin.html',
                         users_list=users_list,
                         users=len(users_list),
                         quests=total_quests,
                         feedbacks=active_feedbacks)

@app.route('/admin/toggle_pro/<int:user_id>')
@login_required
def toggle_pro(user_id):
    # Only Admin can flip this switch
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    u = db.session.get(User, user_id)
    if u:
        u.is_pro = not u.is_pro
        db.session.commit()
        status = "ENABLED" if u.is_pro else "DISABLED"
        flash(f"AI Clearance {status} for Agent {u.username}.", "info")

    return redirect(url_for('admin_panel'))

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    msg = request.form.get('message')
    if msg:
        db.session.add(Feedback(user_id=current_user.id, message=msg))
        db.session.commit()
        flash("System Log updated.", "success")
    return redirect(url_for('dashboard'))

@app.route('/delete_account')
@login_required
def delete_account():
    feedbacks = Feedback.query.filter_by(user_id=current_user.id).all()
    for f in feedbacks: db.session.delete(f)
    history = QuestHistory.query.filter_by(user_id=current_user.id).all()
    for h in history: db.session.delete(h)
    db.session.commit()
    user = db.session.get(User, current_user.id)
    db.session.delete(user)
    db.session.commit()
    logout_user()
    return redirect(url_for('register'))

@app.route('/admin/mark_read/<int:feedback_id>')
@login_required
def mark_read(feedback_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    f = db.session.get(Feedback, feedback_id)
    if f:
        f.is_read = not f.is_read
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/ban/<int:user_id>')
@login_required
def ban_user(user_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    u = db.session.get(User, user_id)
    if u and not u.is_admin:
        u.is_banned = not u.is_banned
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_feedback', methods=['POST'])
@login_required
def delete_feedback():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    action = request.form.get('action')
    if action == 'delete_all':
        db.session.query(Feedback).delete()
    elif action == 'delete_selected':
        ids = request.form.getlist('feedback_ids')
        for fid in ids:
            f = db.session.get(Feedback, int(fid))
            if f: db.session.delete(f)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_tasks():
    if request.method == 'POST':
        # --- 1. COOLDOWN CHECK ---
        current_time = time.time()
        last_request_time = session.get('last_ai_usage', 0)
        cooldown_duration = 30 # Lock for 30 seconds (Increase to 60 if you want)

        if (current_time - last_request_time) < cooldown_duration:
            wait_seconds = int(cooldown_duration - (current_time - last_request_time))
            flash(f"⚠️ AI Core Recharging. Stand by for {wait_seconds} seconds.", "warning")
            return redirect(url_for('import_tasks'))

        # --- 2. STANDARD PROCESSING ---
        raw_text = request.form.get('raw_text')
        if not raw_text:
            flash("Please paste some text first!", "error")
            return redirect(url_for('import_tasks'))

        new_tasks_data = []
        # Mark the timestamp NOW so the lock engages
        session['last_ai_usage'] = current_time

        if current_user.is_pro:
           api_key = os.getenv('GEMINI_API_KEY')
           # Note: Make sure smart_ai_parse is imported from utils
           new_tasks_data = smart_ai_parse(raw_text, api_key)
        else:
            # Fallback for non-pro users
            lines = raw_text.split('\n')
            for line in lines:
                if line.strip():
                    new_tasks_data.append(guess_category(line))

        # --- 3. SAVE TO DB (Standard Logic) ---
        count = 0
        diff_map = {1: 'Easy', 2: 'Medium', 3: 'Hard'}
        stat_map = {
            'Strength': 'STR', 'Physical': 'STR', 'Intelligence': 'INT',
            'Intellect': 'INT', 'Charisma': 'CHA', 'Social': 'CHA',
            'Creativity': 'WIS', 'Mental Health': 'WIS', 'General': 'CON', 'Health': 'CON'
        }

        for data in new_tasks_data:
            cat_name = data.get('category', 'General')
            goal = Goal.query.filter_by(user_id=current_user.id, name=cat_name).first()
            if not goal:
                goal = Goal(name=cat_name, user_id=current_user.id)
                db.session.add(goal)
                db.session.flush()

            difficulty_int = data.get('difficulty', 1)

            # Handle potential AI date errors gracefully
            target_date_obj = None
            date_str = data.get('target_date')
            if date_str:
                try:
                    target_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    target_date_obj = None

            new_habit = Habit(
                name=data['name'],
                goal_id=goal.id,
                difficulty=diff_map.get(difficulty_int, 'Easy'),
                stat_type=stat_map.get(cat_name, 'CON'),
                xp_value=10 * difficulty_int,
                is_daily=False,
                completed=False,
                target_date=target_date_obj,
                description=data.get('description', '')
            )
            db.session.add(new_habit)
            count += 1

        db.session.commit()
        flash(f"Successfully imported {count} quests!", "success")
        return redirect(url_for('dashboard'))

    return render_template('import_tasks.html')

@app.route('/focus_hub')
@login_required
def focus_hub():
    from datetime import date
    today = date.today()
    if current_user.last_active_date:
        delta = (today - current_user.last_active_date).days
        if delta > 1:
            current_user.current_streak = 0
            db.session.commit()
    daily_target = 240
    user_time = current_user.total_focus_time if current_user.total_focus_time else 0
    progress_pct = min(100, int((user_time / daily_target) * 100))
    return render_template('focus.html', user=current_user, target=daily_target, progress=progress_pct)

@app.route('/save_focus_session', methods=['POST'])
@login_required
def save_focus_session():
    data = request.json
    minutes = data.get('minutes', 25)
    current_user.total_focus_time += minutes
    current_user.last_active_date = date.today()
    xp_gained = minutes * 2
    gold_gained = max(1, int(minutes / 10))
    current_user.total_xp += xp_gained
    current_user.gold += gold_gained
    db.session.commit()
    return jsonify({'success': True, 'new_xp': current_user.total_xp, 'new_gold': current_user.gold})

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/audit')
@login_required
def audit():
    today = date.today()
    overdue_tasks = Habit.query.join(Goal).filter(
        Goal.user_id == current_user.id,
        Habit.target_date < today,
        Habit.completed == False
    ).order_by(Habit.target_date).all()
    return render_template('audit.html', tasks=overdue_tasks)

@app.route('/process_audit', methods=['POST'])
@login_required
def process_audit():
    action = request.form.get('action')
    task_ids = request.form.getlist('task_ids')
    today = date.today()
    count = 0
    for tid in task_ids:
        habit = Habit.query.get(int(tid))
        if habit and habit.goal.user_id == current_user.id:
            if action == 'delete':
                db.session.delete(habit)
            # FIXED: Matches value="today" from HTML
            elif action == 'today':
                habit.target_date = today
            # FIXED: Matches value="tomorrow" from HTML
            elif action == 'tomorrow':
                habit.target_date = today + timedelta(days=1)
            # FIXED: Matches value="unschedule" from HTML
            elif action == 'unschedule':
                habit.target_date = None
            count += 1
    db.session.commit()
    flash(f"Processed {count} items.", "success")
    return redirect(url_for('audit'))

@app.route('/edit_goal', methods=['POST'])
@login_required
def edit_goal():
    goal_id = request.form.get('goal_id')
    new_name = request.form.get('name')

    goal = db.session.get(Goal, goal_id)
    if goal and goal.user_id == current_user.id and new_name:
        goal.name = new_name
        db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/admin/bulk_purge', methods=['POST'])
@login_required
def bulk_purge():
    if not current_user.is_admin:
        flash("Unauthorized Access.", "danger")
        return redirect(url_for('dashboard'))

    target_user_id = request.form.get('target_user_id')
    habit_ids = request.form.getlist('habit_ids')
    system_msg = request.form.get('system_message') # Capture your custom text

    if not habit_ids:
        flash("No missions selected.", "info")
        return redirect(url_for('admin_inspect', user_id=target_user_id))

    count = 0
    for hid in habit_ids:
        habit = db.session.get(Habit, int(hid))
        if habit:
            db.session.delete(habit)
            count += 1

    # SEND NOTIFICATION IF MESSAGE PROVIDED
    if system_msg and target_user_id:
        new_notif = Notification(
            user_id=target_user_id,
            message=system_msg,
            type='warning'
        )
        db.session.add(new_notif)

    db.session.commit()
    flash(f"Purged {count} missions. User notified.", "warning")
    return redirect(url_for('admin_inspect', user_id=target_user_id))

@app.route('/admin/broadcast', methods=['POST'])
@login_required
def admin_broadcast():
    if not current_user.is_admin:
        flash("Unauthorized.", "danger")
        return redirect(url_for('dashboard'))

    msg_text = request.form.get('broadcast_message')

    if msg_text:
        all_agents = User.query.all()
        count = 0
        for agent in all_agents:
            new_notif = Notification(
                user_id=agent.id,
                message=msg_text,
                type='info'  # <--- CHANGE THIS: Sets the color to Blue
            )
            db.session.add(new_notif)
            count += 1

        db.session.commit()
        flash(f"📢 Transmission sent to {count} agents.", "info") # Blue flash for you too

    return redirect(url_for('admin_panel'))

@app.route('/dismiss_notification/<int:notif_id>')
@login_required
def dismiss_notification(notif_id):
    n = db.session.get(Notification, notif_id)
    if n and n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return redirect(url_for('dashboard'))

# Inside app.py

@app.route('/api/strategy_brief', methods=['POST'])
@login_required
@csrf.exempt
def strategy_brief():
    data = request.json
    hours = data.get('hours', 0)
    days = data.get('days', 0)
    mode = data.get('mode', 'General')

    # Call the AI function we just wrote
    ai_message = get_backlog_strategy(hours, days, mode)

    return jsonify({'message': ai_message})

# --- MISSING GRAPH ROUTE ---
# --- MISSING GRAPH DATA (FIXED FOR DailyLog) ---
@app.route('/api/missed_data')
@login_required
def missed_data():
    today = date.today()
    missed_points = []
    cat_map = {"Strength": 4, "Intelligence": 3, "Charisma": 2, "Creativity": 1, "General": 0}

    for i in range(7):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%b %d")

        # FIXED: Use QuestHistory instead of HabitHistory
        # We match by NAME because QuestHistory doesn't store habit_id
        completed_names = [h.name for h in QuestHistory.query.filter_by(user_id=current_user.id, date_completed=check_date).all()]
        active_habits = Habit.query.filter(Habit.goal.has(user_id=current_user.id)).all()

        for habit in active_habits:
            if habit.name not in completed_names:
                missed_points.append({
                    "x": date_str,
                    "y": cat_map.get(habit.stat_type, 0),
                    "task": habit.name,
                    "r": 6
                })

    return jsonify(missed_points)

# --- ARCHIVE & HISTORY ROUTES ---

# --- FIXED: RENAMED TO 'history' TO MATCH BASE.HTML ---
@app.route('/history')
@login_required
def history():
    # Get distinct dates from history
    dates = db.session.query(QuestHistory.date_completed).filter_by(user_id=current_user.id).distinct().all()
    months = set()
    for d in dates:
        if d.date_completed:
            months.add((d.date_completed.year, d.date_completed.month))

    sorted_months = sorted(list(months), reverse=True)
    archives = []
    for y, m in sorted_months:
        month_name = calendar.month_name[m]
        xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter(
            QuestHistory.user_id == current_user.id,
            extract('year', QuestHistory.date_completed) == y,
            extract('month', QuestHistory.date_completed) == m
        ).scalar() or 0

        archives.append({'year': y, 'month': m, 'name': month_name, 'xp': xp})

    return render_template('history.html', archives=archives)

@app.route('/history_details/<int:year>/<int:month>')
@login_required
def history_details(year, month):
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).order_by(QuestHistory.date_completed.desc()).all()

    month_name = calendar.month_name[month]
    total_xp = sum(l.xp_gained for l in logs)

    return render_template('history_details.html', logs=logs, month=month_name, year=year, total_xp=total_xp)

@app.route('/download_report/<int:year>/<int:month>')
@login_required
def download_report(year, month):
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).order_by(QuestHistory.date_completed).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Mission Name', 'Category', 'Difficulty', 'XP Gained'])
    for log in logs:
        writer.writerow([log.date_completed, log.name, log.stat_type, log.difficulty, log.xp_gained])

    output.seek(0)
    month_name = calendar.month_name[month]
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=Mission_Report_{month_name}_{year}.csv"}
    )

# --- NEW PDF ROUTE ---
@app.route('/download_report_pdf/<int:year>/<int:month>')
@login_required
def download_report_pdf(year, month):
    # 1. Fetch Data
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).order_by(QuestHistory.date_completed).all()

    total_xp = sum(l.xp_gained for l in logs)
    month_name = calendar.month_name[month]

    # 2. Render HTML Template
    html = render_template('report_pdf.html',
                           user=current_user,
                           logs=logs,
                           total_xp=total_xp,
                           mission_count=len(logs),
                           month_name=month_name,
                           year=year,
                           now=datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 3. Convert to PDF using WeasyPrint
    pdf = HTML(string=html).write_pdf()

    # 4. Return as Download
    return Response(
        pdf,
        mimetype='application/pdf',
        headers={"Content-Disposition": f"attachment;filename=Mission_Dossier_{month_name}_{year}.pdf"}
    )

if __name__ == '__main__':
    app.run(debug=True)