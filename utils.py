import os
import json
import random
import google.generativeai as genai
from datetime import date

def guess_category(text):
    text = text.lower()
    strength_keywords = ['gym', 'run', 'walk', 'exercise', 'pushup', 'sport', 'workout']
    intel_keywords = ['study', 'read', 'book', 'math', 'code', 'python', 'exam', 'test']
    charisma_keywords = ['call', 'meet', 'talk', 'message', 'text', 'date', 'party']
    creativity_keywords = ['draw', 'paint', 'write', 'design', 'idea', 'music', 'video']

    category = "General"
    if any(word in text for word in strength_keywords): category = "Strength"
    elif any(word in text for word in intel_keywords): category = "Intelligence"
    elif any(word in text for word in charisma_keywords): category = "Charisma"
    elif any(word in text for word in creativity_keywords): category = "Creativity"

    difficulty = 1
    if "hour" in text or "finish" in text or "complete" in text: difficulty = 2
    if "project" in text or "mock" in text or "syllabus" in text: difficulty = 3

    return {"name": text.capitalize(), "category": category, "difficulty": difficulty}

def smart_ai_parse(text_input, primary_api_key):
    # 1. Proxy Setup (Keep for PythonAnywhere)
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    # --- HYDRA PROTOCOL: LOAD & SHUFFLE KEYS ---
    # Start with the key passed from app.py
    available_keys = [primary_api_key]

    # Check environment for reinforcements
    if os.getenv('GEMINI_API_KEY_2'): available_keys.append(os.getenv('GEMINI_API_KEY_2'))
    if os.getenv('GEMINI_API_KEY_3'): available_keys.append(os.getenv('GEMINI_API_KEY_3'))

    # Shuffle keys to spread the load (Load Balancing)
    random.shuffle(available_keys)

    # 👇 UPDATED MODEL LIST (Based on your successful audit)
    # We put the fastest/newest ones first.
    model_candidates = [
        'models/gemini-2.5-flash',       # Newest standard
        'models/gemini-2.5-flash-lite',  # Newest lightweight
        'models/gemini-flash-latest'     # Reliable backup
    ]

    today_str = date.today().strftime("%Y-%m-%d")

    prompt = f"""
    Act as an elite RPG Life Coach.
    Current Date: {today_str}
    User Input: "{text_input}"

    INSTRUCTIONS:
    1. ANALYZE: Is the user giving a list, or asking for a plan?

    2. IMPORTANT: Make all task names easy and understandable instead of fancy sci-fi ones until the user's theme is that or instructions by user.
       - Analyze user promt carefully.
    3. IF ASKING FOR A PLAN (e.g. "how to get abs"):
       - GENERATE 5-10 specific tasks.
       - INVENT a Category name (e.g. "Abs").
       - DESCRIPTION: Write a short, 1-sentence step-by-step guide (e.g. "Lie on back, lift knees, crunch up.").
       - Assign realistic dates.

    4. IF GIVING A LIST (e.g. "buy milk"):
       - Extract tasks.
       - DESCRIPTION: Leave empty or generic.

    5. OUTPUT: Return ONLY a JSON list.
       - "name": Task name.
       - "category": Short 1-word tag.
       - "difficulty": 1 (Easy), 2 (Medium), 3 (Hard).
       - "target_date": YYYY-MM-DD.
       - "description": The short guide string.
    """

    # --- THE FAILOVER LOOP ---
    # We try every Key. For every Key, we try every Model.
    for current_key in available_keys:
        try:
            genai.configure(api_key=current_key)

            for model_name in model_candidates:
                try:
                    # print(f"Testing {model_name} with key ending in ...{current_key[-4:]}") # Optional Debug
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)

                    clean_text = response.text.strip().replace("```json", "").replace("```", "")
                    tasks = json.loads(clean_text)
                    if isinstance(tasks, dict): tasks = [tasks]
                    return tasks # SUCCESS! Exit immediately.

                except Exception as model_error:
                    error_str = str(model_error)
                    # If it's a Rate Limit (429), break the MODEL loop to switch KEYS immediately
                    if "429" in error_str or "exhausted" in error_str:
                        # print(f"⚠️ Key exhausted. Switching...")
                        break # Breaks inner loop -> goes to next key in outer loop

                    # If it's just a random error, try the next model with SAME key
                    continue

        except Exception as e:
            # If the configuration itself fails, try next key
            continue

    # If we run out of ALL keys and ALL models:
    return [{
        "name": "⚠️ System Overload - All APIs Busy",
        "category": "General",
        "difficulty": 1,
        "target_date": None
    }]