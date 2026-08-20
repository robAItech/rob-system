# FastAPI Integration Router
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from decimal import Decimal, InvalidOperation

from .schemas import ConversionRequest, ConversionResponse, ErrorResponse
from .currency_converter import (
    convert_currency,
    UnsupportedCurrencyError,
    InvalidAmountError,
    EXCHANGE_RATES,
)

router = APIRouter(prefix="/api/v1", tags=["currency-converter"])


@router.post(
    "/convert",
    response_model=ConversionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def convert(request: ConversionRequest):
    """
    Convert an amount from one currency to another.
    
    Args:
        request: ConversionRequest with amount, from_currency, to_currency.
    
    Returns:
        ConversionResponse with converted amount and rate.
    
    Raises:
        HTTPException: 400 for invalid currency/amount, 500 for unexpected errors.
    """
    try:
        # Perform conversion
        converted = await convert_currency(
            amount=request.amount,
            from_currency=request.from_currency,
            to_currency=request.to_currency,
        )
        
        # Calculate rate
        rate = EXCHANGE_RATES[request.to_currency] / EXCHANGE_RATES[request.from_currency]
        
        return ConversionResponse(
            amount=request.amount,
            from_currency=request.from_currency,
            to_currency=request.to_currency,
            converted_amount=float(converted),
            rate=float(rate),
        )
    
    except UnsupportedCurrencyError as e:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="Unsupported currency", detail=str(e)).model_dump(),
        )
    
    except InvalidAmountError as e:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="Invalid amount", detail=str(e)).model_dump(),
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error="Internal server error", detail=str(e)).model_dump(),
        )