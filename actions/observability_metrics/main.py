import time
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from actions.observability_metrics.observability_metrics import EnterpriseMetricsRegistry
from actions.observability_metrics.schemas import MetricSnapshot

app = FastAPI(title="Rob AI Studio - Observability & Metrics")
registry = EnterpriseMetricsRegistry()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise e
    finally:
        duration = time.time() - start_time
        # Normaliziramo pot, da se izognemo eksploziji kardinalnosti (npr. /users/123 -> /users/{id})
        path = request.url.path
        await registry.record_request(request.method, path, status_code, duration)
        
    return response

@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Izpostavi metrike za Prometheus scraperje."""
    return await registry.generate_prometheus_metrics()

@app.get("/snapshot", response_model=MetricSnapshot)
async def get_system_snapshot():
    """Hitri pregled zdravja sistema v JSON obliki."""
    return await registry.get_snapshot()

@app.get("/health")
async def health_check():
    return {"status": "UP"}
