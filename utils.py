import os
import json
import google.generativeai as genai

def guess_category(text):
    text = text.lower()
    
    strength_keywords = ['gym', 'run', 'walk', 'exercise', 'pushup', 'sport', 'football', 'cricket', 'lift', 'workout']
    intel_keywords = ['study', 'read', 'book', 'math', 'code', 'python', 'exam', 'test', 'revise', 'learn', 'clat', 'gk']
    charisma_keywords = ['call', 'meet', 'talk', 'message', 'text', 'date', 'party', 'presentation', 'ask', 'email']
    creativity_keywords = ['draw', 'paint', 'write', 'design', 'idea', 'brainstorm', 'music', 'video', 'edit']

    category = "General"
    
    if any(word in text for word in strength_keywords):
        category = "Strength"
    elif any(word in text for word in intel_keywords):
        category = "Intelligence"
    elif any(word in text for word in charisma_keywords):
        category = "Charisma"
    elif any(word in text for word in creativity_keywords):
        category = "Creativity"

    difficulty = 1
    if "hour" in text or "finish" in text or "complete" in text: difficulty = 2
    if "project" in text or "mock" in text or "syllabus" in text: difficulty = 3

    return {"name": text.capitalize(), "category": category, "difficulty": difficulty}

def smart_ai_parse(text_input, api_key):
    # 1. PythonAnywhere Proxy Setup
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    genai.configure(api_key=api_key)

    # 2. UPDATED MODEL LIST (Based on your check_models.py output)
    # We prioritize 2.0 Flash as it is stable and available to you.
    model_candidates = [
        'models/gemini-2.0-flash', 
        'models/gemini-2.0-flash-lite',
        'models/gemini-flash-latest'
    ]

    last_error = ""

    prompt = f"""
    You are a task manager. Extract distinct tasks from this text:
    "{text_input}"
    
    Return a JSON LIST where each item has:
    - "name": (string) The task name
    - "category": (string) Choose EXACTLY one: Strength, Intelligence, Charisma, Creativity, General
    - "difficulty": (int) 1 (Easy), 2 (Medium), or 3 (Hard)
    
    IMPORTANT: Return ONLY raw JSON. No markdown formatting.
    """

    for model_name in model_candidates:
        try:
            # Try to generate with this model name
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            # If we get here, it worked! Process and return.
            clean_text = response.text.strip().replace("```json", "").replace("```", "")
            tasks = json.loads(clean_text)
            if isinstance(tasks, dict): tasks = [tasks]
            return tasks

        except Exception as e:
            # If this model failed, save error and loop to the next one
            last_error = str(e)
            continue

    # 3. If ALL models fail, return the error to the user
    return [{
        "name": f"⚠️ AI ERROR: {last_error}",
        "category": "General",
        "difficulty": 1
    }]
