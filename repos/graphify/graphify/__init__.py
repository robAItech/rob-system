"""Graphify — indeksacija in analiza grafa odvisnosti za Rob AI Studio.

Zgradi strukturni graf (``nodes``/``edges``) iz Python izvorne mape.
Neodvisna, lahka implementacija brez zunanjih odvisnosti; polnopravna
AST-scan (s podrobnostmi) živi v ``core.graphify_bridge.GraphifyBridge``.

Javni vmesniki:
- ``build_graph`` — vrne dict s ``nodes`` in ``edges``.
- ``GraphIndex`` — majhen pomožni razred za poizvedbe po grafu.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

__version__ = "0.1.0"
__all__ = ["build_graph", "GraphIndex"]


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def build_graph(root: str = ".") -> Dict[str, object]:
    """Zgradi graf odvisnosti over Python datotek pod ``root``.

    Returns:
        Dict z ``nodes`` (file -> {imports, funcs, classes}) in ``edges``.
    """
    base = Path(root)
    nodes: Dict[str, object] = {}
    edges: List[Dict[str, str]] = []

    for py_file in base.rglob("*.py"):
        if any(part in ("venv", ".pytest_cache", ".git", "node_modules") for part in py_file.parts):
            continue
        rel = str(py_file.relative_to(base))
        source = _safe_read(py_file)
        if not source:
            continue
        tree = ast.parse(source)
        imports: List[str] = []
        funcs: List[str] = []
        classes: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    imports += [a.name for a in node.names]
                elif node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                funcs.append(node.name)
        for imp in imports:
            edges.append({"source": rel, "target": imp})
        nodes[rel] = {"imports": imports, "functions": funcs, "classes": classes}

    return {"nodes": nodes, "edges": edges}


class GraphIndex:
    """Poizvedbe po grafu odvisnosti."""

    def __init__(self, root: str = ".") -> None:
        self.graph = build_graph(root)

    def nodes_from(self) -> Set[str]:
        return set(self.graph["nodes"].keys())

    def importers_of(self, module: str) -> List[str]:
        return [e["source"] for e in self.graph["edges"] if e["target"] == module]
