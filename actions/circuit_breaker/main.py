from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from actions.circuit_breaker.schemas import ExecutionRequest, CircuitStatusResponse, CircuitConfig
from actions.circuit_breaker.circuit_breaker import EnterpriseCircuitBreaker, CircuitBreakerOpenException

app = FastAPI(title="Rob AI Studio - Enterprise Circuit Breaker API")
breakers: dict[str, EnterpriseCircuitBreaker] = {}

def get_or_create_breaker(service_name: str) -> EnterpriseCircuitBreaker:
    if service_name not in breakers:
        breakers[service_name] = EnterpriseCircuitBreaker(
            service_name=service_name,
            config=CircuitConfig(failure_threshold=3, recovery_timeout=0.2, half_open_success_threshold=2)
        )
    return breakers[service_name]

@app.post("/execute", response_model=dict)
async def execute_action(request: ExecutionRequest):
    breaker = get_or_create_breaker(request.service_name)
    async def task():
        if request.should_fail:
            raise ValueError("Downstream error")
        return {"status": "SUCCESS", "payload": request.payload}

    try:
        res = await breaker.execute(task)
        return JSONResponse(status_code=status.HTTP_200_OK, content=res)
    except CircuitBreakerOpenException as cbe:
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"error": "CIRCUIT_OPEN", "detail": str(cbe)})
    except ValueError as ve:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": "TASK_FAILED", "detail": str(ve)})

@app.get("/status/{service_name}", response_model=CircuitStatusResponse)
async def get_status(service_name: str):
    if service_name not in breakers:
        raise HTTPException(status_code=404, detail="Service not found")
    return breakers[service_name].get_status()
