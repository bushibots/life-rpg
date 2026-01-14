import os
import google.generativeai as genai

def load_keys_from_env():
    """Manually reads the .env file to get keys."""
    keys = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.strip().startswith('#') or not line.strip(): continue
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    # Clean up quotes and whitespace
                    keys[key] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        print("❌ ERROR: .env file not found!")
        return {}
    return keys

def test_keys():
    # 1. Setup Proxy for PythonAnywhere
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    # 2. Get Keys
    env_vars = load_keys_from_env()
    
    key_list = [
        ('Key 1 (Main)', env_vars.get('GEMINI_API_KEY')),
        ('Key 2 (Backup)', env_vars.get('GEMINI_API_KEY_2')),
        ('Key 3 (Emergency)', env_vars.get('GEMINI_API_KEY_3'))
    ]

    # 👇 UPDATED MODEL (From your successful audit)
    TEST_MODEL = 'models/gemini-2.5-flash'

    print(f"\n🔍 --- HYDRA SYSTEM DIAGNOSTIC ---")
    print(f"🎯 Target Model: {TEST_MODEL}\n")

    for name, api_key in key_list:
        if not api_key:
            print(f"⚠️  {name}: NOT FOUND in .env file.")
            continue

        print(f"Testing {name}...", end=" ", flush=True)
        
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(TEST_MODEL)
            
            # Simple ping
            response = model.generate_content("Reply with only the word: ONLINE")
            
            if response.text:
                print("✅ ONLINE")
            else:
                print(f"❓ NO TEXT RECEIVED")
                
        except Exception as e:
            print(f"❌ FAILED")
            print(f"   Error: {str(e)}")

    print("\n---------------------------------------")

if __name__ == "__main__":
    test_keys()