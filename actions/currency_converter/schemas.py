# Pydantic V2 Schemas
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ConversionRequest(BaseModel):
    """Request schema for currency conversion."""
    model_config = ConfigDict(extra="forbid")
    
    amount: float = Field(..., gt=0, description="Amount to convert (must be positive)")
    from_currency: str = Field(..., min_length=3, max_length=3, description="Source currency code (e.g., USD)")
    to_currency: str = Field(..., min_length=3, max_length=3, description="Target currency code (e.g., EUR)")
    
    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be positive")
        if not isinstance(v, (int, float)):
            raise ValueError("Amount must be a number")
        return float(v)
    
    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("Currency code must contain only letters")
        return v.upper()


class ConversionResponse(BaseModel):
    """Response schema for currency conversion."""
    model_config = ConfigDict(extra="forbid")
    
    amount: float = Field(..., description="Original amount")
    from_currency: str = Field(..., description="Source currency code")
    to_currency: str = Field(..., description="Target currency code")
    converted_amount: float = Field(..., description="Converted amount")
    rate: float = Field(..., description="Exchange rate used")
    
    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        return v.upper()


class ErrorResponse(BaseModel):
    """Error response schema."""
    model_config = ConfigDict(extra="forbid")
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")