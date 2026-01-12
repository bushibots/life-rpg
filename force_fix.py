import os
from app import app, db
from sqlalchemy import text

print("--- 🕵️ DATABASE LOCATOR ---")
print(f"📂 Current Folder: {os.getcwd()}")
db_path = app.config.get('SQLALCHEMY_DATABASE_URI', 'Unknown')
print(f"🔗 Database Path: {db_path}")

with app.app_context():
    print("\n--- 🛠️ ATTEMPTING REPAIR ---")
    with db.engine.connect() as conn:
        # The list of columns we NEED to add
        columns_to_add = [
            ("gold", "INTEGER DEFAULT 0"),
            ("current_streak", "INTEGER DEFAULT 0"),
            ("last_active_date", "DATE"),
            ("total_focus_time", "INTEGER DEFAULT 0"),
            ("is_admin", "BOOLEAN DEFAULT 0")
        ]

        for col_name, col_type in columns_to_add:
            try:
                # Try to add the column
                sql = f"ALTER TABLE user ADD COLUMN {col_name} {col_type}"
                conn.execute(text(sql))
                print(f"✅ SUCCESS: Added '{col_name}'")
            except Exception as e:
                # If it fails, check if it's because it's already there
                if "duplicate column" in str(e).lower():
                    print(f"👍 SKIPPED: '{col_name}' already exists.")
                else:
                    print(f"⚠️ ERROR on '{col_name}': {e}")
        
        conn.commit()
    print("\n--- 🎉 FINISHED ---")
