from typing import Dict, Any, List

class GSTACKArchitectBridge:
    def __init__(self, blacklists: List[Dict[str, Any]]):
        self.blacklists = blacklists

    def generate_manifest(self, project: str, directive: str) -> Dict[str, Any]:
        known_errors = [b["error_pattern"] for b in self.blacklists]
        
        return {
            "project_name": project,
            "target_dir": f"actions/{project}",
            "architecture_blueprint": {
                "schemas": "Pydantic V2 s strogimi validatorji",
                "domain_logic": f"Cista async logic za: {directive}",
                "api_layer": "FastAPI z direct JSONResponse 4xx/5xx handlingom",
                "test_suite": "Pytest 100% pokritost s pokrivanjem robnih pogojev"
            },
            "files": [
                f"actions/{project}/schemas.py",
                f"actions/{project}/{project}.py",
                f"actions/{project}/main.py",
                f"actions/{project}/test_{project}.py"
            ],
            "known_blacklists": known_errors,
            "boil_the_ocean_mandate": True
        }