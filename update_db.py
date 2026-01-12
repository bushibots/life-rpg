from app import app, db
from sqlalchemy import text

# This script manually adds the 'is_pro' column to your SQLite database
with app.app_context():
    try:
        with db.engine.connect() as conn:
            # We use SQL command to add the column safely
            conn.execute(text("ALTER TABLE user ADD COLUMN is_pro BOOLEAN DEFAULT 0"))
            conn.commit()
        print("✅ Success! 'is_pro' column added to User table.")
    except Exception as e:
        print(f"⚠️ Report: {e}")
        print("If it says 'duplicate column name', that means it's already done. You are safe.")