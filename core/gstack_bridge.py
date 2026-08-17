from typing import Dict, Any, List

class GSTACKArchitectBridge:
    def __init__(self, blacklists: List[Dict[str, Any]], code_graph_context: str = ""):
        """code_graph_context: compact izvleček kode grafa (graphify render_context).

        Vključi se v architecture_blueprint.dependency_context — pripravi graf
        kontekst v spec manifestu za (morebitno) poznejšo LLM uporabo.
        """
        self.blacklists = blacklists
        self.code_graph_context = code_graph_context

    def generate_manifest(self, project: str, directive: str) -> Dict[str, Any]:
        known_errors = [b["error_pattern"] for b in self.blacklists]

        return {
            "project_name": project,
            "target_dir": f"actions/{project}",
            "architecture_blueprint": {
                "schemas": "Pydantic V2 s strogimi validatorji",
                "domain_logic": f"Cista async logic za: {directive}",
                "api_layer": "FastAPI z direct JSONResponse 4xx/5xx handlingom",
                "test_suite": "Pytest 100% pokritost s pokrivanjem robnih pogojev",
                "dependency_context": self.code_graph_context
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

    @staticmethod
    def render_spec_hint(manifest: Dict[str, Any]) -> str:
        """Spremeni spec manifest v kratek LLM-berljiv niz (arhitekturna usmeritev).

        To je tisto, kar GStack dejansko posreduje LLM-ju v prompt (P0):
        blueprint + known_blacklists postanejo vodilo izvedbe. Prazen izpusti
        prazne dele. Determininš, kratko (brez dolgega dump-a).
        """
        lines = []
        bp = manifest.get("architecture_blueprint") or {}
        if bp:
            lines.append("Arhitekturne smernice:")
            if bp.get("schemas"):
                lines.append(f"  - sheme: {bp['schemas']}")
            if bp.get("domain_logic"):
                lines.append(f"  - logika: {bp['domain_logic']}")
            if bp.get("api_layer"):
                lines.append(f"  - API: {bp['api_layer']}")
            if bp.get("test_suite"):
                lines.append(f"  - testi: {bp['test_suite']}")
        blacklists = manifest.get("known_blacklists") or []
        if blacklists:
            lines.append("Prepovedani/odstopljeni vzorci iz preteklih tekov:")
            for b in blacklists:
                lines.append(f"  - {b}")
        if not lines:
            return ""
        return "\n".join(lines)