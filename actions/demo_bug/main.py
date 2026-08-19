# FastAPI Integration Router
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from actions.demo_bug.demo_bug import divide
from actions.demo_bug.schemas import DivideRequest, DivideResponse

router = APIRouter(prefix="/demo_bug", tags=["demo_bug"])


@router.post("/divide", response_model=DivideResponse)
async def divide_endpoint(request: DivideRequest) -> DivideResponse:
    """API endpoint za deljenje dveh števil."""
    try:
        result = divide(request.a, request.b)
        return DivideResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Napaka pri deljenju: {str(e)}")