from flask_login import UserMixin
from datetime import datetime, date
from extensions import db  # Importing from extensions to avoid loops

# --- 1. TASK CLASS ---
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    complete = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # --- NEW GENIE ADDITIONS ---
    description = db.Column(db.Text, nullable=True) # For the detailed AI task descriptions
    is_genie_task = db.Column(db.Boolean, default=False) # Triggers the special Arabic animations
    completion_notes = db.Column(db.Text, nullable=True) # For the weekly AI to read

# --- 2. GOAL CLASS ---
class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # --- NEW GENIE ADDITIONS ---
    is_genie_quest = db.Column(db.Boolean, default=False) # Identifies it as a Master Quest

    # Relationship to Habits
    habits = db.relationship('Habit', backref='goal', cascade="all, delete-orphan", lazy=True)

# --- 3. HABIT CLASS ---
class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)
    difficulty = db.Column(db.String(20), default="Medium")
    xp_value = db.Column(db.Integer, default=10)
    stat_type = db.Column(db.String(10), default="INT") # STR, INT, WIS, etc.
    completed = db.Column(db.Boolean, default=False)
    is_daily = db.Column(db.Boolean, default=False)
    target_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(500), nullable=True)

# --- 4. USER CLASS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    is_guest = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password = db.Column(db.String(150), nullable=False)

    # Permissions
    is_pro = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)

    # Stats & RPG Elements
    gold = db.Column(db.Integer, default=0)
    current_streak = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.Date, nullable=True)
    total_focus_time = db.Column(db.Integer, default=0)
    total_xp = db.Column(db.Integer, default=0)
    last_check_in = db.Column(db.Date, default=date.today)
    last_check_date = db.Column(db.Date, nullable=True)

    # --- NEW GENIE TRACKING ---
    has_used_free_wish = db.Column(db.Boolean, default=False) # Locks out the 1 Lifetime Wish
    genie_wishes = db.Column(db.Integer, default=0) # Weekly wishes for Pro users
    last_wish_reset = db.Column(db.DateTime, nullable=True) # Tracks Sunday resets
    last_genie_evaluation = db.Column(db.DateTime, nullable=True) # Tracks the weekly AI task review

    # S.P.E.C.I.A.L. Scores
    str_score = db.Column(db.Integer, default=0)
    int_score = db.Column(db.Integer, default=0)
    wis_score = db.Column(db.Integer, default=0)
    cha_score = db.Column(db.Integer, default=0)
    con_score = db.Column(db.Integer, default=0)

    # Relationships
    goals = db.relationship('Goal', backref='author', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship('Task', backref='author', lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade="all, delete-orphan")

# --- 5. OTHER MODELS ---
class QuestHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150))
    difficulty = db.Column(db.String(20))
    stat_type = db.Column(db.String(10))
    xp_gained = db.Column(db.Integer)
    date_completed = db.Column(db.Date, default=date.today)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    user_rel = db.relationship('User', backref='feedbacks')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(20), default='info') # info, warning, success
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    mood = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)