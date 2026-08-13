import ast
import json
from pathlib import Path
from typing import Dict, Any

class GraphifyBridge:
    def __init__(self, root_dir: Path = Path(".")):
        self.root_dir = root_dir
        self.graph_file = Path(".rob_ai/graph.json")

    def build_code_graph(self) -> Dict[str, Any]:
        graph: Dict[str, Any] = {"nodes": {}, "edges": []}
        for py_file in self.root_dir.glob("**/*.py"):
            if any(p in py_file.parts for p in ["venv", ".pytest_cache", "repos", ".git"]):
                continue
            rel_path = str(py_file.relative_to(self.root_dir))
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=rel_path)
                imports, functions, classes = [], [], []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                    elif isinstance(node, ast.FunctionDef):
                        functions.append(node.name)
                graph["nodes"][rel_path] = {"classes": classes, "functions": functions, "imports": imports}
            except Exception as e:
                graph["nodes"][rel_path] = {"error": str(e)}

        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.graph_file, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2)
        return graph
