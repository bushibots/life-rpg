from app import app, db
from models import User

# This starts the connection to the database
with app.app_context():
    # REPLACE 'CosmoCommander' WITH YOUR EXACT USERNAME
    user = User.query.filter_by(username='Arish').first()
    
    if user:
        user.is_admin = True
        db.session.commit()
        print(f"SUCCESS: {user.username} is now an Admin!")
    else:
        print("User not found! Did you register on the website first?")

from app import app, db
from models import User

# This starts the connection to the database
with app.app_context():
    # REPLACE 'CosmoCommander' WITH YOUR EXACT USERNAME
    user = User.query.filter_by(username='Arish').first()
    
    if user:
        user.is_admin = True
        db.session.commit()
        print(f"SUCCESS: {user.username} is now an Admin!")
    else:
        print("User not found! Did you register on the website first?")