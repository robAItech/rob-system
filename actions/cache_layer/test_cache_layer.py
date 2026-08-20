import pytest
import asyncio
from fastapi.testclient import TestClient
from actions.cache_layer.main import app, cache
from actions.cache_layer.cache_layer import EnterpriseCacheLayer

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_cache():
    asyncio.run(cache.flush())

@pytest.mark.asyncio
async def test_lru_eviction_logic():
    small_cache = EnterpriseCacheLayer(max_size=3)
    
    # Napolni do meje
    await small_cache.set("A", 1)
    await small_cache.set("B", 2)
    await small_cache.set("C", 3)
    
    # Dostop do A (premakne A na konec LRU vrste)
    assert await small_cache.get("A") == 1
    
    # Dodaj D, kar mora evictati B (saj je A bil uporabljen)
    await small_cache.set("D", 4)
    
    assert await small_cache.get("B") is None
    assert await small_cache.get("A") == 1
    assert await small_cache.get("C") == 3
    assert await small_cache.get("D") == 4
    
    stats = await small_cache.get_stats()
    assert stats.evictions == 1

@pytest.mark.asyncio
async def test_ttl_expiration():
    c = EnterpriseCacheLayer()
    await c.set("temp", "data", ttl_seconds=0.1)
    
    assert await c.get("temp") == "data"
    await asyncio.sleep(0.15)
    assert await c.get("temp") is None

def test_fastapi_cache_endpoints():
    # 1. SET
    res_set = client.post("/cache", json={"key": "user_1", "value": {"name": "Rob"}, "ttl_seconds": 60})
    assert res_set.status_code == 201

    # 2. GET
    res_get = client.get("/cache/user_1")
    assert res_get.status_code == 200
    assert res_get.json()["value"]["name"] == "Rob"

    # 3. STATS
    res_stats = client.get("/stats")
    assert res_stats.status_code == 200
    assert res_stats.json()["hits"] == 1
    
    # 4. DELETE
    res_del = client.delete("/cache/user_1")
    assert res_del.status_code == 200
    
    # 5. GET Not Found
    res_get_fail = client.get("/cache/user_1")
    assert res_get_fail.status_code == 404
