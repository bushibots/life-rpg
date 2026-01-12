import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# 1. Setup Proxy (Required for PythonAnywhere)
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    os.environ["http_proxy"] = "http://proxy.server:3128"
    os.environ["https_proxy"] = "http://proxy.server:3128"

# 2. Configure API (Safe Import)
api_key = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=api_key)

print("--- CONTACTING GOOGLE ---")
try:
    print("Available Models for you:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ {m.name}")
except Exception as e:
    print(f"❌ ERROR: {e}")
print("-------------------------")
