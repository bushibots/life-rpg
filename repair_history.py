from app import app, db
from models import User, Goal, Habit, QuestHistory
from datetime import date

print("--- STARTING HISTORY REPAIR ---")

with app.app_context():
    # 1. Get the user (Arish)
    user = User.query.filter_by(username='Arish').first()
    
    if not user:
        print("Error: User 'Arish' not found.")
    else:
        print(f"Scanning active quests for Commander {user.username}...")
        
        # 2. Find all Goals & Habits for this user
        goals = Goal.query.filter_by(user_id=user.id).all()
        repaired_count = 0
        
        for goal in goals:
            for habit in goal.habits:
                # 3. If the habit is marked 'Completed' (Green Check)
                if habit.completed:
                    # Check if it is already in history to avoid duplicates for today
                    existing = QuestHistory.query.filter_by(
                        user_id=user.id, 
                        name=habit.name,
                        date_completed=date.today()
                    ).first()
                    
                    if not existing:
                        # 4. Create the missing History Record
                        print(f"• Repairing: {habit.name} (+{habit.xp_value} XP)")
                        
                        history_entry = QuestHistory(
                            user_id=user.id,
                            name=habit.name,
                            difficulty=habit.difficulty,
                            stat_type=habit.stat_type, # Using the stat from the habit
                            xp_gained=habit.xp_value,
                            date_completed=date.today()
                        )
                        db.session.add(history_entry)
                        repaired_count += 1
        
        # 5. Save changes
        if repaired_count > 0:
            db.session.commit()
            print(f"\n✓ SUCCESS: synced {repaired_count} completed quests to the War Room.")
        else:
            print("\n✓ System is already in sync. No missing records found.")

print("--- REPAIR COMPLETE ---")