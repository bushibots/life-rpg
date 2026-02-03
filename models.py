from datetime import date, datetime
from flask_login import UserMixin
from extensions import db


class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    # Foreign Key: Links this goal to a specific User ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False) # <--- Moved from User
    complete = db.Column(db.Boolean, default=False)   # <--- Moved from User
    # Foreign Key: Links this task to a specific User ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
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

    # S.P.E.C.I.A.L. Scores
    str_score = db.Column(db.Integer, default=0)
    int_score = db.Column(db.Integer, default=0)
    wis_score = db.Column(db.Integer, default=0)
    cha_score = db.Column(db.Integer, default=0)
    con_score = db.Column(db.Integer, default=0)

    # Relationships
    # These link to the classes defined above
    goals = db.relationship('Goal', backref='author', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship('Task', backref='author', lazy=True, cascade="all, delete-orphan")

    # ... (Keep your existing Property methods: level, xp_progress, title_info) ...
    # PASTE YOUR EXISTING @property METHODS HERE (I am hiding them to save space, but DO NOT DELETE THEM)
    @property
    def level(self):
        return max(1, 1 + (self.total_xp // 100))

    @property
    def xp_progress(self):
        current_level_xp = ((self.level - 1) * 100)
        return int(((self.total_xp - current_level_xp) / 100) * 100)

    @property
    def title_info(self):
        stats = {'Warrior': self.str_score, 'Mage': self.int_score, 'Monk': self.wis_score, 'Bard': self.cha_score, 'Guardian': self.con_score}
        highest = max(stats, key=stats.get)
        return {"name": f"{highest} {self.level}", "reason": f"Class: {highest}"}
# --- PASTE THIS MISSING CODE INTO YOUR FILE ---

# ----------------------------------------------

class QuestHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150))
    difficulty = db.Column(db.String(50))
    stat_type = db.Column(db.String(10))
    xp_gained = db.Column(db.Integer)
    date_completed = db.Column(db.Date, default=datetime.now)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'))
    xp_value = db.Column(db.Integer)
    difficulty = db.Column(db.String(50))
    stat_type = db.Column(db.String(10))
    target_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, nullable=True)

    # These were likely missing or misnamed
    completed = db.Column(db.Boolean, default=False)
    is_daily = db.Column(db.Boolean, default=False)

    # Timer/Duration column (just in case you use the timer feature)
    duration = db.Column(db.Integer, default=0)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    status = db.Column(db.Boolean, default=False)

# NEW: Feedback Table
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)

    # Link to know WHO sent it
    user = db.relationship('User', backref='feedbacks')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    type = db.Column(db.String(20), default='system') # 'system', 'warning', 'info'

    user = db.relationship('User', backref='notifications')