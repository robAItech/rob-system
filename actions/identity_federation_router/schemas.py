"""identity_federation_router — Pydantic sheme (API plast)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class IdpRegisterRequest(BaseModel):
    """Vhod za POST /idps — registracija zunanjega IdP-ja."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    issuer: str = Field(..., min_length=1)
    token_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(default="", description="HMAC secret za JWT validacijo.")
    jwks_uri: Optional[str] = Field(default=None)


class AuthCodeUrlRequest(BaseModel):
    """Vhod za GET /authorize-url — zgradi PKCE avtorizacijski URL."""

    idp: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    code_challenge: str = Field(..., min_length=1)


class TokenExchangeRequest(BaseModel):
    """Vhod za POST /token — authorization_code ali client_credentials."""

    idp: str = Field(..., min_length=1)
    grant_type: str = Field(default="client_credentials", pattern=r"^(authorization_code|client_credentials)$")
    code: Optional[str] = Field(default=None)
    code_verifier: Optional[str] = Field(default=None)
    redirect_uri: Optional[str] = Field(default=None)
    scope: Optional[List[str]] = Field(default=None)


class TokenContextResponse(BaseModel):
    """Standardiziran izhod: TokenContext."""

    idp: str
    subject: str
    scopes: List[str]
    token_type: str
    expires_at: float
    claims: Dict[str, Any]
    raw_token: str


class DeviceFlowStartRequest(BaseModel):
    idp: str = Field(..., min_length=1)
    scope: Optional[List[str]] = Field(default=None)


class JwtValidateRequest(BaseModel):
    idp: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)
