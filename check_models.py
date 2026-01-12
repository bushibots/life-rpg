import os
import google.generativeai as genai

# 1. Setup Proxy (Required for PythonAnywhere)
os.environ["http_proxy"] = "http://proxy.server:3128"
os.environ["https_proxy"] = "http://proxy.server:3128"

# 2. Configure API (I am using the key you pasted earlier)
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')

print("--- CONTACTING GOOGLE ---")
try:
    # 3. Ask Google for the list
    print("Available Models for you:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ {m.name}")
except Exception as e:
    print(f"❌ ERROR: {e}")
print("-------------------------")
