import sqlite3
import json
import importlib
from pathlib import Path

def inspect_system_modules():
    print("=" * 80)
    print("🔍 ROB AI STUDIO | MODUL-PO-MODUL SISTEMSKA DIAGNOSTIKA")
    print("=" * 80)

    # 1. Pregled kloniranih repozitorijev (repos/)
    print("\n📦 1. URADNI REPOZITORIJI (repos/):")
    repos = ["gbrain", "loopx", "gstack", "gbrain-evals", "hermes-agent", "graphify"]
    for repo in repos:
        p = Path(f"repos/{repo}")
        has_toml = (p / "pyproject.toml").exists()
        status = "✅ VELJAVEN (pyproject.toml prisoten)" if has_toml else "❌ MANJKA MANIFEST"
        print(f"  • {repo:<18}: {status}")

    # 2. Pregled core mostov (core/)
    print("\n🌉 2. INTEGRACIJSKO JEDRO (core/):")
    bridges = ["gbrain_bridge.py", "graphify_bridge.py", "gstack_bridge.py", "hermes_bridge.py", "loopx_bridge.py", "orchestrator.py"]
    for bridge in bridges:
        p = Path(f"core/{bridge}")
        status = "✅ DELUJE" if p.exists() else "❌ MANJKA"
        print(f"  • core/{bridge:<20}: {status}")

    # 3. Pregled ustvarjenih avtonomnih modulov (actions/)
    print("\n🚀 3. AVTONOMNI SHIPPED MODULI (actions/):")
    actions_dir = Path("actions")
    actions = [d for d in actions_dir.iterdir() if d.is_dir() and not d.name.startswith("__")]
    
    if not actions:
        print("  • Ni še generiranih modulov.")
    else:
        for act in actions:
            name = act.name
            req_files = ["schemas.py", f"{name}.py", "main.py", f"test_{name}.py"]
            missing = [f for f in req_files if not (act / f).exists()]
            if not missing:
                print(f"  • actions/{name:<25}: ✅ COMPLETE (Vseh 4/4 datotek prisotnih)")
            else:
                print(f"  • actions/{name:<25}: ❌ INCOMPLETE (Manjka: {missing})")

    # 4. GBRAIN Pregled Zgodovine
    print("\n🧠 4. GBRAIN MEMORY KERNEL DB (.rob_ai/memory.db):")
    db_path = Path(".rob_ai/memory.db")
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT task_id, project, status, timestamp FROM task_history ORDER BY task_id DESC LIMIT 5").fetchall()
            if rows:
                for r in rows:
                    print(f"  • [ID: {r['task_id']}] Modul: {r['project']:<25} | Status: {r['status']:<15} | Čas: {r['timestamp']}")
            else:
                print("  • Baza je prazna.")
    else:
        print("  • Baza ne obstaja.")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    inspect_system_modules()
