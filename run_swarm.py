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

def _process_items(items: list) -> list:
    """Obdela dane naloge skozi RSI zanko (mark running → run → mark done/failed).

    Deljeno jedro F3 (`--process-agenda`) in daemonovega `--item <id>` (P1), da se
    mark/run/mark logika ne podvaja. Vrne [(id, ok), ...].
    """
    from core.agenda import mark
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
    return results


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
        help="Ime ciljnega modula (ustvari se v actions/{target}/)"
    )
    parser.add_argument(
        "--directive",
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
    parser.add_argument(
        "--item",
        metavar="ID",
        help="Faza 3b: obdela ENO naročilo iz agende (po id) — kljub daemonu"
    )
    parser.add_argument(
        "--business",
        metavar="IDEJA",
        help="Faza 6: iz poslovne ideje izdela predlog (RSI Sales delovnik), ga presodi"
             " in vnese v glavno knjigo podjetja"
    )
    parser.add_argument(
        "--visual-qa",
        metavar="POT_ALI_URL",
        help="Neobvezen vizualni QA: Gemma 4 (Ollama) pogleda HTML sliko in vrne "
             "kakovostno poročilo UI. Za Hermes/dashboard ali ročno tarčo."
    )
    parser.add_argument(
        "--visual-qa-model",
        default=None,
        metavar="MODEL",
        help="Ollama model za vizualni QA (privzeto gemma4:latest). Npr. "
             "--visual-qa-model gemma4:31b za večji model."
    )

    args = parser.parse_args()

    # 1. Preverjanje in priprava okolja
    validate_environment()

    # Ročna validacija: --target/--directive sta potrebna le za redni/autonomous build
    # (ne za --process-agenda ali --item ali --business ali --visual-qa).
    if not (args.process_agenda or args.item or args.business or args.visual_qa):
        if not args.target or not args.directive:
            parser.error("--target in --directive sta obvezna (ali uporabi --process-agenda / --business / --visual-qa)")

    # Neobvezen vizualni QA (Gemma 4): pogleda HTML pot | url in izpiše poročilo.
    if args.visual_qa:
        try:
            from core.visual_qa import review as visual_review
            print(f"🔍 [VQA] Vizualni QA: {args.visual_qa} "
                  f"(model={args.visual_qa_model or 'privzeti'})")
            # model=None → uporabi modulov privzeti (ne posreduj, da ne preglasi default).
            if args.visual_qa_model:
                report = visual_review(args.visual_qa, model=args.visual_qa_model)
            else:
                report = visual_review(args.visual_qa)
            print("\n".join(f"  {k}: {v}" for k, v in report.items()))
        except Exception as e:
            print(f"[VQA] napaka pri vizualnem QA: {e}")
        return 0 if report.get("ok") is True else 1 if report.get("error") else 0

    # Faza 6 — poslovni delovnik (Sales): ideja → predlog → presodba → glavna knjiga.
    if args.business:
        from core.business import create_proposal, update
        idea = args.business
        target = _business_slug(idea)
        print(f"🤝 [F6] Poslovni delovnik za idejo: '{idea[:80]}'")
        # 1) Zabeleži idejo v knjigo.
        prop = create_proposal(idea, target=target)
        # 2) Izdelaj predlog (RSI markdown) skozi avtonomno zanko.
        builder_directive = (
            f"Izdelaj Markdown poslovni predlog v actions/{target}/ imenovan predlog.md. "
            f"Vsebuj naslov #, kratek opis ideje in glave tocke. Ideja: {idea}. Vsebina polna, ne stub."
        )
        ok = RobAIOrchestrator.run(target, builder_directive)
        # 3) Menedžer presoja (deterministično: predlog velja, če narobe RSI zelen).
        if ok:
            update(prop["id"], status="sent")
            print(f"✅ [F6] Predlog izdelan in poslan → stranka. Menedžer: ODOBREN.")
        else:
            update(prop["id"], status="proposal")
            print(f"❌ [F6] Predlog ni zelen — ostaja v stanju proposal.")
        sys.exit(0 if ok else 1)

    # Faza 3 — obdelaj čakalno vrsto (agenda) skozi RSI.
    if args.process_agenda:
        from core.agenda import pending
        print("🤖 [F3] Začenjam obdelavo čakalne vrste (agenda):")
        items = pending()
        if not items:
            print("  Agenda je prazna. Dodaj naloge (npr. prek dashboarda).")
            sys.exit(0)
        results = _process_items(items)
        # F3 repeat — ponavljajoča naročila znova postavimo v pending (schedule).
        from core.agenda import rearm_repeat
        rearmed = rearm_repeat()
        print(f"🤖 [F3] Agenda obdelana. Ponovno aktiviranih (repeat): {rearmed}.")
        sys.exit(0 if all(r[1] for r in results) else 1)

    # Faza 3b — obdelaj ENO naročilo iz agende (po id) — kljub daemonu (P1).
    # Daemon poganja naloge eno po eno skozi RSI zanko v subprocesu s trdim
    # timeoutom; `--item` omogoči, da se mark/run/mark logika ne duplicira.
    if args.item:
        from core.agenda import get
        print(f"🤖 [DAEMON] Obdelujem naročilo: {args.item}")
        item = get(args.item)
        if item is None:
            print(f"  ❌ naročilo {args.item} ne obstaja.")
            sys.exit(2)
        results = _process_items([item])
        from core.agenda import rearm_repeat
        rearmed = rearm_repeat()
        print(f"🤖 [DAEMON] Naročilo {args.item} obdelano. "
              f"Ponovno aktiviranih (repeat): {rearmed}.")
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


def _business_slug(idea: str) -> str:
    from re import sub as _sub
    words = idea.strip().split()
    s = _sub(r"[^a-zA-Z0-9_-]", "_", words[0].lower()) if words else "predlog"
    return s


if __name__ == "__main__":
    main()