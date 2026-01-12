from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # 1. Consistency Tracking
            conn.execute(text("ALTER TABLE user ADD COLUMN current_streak INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE user ADD COLUMN last_active_date DATE"))
            
            # 2. Time Tracking
            conn.execute(text("ALTER TABLE user ADD COLUMN total_focus_time INTEGER DEFAULT 0"))
            
            conn.commit()
        print("✅ SUCCESS: Focus stats added to database!")
    except Exception as e:
        print(f"⚠️ NOTE: {e}")
