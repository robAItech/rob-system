import json
import sqlite3
from pathlib import Path

def inspect_flowchart():
    db_path = Path(".rob_ai/memory.db")
    graph_path = Path(".rob_ai/graph.json")

    gbrain_tasks = 0
    gbrain_blacklists = 0
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            gbrain_tasks = c.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
            gbrain_blacklists = c.execute("SELECT COUNT(*) FROM blacklist_patterns").fetchone()[0]

    graph_nodes = 0
    if graph_path.exists():
        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            graph_nodes = len(data.get("nodes", {}))

    actions = [d.name for d in Path("actions").iterdir() if d.is_dir() and not d.name.startswith("__")]

    # Uporaba raw formatted stringa (rf) prepreči DeprecationWarning pri backslashih
    flowchart = rf"""
================================================================================
          🤖 ROB AI STUDIO | HEADLESS SWARM FLOW CHART & LIVE STATE
================================================================================

                   [ CLI / Terminal Input ]
                              │
                              ▼
                +----------------------------+
                │   GSTACK-Architect         │  [STATUS: ACTIVE]
                │   (Task Decomposition)     │  Spec manifest: Ready
                +--------------+-------------+
                               │
       +-----------------------+-----------------------+
       │                                               │
       ▼                                               ▼
+--------------+                               +---------------+
│   GRAPHIFY   │ [STATUS: INDEXED]             │    GBRAIN     │ [STATUS: PERSISTED]
│ (Code Graph  │ Nodes: {graph_nodes:<23} │ (Memory DB &  │ Tasks: {gbrain_tasks:<15}
│ & Impact)    │                               │ Context Vault)│ Blacklists: {gbrain_blacklists:<10}
+------+-------+                               +-------+-------+
       │                                               │
       +-----------------------+-----------------------+
                               │
                               ▼
                +----------------------------+
                │   HERMES CODE BUILDER      │  [STATUS: ACTIVE]
                │ (Generates Code & Pytest)  │  Modules Shipped: {len(actions):<10}
                +--------------+-------------+
                               │
                               ▼ (Writes files to /actions/{{target}}/)
                +----------------------------+
                │   LOOPX ENGINE             │◄--+
                │ (Runs Pytest Trace Loop)   │   │ Self-Healing Zanka
                +--------------+-------------+   │ (Max 5 Retries)
                               │                 │
                      [ Pytest Passed? ]         │
                         /          \            │
                       No            Yes --------+
                       │
                       ▼
         +---------------------------+
         │ LoopX Auto-Patches Code   │
         │ (Fixes Syntax/Logic/Pyd)  │
         +---------------------------+
                       │
                       ▼
        +-----------------------------+
        │ GBRAIN Write & Consolidation│
        │  - Status: COMPLETED GREEN  │
        │  - Update graph.json        │
        +--------------+--------------+
                       │
                       ▼
            [ Terminal CLI Output: ]
       "✅ 100% VERIFIED GREEN & SHIPPED"
================================================================================
"""
    print(flowchart)

if __name__ == "__main__":
    inspect_flowchart()
