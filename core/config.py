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
    # ─── P1 — avtonomni daemon (core/daemon.py) ───────────────────────────
    daemon_idle_seconds: int = Field(default=5, alias="DAEMON_IDLE_SECONDS")
    daemon_heartbeat_seconds: int = Field(default=30, alias="DAEMON_HEARTBEAT_SECONDS")
    daemon_proxy_retry_seconds: int = Field(default=60, alias="DAEMON_PROXY_RETRY_SECONDS")
    # Trdi timeout na nalogo (subprocess kill): prepreči, da obešena naloga
    # (npr. host-pytest brez timeouta) ustavi daemon za nedoločen čas. 0 = brez.
    daemon_task_timeout_seconds: int = Field(default=1800, alias="DAEMON_TASK_TIMEOUT_SECONDS")
    # Paralelni daemon: število sočasnih nalog (subprocesov run_swarm.py --item).
    # 1 = stara single-flight semantika; N>1 = N sočasnih buildov (distinct targets).
    # Velikost glede na HW — vsak build = LLM + Docker sandbox (~512 MB).
    daemon_workers: int = Field(default=2, alias="DAEMON_WORKERS")
    # ─── Učinkovitost RSI (A-B toggle-a) ─────────────────────────────────────
    # Adaptivno ciljanje: normalni buildi po prvi rdeči prevzamejo padli test →
    # heali tečejo samo `-k <test>` (hitro), končni poln gate lovi regresije.
    loopx_adaptive_targeting: bool = Field(default=True, alias="LOOPX_ADAPTIVE_TARGETING")
    # Caching graph/RAG per build: render_context + retrieve_relevant (whole-repo
    # scan) se izračunata enkrat na _heal_loop, ne na vsak heal.
    loopx_heal_prompt_cache: bool = Field(default=True, alias="LOOPX_HEAL_PROMPT_CACHE")
    # Periodični jobi (intervali v urah).
    daemon_consolidate_hours: int = Field(default=24, alias="DAEMON_CONSOLIDATE_HOURS")
    daemon_reflect_hours: int = Field(default=168, alias="DAEMON_REFLECT_HOURS")
    daemon_improve_hours: int = Field(default=168, alias="DAEMON_IMPROVE_HOURS")
    daemon_meta_check_hours: int = Field(default=168, alias="DAEMON_META_CHECK_HOURS")
    daemon_full_eval_hours: int = Field(default=168, alias="DAEMON_FULL_EVAL_HOURS")  # 0 = onemogoči
    daemon_goal_hours: int = Field(default=6, alias="DAEMON_GOAL_HOURS")
    # Goal tick: max število novo vvrženih nalog na cikel + flood guard (če je
    # v agendi že >= cap pending nalog, ne vvrzi novih).
    daemon_goal_max_enqueue: int = Field(default=2, alias="DAEMON_GOAL_MAX_ENQUEUE")
    daemon_goal_pending_cap: int = Field(default=3, alias="DAEMON_GOAL_PENDING_CAP")
    # Guard pred polnim diskom za težek full_eval.
    daemon_min_free_gb: float = Field(default=2.0, alias="DAEMON_MIN_FREE_GB")

    def is_real_key_available(self) -> bool:
        return bool(
            self.deepseek_api_key 
            and self.deepseek_api_key != "sk-your-deepseek-api-key-here" 
            and self.deepseek_api_key.startswith("sk-")
        )

settings = SystemSettings()
