import os
import shutil
import json
from fastapi.testclient import TestClient
from actions.enterprise_rsi_engine.main import app

def run_verification():
    client = TestClient(app)
    print("=" * 80)
    print("🧪 PREVERJANJE DELOVANJA ENTERPRISE_RSI_ENGINE V ŽIVO")
    print("=" * 80)

    # 1. TEST AST ANALIZATORJA
    print("\n🔍 [1/2] Testiranje endpointa POST /rsi/analyze...")
    sample_code = """
def slow_function(x):
    res = 0
    for i in range(x):
        for j in range(x):
            res += i * j
    return res

class HeavyWorker:
    def process(self, data):
        return [x * 2 for x in data]
"""
    res_analyze = client.post("/rsi/analyze", json={"module_code": sample_code})
    print(f"Status: {res_analyze.status_code}")
    print("Rezultat AST analize:")
    print(json.dumps(res_analyze.json(), indent=2))

    # 2. TEST AVTONOMNE ZANKE IN ROLLBACKA
    print("\n🔄 [2/2] Testiranje endpointa POST /rsi/run-loop na začasnem modulu...")
    
    # Ustvarimo lažni modul v tisočih
    test_dir = "actions/temp_test_module"
    os.makedirs(test_dir, exist_ok=True)
    
    module_file = os.path.join(test_dir, "temp_module.py")
    test_file = os.path.join(test_dir, "test_temp_module.py")
    init_file = os.path.join(test_dir, "__init__.py")

    with open(init_file, "w") as f:
        f.write("")

    with open(module_file, "w") as f:
        f.write("def add(a, b):\n    return a + b\n")

    with open(test_file, "w") as f:
        f.write("from .temp_module import add\ndef test_add():\n    assert add(2, 3) == 5\n")

    try:
        print(f"  ↳ Zaganjam RSI zanko nad: {module_file}")
        res_loop = client.post("/rsi/run-loop", json={
            "target_module_path": module_file,
            "max_retries": 2
        })
        print(f"Status: {res_loop.status_code}")
        print("Rezultat RSI Zanke:")
        print(json.dumps(res_loop.json(), indent=2))

    finally:
        # Počistimo začasni modul
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    print("\n" + "=" * 80)
    print("✅ PREVIZUS ZAKLJUČEN.")
    print("=" * 80)

if __name__ == "__main__":
    run_verification()
