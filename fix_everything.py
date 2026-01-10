import os
import shutil
import subprocess
from werkzeug.security import generate_password_hash

print("--- STARTING AUTOMATED FIX ---")

# 1. DELETE ALL CONFLICTING FILES
paths_to_delete = ["migrations", "instance", "life_rpg.db", "life_rpg_v2.db"]

for path in paths_to_delete:
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print(f"✓ Deleted: {path}")
    else:
        print(f"• Not found (Clean): {path}")

# 2. RUN FLASK COMMANDS
print("\n--- REBUILDING DATABASE ---")
subprocess.run(["flask", "db", "init"], check=True)
subprocess.run(["flask", "db", "migrate", "-m", "Automated Fix"], check=True)
subprocess.run(["flask", "db", "upgrade"], check=True)

# 3. CREATE ADMIN USER
print("\n--- CREATING ADMIN USER ---")
# delayed import to ensure app loads with new DB config
from app import app, db
from models import User

with app.app_context():
    # Create Arish
    u = User(username='Arish', password=generate_password_hash('password123', method='pbkdf2:sha256'))
    u.is_admin = True
    db.session.add(u)
    db.session.commit()
    print("✓ SUCCESS: Commander 'Arish' created.")

print("\n--- MISSION COMPLETE ---")
print("Go to the WEB tab and click RELOAD now.")