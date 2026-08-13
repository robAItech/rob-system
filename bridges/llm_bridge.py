import os
import requests
from dotenv import load_dotenv

load_dotenv()

class LLMBridge:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com/v1/chat/completions"

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set in .env file")
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt or "You are an expert Python architect."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        response = requests.post(self.base_url, headers=headers, json=payload, timeout=45.0)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
