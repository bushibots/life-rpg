import csv
import io
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import date, timedelta, datetime
from extensions import db, login_manager
from flask_migrate import Migrate
from models import User, Goal, Habit, DailyLog, Feedback, QuestHistory
from utils import guess_category, smart_ai_parse
# --- MISSING IMPORTS FOR FORMS ---
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import google.generativeai as genai
load_dotenv()

# --- FORM CLASSES ---
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])

    # DELETE THIS LINE BELOW (or put a # in front of it)
    # confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])

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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rpg.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 👇 ADD THIS NEW LINE HERE 👇
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

with app.app_context():
    db.create_all()

# --- ROUTES ---

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    # Daily Reset Logic
    from datetime import date
    if current_user.last_check_date != date.today():
        user_goals = Goal.query.filter_by(user_id=current_user.id).all()
        reset_count = 0
        for goal in user_goals:
            for habit in goal.habits:
                if habit.is_daily and habit.completed:
                    habit.completed = False
                    reset_count += 1
        current_user.last_check_date = date.today()
        db.session.commit()
        if reset_count > 0:
            flash(f"System refreshed. {reset_count} recurring tasks reset.", "info")

    goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', user=current_user, goals=goals)

@app.route('/analytics')
@login_required
def analytics():
    stats = {'STR': 0, 'INT': 0, 'WIS': 0, 'CON': 0, 'CHA': 0}
    history = QuestHistory.query.filter_by(user_id=current_user.id).all()
    for h in history:
        if h.stat_type in stats:
            stats[h.stat_type] += h.xp_gained

    from datetime import date, timedelta
    today = date.today()
    last_7_days = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    xp_trend = [0] * 7
    for h in history:
        h_date = h.date_completed.strftime('%Y-%m-%d')
        if h_date in last_7_days:
            index = last_7_days.index(h_date)
            xp_trend[index] += h.xp_gained

    difficulty_counts = {'Easy': 0, 'Medium': 0, 'Hard': 0, 'Epic': 0}
    for h in history:
        if h.difficulty in difficulty_counts:
            difficulty_counts[h.difficulty] += 1

    return render_template('analytics.html',
                         user=current_user,
                         radar_data=list(stats.values()),
                         radar_labels=list(stats.keys()),
                         trend_dates=last_7_days,
                         trend_data=xp_trend,
                         diff_data=list(difficulty_counts.values()))

@app.route('/history')
@login_required
def history():
    history_data = QuestHistory.query.filter_by(user_id=current_user.id).order_by(QuestHistory.date_completed.desc()).all()
    return render_template('history.html', history=history_data, user=current_user)

@app.route('/planning')
@login_required
def planning():
    goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('planning.html', user=current_user, goals=goals)

@app.route('/stats')
@login_required
def stats():
    radar_labels = ['STR', 'INT', 'WIS', 'CHA', 'CON']
    radar_data = [current_user.str_score, current_user.int_score, current_user.wis_score, current_user.cha_score, current_user.con_score]

    history = QuestHistory.query.filter_by(user_id=current_user.id).order_by(QuestHistory.date_completed.asc()).all()

    heatmap_data = {}
    today = date.today()
    dates_last_30 = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    daily_xp_map = {d: 0 for d in dates_last_30}

    for h in history:
        d_str = h.date_completed.strftime('%Y-%m-%d')
        heatmap_data[d_str] = heatmap_data.get(d_str, 0) + h.xp_gained
        if d_str in daily_xp_map:
            daily_xp_map[d_str] += h.xp_gained

    line_data = []
    running_total = current_user.total_xp - sum(daily_xp_map.values())

    for d in dates_last_30:
        running_total += daily_xp_map[d]
        line_data.append(running_total)

    active_days_last_7 = 0
    for i in range(7):
        d_check = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        if heatmap_data.get(d_check, 0) > 0:
            active_days_last_7 += 1
    health_score = int((active_days_last_7 / 7) * 100) if active_days_last_7 > 0 else 0

    return render_template('stats.html',
                           radar_labels=radar_labels, radar_data=radar_data,
                           line_labels=dates_last_30, line_data=line_data,
                           heatmap_data=heatmap_data,
                           health_score=health_score,
                           user=current_user)

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    goal_id = request.form.get('goal_id')
    name = request.form.get('name')
    stat_type = request.form.get('stat_type')
    difficulty = request.form.get('difficulty')
    duration = request.form.get('duration')

    xp_map = {'Easy': 10, 'Medium': 30, 'Hard': 50, 'Epic': 100}
    xp = xp_map.get(difficulty, 10)

    if name and goal_id:
        new_habit = Habit(
            goal_id=int(goal_id),
            name=name,
            stat_type=stat_type,
            difficulty=difficulty,
            xp_value=xp,
            duration=int(duration) if duration else 0,
            completed=False,
            is_daily=True
        )
        db.session.add(new_habit)
        db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/toggle_habit/<int:habit_id>')
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.get(habit_id)
    if habit and habit.goal.user_id == current_user.id:
        habit.completed = not habit.completed

        from datetime import date

        if habit.completed:
            # --- TASK COMPLETED ---
            current_user.total_xp += habit.xp_value
            # Add Attribute Score
            if habit.stat_type == 'STR': current_user.str_score += habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score += habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score += habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score += habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score += habit.xp_value

            # Create Log
            history_entry = QuestHistory(
                user_id=current_user.id,
                name=habit.name,
                difficulty=habit.difficulty,
                stat_type=habit.stat_type,
                xp_gained=habit.xp_value,
                date_completed=date.today()
            )
            db.session.add(history_entry)
            flash(f"Task Complete. +{habit.xp_value} XP", "success")

        else:
            # --- TASK UN-COMPLETED ---
            current_user.total_xp -= habit.xp_value
            # Remove Attribute Score
            if habit.stat_type == 'STR': current_user.str_score -= habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score -= habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score -= habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score -= habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score -= habit.xp_value

            # FIX: Find and delete the log entry for today
            log_to_delete = QuestHistory.query.filter_by(
                user_id=current_user.id,
                name=habit.name,
                date_completed=date.today()
            ).order_by(QuestHistory.id.desc()).first()

            if log_to_delete:
                db.session.delete(log_to_delete)

        db.session.commit()
    return redirect(url_for('dashboard'))

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
    if h and h.goal.user_id == current_user.id:
        db.session.delete(h)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/edit_habit', methods=['POST'])
@login_required
def edit_habit():
    h = db.session.get(Habit, request.form.get('habit_id'))
    if h and h.goal.user_id == current_user.id:
        h.name = request.form.get('name')
        h.difficulty = request.form.get('difficulty')
        h.is_daily = True if request.form.get('is_daily') else False
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()

    # --- DEBUGGING BLOCK ---
    if request.method == 'POST':
        print("📝 Form Data Received:", request.form) # See if data is arriving
        if form.validate_on_submit():
            print("✅ Validation Success! Creating user...")
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(username=form.username.data, password=hashed_password)
            db.session.add(user)

            # Add Starter Quests
            q1 = Goal(name="Create your first real task", difficulty=1, stat_type='INT', user=user)
            q2 = Goal(name="Drink a glass of water", difficulty=1, stat_type='CON', user=user)
            q3 = Goal(name="Visit the Focus Hub", difficulty=1, stat_type='WIS', user=user)
            db.session.add_all([q1, q2, q3])

            db.session.commit()
            login_user(user)
            flash('Welcome, Agent.', 'success')
            return redirect(url_for('dashboard'))
        else:
            print("❌ VALIDATION FAILED!")
            print("⚠️ Errors:", form.errors) # <--- THIS WILL TELL US THE SECRET ERROR
    # -----------------------

    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True if request.form.get('remember') else False)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
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
    if request.form.get('password'): current_user.password = generate_password_hash(request.form.get('password'), method='scrypt')
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

# --- ADMIN PANEL ROUTES ---
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access Denied: Admin privileges required.", "danger")
        return redirect(url_for('dashboard'))

    total_users = User.query.count()
    total_quests = Habit.query.count()
    active_feedbacks = Feedback.query.order_by(Feedback.timestamp.desc()).all()

    return render_template('admin.html',
                           users=total_users,
                           quests=total_quests,
                           feedbacks=active_feedbacks)

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
    for f in feedbacks:
        db.session.delete(f)

    history = QuestHistory.query.filter_by(user_id=current_user.id).all()
    for h in history:
        db.session.delete(h)

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
        raw_text = request.form.get('raw_text')

        if not raw_text:
            flash("Please paste some text first!", "error")
            return redirect(url_for('import_tasks'))

        # --- THE DECISION LOGIC ---
        new_tasks_data = []

        if current_user.is_pro:
            # OPTION A: Use AI (Admin/Paid)
           api_key = os.getenv('GEMINI_API_KEY')
           genai.configure(api_key=api_key)
           new_tasks_data = smart_ai_parse(raw_text, api_key)
        else:
            # OPTION B: Use Keyword Matcher (Free)
            lines = raw_text.split('\n')
            for line in lines:
                if line.strip():
                    new_tasks_data.append(guess_category(line))

        # --- SAVE TO DATABASE (The Fixed Part) ---
        count = 0

        # Helper maps for converting AI data to your App's format
        diff_map = {1: 'Easy', 2: 'Medium', 3: 'Hard'}
        stat_map = {
            'Strength': 'STR', 'Physical': 'STR',
            'Intelligence': 'INT', 'Intellect': 'INT',
            'Charisma': 'CHA', 'Social': 'CHA',
            'Creativity': 'WIS', 'Mental Health': 'WIS',
            'General': 'CON', 'Health': 'CON'
        }

        for data in new_tasks_data:
            # 1. Find or Create the Goal (Category)
            cat_name = data.get('category', 'General')
            goal = Goal.query.filter_by(user_id=current_user.id, name=cat_name).first()

            if not goal:
                goal = Goal(name=cat_name, user_id=current_user.id)
                db.session.add(goal)
                db.session.flush() # Save it to get the ID immediately

            # 2. Determine Stats
            difficulty_int = data.get('difficulty', 1)
            difficulty_str = diff_map.get(difficulty_int, 'Easy')
            stat_type = stat_map.get(cat_name, 'CON')

            # 3. Create the Habit (Your actual Task model)
            new_habit = Habit(
                name=data['name'],
                goal_id=goal.id,
                difficulty=difficulty_str,
                stat_type=stat_type,
                xp_value=10 * difficulty_int, # 10, 20, or 30 XP
                is_daily=False,
                completed=False
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
    # 1. CONSISTENCY CHECK
    from datetime import date, timedelta
    today = date.today()

    if current_user.last_active_date:
        delta = (today - current_user.last_active_date).days
        if delta > 1:
            current_user.current_streak = 0 # Missed a day, reset metric
            db.session.commit()

    # 2. BENCHMARK LOGIC
    # Professional Standard: 4 Hours (240 mins) of Deep Work per day
    daily_target = 240
    user_time = current_user.total_focus_time if current_user.total_focus_time else 0

    progress_pct = min(100, int((user_time / daily_target) * 100))

    return render_template('focus.html',
                           user=current_user,
                           target=daily_target,
                           progress=progress_pct)

@app.route('/save_focus_session', methods=['POST'])
@login_required
def save_focus_session():
    data = request.json
    minutes = data.get('minutes', 25)

    # 1. Update Focus Stats
    current_user.total_focus_time += minutes
    current_user.last_active_date = date.today()

    # 2. Update Streak (Simple Logic: If active today, keep streak)
    # (Complex logic can be added later, let's just mark them active for now)

    # 3. Give Rewards (1 min = 1 XP, 10 mins = 1 Gold)
    xp_gained = minutes * 2  # 2 XP per minute of deep work
    gold_gained = max(1, int(minutes / 10))

    current_user.total_xp += xp_gained
    current_user.gold += gold_gained

    db.session.commit()

    return jsonify({
        'success': True,
        'new_xp': current_user.total_xp,
        'new_gold': current_user.gold
    })

if __name__ == '__main__':
    app.run(debug=True)