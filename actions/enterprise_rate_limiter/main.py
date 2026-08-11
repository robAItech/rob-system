from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from actions.enterprise_rate_limiter.schemas import RateLimitRequest, RateLimitResponse, RateLimitConfig
from actions.enterprise_rate_limiter.enterprise_rate_limiter import EnterpriseRateLimiter

app = FastAPI(title="Rob AI Studio - Enterprise Rate Limiter API")

limiter = EnterpriseRateLimiter(config=RateLimitConfig(max_requests=3, window_seconds=0.5))

@app.post("/check", response_model=RateLimitResponse)
async def check_rate_limit(request: RateLimitRequest):
    allowed, remaining, reset_in = limiter.is_allowed(request.key)
    
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "key": request.key,
                "allowed": False,
                "remaining": 0,
                "reset_in_seconds": reset_in,
                "error": "RATE_LIMIT_EXCEEDED"
            }
        )
    
    return RateLimitResponse(
        key=request.key,
        allowed=True,
        remaining=remaining,
        reset_in_seconds=0.0
    )
