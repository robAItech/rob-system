from fastapi import FastAPI, HTTPException, status
from actions.enterprise_cache_layer.schemas import CacheSetRequest, CacheResponse, CacheStats
from actions.enterprise_cache_layer.enterprise_cache_layer import EnterpriseCacheLayer

app = FastAPI(title="Rob AI Studio - Enterprise Cache Layer API")
# Inicializacija predpomnilnika z max kapaciteto 500 elementov za testno okolje
cache = EnterpriseCacheLayer(max_size=500)

@app.post("/cache", status_code=status.HTTP_201_CREATED)
async def set_cache(request: CacheSetRequest):
    await cache.set(request.key, request.value, request.ttl_seconds)
    return {"status": "SET_SUCCESS", "key": request.key}

@app.get("/cache/{key}", response_model=CacheResponse)
async def get_cache(key: str):
    value = await cache.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found or expired")
    return CacheResponse(key=key, value=value, found=True)

@app.delete("/cache/{key}")
async def delete_cache(key: str):
    deleted = await cache.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "DELETE_SUCCESS", "key": key}

@app.get("/stats", response_model=CacheStats)
async def get_cache_stats():
    return await cache.get_stats()

@app.post("/flush")
async def flush_cache():
    await cache.flush()
    return {"status": "FLUSHED"}
