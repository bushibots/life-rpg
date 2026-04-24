import os
import json
import random
import time
import re
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

ALLOWED_STAT_TYPES = {"STR", "INT", "WIS", "CON", "CHA"}
DEFAULT_MODEL = MODEL_LIST[0]

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


def _configure_network_proxy():
    """Enable outbound proxy automatically on PythonAnywhere."""
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"


def _extract_json_payload(raw_text, expected="array"):
    """
    Extract JSON from model output that may include markdown/code fences.
    expected: "array" or "object"
    """
    if not raw_text:
        raise ValueError("Empty model response")

    clean_text = raw_text.strip()
    clean_text = clean_text.replace("```json", "").replace("```", "").strip()

    if expected == "array":
        start, end = clean_text.find("["), clean_text.rfind("]")
    else:
        start, end = clean_text.find("{"), clean_text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("No valid JSON payload found in model response")

    return clean_text[start:end + 1]


def _safe_int(value, default=1, minimum=1, maximum=4):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _normalize_task(task):
    """Normalize an AI task object into the schema expected by the app."""
    if not isinstance(task, dict):
        return None

    name = str(task.get("name", "")).strip()
    category = str(task.get("category", "General")).strip() or "General"
    stat_type = str(task.get("stat_type", "CON")).strip().upper()
    if stat_type not in ALLOWED_STAT_TYPES:
        stat_type = "CON"

    difficulty = _safe_int(task.get("difficulty", 1), default=1, minimum=1, maximum=4)
    description = str(task.get("description", "")).strip()

    target_date = task.get("target_date")
    if target_date is not None:
        target_date = str(target_date).strip() or None
        if target_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", target_date):
            target_date = None

    if not name:
        return None

    return {
        "name": name,
        "category": category,
        "stat_type": stat_type,
        "difficulty": difficulty,
        "description": description,
        "target_date": target_date
    }


def _call_model_with_fallback(prompt, available_keys, expected_json="array"):
    """Try multiple keys and models, returning parsed JSON payload on success."""
    for current_key in available_keys:
        if not current_key:
            continue
        try:
            genai.configure(api_key=current_key)
            for model_name in MODEL_LIST:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    payload = _extract_json_payload(getattr(response, "text", ""), expected=expected_json)
                    return json.loads(payload)
                except Exception:
                    continue
        except Exception:
            continue
    return None

# ---------------------------------------------------------
# 1. SIMPLE KEYWORD PARSER (Fallback Logic)
# ---------------------------------------------------------
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
    stat_type = "CON"

    if any(word in text for word in strength_keywords):
        category = "Strength"
        stat_type = "STR"
    elif any(word in text for word in intel_keywords):
        category = "Intelligence"
        stat_type = "INT"
    elif any(word in text for word in charisma_keywords):
        category = "Charisma"
        stat_type = "CHA"
    elif any(word in text for word in creativity_keywords):
        category = "Creativity"
        stat_type = "WIS"

    difficulty = 1
    if "hour" in text or "finish" in text or "complete" in text: difficulty = 2
    if "project" in text or "mock" in text or "syllabus" in text: difficulty = 3

    return {
        "name": text.capitalize(),
        "category": category,
        "stat_type": stat_type,
        "difficulty": difficulty,
        "description": "",
        "target_date": None
    }

# ---------------------------------------------------------
# 2. SMART BRAIN DUMP PARSER (Gemini)
# ---------------------------------------------------------
def smart_ai_parse(text_input, primary_api_key):
    _configure_network_proxy()

    available_keys = [primary_api_key, os.getenv('GEMINI_API_KEY_2'), os.getenv('GEMINI_API_KEY_3')]
    available_keys = [k for k in available_keys if k]
    random.shuffle(available_keys)

    today_str = date.today().strftime("%Y-%m-%d")

    prompt = f"""
    You are a strict JSON task parser.
    Current Date: {today_str}
    User Input: "{text_input}"

    Convert the input into a JSON array of actionable tasks.
    Rules:
    1) Return ONLY valid JSON array and nothing else.
    2) Use this schema for each task.
    [
        {{
            "name": "Clear action name",
            "category": "Project or area",
            "stat_type": "STR|INT|WIS|CON|CHA",
            "difficulty": 1,
            "target_date": "YYYY-MM-DD or null",
            "description": "One short practical sentence."
        }}
    ]
    3) difficulty must be an integer from 1 to 4.
    4) stat_type mapping:
       STR physical/health, INT study/coding, WIS planning/finance, CON chores/routine, CHA social/communication.
    5) If date is missing/unclear, set target_date to null.
    6) Split multiple tasks into separate objects.
    """
    tasks = _call_model_with_fallback(prompt, available_keys, expected_json="array")
    if isinstance(tasks, dict):
        tasks = [tasks]

    normalized = []
    if isinstance(tasks, list):
        for raw_task in tasks:
            normalized_task = _normalize_task(raw_task)
            if normalized_task:
                normalized.append(normalized_task)

    if normalized:
        return normalized

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

        _configure_network_proxy()

        genai.configure(api_key=api_key)

        prompt = (
            f"The user has {hours_debt} hours of academic backlog to cover in {days_to_clear} days "
            f"using {mode} methods. "
            f"Give one tactical recommendation with concrete execution advice. "
            f"Keep it direct and practical. Maximum 25 words."
        )

        # Try primary model
        model = genai.GenerativeModel(DEFAULT_MODEL)
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
        api_key = os.getenv('GEMINI_API_KEY_2')
        if not api_key: return "AI offline."

        _configure_network_proxy()

        genai.configure(api_key=api_key)

        prompt = f"""
        Analyze this user performance report: "{stats_text}"
        Give 2 sentences of feedback. Be analytical and clear.
        Avoid flowery language. Focus on facts and improvement.
        """

        # Try primary model
        model = genai.GenerativeModel(DEFAULT_MODEL)
        response = model.generate_content(prompt)

        API_TIMESTAMPS['feedback'] = time.time()
        return response.text.strip()
    except Exception:
        return random.choice(FEEDBACK_FALLBACKS)

def generate_genie_questions(wish):
    try:
        # 1. Setup API Key and PythonAnywhere Proxy
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Missing Gemini API key")
        _configure_network_proxy()

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(DEFAULT_MODEL)

        prompt = f"""
        The user wants to achieve this major life goal: "{wish}".
        You are a wise, analytical Genie. To create a perfect, personalized Master Quest for them,
        you need to ask 3 highly specific, practical questions about their current situation,
        limitations, or preferences regarding this exact goal.

        Return ONLY a JSON array of 3 strings containing the questions. Do not include markdown formatting or extra text.
        Example format:
        ["How many hours a week can you dedicate to this?", "What is your current budget?", "Do you have any prior experience with this?"]
        """
        response = model.generate_content(prompt)
        payload = _extract_json_payload(getattr(response, "text", ""), expected="array")
        questions = json.loads(payload)
        if not isinstance(questions, list):
            raise ValueError("Question response is not a list")
        return [str(q).strip() for q in questions if str(q).strip()][:3]

    except Exception as e:
        print(f"Genie Question Generation Error: {e}")
        # Intelligent fallback questions just in case the API glitches
        return [
            "How much time can you realistically dedicate to this goal each week?",
            "What is the biggest obstacle currently standing in your way?",
            "What specific resources, tools, or budget do you currently have available for this?"
        ]

def generate_genie_blueprint(wish, q1, a1, q2, a2, q3, a3):
    try:
        # 1. Setup API Key and PythonAnywhere Proxy
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Missing Gemini API key")
        _configure_network_proxy()

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(DEFAULT_MODEL)

        prompt = f"""
        You are a master life coach AI. The user wants to achieve this major life goal: "{wish}".
        You asked them these questions and received these answers:
        1. {q1} -> {a1}
        2. {q2} -> {a2}
        3. {q3} -> {a3}

        Based on their specific answers, create a highly personalized Master Quest blueprint.
        Return ONLY a JSON object with this EXACT structure. Do not include markdown formatting or extra text.
        {{
            "goal_name": "A short, inspiring name for this Master Quest",
            "habit": {{
                "name": "One highly specific daily habit to build momentum",
                "time_of_day": "Morning"
            }},
            "tasks": [
                {{
                    "title": "Phase 1: Beginner Milestone",
                    "description": "Detailed, step-by-step instructions on exactly what to do first based on their answers."
                }},
                {{
                    "title": "Phase 2: Intermediate Milestone",
                    "description": "The next major hurdle they need to clear."
                }},
                {{
                    "title": "Phase 3: Final Mastery",
                    "description": "The final step to conquer the goal."
                }}
            ]
        }}
        """
        response = model.generate_content(prompt)
        payload = _extract_json_payload(getattr(response, "text", ""), expected="object")
        blueprint = json.loads(payload)
        if not isinstance(blueprint, dict):
            raise ValueError("Blueprint response is not an object")
        return blueprint

    except Exception as e:
        print(f"Genie Blueprint Generation Error: {e}")
        return None
