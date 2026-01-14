import os
import google.generativeai as genai

def load_keys_from_env():
    """Manually reads the .env file to get keys without needing python-dotenv."""
    keys = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.strip().startswith('#') or not line.strip(): continue
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    keys[key] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        print("❌ ERROR: .env file not found!")
        return {}
    return keys

def audit_all_keys():
    # 1. Setup Proxy (Required for PythonAnywhere)
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"

    # 2. Get Keys
    env_vars = load_keys_from_env()
    key_list = [
        ('KEY 1', env_vars.get('GEMINI_API_KEY')),
        ('KEY 2', env_vars.get('GEMINI_API_KEY_2')),
        ('KEY 3', env_vars.get('GEMINI_API_KEY_3'))
    ]

    print("\n🔍 --- GOOGLE CLOUD ACCESS AUDIT --- 🔍")

    for name, api_key in key_list:
        print(f"\nScanning permissions for {name}...")
        
        if not api_key:
            print("   ⚠️  Key not found in .env")
            continue

        try:
            genai.configure(api_key=api_key)
            
            # Ask Google what models are valid for this specific key
            valid_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    valid_models.append(m.name)
            
            if valid_models:
                print(f"   ✅ ACCESS GRANTED. Valid Models:")
                # Print only the useful 'Flash' and 'Pro' models to keep list clean
                for m in valid_models:
                    if 'flash' in m or 'pro' in m:
                        print(f"      • {m}")
            else:
                print("   ❌ Key works, but no models available (Billing issue?)")

        except Exception as e:
            print(f"   ❌ ACCESS DENIED: {e}")

    print("\n---------------------------------------")

if __name__ == "__main__":
    audit_all_keys()