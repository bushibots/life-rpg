import os
import time
import io  # <--- FIXED: Added missing import
import csv # <--- FIXED: Added missing import
from collections import Counter # <--- FIXED: Added missing import
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import requests
from utils import generate_genie_questions, generate_genie_blueprint

# --- FLASK & EXTENSIONS ---
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_bcrypt import Bcrypt
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import func, extract
import google.generativeai as genai
from weasyprint import HTML # <--- FIXED: Added missing import
import uuid

# --- LOCAL IMPORTS ---
from extensions import db
# Import utils functions
from utils import guess_category, smart_ai_parse, get_ai_feedback, get_backlog_strategy

# Load Environment Variables
load_dotenv()

# Setup Timezone
os.environ['TZ'] = 'Asia/Kolkata'
try:
    time.tzset()
except AttributeError:
    pass

app = Flask(__name__)

# ========================================================
# 1. CONFIGURATION
# ========================================================
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'rpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-dev-key-change-this')

# Email Config
app.config['MAIL_SERVER'] = 'smtp-relay.brevo.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('LifeRPG Command', os.getenv('MAIL_USERNAME'))

# ========================================================
# 2. INITIALIZATION
# ========================================================
db.init_app(app)
bcrypt = Bcrypt(app)
mail = Mail(app)
migrate = Migrate(app, db)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========================================================
# 3. LOAD MODELS
# ========================================================
from models import User, Goal, Habit, DailyLog, Feedback, QuestHistory, Notification, Task

# ========================================================
# 4. PRESETS
# ========================================================
PRESETS = [
    {"id": 1, "name": "50 Pushups", "category": "Physical", "attribute": "STR", "difficulty": "Medium", "is_daily": True},
    {"id": 2, "name": "Morning Run (3km)", "category": "Physical", "attribute": "STR", "difficulty": "Hard", "is_daily": True},
    {"id": 11, "name": "Read 10 Pages", "category": "Intellect", "attribute": "INT", "difficulty": "Easy", "is_daily": True},
    {"id": 12, "name": "Code for 1 Hour", "category": "Career", "attribute": "INT", "difficulty": "Hard", "is_daily": True},
    {"id": 21, "name": "Meditation (10m)", "category": "Mental Health", "attribute": "WIS", "difficulty": "Easy", "is_daily": True},
    {"id": 31, "name": "Drink 3L Water", "category": "Health", "attribute": "CON", "difficulty": "Medium", "is_daily": True},
    {"id": 41, "name": "Call Family", "category": "Social", "attribute": "CHA", "difficulty": "Medium", "is_daily": False},
]

# ========================================================
# 5. HELPER FUNCTIONS
# ========================================================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def check_ban():
    if current_user.is_authenticated and hasattr(current_user, 'is_banned') and current_user.is_banned:
        logout_user()
        flash("Access Denied: Account suspended.", "danger")
        return redirect(url_for('login'))

def get_monthly_xp(user_id):
    today = date.today()
    total = db.session.query(func.sum(QuestHistory.xp_gained)).filter(
        QuestHistory.user_id == user_id,
        extract('year', QuestHistory.date_completed) == today.year,
        extract('month', QuestHistory.date_completed) == today.month
    ).scalar()
    return total if total else 0

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

# ========================================================
# 6. ROUTES
# ========================================================

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

    # 2. GET COMPLETED TASKS
    todays_completed = [
        q.name for q in QuestHistory.query.filter_by(user_id=current_user.id, date_completed=today).all()
    ]

    # 3. STATS
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
                           todays_completed=todays_completed)

@app.route('/guest_login')
def guest_login():
    # Generate a random temporary username
    guest_name = f"Guest_{uuid.uuid4().hex[:8]}"

    # Create the guest user
    guest_user = User(
        username=guest_name,
        email=f"{guest_name}@temp.com",
        password="none",
        is_guest=True
    )
    db.session.add(guest_user)
    db.session.commit()

    # Log them in instantly
    login_user(guest_user)
    flash("Welcome, Guest! Register to save your progress.", "info")
    return redirect(url_for('dashboard'))

@app.route('/analytics')
@login_required
def analytics():
    today = date.today()
    try:
        selected_month = int(request.args.get('month', today.month))
        selected_year = int(request.args.get('year', today.year))
    except ValueError:
        selected_month = today.month
        selected_year = today.year

    show_all = request.args.get('all') == 'true'

    query = QuestHistory.query.filter_by(user_id=current_user.id)

    if not show_all:
        query = query.filter(
            extract('year', QuestHistory.date_completed) == selected_year,
            extract('month', QuestHistory.date_completed) == selected_month
        )

    history = query.order_by(QuestHistory.date_completed.asc()).all()

    # A. RADAR
    stats = {'STR': 0, 'INT': 0, 'WIS': 0, 'CON': 0, 'CHA': 0}
    for h in history:
        if h.stat_type in stats:
            stats[h.stat_type] += h.xp_gained
    radar_data = list(stats.values())
    radar_labels = list(stats.keys())

    # B. XP MAP
    xp_map = {}
    for h in history:
        d_str = h.date_completed.strftime('%Y-%m-%d')
        xp_map[d_str] = xp_map.get(d_str, 0) + h.xp_gained

    # C. HEALTH SCORE
    last_7_days_dates = [today - timedelta(days=i) for i in range(7)]
    active_days = sum(1 for day in last_7_days_dates if day.strftime('%Y-%m-%d') in xp_map)
    health_score = int((active_days / 7) * 100)

    # D. LINE CHART
    line_labels = []
    line_data = []
    cumulative_xp = 0
    sorted_dates = sorted(xp_map.keys())

    for d_str in sorted_dates:
        cumulative_xp += xp_map.get(d_str, 0)
        line_labels.append(d_str)
        line_data.append(cumulative_xp)

    if not line_data:
        line_labels = [today.strftime('%Y-%m-%d')]
        line_data = [0]

    # E. DONUT
    difficulty_counts = {'Easy': 0, 'Medium': 0, 'Hard': 0, 'Epic': 0}
    for h in history:
        if h.difficulty in difficulty_counts:
            difficulty_counts[h.difficulty] += 1

    # F. BAR CHART
    bar_labels = []
    bar_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        bar_labels.append(d.strftime('%a'))
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
    counts = Counter(date_strings) # <--- This works now because we imported Counter
    sorted_dates = sorted(counts.keys())
    chart_data = [counts[d] for d in sorted_dates]

    return render_template('planning.html',
                           user=current_user,
                           goals=goals,
                           scheduled=scheduled,
                           chart_labels=sorted_dates,
                           chart_data=chart_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # 1. Create the form so the HTML page doesn't crash
    form = RegisterForm()

    # If a normal user is logged in, send them away. If it's a guest, let them stay.
    if current_user.is_authenticated and not current_user.is_guest:
        return redirect(url_for('dashboard'))

    # 2. Use WTForms validation
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # CHECK IF THEY ARE A GUEST UPGRADING
        if current_user.is_authenticated and current_user.is_guest:
            current_user.username = username
            current_user.password = hashed_password
            current_user.email = None  # Clear the temporary guest email
            current_user.is_guest = False
            db.session.commit()
            flash("Account linked! WARNING: No recovery email set. Add one in Settings to prevent data loss.", "warning")
            return redirect(url_for('dashboard'))

        # ELSE: Normal registration for totally new people
        else:
            # We pass email=None explicitly
            new_user = User(username=username, password=hashed_password, email=None)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful! WARNING: No recovery email set. Add one in Settings to prevent data loss.", "warning")
            return redirect(url_for('login'))

    # 3. Pass the form to the template
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        # FIXED: Using bcrypt.check_password_hash
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True if request.form.get('remember') else False)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Check username and password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    goal_id = request.form.get('goal_id')
    name = request.form.get('name')
    stat_type = request.form.get('stat_type')
    difficulty = request.form.get('difficulty')
    date_str = request.form.get('target_date')
    description = request.form.get('description')

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
            completed=False,
            is_daily=False,
            target_date=target_date_obj,
            description=description if description else ""
        )
        db.session.add(new_habit)
        db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/toggle_habit/<int:habit_id>', methods=['POST'])
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.get(habit_id)
    if habit and habit.goal.user_id == current_user.id:
        habit.completed = not habit.completed
        today = date.today()

        if habit.completed:
            current_user.total_xp += habit.xp_value
            if habit.stat_type == 'STR': current_user.str_score += habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score += habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score += habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score += habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score += habit.xp_value

            history_entry = QuestHistory(
                user_id=current_user.id,
                name=habit.name,
                difficulty=habit.difficulty,
                stat_type=habit.stat_type,
                xp_gained=habit.xp_value,
                date_completed=today
            )
            db.session.add(history_entry)
        else:
            current_user.total_xp -= habit.xp_value
            if habit.stat_type == 'STR': current_user.str_score -= habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score -= habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score -= habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score -= habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score -= habit.xp_value

            log_to_delete = QuestHistory.query.filter_by(
                user_id=current_user.id,
                name=habit.name,
                date_completed=today
            ).order_by(QuestHistory.id.desc()).first()
            if log_to_delete:
                db.session.delete(log_to_delete)

        db.session.commit()
        new_monthly_xp = get_monthly_xp(current_user.id)

        return jsonify({
            'success': True,
            'new_total_xp': current_user.total_xp,
            'new_monthly_xp': new_monthly_xp
        })

    return jsonify({'success': False}), 400

@app.route('/add_goal', methods=['POST'])
@login_required
def add_goal():
    name = request.form.get('name')
    # ADD THIS GUEST CHECK:
    if current_user.is_guest:
        current_goals = Goal.query.filter_by(user_id=current_user.id).count()
        if current_goals >= 2:
            flash("Guests can only create 2 categories. Please Register to unlock unlimited slots!", "warning")
            return redirect(url_for('planning'))
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
    if h and (h.goal.user_id == current_user.id or current_user.is_admin):
        target_id = h.goal.user_id
        db.session.delete(h)
        db.session.commit()
        if current_user.is_admin and target_id != current_user.id:
            return redirect(url_for('admin_inspect', user_id=target_id))
    return redirect(url_for('dashboard'))

@app.route('/edit_habit', methods=['POST'])
@login_required
def edit_habit():
    h = db.session.get(Habit, request.form.get('habit_id'))
    if h and h.goal.user_id == current_user.id:
        h.name = request.form.get('name')
        h.difficulty = request.form.get('difficulty')
        h.description = request.form.get('description')
        h.is_daily = True if request.form.get('is_daily') else False

        date_str = request.form.get('target_date')
        if date_str:
            h.target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            h.target_date = None

        # Handle Category Move
        new_cat = request.form.get('category_name')
        if new_cat and new_cat != h.goal.name:
            goal = Goal.query.filter_by(user_id=current_user.id, name=new_cat).first()
            if not goal:
                goal = Goal(name=new_cat, user_id=current_user.id)
                db.session.add(goal)
                db.session.flush()
            h.goal_id = goal.id

        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        new_email = request.form.get('email')
        if new_email:
            existing = User.query.filter_by(email=new_email).first()
            if existing and existing.id != current_user.id:
                flash('Email already in use.', 'danger')
            else:
                current_user.email = new_email
                db.session.commit()
                flash('Settings updated.', 'success')
    return render_template('settings.html', user=current_user, presets=PRESETS)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    if request.form.get('username'):
        current_user.username = request.form.get('username')
    if request.form.get('password'):
        # FIXED: Use bcrypt
        current_user.password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
    db.session.commit()
    return redirect(url_for('settings'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    return redirect(url_for('login'))

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
    for h in habits: h.completed = False

    QuestHistory.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for('settings'))

@app.route('/restore_preset/<int:preset_id>')
@login_required
def restore_preset(preset_id):
    p = next((x for x in PRESETS if x['id'] == preset_id), None)
    if p:
        g = Goal.query.filter_by(user_id=current_user.id, name=p['category']).first()
        if not g:
            g = Goal(name=p['category'], user_id=current_user.id)
            db.session.add(g)
            db.session.commit()

        h = Habit(name=p['name'], goal_id=g.id, difficulty=p['difficulty'],
                  is_daily=p['is_daily'], xp_value=10, stat_type=p['attribute'])
        db.session.add(h)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/mission_print')
@login_required
def mission_print():
    habits = Habit.query.join(Goal).filter(Goal.user_id == current_user.id).all()
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    week_labels = [(start_week + timedelta(days=i)).strftime('%a %d') for i in range(7)]
    return render_template('print.html', habits=habits, week_labels=week_labels, user=current_user)

@app.route('/export')
@login_required
def export_data():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Task', 'Category', 'Attribute', 'XP', 'Difficulty'])
    history = QuestHistory.query.filter_by(user_id=current_user.id).order_by(QuestHistory.date_completed.desc()).all()
    for h in history:
        writer.writerow([h.date_completed, h.name, 'N/A', h.stat_type, h.xp_gained, h.difficulty])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=cosmo_export.csv"})

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    users_list = User.query.all()
    total_quests = Habit.query.count()
    feedbacks = Feedback.query.order_by(Feedback.timestamp.desc()).all()

    return render_template('admin.html',
                           users=users_list,
                           user_count=len(users_list),
                           quests=total_quests,
                           feedbacks=feedbacks)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    if user_id == current_user.id: return redirect(url_for('admin_panel'))

    u = db.session.get(User, user_id)
    if u:
        db.session.delete(u)
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/inspect/<int:user_id>')
@login_required
def admin_inspect(user_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    target = db.session.get(User, user_id)
    habits = Habit.query.join(Goal).filter(Goal.user_id == user_id).all()
    return render_template('admin_inspect.html', target=target, habits=habits)

@app.route('/admin/bulk_purge', methods=['POST'])
@login_required
def bulk_purge():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    target_id = request.form.get('target_user_id')
    habit_ids = request.form.getlist('habit_ids')
    msg = request.form.get('system_message')

    for hid in habit_ids:
        h = db.session.get(Habit, int(hid))
        if h: db.session.delete(h)

    if msg and target_id:
        db.session.add(Notification(user_id=target_id, message=msg, type='warning'))

    db.session.commit()
    return redirect(url_for('admin_inspect', user_id=target_id))

@app.route('/admin/broadcast', methods=['POST'])
@login_required
def admin_broadcast():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    msg = request.form.get('broadcast_message')
    if msg:
        for u in User.query.all():
            db.session.add(Notification(user_id=u.id, message=msg, type='info'))
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_pro/<int:user_id>')
@login_required
def toggle_pro(user_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    u = db.session.get(User, user_id)
    if u:
        u.is_pro = not u.is_pro
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

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    msg = request.form.get('message')
    if msg:
        db.session.add(Feedback(user_id=current_user.id, message=msg))
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/dismiss_notification/<int:notif_id>')
@login_required
def dismiss_notification(notif_id):
    n = db.session.get(Notification, notif_id)
    if n and n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/get_reminders')
def get_reminders():
    return {"alert": False}

@app.route('/focus_hub')
@login_required
def focus_hub():
    return render_template('focus.html', user=current_user, target=240, progress=0)

@app.route('/save_focus_session', methods=['POST'])
@login_required
def save_focus_session():
    data = request.json
    minutes = data.get('minutes', 25)
    current_user.total_focus_time += minutes
    current_user.total_xp += (minutes * 2)
    current_user.gold += int(minutes / 10)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_tasks():
    if request.method == 'POST':
        text = request.form.get('raw_text')
        if not text: return redirect(url_for('import_tasks'))

        # 1. GET TASKS FROM AI
        if current_user.is_pro:
            key = os.getenv('GEMINI_API_KEY')
            tasks = smart_ai_parse(text, key)
        else:
            tasks = [guess_category(line) for line in text.split('\n') if line.strip()]

        # 2. SAVE TO DATABASE
        for t in tasks:
            # Ensure Goal Exists
            cat = t.get('category', 'General')
            goal = Goal.query.filter_by(user_id=current_user.id, name=cat).first()
            if not goal:
                goal = Goal(name=cat, user_id=current_user.id) # Fixed 'author' here too
                db.session.add(goal)
                db.session.flush()

            # Map Difficulty Number to Name
            diff_map = {1: 'Easy', 2: 'Medium', 3: 'Hard', 4: 'Epic'}
            diff_val = t.get('difficulty', 1)
            # Handle if AI returns a string "Easy" instead of number
            if isinstance(diff_val, str):
                diff_name = diff_val
            else:
                diff_name = diff_map.get(diff_val, 'Easy')

            # Parse Date
            date_obj = None
            if t.get('target_date'):
                try:
                    date_obj = datetime.strptime(t['target_date'], '%Y-%m-%d').date()
                except:
                    date_obj = None

            # Create Habit
            h = Habit(
                name=t['name'],
                goal_id=goal.id,
                difficulty=diff_name,
                xp_value=10 * (t.get('difficulty', 1) if isinstance(t.get('difficulty', 1), int) else 1),
                completed=False,
                description=t.get('description', ''), # <--- ADDED DESCRIPTION
                target_date=date_obj                 # <--- ADDED DATE
            )
            db.session.add(h)

        db.session.commit()
        flash(f"Successfully imported {len(tasks)} tasks!", "success")
        return redirect(url_for('dashboard'))

    return render_template('import_tasks.html')

@app.route('/operations/backlog')
@login_required
def backlog_calculator():
    return render_template('backlog_calculator.html')

@app.route('/api/strategy_brief', methods=['POST'])
@login_required
def strategy_brief():
    data = request.json
    msg = get_backlog_strategy(data.get('hours'), data.get('days'), data.get('mode'))
    return jsonify({'message': msg})

@app.route('/audit')
@login_required
def audit():
    today = date.today()
    tasks = Habit.query.join(Goal).filter(
        Goal.user_id == current_user.id,
        Habit.target_date < today,
        Habit.completed == False
    ).all()
    return render_template('audit.html', tasks=tasks)

@app.route('/process_audit', methods=['POST'])
@login_required
def process_audit():
    action = request.form.get('action')
    ids = request.form.getlist('task_ids')
    today = date.today()

    for tid in ids:
        h = db.session.get(Habit, int(tid))
        if h and h.goal.user_id == current_user.id:
            if action == 'delete': db.session.delete(h)
            elif action == 'today': h.target_date = today
            elif action == 'tomorrow': h.target_date = today + timedelta(days=1)
            elif action == 'unschedule': h.target_date = None

    db.session.commit()
    return redirect(url_for('audit'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/edit_goal', methods=['POST'])
@login_required
def edit_goal():
    gid = request.form.get('goal_id')
    name = request.form.get('name')
    g = db.session.get(Goal, gid)
    if g and g.user_id == current_user.id:
        g.name = name
        db.session.commit()
    return redirect(url_for('dashboard'))

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

@app.route('/admin/mark_read/<int:feedback_id>')
@login_required
def mark_read(feedback_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    f = db.session.get(Feedback, feedback_id)
    if f:
        f.is_read = not f.is_read
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/history')
@login_required
def history():
    # Group by month
    dates = db.session.query(QuestHistory.date_completed).filter_by(user_id=current_user.id).distinct().all()
    months = set([(d.date_completed.year, d.date_completed.month) for d in dates if d.date_completed])
    sorted_months = sorted(list(months), reverse=True)

    archives = []
    import calendar
    for y, m in sorted_months:
        total = db.session.query(func.sum(QuestHistory.xp_gained)).filter(
            QuestHistory.user_id == current_user.id,
            extract('year', QuestHistory.date_completed) == y,
            extract('month', QuestHistory.date_completed) == m
        ).scalar() or 0
        archives.append({'year': y, 'month': m, 'name': calendar.month_name[m], 'xp': total})

    return render_template('history.html', archives=archives)

@app.route('/history_details/<int:year>/<int:month>')
@login_required
def history_details(year, month):
    import calendar
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).order_by(QuestHistory.date_completed.desc()).all()

    total = sum(l.xp_gained for l in logs)
    return render_template('history_details.html', logs=logs, month=calendar.month_name[month], year=year, total_xp=total)

@app.route('/download_report/<int:year>/<int:month>')
@login_required
def download_report(year, month):
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Mission', 'Type', 'XP'])
    for log in logs:
        writer.writerow([log.date_completed, log.name, log.stat_type, log.xp_gained])

    return Response(output.getvalue(), mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment;filename=Report_{year}_{month}.csv"})

@app.route('/download_report_pdf/<int:year>/<int:month>')
@login_required
def download_report_pdf(year, month):
    import calendar
    logs = QuestHistory.query.filter(
        QuestHistory.user_id == current_user.id,
        extract('year', QuestHistory.date_completed) == year,
        extract('month', QuestHistory.date_completed) == month
    ).all()

    html = render_template('report_pdf.html', user=current_user, logs=logs,
                           total_xp=sum(l.xp_gained for l in logs),
                           mission_count=len(logs), month_name=calendar.month_name[month],
                           year=year, now=datetime.now().strftime('%Y-%m-%d'))

    pdf = HTML(string=html).write_pdf()
    return Response(pdf, mimetype='application/pdf',
                    headers={"Content-Disposition": f"attachment;filename=Report_{year}_{month}.pdf"})

# --- PASSWORD RESET ---
# --- PASSWORD RESET ---
@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user:
            token = s.dumps(user.email, salt='recover-key')
            base_url = request.host_url.rstrip('/')
            path = url_for('reset_token', token=token)
            link = f"{base_url}{path}"

            # --- SEND EMAIL VIA BREVO HTTP API ---
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": os.getenv('BREVO_API_KEY'),
                "content-type": "application/json"
            }
            payload = {
                "sender": {"name": "LifeRPG Command", "email": os.getenv('MAIL_USERNAME')},
                "to": [{"email": user.email}],
                "subject": "LifeRPG - Password Reset",
                "htmlContent": f"<html><body><h3>Password Reset Request</h3><p>Click the link below to reset your LifeRPG password:</p><p><a href='{link}'>{link}</a></p></body></html>"
            }

            try:
                # This bypasses the firewall!
                requests.post(url, json=payload, headers=headers)
                flash('Email sent! Please check your inbox.', 'info')
            except Exception as e:
                flash('Error communicating with mail server.', 'danger')

            return redirect(url_for('login'))

        flash('Email not found.', 'danger')
    return render_template('reset_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    try:
        email = s.loads(token, salt='recover-key', max_age=1800)
    except:
        flash('Invalid token.', 'danger')
        return redirect(url_for('reset_request'))

    if request.method == 'POST':
        user = User.query.filter_by(email=email).first()
        # FIXED: Using bcrypt
        user.password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        db.session.commit()
        flash('Password updated.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html')

# ========================================================
# 7. PROTOCOL API (FOR ANDROID WIDGET)
# ========================================================

@app.route('/api/get_protocol', methods=['GET'])
def get_protocol():
    """
    The Widget calls this to get the Agent's status and top 3 missions.
    Usage: /api/get_protocol?username=CosmoCommander&key=YOUR_SECRET_KEY
    """
    username = request.args.get('username')
    # In a real app, use a real API Token. For now, we trust the username for personal use.

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "Agent not found"}), 404

    # 1. Get Stats
    stats = {
        "level": int(user.total_xp / 1000) + 1, # Simple level calc
        "xp": user.total_xp,
        "streak": user.current_streak,
        "gold": user.gold
    }

    # 2. Get Top 3 Priority Tasks
    # Prioritizes: Overdue -> Today -> High Difficulty
    today = date.today()

    tasks_query = Habit.query.join(Goal).filter(
        Goal.user_id == user.id,
        Habit.completed == False
    ).order_by(
        Habit.target_date.asc(), # Oldest dates first
        Habit.difficulty.desc()  # Then hardest tasks
    ).limit(3).all()

    mission_list = []
    for t in tasks_query:
        # Calculate if overdue
        status = "Active"
        if t.target_date and t.target_date < today: status = "OVERDUE"
        elif t.target_date == today: status = "TODAY"

        mission_list.append({
            "id": t.id,
            "name": t.name,
            "status": status,
            "xp": t.xp_value,
            "difficulty": t.difficulty
        })

    return jsonify({
        "agent": user.username,
        "status": "OPERATIONAL",
        "stats": stats,
        "missions": mission_list
    })

@app.route('/api/complete_mission/<int:task_id>', methods=['POST'])
# @csrf.exempt # Uncomment if you enable global CSRF later
def complete_mission_api(task_id):
    """
    The Widget calls this when you tap the checkbox.
    """
    # 1. Verification (Simple version)
    username = request.args.get('username')
    user = User.query.filter_by(username=username).first()

    task = db.session.get(Habit, task_id)

    if not task or not user or task.goal.user_id != user.id:
        return jsonify({"error": "Access Denied"}), 403

    # 2. Complete the Task
    if not task.completed:
        task.completed = True
        user.total_xp += task.xp_value
        user.gold += int(task.xp_value / 10)

        # Log History
        history = QuestHistory(
            user_id=user.id,
            name=task.name,
            difficulty=task.difficulty,
            stat_type=task.stat_type,
            xp_gained=task.xp_value,
            date_completed=date.today()
        )
        db.session.add(history)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Objective Complete",
            "new_xp": user.total_xp
        })

    return jsonify({"success": False, "message": "Already completed"})

# --- VIP GENIE FEATURE ---
# --- VIP GENIE FEATURE ---
@app.route('/genie', methods=['GET', 'POST'])
@login_required
def genie():
    # 1. Lock out Guests completely
    if current_user.is_guest:
        flash("The Genie only appears to Masters who engrave their name in the registry. Please register.", "warning")
        return redirect(url_for('dashboard'))

    # --- AUTO-HEAL OLD ACCOUNTS ---
    if current_user.has_used_free_wish is None:
        current_user.has_used_free_wish = False
        db.session.commit()
    if current_user.genie_wishes is None and current_user.is_pro:
        current_user.genie_wishes = 3
        db.session.commit()

    # 2. Check VIP Limits
    # Free users get 1 lifetime wish. Pro users get 3 per week.
    if not current_user.is_pro:
        if current_user.has_used_free_wish:
            flash("Your free lifetime wish has been exhausted. Upgrade to Pro to summon the Genie again.", "info")
            return redirect(url_for('dashboard'))
    else:
        # Check weekly resets for Pro users
        if current_user.genie_wishes <= 0:
            flash("The Genie rests. Your 3 wishes will replenish next week.", "info")
            return redirect(url_for('dashboard'))

    # 3. Handle the Wish Submission
    if request.method == 'POST':
        wish = request.form.get('wish')

        # Ask Gemini to generate the 3 specific questions
        questions = generate_genie_questions(wish)

        # Send the user to the questionnaire room
        return render_template('genie_questions.html', wish=wish, questions=questions)

    # 4. Show the magical room
    return render_template('genie.html')

# --- VIP GENIE: QUEST GENERATOR ---
# --- VIP GENIE: QUEST GENERATOR ---
# --- VIP GENIE: QUEST GENERATOR ---
@app.route('/genie_generate_quest', methods=['POST'])
@login_required
def genie_generate_quest():
    # 1. Grab the original wish and the answers
    wish = request.form.get('wish')
    question_1 = request.form.get('question_1')
    answer_1 = request.form.get('answer_1')
    question_2 = request.form.get('question_2')
    answer_2 = request.form.get('answer_2')
    question_3 = request.form.get('question_3')
    answer_3 = request.form.get('answer_3')

    # 2. Call the AI to forge the Master Blueprint
    blueprint = generate_genie_blueprint(wish, question_1, answer_1, question_2, answer_2, question_3, answer_3)

    if not blueprint:
        flash("The Genie's magic was interrupted by a cosmic storm (AI Error). Please try again.", "danger")
        return redirect(url_for('dashboard'))

    # 3. Create the New Goal in the Database
    new_goal = Goal(
        name=f"🧞‍♂️ {blueprint['goal_name']}",
        user_id=current_user.id,
        is_genie_quest=True
    )
    db.session.add(new_goal)
    db.session.commit() # Commit here so we get the Goal ID for the habit!

    # 4. Create the Daily Habit tied to the Goal
    time_label = blueprint['habit'].get('time_of_day', 'Anytime')
    new_daily = Habit(
        name=f"🧞‍♂️ DAILY: {blueprint['habit']['name']} [{time_label}]",
        goal_id=new_goal.id,
        is_daily=True,
        difficulty="Medium",
        description="Daily momentum builder for your Master Quest."
    )
    db.session.add(new_daily)

    # 5. Create the 3 Milestones AS HABITS (So they appear on the dashboard with notes!)
    for t in blueprint['tasks']:
        new_milestone = Habit(
            name=f"🧞‍♂️ MILESTONE: {t['title']}",
            description=t['description'], # The detailed AI instructions are now here!
            goal_id=new_goal.id,
            is_daily=False, # One-time epic tasks
            difficulty="Epic",
            xp_value=100
        )
        db.session.add(new_milestone)

    # 6. Deduct the wish from the user's wallet
    if not current_user.is_pro:
        current_user.has_used_free_wish = True
    else:
        current_user.genie_wishes -= 1

    db.session.commit()

    flash(f"The Genie has forged your Master Quest! Check your Active Protocols.", "success")
    return redirect(url_for('dashboard'))

# --- VIRAL GROWTH: INSTAGRAM UNLOCK ---
@app.route('/unlock_beta', methods=['POST'])
@login_required
def unlock_beta():
    # Instantly upgrade the user to PRO
    current_user.is_pro = True
    db.session.commit()
    return {"status": "success", "message": "Unlocked!"}, 200

@app.route('/admin/mailer', methods=['GET', 'POST'])
@login_required
def admin_mailer():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user_ids = request.form.getlist('user_ids')
        subject = request.form.get('subject')
        body = request.form.get('body')

        if not user_ids or not subject or not body:
            flash('Please select targets and provide a subject/body.', 'warning')
            return redirect(url_for('admin_mailer'))

        users = User.query.filter(User.id.in_(user_ids)).all()
        sent_count = 0

        # --- USE BREVO HTTP API (Matches your working password reset) ---
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": os.getenv('BREVO_API_KEY'),
            "content-type": "application/json"
        }

        for u in users:
            if u.email:
                try:
                    # Automatically personalize the email
                    personalized_body = body.replace('[USERNAME]', u.username)

                    # Convert line breaks to HTML breaks so it formats correctly in email
                    html_body = personalized_body.replace('\n', '<br>')

                    payload = {
                        # Change this line inside app.py:
                        "sender": {"name": "Cosmo Command", "email": "bushibots@gmail.com"}, # You can change this to your verified sender email
                        "to": [{"email": u.email}],
                        "subject": subject,
                        "htmlContent": f"<html><body style='font-family: sans-serif;'><p>{html_body}</p></body></html>"
                    }

                    response = requests.post(url, json=payload, headers=headers)

                    if response.status_code in [200, 201, 202]:
                        sent_count += 1
                    else:
                        print(f"Brevo API Error for {u.email}: {response.text}")
                        flash(f'Failed to send to {u.email}. API Error.', 'danger')

                except Exception as e:
                    print(f"Failed to send to {u.email}: {e}")
                    flash(f'System error sending to {u.email}.', 'danger')

        if sent_count > 0:
            flash(f'Uplink successfully transmitted to {sent_count} users.', 'success')

        return redirect(url_for('admin_mailer'))

    # Only load users who have an email address linked
    users = User.query.filter(User.email != None, User.email != '').all()
    return render_template('admin_mailer.html', users=users)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)