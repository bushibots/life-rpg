import csv
import io
from flask import Flask, render_template, redirect, url_for, request, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import date, timedelta, datetime
from extensions import db, login_manager
from flask_migrate import Migrate
from models import User, Goal, Habit, DailyLog, Feedback, QuestHistory

# --- PRESET QUEST LIBRARY ---
PRESETS = [
    {"id": 1, "name": "50 Pushups", "category": "Fitness", "attribute": "STR", "difficulty": "Medium", "is_daily": True},
    {"id": 2, "name": "Morning Run (3km)", "category": "Fitness", "attribute": "STR", "difficulty": "Hard", "is_daily": True},
    {"id": 11, "name": "Read 10 Pages", "category": "Intellect", "attribute": "INT", "difficulty": "Easy", "is_daily": True},
    {"id": 12, "name": "Code for 1 Hour", "category": "Career", "attribute": "INT", "difficulty": "Hard", "is_daily": True},
    {"id": 21, "name": "Meditation (10m)", "category": "Mental Health", "attribute": "WIS", "difficulty": "Easy", "is_daily": True},
    {"id": 31, "name": "Drink 3L Water", "category": "Health", "attribute": "CON", "difficulty": "Medium", "is_daily": True},
    {"id": 41, "name": "Call Family", "category": "Social", "attribute": "CHA", "difficulty": "Medium", "is_daily": False},
]

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_rpg_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rpg.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.before_request
def check_ban():
    if current_user.is_authenticated and hasattr(current_user, 'is_banned') and current_user.is_banned:
        logout_user()
        flash("Access Denied: Your account has been suspended by Command.", "danger")
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
            flash(f"System Reset: {reset_count} daily quests refreshed.", "info")

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
    
    # Removed broken date/time/streak logic to fix crashes
    
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
        if habit.completed:
            current_user.total_xp += habit.xp_value
            if habit.stat_type == 'STR': current_user.str_score += habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score += habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score += habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score += habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score += habit.xp_value
            
            from datetime import date
            history_entry = QuestHistory(
                user_id=current_user.id,
                name=habit.name,
                difficulty=habit.difficulty,
                stat_type=habit.stat_type,
                xp_gained=habit.xp_value,
                date_completed=date.today()
            )
            db.session.add(history_entry)
            flash(f"Quest Complete! +{habit.xp_value} XP", "success")
        else:
            current_user.total_xp -= habit.xp_value
            if habit.stat_type == 'STR': current_user.str_score -= habit.xp_value
            elif habit.stat_type == 'INT': current_user.int_score -= habit.xp_value
            elif habit.stat_type == 'WIS': current_user.wis_score -= habit.xp_value
            elif habit.stat_type == 'CON': current_user.con_score -= habit.xp_value
            elif habit.stat_type == 'CHA': current_user.cha_score -= habit.xp_value
            
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
    if request.method == 'POST':
        if User.query.filter_by(username=request.form.get('username')).first():
            flash('Username exists.')
            return redirect(url_for('register'))
        new_user = User(username=request.form.get('username'), password=generate_password_hash(request.form.get('password'), method='scrypt'))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

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
    writer.writerow(['Date', 'Quest', 'Category', 'Stat', 'XP', 'Difficulty'])
    
    history = QuestHistory.query.filter_by(user_id=current_user.id).order_by(QuestHistory.date_completed.desc()).all()
    for h in history:
        writer.writerow([h.date_completed, h.name, 'N/A', h.stat_type, h.xp_gained, h.difficulty])
        
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=life_rpg_export.csv"})

# --- ADMIN PANEL ROUTES ---
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access Denied: Clearance Level Too Low.", "danger")
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
        flash("Transmission sent to Command.", "success")
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

if __name__ == '__main__':
    app.run(debug=True)