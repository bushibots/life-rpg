from app import app, db
from sqlalchemy import text

with app.app_context():
    print("--- 🛠️ STARTING DATABASE REPAIR ---")
    with db.engine.connect() as conn:
        # A list of every new column we have added recently
        commands = [
            ("gold", "ALTER TABLE user ADD COLUMN gold INTEGER DEFAULT 0"),
            ("current_streak", "ALTER TABLE user ADD COLUMN current_streak INTEGER DEFAULT 0"),
            ("last_active_date", "ALTER TABLE user ADD COLUMN last_active_date DATE"),
            ("total_focus_time", "ALTER TABLE user ADD COLUMN total_focus_time INTEGER DEFAULT 0"),
            ("is_admin", "ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"),
            ("is_pro", "ALTER TABLE user ADD COLUMN is_pro BOOLEAN DEFAULT 0")
        ]

        for col_name, sql in commands:
            try:
                conn.execute(text(sql))
                print(f"✅ Added missing column: {col_name}")
            except Exception as e:
                # If error contains "duplicate column", it means we already have it. Good!
                if "duplicate column" in str(e):
                    print(f"👍 Column '{col_name}' already exists.")
                else:
                    print(f"⚠️ Error adding '{col_name}': {e}")
        
        conn.commit()
    print("--- 🎉 REPAIR COMPLETE ---")
