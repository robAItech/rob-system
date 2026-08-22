"""core/actions_graph.py — realni odvisnostni robovi med action moduli (korak 5).

AST-sken `actions/*/` za dejanske importe (`from actions.X import ...`). Nadomesti
trdo-kodirane `GRAPH_EDGES` robove v server.ts — dashboard graf pokaže REALNE
odvisnosti, ne aspirativnih. Ker katalog dejansko nima veliko medmodulskih importov
(trenutno 2), `all_edges()` doda še MIDDLEWARE verigo runtime-a (auth→rate-limit→
audit→event-bus) iz `core/actions_runtime.py`.

Uporaba (JSON na stdout za server.ts):
  python -m core.actions_graph [--root .]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.actions_scan import list_action_modules


def _action_imports_from_file(path: Path) -> List[str]:
    """Iz .py datoteke izlušči importe drugih action modulov (`actions.X` → `X`)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("actions."):
                    parts = alias.name.split(".")
                    if len(parts) >= 2:
                        out.append(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("actions."):
                parts = node.module.split(".")
                if len(parts) >= 2:
                    out.append(parts[1])
    return out


def build_action_edges(root_dir: Path = Path(".")) -> List[Dict[str, str]]:
    """Realni robovi med action moduli iz dejanskih importov (relation=IMPORTS).

    Preskoči `test_*.py` (testni importi → lažni robovi), `__init__.py` (re-exporti)
    in self-importe. Deterministično (set dedup + sort).
    """
    actions_dir = root_dir / "actions"
    names = {d.name for d in list_action_modules(actions_dir)}
    edges = set()
    for mod_dir in list_action_modules(actions_dir):
        for py in mod_dir.glob("*.py"):
            if py.name.startswith("test_") or py.name == "__init__.py":
                continue
            for target in _action_imports_from_file(py):
                if target in names and target != mod_dir.name:
                    edges.add((mod_dir.name, target))
    return [{"source": s, "target": t, "relation": "IMPORTS"} for s, t in sorted(edges)]


def build_runtime_chain_edges() -> List[Dict[str, str]]:
    """Robovi middleware verige runtime-a (core/actions_runtime.py)."""
    chain = ["auth_vault", "rate_limiter", "audit_trail", "event_bus"]
    return [{"source": chain[i], "target": chain[i + 1], "relation": "MIDDLEWARE"}
            for i in range(len(chain) - 1)]


def all_edges(root_dir: Path = Path(".")) -> List[Dict[str, str]]:
    """Realni importi + middleware veriga runtime-a."""
    return build_action_edges(root_dir) + build_runtime_chain_edges()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.actions_graph",
                                description="Realni odvisnostni robovi action modulov (JSON na stdout).")
    p.add_argument("--root", default=".", help="repo koren")
    args = p.parse_args(argv)
    print(json.dumps(all_edges(Path(args.root)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
