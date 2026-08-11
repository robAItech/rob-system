import subprocess
import sys
import json
import asyncio
from pathlib import Path
from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.llm_client import DeepSeekLLMClient

class LoopXEngineBridge:
    def __init__(self, project: str):
        self.project = project
        self.target_dir = Path(f"actions/{project}")
        self.gbrain = GBrainBridge()
        self.graphify = GraphifyBridge()
        self.llm = DeepSeekLLMClient()

    def execute_and_heal(self, directive: str) -> bool:
        max_retries = 5
        
        for attempt in range(1, max_retries + 1):
            env = {"PYTHONPATH": "."}
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", str(self.target_dir)],
                capture_output=True,
                text=True,
                env=dict(subprocess.os.environ, **env)
            )

            if result.returncode == 0:
                self.gbrain.record_task(self.project, directive, "VERIFIED GREEN", verified_code="Pass")
                self.graphify.build_code_graph()
                return True
            else:
                stderr = result.stderr or result.stdout
                self.gbrain.add_blacklist_pattern(self.project, f"Attempt {attempt} Pytest Failure", stderr[:300])
                
                # Zapis neuspeha ob izčrpanosti poskusov
                if attempt == max_retries:
                    self.gbrain.record_task(self.project, directive, "FAILED", traceback=stderr)
                    return False
        return False
