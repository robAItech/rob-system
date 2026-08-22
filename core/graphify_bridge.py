import ast
import json
from pathlib import Path
from typing import Dict, Any, List, Set

class GraphifyBridge:
    def __init__(self, root_dir: Path = Path(".")):
        self.root_dir = root_dir
        self.graph_file = Path(".rob_ai/graph.json")

    def build_code_graph(self) -> Dict[str, Any]:
        graph: Dict[str, Any] = {"nodes": {}, "edges": []}
        
        for py_file in self.root_dir.glob("**/*.py"):
            if any(p in py_file.parts for p in ["venv", ".pytest_cache", "repos", ".git", "legacy"]):
                continue

            rel_path = str(py_file.relative_to(self.root_dir))
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=rel_path)

                imports: List[str] = []
                functions: List[str] = []
                classes: List[str] = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module)
                    elif isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                    elif isinstance(node, ast.FunctionDef):
                        functions.append(node.name)

                graph["nodes"][rel_path] = {
                    "classes": classes,
                    "functions": functions,
                    "imports": imports
                }

                for imp in imports:
                    graph["edges"].append({
                        "source": rel_path,
                        "target": imp,
                        "relation": "IMPORTS"
                    })

            except Exception as e:
                graph["nodes"][rel_path] = {"error": str(e)}

        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.graph_file, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2)

        return graph

    def get_impacted_files(self, target_module: str) -> List[str]:
        if not self.graph_file.exists():
            self.build_code_graph()

        with open(self.graph_file, "r", encoding="utf-8") as f:
            graph = json.load(f)

        impacted = []
        for file_path, data in graph.get("nodes", {}).items():
            if target_module in data.get("imports", []):
                impacted.append(file_path)
        return impacted

    # ------------------------------------------------------------------ #
    #  Graph-kontekst za LLM (compact izvleček — ne full dump).
    # ------------------------------------------------------------------ #
    @staticmethod
    def _norm(path: str) -> str:
        """Normalizira separatorje → POSIX (/), da deluje na Windows (\\)."""
        return path.replace("\\", "/")

    @classmethod
    def _layer(cls, path: str) -> str:
        """Razvrsti datoteko v plast: core/ actions/ src/ ali koren."""
        p = cls._norm(path)
        for prefix in ("core/", "actions/", "src/"):
            if p.startswith(prefix):
                return prefix.rstrip("/")
        return "koren"

    def render_context(self, project: str, max_chars: int = 2000) -> str:
        """Compact, LLM-berljiv povzetek kode grafa (ne ~110 KB dump-a).

        LLM med RSI healingom vidi: per-plastni pregled (kje so moduli in
        njihova oblika) + vplive ciljnega `project`-a (fan-in / fan-out).
        Determininš, omejen na max_chars, tolerantna na manjkanje grafa
        (zgradi na zahtevo). Izhod se posreduje v RSI `_heal_once` prompt.
        """
        if not self.graph_file.exists():
            self.build_code_graph()

        try:
            with open(self.graph_file, "r", encoding="utf-8") as f:
                graph = json.load(f)
        except OSError:
            return ""

        nodes = graph.get("nodes", {})
        if not nodes:
            return "(graf je prazen)"

        def _in_project(rel: str) -> bool:
            """Ali je rel znotraj map akcijskega modula `project` (POSIX-normalizirano)."""
            p = self._norm(rel)
            return p == project or p.startswith(f"/{project}/") or p.startswith(f"{project}/")

        # 1) Per-plast compact pregled: path (fn N, cls M, imp K).
        by_layer: Dict[str, List[str]] = {}
        for rel, data in nodes.items():
            layer = self._layer(rel)
            by_layer.setdefault(layer, []).append(
                f"{self._norm(rel)} (fn {len(data.get('functions', []))}, "
                f"cls {len(data.get('classes', []))}, imp {len(data.get('imports', []))})"
            )

        lines = ["=== CODE GRAPH (compact) ==="]
        for layer in ("core", "actions", "src", "koren"):
            items = by_layer.get(layer)
            if items:
                lines.append(f"  [{layer}] " + "; ".join(items))

        # 2) Vplivi ciljnega modula: fan-out (kaj ta modul import-ira) + fan-in
        #    (katere datoteke uporabljajo ta modul).
        lines.append(f"  Vplivi za '{project}':")
        fan_out: Set[str] = set()
        for rel, data in nodes.items():
            if _in_project(rel):
                fan_out.update(data.get("imports", []))
        if fan_out:
            lines.append(f"    import-ira: {', '.join(sorted(fan_out)[:30])}")
        fan_in = [self._norm(rel) for rel, data in nodes.items()
                  if any(project in imp for imp in data.get("imports", []))]
        if fan_in:
            lines.append(f"    uporablja ga: {', '.join(sorted(fan_in)[:30])}")

        out = "\n".join(lines)
        if len(out) > max_chars:
            out = out[:max_chars] + f"\n…(+{len(out) - max_chars} znakov izpuščenih)"
        return out

    # ------------------------------------------------------------------ #
    #  Code-RAG: semantična pridobitev podobne kode (leksikalna, brez embeddingov).
    # ------------------------------------------------------------------ #
    @staticmethod
    def _tokenize(text: str) -> set:
        import re
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "your", "you",
            "are", "into", "not", "but", "have", "has", "was", "all", "any",
            "je", "in", "ki", "se", "da", "na", "za", "v", "z", "po", "iz",
        }
        return {t for t in re.findall(r"[a-zčšž0-9_]{2,}", (text or "").lower()) if t not in stop}

    def retrieve_relevant(self, query: str, limit: int = 3, max_chars_per_file: int = 800) -> List[Dict[str, Any]]:
        """Code-RAG: vrni top-N najbolj podobnih kodnih datotek za poizvedbo.

        Leksikalno prekrivanje žetonov (poceni nadomestek embedding-ov) — LLM
        med healingom dobi "podobno kodo" iz celega repa kot referenco.
        Preskoči test datoteke. Tolerantna na manjkajoče mape.
        """
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []
        scored: List[tuple] = []
        for sub in ("actions", "core"):
            d = self.root_dir / sub
            if not d.exists():
                continue
            for f in d.rglob("*.py"):
                if "test_" in f.name or f.name.endswith("_test.py"):
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                except OSError:
                    continue
                low = text.lower()
                overlap = sum(1 for t in q_tokens if t in low)
                if overlap > 0:
                    scored.append((overlap, f, text))
        scored.sort(key=lambda x: -x[0])
        out: List[Dict[str, Any]] = []
        for overlap, f, text in scored[:limit]:
            out.append({
                "path": self._norm(str(f)),
                "overlap": overlap,
                "snippet": text[:max_chars_per_file],
            })
        return out