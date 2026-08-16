from pathlib import Path

class HermesBuilderBridge:
    def __init__(self, project: str):
        self.project = project
        self.base_dir = Path(f"actions/{project}")

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