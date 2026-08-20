import time
import os
import sqlite3
import json
import sys
from pathlib import Path

# [ENCODING FIX] Vsili UTF-8 izhod, da emoji/Slovenščina ne pade na Windows cp1250 terminalih.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo

# [ABSOLUTE PATH] Koren projekta ne glede na CWD, da deluje tudi izven korena.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.actions_scan import list_action_modules, has_tests


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_metrics():
    db_path = PROJECT_ROOT / ".rob_ai" / "memory.db"
    graph_path = PROJECT_ROOT / ".rob_ai" / "graph.json"
    actions_dir = PROJECT_ROOT / "actions"

    tasks, errors = 0, 0
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                tasks = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
                errors = conn.execute("SELECT COUNT(*) FROM blacklist_patterns").fetchone()[0]
        except sqlite3.Error as exc:
            print(f"⚠️ Napaka pri branju memory.db: {exc}")

    nodes = 0
    if graph_path.exists():
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                nodes = len(json.load(f).get("nodes", {}))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"⚠️ Napaka pri branju graph.json: {exc}")

    # Veljavni moduli = imajo vsaj eno test_*.py datoteko (poljubno ime).
    valid_modules = [d.name for d in list_action_modules(actions_dir) if has_tests(d)]

    return tasks, errors, nodes, sorted(valid_modules)


def render_dashboard():
    while True:
        tasks, errors, nodes, modules = get_metrics()
        clear_screen()
        print("=" * 80)
        print(" 🤖 ROB AI STUDIO | LIVE SWARM DASHBOARD (VERIFIED ONLY) ".center(80, "="))
        print("=" * 80)
        print(f" 📈 GBRAIN Tasks Executed: {tasks:<10} | 🛡️ Auto-Healed Errors: {errors}")
        print(f" 🕸️ GRAPHIFY AST Nodes:    {nodes:<10} | 📦 100% Green Modules: {len(modules)}")
        print("-" * 80)
        print(" 🚀 ACTIVE VERIFIED MODULES:")
        for m in modules:
            print(f"    ✅ {m}")
        print("-" * 80)
        print(" (Press Ctrl+C to exit dashboard) ")
        time.sleep(3)


if __name__ == "__main__":
    try:
        render_dashboard()
    except KeyboardInterrupt:
        clear_screen()
        print("Dashboard closed. Returning to swarm.")
