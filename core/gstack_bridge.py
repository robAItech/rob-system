from typing import Dict, Any, List

class GSTACKArchitectBridge:
    def __init__(self, blacklists: List[Dict[str, Any]]):
        self.blacklists = blacklists

    def generate_manifest(self, project: str, directive: str) -> Dict[str, Any]:
        return {
            "project_name": project,
            "target_dir": f"actions/{project}",
            "files": [
                f"actions/{project}/schemas.py",
                f"actions/{project}/{project}.py",
                f"actions/{project}/main.py",
                f"actions/{project}/test_{project}.py"
            ]
        }
