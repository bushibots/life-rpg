from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE habit ADD COLUMN target_date DATE"))
            print("✅ SUCCESS: 'target_date' column added to database!")
        except Exception as e:
            print(f"ℹ️ INFO: {e}")