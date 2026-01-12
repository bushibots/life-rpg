import os
import google.generativeai as genai

# 1. Setup Proxy (Required for PythonAnywhere)
os.environ["http_proxy"] = "http://proxy.server:3128"
os.environ["https_proxy"] = "http://proxy.server:3128"

# 2. Configure API (I am using the key you pasted earlier)
api_key = "AIzaSyBCCKwpuLG9vRWow3kZoh2oNhgnqRajRhc"
genai.configure(api_key=api_key)

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
