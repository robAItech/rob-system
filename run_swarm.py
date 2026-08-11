#!/usr/bin/env python3
import sys
import argparse
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import RobAIOrchestrator
from core.gbrain_bridge import GBrainBridge

def main() -> None:
    parser = argparse.ArgumentParser(description="ROB AI Studio Swarm Runner")
    parser.add_argument("--target", required=True, help="Target module name")
    parser.add_argument("--directive", required=True, help="Directive instruction prompt")
    parser.add_argument("--agent", default="GSTACK-Architect", help="Lead agent name")

    args = parser.parse_args()

    gbrain = GBrainBridge()
    gbrain._init_db()

    print("=" * 80)
    print("🤖 ROB AI STUDIO | AUTONOMOUS SWARM EXECUTION ENGINE")
    print("=" * 80)
    print(f"🎯 CILJNI MODUL   : {args.target}")
    print(f"👑 VODILNI AGENT  : {args.agent}")
    print(f"📜 DIREKTIVA      : {args.directive}")
    print("=" * 80 + "\n")

    start_time = time.time()
    success = RobAIOrchestrator.run(project=args.target, directive=args.directive)
    exec_time = round(time.time() - start_time, 2)

    if success:
        print("\n" + "=" * 80)
        print(f"✅ 100% VERIFIED GREEN & SHIPPED (Čas: {exec_time}s)")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print(f"❌ EXECUTION FAILED (Čas: {exec_time}s)")
        print("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()
