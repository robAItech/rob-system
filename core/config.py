import os
from pathlib import Path
from typing import Optional
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
    # Agentic tool-use v RSI heal zanki (OpenAI function-calling). Privzeto vklopljeno.
    llm_tool_use: bool = Field(default=True, alias="LLM_TOOL_USE")
    # Semantični spomin (korak 2) — embeddingi prek Gemini. DeepSeek ostaja glavni LLM;
    # Gemini se uporablja SAMO za embedContent (vektorji iskanja spomina).
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    memory_embeddings: bool = Field(default=True, alias="MEMORY_EMBEDDINGS")
    memory_embed_model: str = Field(default="gemini-embedding-2", alias="MEMORY_EMBED_MODEL")
    memory_embed_api: str = Field(default="gemini", alias="MEMORY_EMBED_API")
    memory_embed_timeout_seconds: float = Field(default=10.0, alias="MEMORY_EMBED_TIMEOUT")
    # GStack skilli kot LLM orodje (korak 6). Prazno → Path.home()/".claude"/"skills".
    gstack_skills_dir: str = Field(default="", alias="GSTACK_SKILLS_DIR")
    # ─── Kontekst upravljanje (korak 3) ───────────────────────────────────
    # Izhodni cap v tokenih. Privzeto None = NEOMEJENO (varno za heal, ki piše
    # cele datoteke; cap bi lahko odrezal ### FILE blok).
    llm_max_completion_tokens: Optional[int] = Field(default=None, alias="LLM_MAX_COMPLETION_TOKENS")
    # Maks. skupna dolžina heal prompta v znakih (cena + overflow zaščita).
    llm_heal_prompt_chars: int = Field(default=50000, alias="LLM_HEAL_PROMPT_CHARS")
    # Maks. del sources (koda modula) v heal promptu, v znakih.
    llm_heal_sources_chars: int = Field(default=24000, alias="LLM_HEAL_SOURCES_CHARS")
    # Ali v sources vključiti test datoteke (test_*.py, *_test.py, conftest.py).
    # Priporočeno false: Test-Locking jih LLM ne sme spreminjati → ~55 % manj tokenov.
    llm_heal_include_tests: bool = Field(default=False, alias="LLM_HEAL_INCLUDE_TESTS")
    # Maks. skupna dolžina messages v agentic heal zanki (trim praga).
    llm_heal_agentic_context_chars: int = Field(default=50000, alias="LLM_HEAL_AGENTIC_CONTEXT_CHARS")
    # ─── Korak 10 — avto-rollback ob neuspelem buildu ─────────────────────
    # true = ob FAILED se actions/<proj>/ povrne na pred-build stanje
    # (snapshot v .loopx/rollback/). false = stara semantika (zlomljena koda ostane).
    loopx_rollback_on_fail: bool = Field(default=True, alias="LOOPX_ROLLBACK_ON_FAIL")
    # ─── P2 — plan-time kontekst ──────────────────────────────────────────
    # true = načrtovalci (task_planner, team, run_autonomous) dobijo pretekle
    # lekcije + world-model napoved v prompt (core/plan_context.py).
    llm_plan_context: bool = Field(default=True, alias="LLM_PLAN_CONTEXT")

    def is_real_key_available(self) -> bool:
        return bool(
            self.deepseek_api_key 
            and self.deepseek_api_key != "sk-your-deepseek-api-key-here" 
            and self.deepseek_api_key.startswith("sk-")
        )

settings = SystemSettings()
