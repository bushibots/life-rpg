from app import app, db
from models import Habit
import re
from datetime import datetime

# Regex to find dates like "14 Jan", "15 Jan 2026", "Jan 14"
# It looks for: (Number) (Word) or (Word) (Number)
date_pattern = re.compile(r'\(?(\d{1,2})\s+([A-Za-z]{3,})\s*(\d{4})?\)?')

month_map = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

with app.app_context():
    print("--- 🕵️ SCANNING FOR TRAPPED DATES ---")
    habits = Habit.query.filter_by(completed=False).all()
    count = 0
    
    for h in habits:
        # Check if name contains a date pattern
        match = date_pattern.search(h.name)
        if match:
            # We found a date!
            day, month_str, year = match.groups()
            
            # 1. Parse the Month
            month = month_map.get(month_str.lower()[:3])
            
            # 2. Parse the Year (Default to 2026 if missing)
            if not year:
                year = 2026
            else:
                year = int(year)
                
            if month:
                # 3. Create the Date Object
                try:
                    new_date = datetime(year, month, int(day)).date()
                    
                    # 4. Update the Habit
                    h.target_date = new_date
                    
                    # 5. Clean the Name (Remove the date string)
                    # We remove the matched text from the name
                    clean_name = h.name.replace(match.group(0), "").strip()
                    # Remove trailing parenthesis if left over
                    clean_name = clean_name.replace("()", "").strip()
                    h.name = clean_name
                    
                    print(f"✅ FIXED: '{clean_name}' -> Scheduled for {new_date}")
                    count += 1
                except ValueError:
                    print(f"⚠️ Skipped invalid date in: {h.name}")

    if count > 0:
        db.session.commit()
        print(f"\n✨ Successfully repaired {count} tasks! They are now on your Timeline.")
    else:
        print("\n🤷 No tasks with text dates found.")
