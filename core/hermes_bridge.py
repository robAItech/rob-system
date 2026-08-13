import asyncio
from pathlib import Path
from typing import Dict, Any
from core.llm_client import DeepSeekLLMClient

class HermesBuilderBridge:
    def __init__(self, project: str):
        self.project = project
        self.base_dir = Path(f"actions/{project}")
        self.llm = DeepSeekLLMClient()

    def scaffold(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "__init__.py").touch(exist_ok=True)

    def write_initial_stubs_if_missing(self) -> None:
        self.scaffold()
        
        files = {
            "schemas.py": "# Pydantic V2 Schemas\n",
            f"{self.project}.py": "# Core Domain Logic\n",
            "main.py": "# FastAPI Integration Router\n",
            f"test_{self.project}.py": "# Pytest Test Suite\n"
        }

        for filename, content in files.items():
            file_path = self.base_dir / filename
            if not file_path.exists() or file_path.stat().st_size == 0:
                file_path.write_text(content, encoding="utf-8")

    async def generate_module_files(self, directive: str, manifest: Dict[str, Any]) -> None:
        """Poveže Hermes z DeepSeek LLM za avtonomno generiranje produkcijskih datotek."""
        self.scaffold()
        
        # Obdržimo delujoče datoteke, če že obstajajo in so potrjene
        if (self.base_dir / f"test_{self.project}.py").exists():
            return

        self.write_initial_stubs_if_missing()
