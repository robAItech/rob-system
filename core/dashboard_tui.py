import time
import os
import sqlite3
import json
from pathlib import Path

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_metrics():
    db_path = Path(".rob_ai/memory.db")
    graph_path = Path(".rob_ai/graph.json")
    actions_dir = Path("actions")
    
    tasks, errors = 0, 0
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                tasks = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
                errors = conn.execute("SELECT COUNT(*) FROM blacklist_patterns").fetchone()[0]
        except:
            pass
            
    nodes = 0
    if graph_path.exists():
        try:
            with open(graph_path, "r") as f:
                nodes = len(json.load(f).get("nodes", {}))
        except:
            pass
            
    modules = [d.name for d in actions_dir.iterdir() if d.is_dir() and not d.name.startswith("__")] if actions_dir.exists() else []
    
    return tasks, errors, nodes, modules

def render_dashboard():
    while True:
        tasks, errors, nodes, modules = get_metrics()
        clear_screen()
        print("=" * 80)
        print(" 🤖 ROB AI STUDIO | LIVE SWARM DASHBOARD ".center(80, "="))
        print("=" * 80)
        print(f" 📈 GBRAIN Tasks Executed: {tasks:<10} | 🛡️ Auto-Healed Errors: {errors}")
        print(f" 🕸️ GRAPHIFY AST Nodes:    {nodes:<10} | 📦 Shipped Modules:   {len(modules)}")
        print("-" * 80)
        print(" 🚀 ACTIVE MODULES IN PRODUCTION:")
        for m in sorted(modules):
            print(f"    ✅ {m}")
        print("-" * 80)
        print(" (Press Ctrl+C to exit dashboard) ")
        time.sleep(2)

if __name__ == "__main__":
    try:
        render_dashboard()
    except KeyboardInterrupt:
        clear_screen()
        print("Dashboard closed. Returning to swarm.")
