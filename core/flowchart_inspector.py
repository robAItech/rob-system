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

    # Live-loop parametri (privzeto 5 poskusov; tuning jih lahko preglasi).
    max_attempts = 5
    if db_path.exists():
        try:
            from core.tuning import Tuning
            max_attempts = int(Tuning(db_path).get("max_attempts", 5))
        except Exception:
            pass  # ob napaki ostanemo pri privzetem številu poskusov

    # actions/ = realizirani moduli (vsaj ena .py; `_`/prazne mape izvzete).
    # To NI nujno "shipped", zato poštena oznaka "modulov s kodo".
    actions = sorted(
        d.name for d in Path("actions").iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and list(d.glob("*.py"))
    )

    # Uporaba raw formatted stringa (rf) prepreči DeprecationWarning pri backslashih.
    # Diagram = DEJANSKA veriga iz core/orchestrator._phase + core/loopx_bridge._heal_loop:
    #   GBRAIN → GRAPHIFY → GSTACK → HERMES → LOOPX (verify↔heal, do max_attempts).
    flowchart = rf"""
================================================================================
          🤖 ROB AI STUDIO | HEADLESS SWARM FLOW CHART & LIVE STATE
================================================================================

            [ CLI | --process-agenda | --item (daemon) | --business ]
                                │
                                ▼
        +------------------------------------------+
        │  ORCHESTRATOR (RobAIOrchestrator)        │
        │  dispatch po kind: python · modify ·     │
        │  team · fork · plan · autonomous ·       │
        │  surgical (fix_loop)                     │
        +-------------------+----------------------+
                            │   (vsak RSI fazni tek)
                            ▼
        +------------------------------------------+
        │  GBRAIN — Context Vault                  │
        │  kontekst + blacklisti (naučene napake)  │
        +-------------------+----------------------+
                            │   blacklisti kot usmeritev
                            ▼
        +------------------------------------------+
        │  GRAPHIFY — AST kodni graf               │
        │  build_code_graph + dependency kontekst  │
        +-------------------+----------------------+
                            │   graf-kontekst v manifest
                            ▼
        +------------------------------------------+
        │  GSTACK-Architect                        │
        │  generate_manifest → spec_hint           │
        +-------------------+----------------------+
                            │
                            ▼
        +------------------------------------------+
        │  HERMES — stubi, SAMO če manjkajo        │
        │  (kodo in teste generira LoopX, ne Hermes)│
        +-------------------+----------------------+
                            │
                            ▼
   ┌───────────────────────────────────────────────────────┐
   │  LOOPX ENGINE — RSI heal zanka                        │
   │   ponavljaj (max {max_attempts}):                      │
   │                                                       │
   │    (1) verify: Ruff F821 → pytest  (Docker | host)    │
   │         │                                             │
   │         ├── zelen → izhod iz zanke (spodaj ▼)         │
   │         │                                             │
   │         └── rdeč → (2) LLM heal + učenje              │
   │                    (Test-Locking, 3× ista → FAIL)     │
   │                    └──── retry ────▶ ponovi (1)       │
   └─────────┬─────────────────────────────────────────────┘
             │  zelen (exit zanke)
             ▼
        +------------------------------------------+
        │  GBRAIN Write & Consolidation            │
        │  record_task VERIFIED GREEN +            │
        │  graphify rebuild (svež graf)            │
        +-------------------+----------------------+
                            │
                            ▼
        [ Terminal CLI Output: ]
   "✅ 100% VERIFIED GREEN & SHIPPED"

   Ob FAIL: auto-rollback (.loopx/rollback) + post-run review →
             C2 fix naloga v agendo (daemon pobere) →
             CLI "❌ EXECUTION FAILED"

  ── LIVE STATE ─────────────────────────────────────────────
  GRAPHIFY : {graph_nodes} vozlišč  (.rob_ai/graph.json)
  GBRAIN   : {gbrain_tasks} taskov · {gbrain_blacklists} blacklistov  (memory.db)
  actions/ : {len(actions)} modulov s kodo  (≈ realiziranih, ne nujno shipped)
  LOOPX    : max {max_attempts} poskusov na tek  (tuning: max_attempts)
================================================================================
"""
    print(flowchart)

if __name__ == "__main__":
    inspect_flowchart()
