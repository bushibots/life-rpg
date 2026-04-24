import os
import json
import random
import time
import re
import google.generativeai as genai
from datetime import date, timedelta

# ---------------------------------------------------------
# GLOBAL SETTINGS & COOLDOWNS
# ---------------------------------------------------------
API_TIMESTAMPS = {'strategy': 0, 'feedback': 0}

# FIX: 10-minute cooldown meant users almost never got real AI responses.
# Reduced to 60 seconds — enough to prevent abuse, not enough to break UX.
COOLDOWN_SECONDS = 60

MODEL_LIST = [
    'models/gemini-2.5-flash',
    'models/gemini-2.5-flash-lite',
    'models/gemini-flash-latest'
]

ALLOWED_STAT_TYPES = {"STR", "INT", "WIS", "CON", "CHA"}
DEFAULT_MODEL = MODEL_LIST[0]

# ---------------------------------------------------------
# PRE-WRITTEN STATIC TEXT (Used during Cooldown / API failure)
# ---------------------------------------------------------
BACKLOG_FALLBACKS = [
    "Identify your heaviest task right now and spend 25 minutes on it — nothing else.",
    "Block 2-hour deep work slots. Distraction is the enemy of backlog clearance.",
    "Do the hardest task first. Everything else will feel easy after.",
    "Break each backlog item into one clear next action. Ambiguity causes procrastination.",
    "Set a visible countdown timer. Urgency activates focus.",
    "Review your list. Delete anything that no longer matters — reduce before you execute.",
    "Batch similar tasks together. Context switching adds 20 minutes of mental overhead per switch.",
    "Consistency beats intensity. 1 hour daily beats a 10-hour Saturday sprint."
]

FEEDBACK_FALLBACKS = [
    "Data shows consistent effort. Focus on maintaining streak momentum.",
    "Your strongest stat is leading — double down on it while bringing up the weakest.",
    "Active days are your key metric. Aim for 5+ active days per week.",
    "Pattern detected: most XP earned mid-week. Use weekends as catch-up sessions.",
    "Quality over quantity — a few Hard/Epic completions outperform many Easy ones.",
    "Your weekly trend shows improvement. Keep the current pace for measurable monthly gains."
]

# ---------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------

def _configure_network_proxy():
    """Enable outbound proxy automatically on PythonAnywhere."""
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"]  = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"


def _extract_json_payload(raw_text, expected="array"):
    """
    Robustly extract JSON from model output that may include markdown/code fences.
    Handles triple-backtick blocks, stray text before/after, and nested quotes.
    """
    if not raw_text:
        raise ValueError("Empty model response")

    clean = raw_text.strip()

    # Strip ```json ... ``` or ``` ... ``` fences
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    clean = clean.strip()

    if expected == "array":
        start = clean.find("[")
        end   = clean.rfind("]")
    else:
        start = clean.find("{")
        end   = clean.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No valid JSON {expected} found in model response")

    return clean[start:end + 1]


def _safe_int(value, default=1, minimum=1, maximum=4):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _normalize_task(task):
    """
    Normalize an AI task object into the schema expected by app.py.
    Validates every field — returns None if name is empty/missing.
    """
    if not isinstance(task, dict):
        return None

    name        = str(task.get("name", "")).strip()
    category    = str(task.get("category", "General")).strip() or "General"
    stat_type   = str(task.get("stat_type", "CON")).strip().upper()
    description = str(task.get("description", "")).strip()
    target_date = task.get("target_date")

    # Validate stat_type
    if stat_type not in ALLOWED_STAT_TYPES:
        stat_type = "CON"

    # Validate difficulty
    difficulty = _safe_int(task.get("difficulty", 1), default=1, minimum=1, maximum=4)

    # Validate target_date format
    if target_date is not None:
        target_date = str(target_date).strip() or None
        if target_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", target_date):
            target_date = None

    # Must have a real name
    if not name or len(name) < 2:
        return None

    # Clean up category — strip leading/trailing whitespace, title-case it
    category = " ".join(w.capitalize() for w in category.split())

    # Ensure name starts with a capital
    name = name[0].upper() + name[1:]

    return {
        "name":        name,
        "category":    category,
        "stat_type":   stat_type,
        "difficulty":  difficulty,
        "description": description,
        "target_date": target_date
    }


def _call_model_with_fallback(prompt, available_keys, expected_json="array"):
    """
    Try each API key + each model until one succeeds.
    Returns parsed JSON (list or dict) or None on total failure.
    """
    for current_key in available_keys:
        if not current_key:
            continue
        try:
            genai.configure(api_key=current_key)
            for model_name in MODEL_LIST:
                try:
                    model    = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    raw_text = getattr(response, "text", "") or ""
                    payload  = _extract_json_payload(raw_text, expected=expected_json)
                    return json.loads(payload)
                except Exception:
                    continue
        except Exception:
            continue
    return None


# ---------------------------------------------------------
# 1. SMART FALLBACK KEYWORD PARSER (No API required)
#    Massively expanded keyword lists + real descriptions
# ---------------------------------------------------------

# stat_type -> (keywords, category_name, description_templates)
_KEYWORD_MAP = {
    "STR": {
        "keywords": [
            "gym", "run", "running", "jog", "jogging", "walk", "walking", "sprint",
            "exercise", "workout", "pushup", "push-up", "pullup", "squat", "plank",
            "lift", "lifting", "weight", "weights", "bench", "deadlift", "curl",
            "cardio", "hiit", "yoga", "stretching", "swim", "swimming", "cycling",
            "bike", "sport", "sports", "football", "basketball", "cricket", "tennis",
            "martial arts", "boxing", "fight", "muscle", "fitness", "training",
            "abs", "core", "legs", "chest", "shoulders", "back exercise"
        ],
        "category": "Physical Training",
        "descriptions": [
            "Focus on proper form over speed. Track reps and increase by 5% each week.",
            "Warm up for 5 minutes first. Stay consistent — results show in 4 weeks.",
            "Set a timer and push to completion. Log your performance after every session.",
            "Pair this with adequate protein intake (1.6g per kg bodyweight) for best results."
        ]
    },
    "INT": {
        "keywords": [
            "study", "read", "reading", "book", "books", "math", "maths", "physics",
            "chemistry", "biology", "history", "geography", "code", "coding", "program",
            "programming", "python", "javascript", "java", "c++", "html", "css",
            "exam", "test", "assignment", "homework", "notes", "lecture", "course",
            "learn", "learning", "research", "thesis", "essay", "paper", "report",
            "solve", "algorithm", "data structure", "machine learning", "ai", "ml",
            "chapter", "topic", "subject", "syllabus", "revision", "revise",
            "flashcard", "quiz", "tutorial", "class", "college", "school", "university"
        ],
        "category": "Learning & Study",
        "descriptions": [
            "Use the Pomodoro technique: 25 mins focused work, 5 min break. Repeat 4 times.",
            "Summarize key points in your own words after each session to boost retention.",
            "Remove all distractions — phone on silent, close unnecessary tabs before starting.",
            "Connect new concepts to things you already know. Context makes memory stick."
        ]
    },
    "WIS": {
        "keywords": [
            "plan", "planning", "journal", "journaling", "meditate", "meditation",
            "reflect", "reflection", "think", "thinking", "review", "strategy",
            "budget", "finance", "money", "savings", "invest", "investment",
            "goal", "goals", "vision", "priorities", "schedule", "organize",
            "organize", "declutter", "mindfulness", "gratitude", "affirmation",
            "habit tracker", "morning routine", "evening routine", "weekly review",
            "decision", "solve problem", "analyze", "brainstorm", "write", "writing",
            "blog", "content", "creative", "design", "draw", "drawing", "art"
        ],
        "category": "Mind & Strategy",
        "descriptions": [
            "Block 20 minutes of uninterrupted time. Write without editing — clarity comes from volume.",
            "Set a specific intention before starting. Vague planning leads to vague results.",
            "Use the Eisenhower matrix: separate urgent from important before executing.",
            "Review your last week's outcomes before planning the next one."
        ]
    },
    "CON": {
        "keywords": [
            "sleep", "wake up", "water", "drink", "hydrate", "hydration", "eat",
            "meal", "diet", "nutrition", "cook", "cooking", "clean", "cleaning",
            "laundry", "dishes", "chore", "chores", "tidy", "tidying", "grocery",
            "groceries", "shop", "shopping", "medicine", "vitamin", "supplement",
            "doctor", "appointment", "skincare", "hygiene", "shower", "bathroom",
            "healthy", "health", "routine", "daily", "habit", "consistency",
            "organize room", "bedroom", "workspace", "desk", "bills", "file"
        ],
        "category": "Health & Routine",
        "descriptions": [
            "Set a phone reminder to make this non-negotiable. Routine is built through repetition.",
            "Track this task for 21 days straight — that's the minimum for habit formation.",
            "Do this immediately after an existing habit to build a habit chain.",
            "Consistency is more important than perfection. Done imperfectly still counts."
        ]
    },
    "CHA": {
        "keywords": [
            "call", "phone", "message", "text", "email", "reply", "respond",
            "meet", "meeting", "talk", "conversation", "network", "networking",
            "friend", "family", "relationship", "date", "social", "party",
            "event", "collaborate", "team", "group", "presentation", "speak",
            "public speaking", "communicate", "follow up", "connect", "linkedin",
            "interview", "apply", "job", "mentor", "mentorship", "feedback"
        ],
        "category": "Social & Communication",
        "descriptions": [
            "Prepare 2-3 talking points before the interaction so you show up confident.",
            "Follow up within 24 hours. Most opportunities are lost to delayed responses.",
            "Listen 70%, speak 30%. People remember how you made them feel, not what you said.",
            "Be specific in your message — vague requests get vague responses."
        ]
    }
}

# Difficulty heuristics — keywords that suggest harder tasks
_DIFFICULTY_SIGNALS = {
    4: ["semester", "project", "thesis", "dissertation", "marathon", "certification",
        "launch", "build", "create app", "finish course", "complete syllabus"],
    3: ["hour", "hours", "chapter", "module", "assignment", "report", "essay",
        "prepare", "complete", "finish", "submit", "present"],
    2: ["30 min", "45 min", "session", "practice", "review", "summarize", "draft"],
    1: ["5 min", "10 min", "quick", "brief", "short", "small", "easy"]
}


def _detect_difficulty(text: str) -> int:
    text_lower = text.lower()
    for level in [4, 3, 2, 1]:
        if any(kw in text_lower for kw in _DIFFICULTY_SIGNALS[level]):
            return level
    return 1


def _smart_category_name(text: str, base_category: str) -> str:
    """
    Try to extract a more specific category name from the task text.
    E.g. "study python chapter 3" -> "Python Study" instead of just "Learning & Study"
    """
    text_lower = text.lower()

    # Subject-specific overrides
    subject_map = {
        "python":        "Python Programming",
        "javascript":    "JavaScript Development",
        "java":          "Java Programming",
        "c++":           "C++ Programming",
        "html":          "Web Development",
        "css":           "Web Development",
        "react":         "React Development",
        "sql":           "Database & SQL",
        "math":          "Mathematics",
        "maths":         "Mathematics",
        "physics":       "Physics Study",
        "chemistry":     "Chemistry Study",
        "biology":       "Biology Study",
        "history":       "History Study",
        "finance":       "Personal Finance",
        "budget":        "Personal Finance",
        "invest":        "Investment Planning",
        "gym":           "Gym Training",
        "run":           "Running & Cardio",
        "yoga":          "Yoga & Flexibility",
        "meditation":    "Mindfulness Practice",
        "journal":       "Daily Journaling",
        "drawing":       "Art & Drawing",
        "design":        "Creative Design",
        "writing":       "Writing Practice",
        "reading":       "Book Reading",
        "sleep":         "Sleep Optimization",
        "diet":          "Diet & Nutrition",
        "grocery":       "Household Errands",
        "clean":         "Home Organization",
        "linkedin":      "Career Networking",
        "interview":     "Job Preparation",
        "presentation":  "Public Speaking",
    }

    for keyword, category in subject_map.items():
        if keyword in text_lower:
            return category

    return base_category


def guess_category(text: str) -> dict:
    """
    Fallback parser when AI is unavailable.
    Uses expanded keyword matching to return a well-formed task dict.
    """
    text_stripped = text.strip()
    if not text_stripped:
        return None

    text_lower = text_stripped.lower()

    # Detect stat_type by keyword matching
    detected_stat = "CON"
    detected_meta = _KEYWORD_MAP["CON"]

    for stat, meta in _KEYWORD_MAP.items():
        if any(kw in text_lower for kw in meta["keywords"]):
            detected_stat   = stat
            detected_meta   = meta
            break

    # Smart category name
    base_category = detected_meta["category"]
    category      = _smart_category_name(text_lower, base_category)

    # Smart task name — capitalize properly, trim to reasonable length
    name = text_stripped
    if len(name) > 60:
        name = name[:57] + "..."
    name = name[0].upper() + name[1:]

    # Pick a contextual description
    description = random.choice(detected_meta["descriptions"])

    # Detect difficulty
    difficulty = _detect_difficulty(text_lower)

    return {
        "name":        name,
        "category":    category,
        "stat_type":   detected_stat,
        "difficulty":  difficulty,
        "description": description,
        "target_date": None
    }


# ---------------------------------------------------------
# 2. SMART BRAIN DUMP PARSER (Gemini AI)
#    FIX: New prompt demands minimum task count, specific names,
#    smart categories, and useful descriptions.
# ---------------------------------------------------------

def smart_ai_parse(text_input: str, primary_api_key: str) -> list:
    _configure_network_proxy()

    available_keys = [
        primary_api_key,
        os.getenv('GEMINI_API_KEY_2'),
        os.getenv('GEMINI_API_KEY_3')
    ]
    available_keys = [k for k in available_keys if k]
    random.shuffle(available_keys)

    today_str    = date.today().strftime("%Y-%m-%d")
    deadline_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

    # Count lines to set minimum task expectation
    lines = [l.strip() for l in text_input.strip().split('\n') if l.strip()]
    n_lines = max(len(lines), 1)
    # Each line should produce at least 2-3 tasks; total minimum is 5
    min_tasks = max(5, n_lines * 2)

    prompt = f"""You are an expert productivity coach and RPG quest designer.
Your job is to turn the user's raw text into a rich, comprehensive list of specific, actionable quests.

TODAY: {today_str}
DEFAULT_DEADLINE (use when dates are vague like "this week"): {deadline_str}

USER INPUT:
\"\"\"
{text_input}
\"\"\"

=== CRITICAL RULES — YOU MUST FOLLOW ALL OF THEM ===

1. OUTPUT: Return ONLY a valid JSON array. Zero markdown. Zero explanation. Just the array.

2. QUANTITY: Generate AT LEAST {min_tasks} tasks. Big goals MUST be broken into multiple sub-tasks.
   Example: "learn Python" → 6+ tasks: Install Python, Learn variables, Write first function, etc.
   Never collapse a full goal into a single task.

3. TASK NAMES: Use action verb + specific object. Max 8 words. NEVER vague.
   BAD:  "Study"  |  "Exercise"  |  "Work on project"
   GOOD: "Complete Python Chapter 3 exercises"  |  "Run 3km at steady pace"  |  "Write 500-word blog draft"

4. CATEGORIES: Be SPECIFIC to the context — never just "General" or "Tasks".
   BAD:  "General"  |  "Tasks"  |  "Work"
   GOOD: "Python Programming"  |  "Morning Fitness"  |  "Financial Planning"  |  "DSA Preparation"

5. DESCRIPTIONS: Write 1-2 sentences of CONCRETE, practical guidance.
   BAD:  "Do this task."  |  "" (empty)
   GOOD: "Open VS Code, create main.py, and implement a function that reverses a list. Run with python main.py."

6. STAT TYPE — assign based on actual task content:
   STR = Physical exercise, gym, running, sport, martial arts
   INT = Studying, coding, reading books, learning any skill, research
   WIS = Planning, journaling, meditation, budgeting, reflection, creative writing
   CON = Health habits, sleep, diet, hydration, household chores, daily routines
   CHA = Social calls, networking, emails, presentations, interviews, teamwork

7. DIFFICULTY:
   1 = Easy   → under 15 mins, simple action
   2 = Medium → 15–60 mins, needs focus
   3 = Hard   → 1–3 hours, significant mental/physical effort
   4 = Epic   → multi-day or major milestone

8. DATES: Only assign target_date if input mentions a specific deadline or timeframe.
   Use null otherwise. Format: YYYY-MM-DD.

=== OUTPUT SCHEMA (repeat for every task) ===
[
  {{
    "name": "Action verb + specific object",
    "category": "Specific project or life area",
    "stat_type": "STR|INT|WIS|CON|CHA",
    "difficulty": 1,
    "target_date": "YYYY-MM-DD or null",
    "description": "Concrete, practical 1-2 sentence instruction."
  }}
]

=== EXAMPLE (for input: "I need to get fit and finish my Python assignment") ===
[
  {{"name": "Complete 20-minute morning jog", "category": "Morning Fitness", "stat_type": "STR", "difficulty": 2, "target_date": null, "description": "Run at a comfortable pace for 20 minutes. Focus on breathing rhythm, not speed. Track distance with any running app."}},
  {{"name": "Do 3 sets of 15 push-ups", "category": "Morning Fitness", "stat_type": "STR", "difficulty": 1, "target_date": null, "description": "Complete 3 sets with 60 seconds rest between each. Keep your core tight throughout the movement."}},
  {{"name": "Stretch for 10 minutes post-workout", "category": "Morning Fitness", "stat_type": "CON", "difficulty": 1, "target_date": null, "description": "Focus on hip flexors, hamstrings, and chest after your session. Hold each stretch for 30 seconds."}},
  {{"name": "Read Python assignment brief carefully", "category": "Python Programming", "stat_type": "INT", "difficulty": 1, "target_date": null, "description": "Read the full assignment PDF. Highlight requirements and mark any unclear parts with questions."}},
  {{"name": "Set up project folder and Git repo", "category": "Python Programming", "stat_type": "INT", "difficulty": 1, "target_date": null, "description": "Create a new folder, run git init, make an initial commit. Good structure saves debugging time."}},
  {{"name": "Write core functions for assignment", "category": "Python Programming", "stat_type": "INT", "difficulty": 3, "target_date": null, "description": "Implement the main logic functions first. Test each function individually before combining them."}},
  {{"name": "Write test cases and debug code", "category": "Python Programming", "stat_type": "INT", "difficulty": 2, "target_date": null, "description": "Write at least 3 test cases covering edge cases. Use print statements or pytest to verify output."}},
  {{"name": "Review and submit final assignment", "category": "Python Programming", "stat_type": "INT", "difficulty": 2, "target_date": null, "description": "Read through the code once, clean up comments, then submit via the required portal."}}
]

NOW generate tasks for the actual user input above. Remember: minimum {min_tasks} tasks, specific names, specific categories, real descriptions."""

    raw_tasks = _call_model_with_fallback(prompt, available_keys, expected_json="array")

    # Handle case where AI returns a single object instead of array
    if isinstance(raw_tasks, dict):
        raw_tasks = [raw_tasks]

    normalized = []
    if isinstance(raw_tasks, list):
        for raw_task in raw_tasks:
            t = _normalize_task(raw_task)
            if t:
                normalized.append(t)

    # If AI produced good results, return them
    if len(normalized) >= 2:
        return normalized

    # Full fallback: parse each line with the expanded keyword parser
    results = []
    for line in text_input.split('\n'):
        line = line.strip()
        if not line:
            continue
        t = guess_category(line)
        if t:
            results.append(t)

    return results if results else [guess_category(text_input)]


# ---------------------------------------------------------
# 3. BACKLOG STRATEGY ADVISOR
#    FIX: Reduced cooldown to 60s, better prompt output
# ---------------------------------------------------------

def get_backlog_strategy(hours_debt, days_to_clear, mode):
    global API_TIMESTAMPS

    if time.time() - API_TIMESTAMPS['strategy'] < COOLDOWN_SECONDS:
        return random.choice(BACKLOG_FALLBACKS)

    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            return random.choice(BACKLOG_FALLBACKS)

        _configure_network_proxy()
        genai.configure(api_key=api_key)

        prompt = (
            f"A student has {hours_debt} hours of academic backlog to clear in {days_to_clear} days "
            f"using the {mode} study method. "
            f"Give ONE specific, tactical recommendation. Include a concrete daily schedule or action. "
            f"Be direct and practical. Maximum 35 words. No fluff."
        )

        model    = genai.GenerativeModel(DEFAULT_MODEL)
        response = model.generate_content(prompt)

        API_TIMESTAMPS['strategy'] = time.time()
        return response.text.strip()

    except Exception as e:
        print(f"[BacklogStrategy] AI Error: {e}")
        return random.choice(BACKLOG_FALLBACKS)


# ---------------------------------------------------------
# 4. GENERAL AI FEEDBACK
#    FIX: Reduced cooldown, more insightful prompt
# ---------------------------------------------------------

def get_ai_feedback(stats_text):
    global API_TIMESTAMPS

    if time.time() - API_TIMESTAMPS['feedback'] < COOLDOWN_SECONDS:
        return random.choice(FEEDBACK_FALLBACKS)

    try:
        api_key = os.getenv('GEMINI_API_KEY_2') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            return random.choice(FEEDBACK_FALLBACKS)

        _configure_network_proxy()
        genai.configure(api_key=api_key)

        prompt = (
            f"You are an analytical performance coach. "
            f"Here is a user's RPG stats and quest history: \"{stats_text}\". "
            f"Give exactly 2 sentences of feedback. "
            f"Sentence 1: identify their strongest pattern or best result. "
            f"Sentence 2: give one specific, actionable improvement they should make this week. "
            f"No flattery. Be data-driven and precise."
        )

        model    = genai.GenerativeModel(DEFAULT_MODEL)
        response = model.generate_content(prompt)

        API_TIMESTAMPS['feedback'] = time.time()
        return response.text.strip()

    except Exception:
        return random.choice(FEEDBACK_FALLBACKS)


# ---------------------------------------------------------
# 5. GENIE QUESTION GENERATOR (unchanged logic, cleaner prompt)
# ---------------------------------------------------------

def generate_genie_questions(wish):
    try:
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Missing Gemini API key")

        _configure_network_proxy()
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(DEFAULT_MODEL)

        prompt = f"""The user wants to achieve: "{wish}"

You are a wise, precise life coach. Ask 3 highly specific, practical questions to understand:
- Their current skill/knowledge level
- Their available time, budget, or resources  
- The biggest obstacle or gap they need to overcome

Return ONLY a JSON array of exactly 3 question strings. No markdown. No extra text.
Example: ["How many hours per week can you realistically dedicate?", "What is your current level with this?", "What has stopped you before?"]"""

        response = model.generate_content(prompt)
        payload   = _extract_json_payload(getattr(response, "text", ""), expected="array")
        questions = json.loads(payload)

        if not isinstance(questions, list):
            raise ValueError("Not a list")

        return [str(q).strip() for q in questions if str(q).strip()][:3]

    except Exception as e:
        print(f"[GenieQuestions] Error: {e}")
        return [
            "How much time can you realistically dedicate to this goal each week?",
            "What is the biggest obstacle currently standing in your way?",
            "What specific resources, tools, or budget do you currently have available?"
        ]


# ---------------------------------------------------------
# 6. GENIE BLUEPRINT GENERATOR
#    FIX: Now generates 5-8 specific tasks instead of 3 generic phases
# ---------------------------------------------------------

def generate_genie_blueprint(wish, q1, a1, q2, a2, q3, a3):
    try:
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Missing Gemini API key")

        _configure_network_proxy()
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(DEFAULT_MODEL)

        prompt = f"""You are a master life coach AI creating a personalized quest blueprint.

GOAL: "{wish}"

USER'S ANSWERS:
1. {q1} → {a1}
2. {q2} → {a2}
3. {q3} → {a3}

Based on these SPECIFIC answers, create a personalized Master Quest blueprint.

IMPORTANT: The tasks array must contain 5 to 8 tasks — not 3. Each task should be a real, specific milestone
tailored to what the user told you. Not generic "Phase 1/2/3" labels.

Return ONLY a JSON object with this EXACT structure. No markdown. No extra text.

{{
  "goal_name": "Short, inspiring name for this Master Quest (max 6 words)",
  "habit": {{
    "name": "One specific daily action that builds direct momentum toward this goal",
    "time_of_day": "Morning"
  }},
  "tasks": [
    {{
      "title": "Specific milestone name (not just 'Phase 1')",
      "description": "Detailed, step-by-step instructions on exactly what to do. At least 2 sentences. Tailored to their answers."
    }},
    {{
      "title": "...",
      "description": "..."
    }}
  ]
}}"""

        response  = model.generate_content(prompt)
        payload   = _extract_json_payload(getattr(response, "text", ""), expected="object")
        blueprint = json.loads(payload)

        if not isinstance(blueprint, dict):
            raise ValueError("Blueprint is not a dict")

        return blueprint

    except Exception as e:
        print(f"[GenieBlueprint] Error: {e}")
        return None
