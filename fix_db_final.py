from app import app, db
from sqlalchemy import text
import os

print("--- DIAGNOSTIC START ---")

# 1. Check where Flask thinks the DB is
db_uri = app.config['SQLALCHEMY_DATABASE_URI']
print(f"📍 Flask is looking for DB at: {db_uri}")

with app.app_context():
    # 2. Force Create Tables (Fixes 'no such table' error)
    try:
        db.create_all()
        print("✅ Database Tables Verified/Created.")
    except Exception as e:
        print(f"⚠️ Table Check Warning: {e}")

    # 3. Force Add Column (Fixes 'no such column' error)
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE habit ADD COLUMN target_date DATE"))
            conn.commit()
        print("✅ SUCCESS: 'target_date' column added!")
    except Exception as e:
        # If it fails, check if it's because it's already there
        if "duplicate column" in str(e).lower():
            print("✅ GOOD NEWS: The column was already there.")
        else:
            print(f"ℹ️ Info: {e}")

print("--- DIAGNOSTIC END ---")