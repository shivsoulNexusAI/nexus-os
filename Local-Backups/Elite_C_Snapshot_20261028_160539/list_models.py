import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load the .env file to get the API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
else:
    genai.configure(api_key=api_key)
    
    print("\n" + "="*60)
    print("AVAILABLE MODELS SUPPORTING 'generateContent':")
    print("="*60)
    
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(m.name)
            
    print("="*60 + "\n")
