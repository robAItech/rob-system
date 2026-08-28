"""temp_conv -- temperature conversion module.

Public API:
    c_to_f(c)   Celsius -> Fahrenheit
    f_to_c(f)   Fahrenheit -> Celsius
    c_to_k(c)   Celsius -> Kelvin

plus the Pydantic V2 request/response schemas and the FastAPI router.
"""
from .main import router
from .schemas import ConversionRequest, ConversionResponse
from .temp_conv import c_to_f, c_to_k, f_to_c

__all__ = [
    "c_to_f",
    "f_to_c",
    "c_to_k",
    "ConversionRequest",
    "ConversionResponse",
    "router",
]