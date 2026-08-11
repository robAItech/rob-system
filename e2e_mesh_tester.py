import asyncio
import httpx
import sys
import subprocess
import time
from httpx import AsyncClient

async def wait_for_services(ports):
    """Dinamično počaka, dokler storitve ne odgovorijo (do 15s max)."""
    async with AsyncClient(timeout=2.0) as client:
        for port in ports:
            ready = False
            for _ in range(15):
                try:
                    await client.get(f"http://127.0.0.1:{port}/docs")
                    ready = True
                    break
                except:
                    await asyncio.sleep(1)
            if not ready:
                raise Exception(f"Service na portu {port} se ni uspel zagnati.")

async def run_e2e_validation():
    print("=" * 80)
    print("🌍 ROB AI STUDIO | ENTERPRISE MICROSERVICES MESH VALIDATION")
    print("=" * 80)
    
    print("🚀 Zaganjam grozd mikroservisov v ozadju...")
    services = [
        ("actions.enterprise_api_gateway.main:app", 8000),
        ("actions.enterprise_auth_vault.main:app", 8001),
        ("actions.enterprise_cache_layer.main:app", 8005),
        ("actions.enterprise_observability_metrics.main:app", 9090)
    ]
    
    processes = []
    for module, port in services:
        p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        processes.append(p)
        
    print("⏳ Čakam na inicializacijo storitev...")
    try:
        await wait_for_services([8000, 8001, 8005, 9090])
        print("✅ Vse storitve uspešno zagnane.")

        async with AsyncClient(base_url="http://127.0.0.1:8000", timeout=5.0) as client:
            # KORAK 1
            print("\n🔑 [KORAK 1] Pridobivanje API Ključa (Gateway -> Auth Vault)...")
            res_auth = await client.post("/api/auth/keys/issue", json={"client_id": "e2e_tester", "role": "ADMIN", "ttl_days": 1})
            assert res_auth.status_code == 200, f"Auth fail: {res_auth.status_code} - {res_auth.text}"
            api_key = res_auth.json()["api_key"]
            print(f"  ✅ Ključ pridobljen: {api_key[:15]}...")

            # KORAK 2
            print("🛡️ [KORAK 2] Testiranje API Gateway Middleware zaščite...")
            res_fail = await client.get("/api/cache/stats")
            assert res_fail.status_code == 401, f"Expected 401, got {res_fail.status_code}"
            print("  ✅ Zaščita deluje (401 Unauthorized ujet na Gateway-u).")

            # KORAK 3
            print("💾 [KORAK 3] Zapis v porazdeljen Cache preko Gatewaya...")
            headers = {"Authorization": f"Bearer {api_key}"}
            res_cache_set = await client.post("/api/cache/cache", json={"key": "e2e_state", "value": "green", "ttl_seconds": 60}, headers=headers)
            assert res_cache_set.status_code == 201, f"Cache set fail: {res_cache_set.status_code} - {res_cache_set.text}"
            print("  ✅ Podatki uspešno zapisani v in-memory Cache.")

            # KORAK 4
            print("📈 [KORAK 4] Preverjanje Observability registra...")
            async with AsyncClient(base_url="http://127.0.0.1:9090", timeout=5.0) as metrics_client:
                res_metrics = await metrics_client.get("/snapshot")
                assert res_metrics.status_code == 200
                data = res_metrics.json()
                assert data["total_requests"] > 0, "No metrics captured"
                print(f"  ✅ Sistem beleži telemetrijo. (Total Requests: {data['total_requests']}, Avg Latency: {data['avg_latency_ms']}ms)")

        print("\n" + "=" * 80)
        print("🏆 HOLY SHIT, THAT'S DONE. E2E MESH VALIDATION COMPLETE.")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ E2E MESH VALIDATION FAILED: {str(e)}")
    finally:
        print("\n🧹 Ugašam procese v ozadju...")
        for p in processes:
            p.terminate()
            p.wait()

if __name__ == "__main__":
    asyncio.run(run_e2e_validation())
