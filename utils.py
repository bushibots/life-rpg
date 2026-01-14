import os
import json
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

def smart_ai_parse(text_input, api_key):
    # 1. Proxy Setup (Keep this for PythonAnywhere)
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    genai.configure(api_key=api_key)

    model_candidates = [
        'models/gemini-2.0-flash',
        'models/gemini-2.0-flash-lite',
        'models/gemini-flash-latest'
    ]

    # We provide today's date so the AI knows when "tomorrow" is
    today_str = date.today().strftime("%Y-%m-%d")

    # 👇 YOUR CUSTOM PROMPT
    prompt = f"""
    Act as an elite RPG Life Coach.
    Current Date: {today_str}
    User Input: "{text_input}"

    INSTRUCTIONS:
    1. ANALYZE: Is the user giving a list, or asking for a plan?

    2. IF ASKING FOR A PLAN (e.g. "how to get abs"):
       - GENERATE 5-10 specific tasks.
       - INVENT a Category name (e.g. "Abs").
       - DESCRIPTION: Write a short, 1-sentence step-by-step guide (e.g. "Lie on back, lift knees, crunch up.").
       - Assign realistic dates.

    3. IF GIVING A LIST (e.g. "buy milk"):
       - Extract tasks.
       - DESCRIPTION: Leave empty or generic.

    4. OUTPUT: Return ONLY a JSON list.
       - "name": Task name.
       - "category": Short 1-word tag.
       - "difficulty": 1 (Easy), 2 (Medium), 3 (Hard).
       - "target_date": YYYY-MM-DD.
       - "description": The short guide string.
    """

    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)

            clean_text = response.text.strip().replace("```json", "").replace("```", "")
            tasks = json.loads(clean_text)
            if isinstance(tasks, dict): tasks = [tasks]
            return tasks

        except Exception as e:
            continue

    return [{
        "name": "⚠️ AI Error - Try Again",
        "category": "General",
        "difficulty": 1,
        "target_date": None
    }]