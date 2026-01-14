from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        # 1. Add 'description' column to Habit table
        try:
            conn.execute(text("ALTER TABLE habit ADD COLUMN description TEXT"))
            print("✅ Added 'description' column.")
        except Exception as e:
            print(f"ℹ️ Description column might already exist: {e}")
            
        conn.commit()
    print("🚀 Database upgrade complete!")