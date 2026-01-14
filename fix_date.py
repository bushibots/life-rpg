from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            # This command manually adds the missing column to your database
            conn.execute(text("ALTER TABLE habit ADD COLUMN target_date DATE"))
            conn.commit()
            print("✅ SUCCESS: 'target_date' column added to Habit table!")
        except Exception as e:
            print(f"ℹ️ REPORT: {e}")
            print("If it says 'duplicate column', you are already good!")