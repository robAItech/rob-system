import json
from fastapi.testclient import TestClient
from actions.enterprise_rsi_engine.main import app

def run_demo():
    client = TestClient(app)
    
    print("=" * 80)
    print("🚀 ROB AI STUDIO | RSI-LITE LIVE DEMONSTRATION")
    print("=" * 80)

    # ---------------------------------------------------------
    # 1. FAZA: ANALIZA
    # ---------------------------------------------------------
    print("\n🔍 [1/2] Zaganja se RSI Analyzer...")
    
    bloated_code = """
def calculate_metrics(data):
    total = 0
    count = 0
    for i in data:
        total += i
    for i in data:
        count += 1
    avg = total / count if count > 0 else 0
    
    variance_sum = 0
    for i in data:
        variance_sum += (i - avg) ** 2
    variance = variance_sum / count if count > 0 else 0
    
    return {"avg": avg, "variance": variance}
"""
    analyze_payload = {"module_code": bloated_code}
    
    response = client.post("/rsi/analyze", json=analyze_payload)
    print("📥 Odgovor Analyzerja:")
    print(json.dumps(response.json(), indent=2))

    # ---------------------------------------------------------
    # 2. FAZA: VALIDACIJA (Kwargs uskladitev)
    # ---------------------------------------------------------
    print("\n⚡ [2/2] Zaganja se RSI Validator (Dokazovanje ekvivalence)...")
    
    original_func = """
def sort_numbers(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
"""
    
    optimized_func = """
def sort_numbers(arr):
    return sorted(arr)
"""
    
    # POPRAVEK: Podano kot slovar (kwargs), ki ustreza definiciji Pydantic modela
    test_args = [{"arr": [5, 2, 9, 1, 5, 6, 12, -3, 8]}]

    validate_payload = {
        "original_func": original_func,
        "optimized_func": optimized_func,
        "func_name": "sort_numbers",
        "test_args": test_args
    }

    response = client.post("/rsi/validate", json=validate_payload)
    print("📥 Odgovor Validatorja:")
    print(json.dumps(response.json(), indent=2))
    
    print("\n" + "=" * 80)
    if response.status_code == 200 and response.json().get("is_equivalent"):
        print("✅ USPEH: RSI Engine je uspešno detektiral slabo kodo in dokazal,")
        print("da optimizirana verzija deluje popolnoma identično kot originalna!")
    else:
        print("❌ NAPAKA: Ekvivalenca ni bila potrjena.")
    print("=" * 80)

if __name__ == "__main__":
    run_demo()
