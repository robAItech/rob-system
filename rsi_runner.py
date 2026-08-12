import os
import sys
import subprocess
from bridges.llm_bridge import LLMBridge
from actions.enterprise_rsi_engine.enterprise_rsi_engine import RSIAnalyzer, RSIValidator

def run_rsi_loop(target_module_path: str, max_retries: int = 5):
    print("=" * 80)
    print(f"🔄 RSI CLOSED-LOOP ENGINE (5-STAGE SELF-HEALING) | ZAGANJANJE NAD: {target_module_path}")
    print("=" * 80)

    if not os.path.exists(target_module_path):
        print(f"❌ Napaka: Datoteka {target_module_path} ne obstaja.")
        return

    with open(target_module_path, "r", encoding="utf-8") as f:
        original_code = f.read()

    # 1. FAZA: ANALIZA
    print("\n🔍 [1/4] Analiza kode in iskanje tarč za optimizacijo...")
    analyzer = RSIAnalyzer()
    targets = analyzer.find_optimization_targets(original_code)
    
    if not targets:
        print("ℹ️ Ni najdenih funkcijskih tarč za optimizacijo.")
        return

    target_func_name = "_normalize_string" 
    print(f"⚡ Izbrana tarča za avtonomno optimizacijo: '{target_func_name}'")

    llm = LLMBridge()
    validator = RSIValidator()
    test_args = [{"val": "  TEST_STRING_123  "}]
    
    feedback = ""
    success = False
    optimized_code = ""

    # 5-STOPENJSKA SAMO-ZDRAVLJALNA ZANKA
    for attempt in range(1, max_retries + 1):
        print(f"\n🧠 [2/4] Generiranje kode - Poskus {attempt}/{max_retries}...")
        
        system_prompt = (
            "Si avtonomni RSI optimizator. Optimiziraj podano kodo. "
            "NE spreminjaj imena funkcije ali parametrov. Vrni SAMO kodo v ```python bloku."
        )
        
        prompt = f"""Optimiziraj kodo v {target_module_path}:

{original_code}

Zahteva:
- Optimiziraj funkcijo '{target_func_name}' (zagotovi točno enak vhodni/izhodni tip in logiko).
- OHRANI vso ostalo kodo, razrede in uvoze nedotaknjene.
{f'POZOR - PREJŠNJA NAPAKA IZ POSKUSA {attempt-1}: {feedback}' if feedback else ''}
"""

        optimized_code = llm.complete(prompt, system_prompt=system_prompt)
        if "```python" in optimized_code:
            optimized_code = optimized_code.split("```python")[1].split("```")[0].strip()
        elif "```" in optimized_code:
            optimized_code = optimized_code.split("```")[1].split("```")[0].strip()

        # 3. FAZA: DOKAZOVANJE EKVIVALENCE (BehaviorGuard)
        print(f"🛡️ [3/4] Validacija obnašanja (Poskus {attempt}/{max_retries})...")
        is_valid = validator.verify_behavioral_equivalence(
            original_func=original_code,
            optimized_func=optimized_code,
            func_name=target_func_name,
            test_args=test_args
        )

        if is_valid:
            print("📊 Rezultat ekvivalence: EKVIVALENTNO ✅")
            success = True
            break
        else:
            print(f"❌ Poskus {attempt}/{max_retries} ni bil ekvivalenten.")
            feedback = (
                f"Funkcija '{target_func_name}' ob izvedbi z test_args={test_args} "
                "ni vrnila ekvivalentnega rezultata ali pa je sprožila izjemo. "
                "Ponovno preveri signature funkcije ter vhodne/izhodne tipe."
            )

    if not success:
        print(f"\n🚨 Vseh {max_retries} poskusov samozdravljenja je bilo neuspešnih. Prekinjam brez sprememb.")
        print("=" * 80)
        return

    # 4. FAZA: ZAMENJAVA IN SINKRONIZACIJA S PYTEST
    print("\n🚀 [4/4] Zamenjava kode in zaganjanje Pytest preverjanja...")
    backup_path = target_module_path + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original_code)

    try:
        with open(target_module_path, "w", encoding="utf-8") as f:
            f.write(optimized_code)

        module_dir = os.path.dirname(target_module_path)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", module_dir],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("✅ PYTEST USPEŠEN! Nova optimizirana koda je prestala 100% testov.")
            print("🎉 Avtonomna RSI zanka je uspešno izvedla samozdravljenje, optimizacijo in zaklep kode.")
            if os.path.exists(backup_path):
                os.remove(backup_path)
        else:
            print("❌ PYTEST PADLE! Sprožam avtomatski ROLLBACK na originalno kodo...")
            with open(target_module_path, "w", encoding="utf-8") as f:
                f.write(original_code)
            print("🔄 Rollback uspešno izveden.")

    except Exception as e:
        print(f"💥 Sistemska napaka: {e}. Izvajam rollback...")
        with open(target_module_path, "w", encoding="utf-8") as f:
            f.write(original_code)

    print("\n" + "=" * 80)
    print("🏁 RSI ZANKA ZAKLJUČENA.")
    print("=" * 80)

if __name__ == "__main__":
    target = "actions/enterprise_core_utils/enterprise_core_utils.py"
    run_rsi_loop(target, max_retries=5)
