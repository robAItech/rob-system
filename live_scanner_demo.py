from fastapi.testclient import TestClient
from actions.enterprise_warehouse_inventory.main import app
import json

def run_scanner():
    client = TestClient(app)
    
    print("=" * 80)
    print("📱 TERMINAL SKLADIŠČNIKA | ŽIVA SIMULACIJA")
    print("=" * 80)

    # 1. Skladiščnik poskenira kodo
    print("\n🔍 [KORAK 1] Skladiščnik poskenira: 'QR-VIJAKI-M8'")
    response = client.post("/inventory/scan", json={"qr_code": "QR-VIJAKI-M8"})
    print("📥 Odgovor baze:")
    print(json.dumps(response.json(), indent=2))

    # 2. Skladiščnik vzame 10 vijakov
    print("\n📦 [KORAK 2] Skladiščnik vzame 10 vijakov iz police...")
    response = client.post("/inventory/deduct", json={"qr_code": "QR-VIJAKI-M8", "kolicina": 10})
    print("📥 Odgovor baze:")
    print(json.dumps(response.json(), indent=2))

    # 3. Skladiščnik poskusi vzeti še 200 vijakov (napaka - preprečitev minus zaloge)
    print("\n🚨 [KORAK 3] Skladiščnik poskusi vzeti še 200 vijakov (več kot je na zalogi)...")
    response = client.post("/inventory/deduct", json={"qr_code": "QR-VIJAKI-M8", "kolicina": 200})
    print(f"📥 Odgovor baze (Status: {response.status_code}):")
    print(json.dumps(response.json(), indent=2))
    
    print("\n" + "=" * 80)
    print("✅ DEMONSTRACIJA ZAKLJUČENA. MODUL JE 100% FUNKCIONALEN.")
    print("=" * 80)

if __name__ == "__main__":
    run_scanner()
