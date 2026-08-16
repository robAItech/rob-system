#!/usr/bin/env python3
"""
ROB AI STUDIO - Headless Swarm Engine
Glavna vstopna točka za avtonomno izvajanje brez človeškega posredovanja.
"""

import sys
import os
import argparse
import time
from pathlib import Path

# Vsili UTF-8 izhod tudi, ko je stdout preusmerjen na pipe (ne terminal).
# Brez tega emoji/šumniki v izpisu crash-on Windows cp1250 (UnicodeEncodeError).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo (nekateri okolji)

# Zagotovi, da je koren projekta vedno na PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import RobAIOrchestrator
from core.gbrain_bridge import GBrainBridge

def validate_environment() -> None:
    """Preveri celovitost sistema pred zagonom swarm zanke."""
    required_dirs = [
        PROJECT_ROOT / "core",
        PROJECT_ROOT / "repos",
        PROJECT_ROOT / ".rob_ai"
    ]
    for r_dir in required_dirs:
        if not r_dir.exists():
            r_dir.mkdir(parents=True, exist_ok=True)

    # Preveri prisotnost SQLite baze
    db_file = PROJECT_ROOT / ".rob_ai" / "memory.db"
    if not db_file.exists():
        gbrain = GBrainBridge(db_path=db_file)
        gbrain._init_db()

def print_banner(target: str, directive: str, agent: str) -> None:
    """Izpiše sistemsko glavo izvajanja."""
    print("=" * 80)
    print("🤖 ROB AI STUDIO | AUTONOMOUS SWARM EXECUTION ENGINE")
    print("=" * 80)
    print(f"🎯 CILJNI MODUL   : {target}")
    print(f"👑 VODILNI AGENT  : {agent}")
    print(f"📜 DIREKTIVA      : {directive}")
    print(f"📂 KOREN PROJEKTA : {PROJECT_ROOT}")
    print("=" * 80 + "\n")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rob AI Studio Headless Swarm Runner",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--target", 
        required=True, 
        help="Ime ciljnega modula (ustvari se v actions/{target}/)"
    )
    parser.add_argument(
        "--directive", 
        required=True, 
        help="Celotna navodila in zahteve za avtonomno izvedbo ('Boil the ocean')"
    )
    parser.add_argument(
        "--agent", 
        default="GSTACK-Architect", 
        help="Začetni vodilni agent (privzeto: GSTACK-Architect)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Največje število poskusov samoozdravitve zanke LoopX (privzeto: 5)"
    )
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Faza 2: avtonomni delovnik — nalogo razdeli na spec + implement (več RSI faz)"
    )
    parser.add_argument(
        "--process-agenda",
        action="store_true",
        help="Faza 3: obdela vso čakalno vrsto naročil (agenda) skozi RSI zanko"
    )

    args = parser.parse_args()

    # 1. Preverjanje in priprava okolja
    validate_environment()

    # Faza 3 — obdelaj čakalno vrsto (agenda) skozi RSI.
    if args.process_agenda:
        from core.agenda import pending, mark
        print("🤖 [F3] Začenjam obdelavo čakalne vrste (agenda):")
        items = pending()
        if not items:
            print("  Agenda je prazna. Dodaj naloge (npr. prek dashboarda).")
            sys.exit(0)
        results = []
        for it in items:
            ok = False
            print(f"  ▶ obdelujem: {it['id']} · {it['goal'][:60]}")
            mark(it["id"], "running")
            try:
                if it.get("kind") == "autonomous":
                    ok = RobAIOrchestrator.run_autonomous(it["target"], it["goal"])
                else:
                    ok = RobAIOrchestrator.run(it["target"], it["goal"])
                mark(it["id"], "done" if ok else "failed")
            except Exception as e:
                print(f"  ❌ napaka: {e}")
                mark(it["id"], "failed")
            results.append((it["id"], ok))
        # Če repeat — ponastavimo v pending (enostaven schedule: enkrat oddane ponovljive).
        print("🤖 [F3] Agenda obdelana.")
        sys.exit(0 if all(r[1] for r in results) else 1)

    # 2. Prikaz sistemskega statusa
    print_banner(target=args.target, directive=args.directive, agent=args.agent)

    # 3. Zagon orkestracije preko spominskega in verifikacijskega jedra
    start_time = time.time()
    
    try:
        from core.audit import record as audit_record
        if args.autonomous:
            success = RobAIOrchestrator.run_autonomous(
                project=args.target, goal=args.directive
            )
        else:
            success = RobAIOrchestrator.run(
                project=args.target,
                directive=args.directive
            )
        # F5 — revizija v živi poti (trajni sledljivi dnevnik).
        audit_record(
            event="build", project=args.target,
            status="ok" if success else "failed",
            detail=args.directive[:400],
            agent=args.agent,
        )

        execution_time = round(time.time() - start_time, 2)

        if success:
            print("\n" + "=" * 80)
            print(f"✅ 100% VERIFIED GREEN & SHIPPED (Čas izvajanja: {execution_time}s)")
            print("=" * 80)
            sys.exit(0)
        else:
            print("\n" + "=" * 80)
            print(f"❌ EXECUTION FAILED | LoopX ni dosegel potrditve (Čas: {execution_time}s)")
            print("=" * 80)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️ Izvajanje prekinjeno s strani uporabnika.")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Kritična sistemska napaka pri izvaanju: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()