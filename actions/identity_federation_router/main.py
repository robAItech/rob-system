"""identity_federation_router — FastAPI aplikacija (API plast).

Expose: registracija IdP-jev, PKCE authorize URL, token exchange (CC/AC),
device flow, JWT validacija + health. Exporta ``app`` — v runtime pod
``/api/identity_federation_router/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.identity_federation_router.federation import (
    FederationError,
    IdPConfig,
    IdentityFederationRouter,
)
from actions.identity_federation_router.schemas import (
    AuthCodeUrlRequest,
    DeviceFlowStartRequest,
    IdpRegisterRequest,
    JwtValidateRequest,
    TokenContextResponse,
    TokenExchangeRequest,
)

app = FastAPI(title="Rob AI Studio - Identity Federation Router", version="1.0.0")
router = IdentityFederationRouter()


def _token_out(ctx) -> TokenContextResponse:
    return TokenContextResponse(
        idp=ctx.idp,
        subject=ctx.subject,
        scopes=ctx.scopes,
        token_type=ctx.token_type,
        expires_at=ctx.expires_at,
        claims=ctx.claims,
        raw_token=ctx.raw_token,
    )


@app.post("/idps")
async def register_idp(body: IdpRegisterRequest) -> JSONResponse:
    """Registriraj zunanji IdP."""
    cfg = router.register_idp(
        IdPConfig(
            name=body.name,
            issuer=body.issuer,
            token_url=body.token_url,
            client_id=body.client_id,
            client_secret=body.client_secret,
            jwks_uri=body.jwks_uri,
        )
    )
    return JSONResponse({"name": cfg.name, "issuer": cfg.issuer, "grant_types": cfg.grant_types})


@app.get("/idps")
async def list_idps() -> JSONResponse:
    """Seznam registriranih IdP-jev (brez secret-a)."""
    return JSONResponse(
        [{"name": c.name, "issuer": c.issuer, "jwks_uri": c.jwks_uri} for c in router.idps.values()]
    )


@app.post("/authorize-url")
async def authorize_url(body: AuthCodeUrlRequest) -> JSONResponse:
    """Zgradi PKCE avtorizacijski URL za IdP."""
    try:
        url = router.authorization_code_url(
            body.idp, body.redirect_uri, body.state, body.code_challenge
        )
    except FederationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse({"authorization_url": url})


@app.post("/token", response_model=TokenContextResponse)
async def token_exchange(body: TokenExchangeRequest) -> JSONResponse:
    """Authorization-code ali client-credentials grant → TokenContext."""
    try:
        if body.grant_type == "client_credentials":
            ctx = router.client_credentials_flow(body.idp, body.scope)
        else:
            if not body.code or not body.code_verifier or not body.redirect_uri:
                raise FederationError("authorization_code zahteva code, code_verifier, redirect_uri")
            ctx = router.exchange_code(
                body.idp, body.code, body.code_verifier, body.redirect_uri, body.scope
            )
        return JSONResponse(_token_out(ctx).model_dump())
    except FederationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/device-flow/start")
async def device_flow_start(body: DeviceFlowStartRequest) -> JSONResponse:
    """Začni device flow: vrne device_code + user_code + verification_uri."""
    try:
        return JSONResponse(router.device_flow_start(body.idp, body.scope))
    except FederationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/validate-jwt")
async def validate_jwt(body: JwtValidateRequest) -> JSONResponse:
    """Verificira JWT (HS256 + exp + iss)."""
    try:
        payload = router.validate(body.idp, body.token)
        return JSONResponse({"valid": True, "payload": payload})
    except FederationError as exc:
        return JSONResponse({"valid": False, "reason": str(exc)})


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "idps": list(router.idps.keys())}
