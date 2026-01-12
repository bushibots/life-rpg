from app import app, db
from models import User

with app.app_context():
    # Replace 'Arish' with your username if it is different!
    username_to_upgrade = 'Arish' 
    
    user = User.query.filter_by(username=username_to_upgrade).first()
    if user:
        user.is_pro = True
        db.session.commit()
        print(f"✅ SUCCESS: {user.username} is now a PRO user!")
    else:
        print(f"❌ ERROR: Could not find user '{username_to_upgrade}'. Check the spelling.")
