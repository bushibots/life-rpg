from datetime import date, datetime
from flask_login import UserMixin
from extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    # NEW: Admin Privilege Badge
    is_admin = db.Column(db.Boolean, default=False)

    is_banned = db.Column(db.Boolean, default=False)

    total_xp = db.Column(db.Integer, default=0)
    last_check_in = db.Column(db.Date, default=date.today)
    str_score = db.Column(db.Integer, default=0)
    int_score = db.Column(db.Integer, default=0)
    wis_score = db.Column(db.Integer, default=0)
    cha_score = db.Column(db.Integer, default=0)
    con_score = db.Column(db.Integer, default=0)
    goals = db.relationship('Goal', backref='owner', lazy=True)
    last_check_date = db.Column(db.Date, nullable=True)

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

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    habits = db.relationship('Habit', backref='goal', cascade="all, delete-orphan", lazy=True)

class QuestHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150))
    difficulty = db.Column(db.String(50))
    stat_type = db.Column(db.String(10))
    xp_gained = db.Column(db.Integer)
    date_completed = db.Column(db.Date, default=datetime.utcnow)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'))
    xp_value = db.Column(db.Integer)
    difficulty = db.Column(db.String(50))
    stat_type = db.Column(db.String(10))

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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    # Link to know WHO sent it
    user = db.relationship('User', backref='feedbacks')