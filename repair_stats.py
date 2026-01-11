from app import app, db
from models import User, QuestHistory
from sqlalchemy import func

def repair_stats():
    with app.app_context():
        print("--- STARTING REPAIR PROTOCOL ---")
        
        # 1. DELETE DUPLICATE LOGS
        # We define a "duplicate" as the same quest completed on the same day multiple times.
        # This keeps the FIRST completion and deletes the rest.
        
        all_history = QuestHistory.query.order_by(QuestHistory.date_completed, QuestHistory.id).all()
        seen = set()
        deleted_count = 0
        
        for h in all_history:
            # Create a unique signature for this event
            signature = (h.user_id, h.name, h.date_completed)
            
            if signature in seen:
                # We have seen this before! Delete it.
                db.session.delete(h)
                deleted_count += 1
            else:
                seen.add(signature)
        
        db.session.commit()
        print(f"Deleted {deleted_count} duplicate ghost logs.")
        
        # 2. RECALCULATE USER TOTALS
        # Now that history is clean, we rebuild the User Profile to match it perfectly.
        
        users = User.query.all()
        for u in users:
            # Sum up all history for this user
            real_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id).scalar() or 0
            
            # Recalculate Attributes
            str_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id, stat_type='STR').scalar() or 0
            int_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id, stat_type='INT').scalar() or 0
            wis_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id, stat_type='WIS').scalar() or 0
            con_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id, stat_type='CON').scalar() or 0
            cha_xp = db.session.query(func.sum(QuestHistory.xp_gained)).filter_by(user_id=u.id, stat_type='CHA').scalar() or 0
            
            print(f"User {u.username}: Correcting XP from {u.total_xp} to {real_xp}")
            
            u.total_xp = real_xp
            u.str_score = str_xp
            u.int_score = int_xp
            u.wis_score = wis_xp
            u.con_score = con_xp
            u.cha_score = cha_xp
            
        db.session.commit()
        print("--- REPAIR COMPLETE. SYSTEMS SYNCED. ---")

if __name__ == "__main__":
    repair_stats()