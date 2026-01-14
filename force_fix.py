import sqlite3
import os

# Connect to the database
db_path = os.path.join(os.path.dirname(__file__), 'rpg.db')
print(f"🔧 Connecting to: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add the missing column
    cursor.execute("ALTER TABLE habit ADD COLUMN target_date DATE")
    conn.commit()

    print("✅ SUCCESS: 'target_date' column added! You are safe.")
    conn.close()

except Exception as e:
    print(f"ℹ️ REPORT: {e}")
    print("(If it says 'duplicate column', that is GOOD. It means you already have it.)")