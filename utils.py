import os
import json
import random
import time
import google.generativeai as genai
from datetime import date

# ---------------------------------------------------------
# GLOBAL SETTINGS & COOLDOWNS
# ---------------------------------------------------------
API_TIMESTAMPS = {'strategy': 0, 'feedback': 0}
COOLDOWN_SECONDS = 600  # 10 Minutes (System will use pre-written text during this time)

# USER-DEFINED MODEL LIST
MODEL_LIST = [
    'models/gemini-2.5-flash',
    'models/gemini-2.5-flash-lite',
    'models/gemini-flash-latest'
]

# ---------------------------------------------------------
# PRE-WRITTEN STATIC TEXT (Used during Cooldown)
# ---------------------------------------------------------
BACKLOG_FALLBACKS = [
    "Focus on the single most important task right now.",
    "Clear your workspace. A clean desk helps a clear mind.",
    "Do not multitask. Finish one thing completely.",
    "Start with a 5-minute task to build momentum.",
    "Review your deadlines and prioritize by urgency.",
    "Take a short break, then restart with full focus.",
    "Break the biggest task into three smaller steps.",
    "Consistency is better than intensity. Just keep going."
]

FEEDBACK_FALLBACKS = [
    "System Status: Stable. Maintain current trajectory.",
    "Performance is within expected parameters.",
    "Keep tracking your data to improve accuracy.",
    "Your activity log shows consistent effort.",
    "Review your completed tasks to see your progress.",
    "Data analysis indicates steady improvement.",
    "Maintain your daily streak for best results."
]

# ---------------------------------------------------------
# 1. SIMPLE KEYWORD PARSER (Fallback Logic)
# ---------------------------------------------------------
def guess_category(text):
    text = text.lower()
    strength_keywords = ['gym', 'run', 'walk', 'exercise', 'pushup', 'sport', 'workout', 'lift']
    intel_keywords = ['study', 'read', 'book', 'math', 'code', 'python', 'exam', 'test', 'class']
    charisma_keywords = ['call', 'meet', 'talk', 'message', 'text', 'date', 'party', 'email']
    creativity_keywords = ['draw', 'paint', 'write', 'design', 'idea', 'music', 'video', 'edit']

    category = "General"
    if any(word in text for word in strength_keywords): category = "Strength"
    elif any(word in text for word in intel_keywords): category = "Intelligence"
    elif any(word in text for word in charisma_keywords): category = "Charisma"
    elif any(word in text for word in creativity_keywords): category = "Creativity"

    difficulty = 1
    if "hour" in text or "finish" in text or "complete" in text: difficulty = 2
    if "project" in text or "mock" in text or "syllabus" in text: difficulty = 3

    return {
        "name": text.capitalize(), 
        "category": category, 
        "difficulty": difficulty,
        # ADDED THESE TWO LINES TO PREVENT CRASHES IN APP.PY
        "description": "",
        "target_date": None
    }

# ---------------------------------------------------------
# 2. SMART BRAIN DUMP PARSER (Gemini)
# ---------------------------------------------------------
def smart_ai_parse(text_input, primary_api_key):
    # Proxy Setup for PythonAnywhere
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    # Load & Shuffle Keys
    available_keys = [primary_api_key]
    if os.getenv('GEMINI_API_KEY_2'): available_keys.append(os.getenv('GEMINI_API_KEY_2'))
    if os.getenv('GEMINI_API_KEY_3'): available_keys.append(os.getenv('GEMINI_API_KEY_3'))
    random.shuffle(available_keys)

    today_str = date.today().strftime("%Y-%m-%d")

    # PROMPT: Updated to allow Custom Categories & Date Extraction
    prompt = f"""
    You are a logic-based task extraction engine.
    Current Date: {today_str}
    User Input: "{text_input}"

    CORE OBJECTIVE:
    Analyze the input and convert it into a structured JSON list of actionable tasks.

    OPERATIONAL MODES:
    1. IF USER ASKS FOR A PLAN (e.g., "How to get fit", "Learn Python"):
       - Break the goal into 5-10 logical, sequential steps.
       - Assign realistic dates starting from today.
       - Description: Write one clear, simple instruction on how to execute the step.

    2. IF USER PROVIDES A LIST (e.g., "Buy milk, gym, email boss"):
       - Extract distinct tasks.
       - Target Date: Today (unless specific dates are mentioned like "tomorrow").
       - Description: Keep it empty or very brief.

    STYLE GUIDELINES:
    - Task Names: Simple and direct (e.g., "Read Chapter 1").
    - Language: Serious, easy to understand. No slang, no roleplay.
    - Category: Use standard tags (Strength, Intelligence, Charisma, Creativity, General) UNLESS the user specifies a new category or the task fits a specific project (e.g., "Finance", "Coding", "Housework").
    - Difficulty: 1 (Easy) to 4 (Epic/Hard).

    OUTPUT FORMAT:
    Return ONLY raw JSON. No markdown.
    [
        {{
            "name": "Task Name",
            "category": "CategoryString",
            "difficulty": 1,
            "target_date": "YYYY-MM-DD",
            "description": "Simple guide."
        }}
    ]
    """

    for current_key in available_keys:
        if not current_key: continue
        try:
            genai.configure(api_key=current_key)
            # Try specific models in the exact order requested
            for model_name in MODEL_LIST:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    
                    clean_text = response.text.strip()
                    if clean_text.startswith("```json"): clean_text = clean_text[7:]
                    if clean_text.endswith("```"): clean_text = clean_text[:-3]
                    
                    tasks = json.loads(clean_text)
                    if isinstance(tasks, dict): tasks = [tasks]
                    return tasks 
                except Exception:
                    continue
        except Exception:
            continue

    # Fallback to local logic if AI fails
    return [guess_category(line) for line in text_input.split('\n') if line.strip()]

# ---------------------------------------------------------
# 3. BACKLOG STRATEGY ADVISOR (With Static Cooldown)
# ---------------------------------------------------------
def get_backlog_strategy(hours_debt, days_to_clear, mode):
    global API_TIMESTAMPS
    
    # --- COOLDOWN CHECK ---
    # If less than 10 mins since last call, return STATIC text.
    if time.time() - API_TIMESTAMPS['strategy'] < COOLDOWN_SECONDS:
        return random.choice(BACKLOG_FALLBACKS)

    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key: return "API Key missing."

        if 'PYTHONANYWHERE_DOMAIN' in os.environ:
            os.environ["http_proxy"] = "http://proxy.server:3128"
            os.environ["https_proxy"] = "http://proxy.server:3128"

        genai.configure(api_key=api_key)
        
        prompt = (
            f"The user has {hours_debt} hours of academic backlog to cover in {days_to_clear} days "
            f"using {mode} methods. "
            f"Provide one sentence of clear, practical, and serious advice. "
            f"No motivational fluff. Just strategy. Under 25 words."
        )
        
        # Try primary model
        model = genai.GenerativeModel(MODEL_LIST[0]) 
        response = model.generate_content(prompt)
        
        # Update Timestamp only on successful AI call
        API_TIMESTAMPS['strategy'] = time.time()
        return response.text.strip()
    except Exception as e:
        print(f"AI Error: {e}")
        # Return static text on error too
        return random.choice(BACKLOG_FALLBACKS)

# ---------------------------------------------------------
# 4. GENERAL AI FEEDBACK (With Static Cooldown)
# ---------------------------------------------------------
def get_ai_feedback(stats_text):
    global API_TIMESTAMPS

    # --- COOLDOWN CHECK ---
    if time.time() - API_TIMESTAMPS['feedback'] < COOLDOWN_SECONDS:
        return random.choice(FEEDBACK_FALLBACKS)

    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key: return "AI offline."

        if 'PYTHONANYWHERE_DOMAIN' in os.environ:
            os.environ["http_proxy"] = "http://proxy.server:3128"
            os.environ["https_proxy"] = "http://proxy.server:3128"

        genai.configure(api_key=api_key)
        
        prompt = f"""
        Analyze this user performance report: "{stats_text}"
        Give 2 sentences of feedback. Be analytical and clear.
        Avoid flowery language. Focus on facts and improvement.
        """
        
        # Try primary model
        model = genai.GenerativeModel(MODEL_LIST[0])
        response = model.generate_content(prompt)
        
        API_TIMESTAMPS['feedback'] = time.time()
        return response.text.strip()
    except Exception:
        return random.choice(FEEDBACK_FALLBACKS)