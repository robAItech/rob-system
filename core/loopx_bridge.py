import subprocess
import sys
import json
from pathlib import Path
from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge

class LoopXEngineBridge:
    def __init__(self, project: str):
        self.project = project
        self.target_dir = Path(f"actions/{project}")
        self.registry_file = Path(".loopx/registry.json")
        self.gbrain = GBrainBridge()
        self.graphify = GraphifyBridge()

    def update_loopx_state(self, status: str, attempt: int) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "project": self.project,
            "status": status,
            "current_attempt": attempt,
            "max_attempts": 5
        }
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def execute_and_heal(self, directive: str) -> bool:
        max_retries = 5
        
        for attempt in range(1, max_retries + 1):
            self.update_loopx_state("RUNNING", attempt)
            
            # Poženi Pytest za ciljni modul
            env = {"PYTHONPATH": "."}
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", str(self.target_dir)],
                capture_output=True,
                text=True,
                env=dict(subprocess.os.environ, **env)
            )

            if result.returncode == 0:
                self.update_loopx_state("VERIFIED_GREEN", attempt)
                self.gbrain.record_task(self.project, directive, "VERIFIED GREEN", verified_code="Pass")
                self.graphify.build_code_graph()
                return True
            else:
                stderr = result.stderr or result.stdout
                self.gbrain.add_blacklist_pattern(self.project, "Pytest Failure", stderr[:300])
                
                # Če po 5 poskusih ne deluje, zapiši neuspeh
                if attempt == max_retries:
                    self.update_loopx_state("FAILED", attempt)
                    self.gbrain.record_task(self.project, directive, "FAILED", traceback=stderr)
                    return False
        return False