import sys
import os
from pathlib import Path

# [ENCODING FIX] Vsili UTF-8 izhod, da emoji/Slovenščina ne pade na Windows cp1250 terminalih.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo (npr. nekateri embded/downstream stdout objekti)

# [ABSOLUTE BULLETPROOF PATH RESOLUTION]
# Ne glede na to, od kod je skripta zagnana, vsili koren projekta v sys.path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import subprocess
import json
from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.llm_client import DeepSeekLLMClient

async def perform_self_check():
    print("=" * 80)
    print("🤖 ROB AI STUDIO | AUTONOMOUS SYSTEM SELF-CHECK & ARCHITECTURAL REVIEW")
    print("=" * 80)
    
    # 1. RUN CORE TESTS
    print("\n🔄 [1/4] Izvajam sistemske teste (Pytest)...")
    env = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT))
    pytest_res = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "tests/"],
        capture_output=True,
        text=True,
        env=env
    )
    test_status = "✅ 100% GREEN" if pytest_res.returncode == 0 else "❌ NAPAKE ZAZNANE"
    print(f"Status testov: {test_status}")

    # 2. GATHER GBRAIN TELEMETRY
    print("\n🧠 [2/4] Zbiram telemetrijo iz GBRAIN spomina...")
    gbrain = GBrainBridge()
    blacklists = gbrain.get_blacklists("ALL") if hasattr(gbrain, 'get_blacklists') else []
    
    # 3. GATHER GRAPHIFY MAP
    print("\n🕸️ [3/4] Analiziram graf odvisnosti (GRAPHIFY)...")
    graphify = GraphifyBridge()
    graph = graphify.build_code_graph()
    total_nodes = len(graph.get("nodes", {}))
    
    # Preštej shranjene module
    actions_dir = PROJECT_ROOT / "actions"
    actions = [d.name for d in actions_dir.iterdir() if d.is_dir() and not d.name.startswith("__")]
    
    # 4. LLM ARCHITECT REVIEW
    print("\n✨ [4/4] Pridobivam predloge za nadgradnjo od DeepSeek AI Arhitekta...")
    llm = DeepSeekLLMClient()
    
    telemetry_report = f"""
    ROB AI STUDIO - CURRENT STATE:
    - Test Suite Status: {test_status}
    - Total AST Nodes: {total_nodes}
    - Deployed Actions (Modules): {', '.join(actions)}
    - Recorded Auto-Healed Errors (Blacklists): {len(blacklists)}
    """

    system_prompt = (
        "Ti si 'Master System Architect' za avtonomni sistem Rob AI Studio. "
        "Preglej podano telemetrijo in obstoječe module. Generiraj kratek, udaren in izjemno tehničen "
        "markdown dokument (v slovenščini), ki vsebuje:\n"
        "1. Oceno trenutne arhitekture.\n"
        "2. Predloge za arhitekturne refaktorizacije (kako zmanjšati redundanco).\n"
        "3. 3 konkretne predloge za povsem nove module (Actions), ki manjkajo za popoln Enterprise API ekosistem."
    )
    
    try:
        proposal = await llm.generate_completion(prompt=telemetry_report, system_prompt=system_prompt, use_coder_model=True)
        print("\n" + "=" * 80)
        print("📋 AI ARHITEKT - PREDLOGI IN NADGRADNJE:")
        print("=" * 80)
        print(proposal)
        print("=" * 80)
    except Exception as e:
        print(f"\n⚠️ Napaka pri komunikaciji z LLM: {e}")
        print("Preverite .env datoteko in DEEPSEEK_API_KEY.")

if __name__ == "__main__":
    asyncio.run(perform_self_check())
