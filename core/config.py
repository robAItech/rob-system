import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class SystemSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    deepseek_api_key: str = Field(default="sk-your-deepseek-api-key-here", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model_chat: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL_CHAT")
    deepseek_model_coder: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL_CODER")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")

    def is_real_key_available(self) -> bool:
        return bool(
            self.deepseek_api_key 
            and self.deepseek_api_key != "sk-your-deepseek-api-key-here" 
            and self.deepseek_api_key.startswith("sk-")
        )

settings = SystemSettings()
