"""identity_federation_router — jedro domenske logike: OAuth2/OIDC federacija.

Kot predlaga arhitekturna revizija (2026): ``auth_vault`` upravlja interno
avtentikacijo; ta modul doda **federativno** avtentikacijo z zunanjimi IdP
(Okta, Azure AD, Keycloak ...):
  - registracija IdP-jev (YAML-dict konfiguracija: issuer, token_url, jwks_uri),
  - PKCE authorization-code flow (code_challenge/code_verifier),
  - client-credentials in device-flow granti,
  - JWT validator (HS256 s stdlib; ``jwks_uri`` je opcijski zunanji vir),
  - standardiziran ``TokenContext`` izhod za api_gateway / event_bus.

Vse je čisto in deterministično (brez omrežja): token exchange simulira
izdajo JWT-ja, ki ga je mogoče neodvisno verificirati z ``validate_jwt``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── IdP + TokenContext ──────────────────────────────────────────────────────
@dataclass
class IdPConfig:
    """Konfiguracija zunanjega identitetnega ponudnika."""

    name: str
    issuer: str
    token_url: str
    client_id: str
    client_secret: str = ""
    jwks_uri: Optional[str] = None
    grant_types: List[str] = field(default_factory=lambda: ["authorization_code", "client_credentials", "device_flow"])
    audience: str = "rob-system"


@dataclass
class TokenContext:
    """Standardiziran avtentikacijski izhod (razumljiv api_gateway/event_bus)."""

    idp: str
    subject: str
    claims: Dict[str, Any]
    scopes: List[str]
    issued_at: float
    expires_at: float
    token_type: str = "Bearer"
    raw_token: str = ""


class FederationError(Exception):
    """Napaka v federativnem toku (neveljaven IdP, koda, token)."""


# ── JWT (HS256, stdlib) ─────────────────────────────────────────────────────
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_jwt(secret: str, claims: Dict[str, Any], ttl_seconds: float = 3600.0) -> str:
    """Ustvari HS256 JWT (za testno izdajo tokenov)."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = time.time()
    payload = {
        "iss": claims.get("iss", "rob-system"),
        "sub": claims.get("sub", ""),
        "aud": claims.get("aud", "rob-system"),
        "iat": int(now),
        "exp": int(now + ttl_seconds),
        **claims,
    }
    signing_input = f"{_b64url_encode(json.dumps(header).encode())}.{_b64url_encode(json.dumps(payload).encode())}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def parse_jwt(token: str) -> Dict[str, Any]:
    """Razstavi JWT na (header, payload) brez preverjanja podpisa."""
    parts = token.split(".")
    if len(parts) != 3:
        raise FederationError("invalid JWT structure")
    try:
        return json.loads(_b64url_decode(parts[1]))
    except Exception as exc:
        raise FederationError(f"invalid JWT payload: {exc}") from None


def validate_jwt(secret: str, token: str, issuer: Optional[str] = None) -> Dict[str, Any]:
    """Verificira HS256 JWT: podpis + exp + (opcijsko) issuer.

    Args:
        secret: deljeni HMAC skrivni ključ IdP-ja.
        token: JWT niz.
        issuer: pričakovani issuer; ``None`` = preskoči preverbo iss.

    Returns:
        payload dict.

    Raises:
        FederationError: če je podpis neveljaven, token potekel ali issuer ne drži.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise FederationError("invalid JWT structure")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    given = _b64url_decode(parts[2])
    if not hmac.compare_digest(expected, given):
        raise FederationError("invalid signature")
    payload = json.loads(_b64url_decode(parts[1]))
    if payload.get("exp", 0) < time.time():
        raise FederationError("token expired")
    if issuer and payload.get("iss") != issuer:
        raise FederationError(f"issuer mismatch: {payload.get('iss')!r} != {issuer!r}")
    return payload


# ── IdentityFederationRouter ────────────────────────────────────────────────
class IdentityFederationRouter:
    """Registracija IdP-jev, PKCE/CC/device tokovi, JWT validacija."""

    def __init__(self):
        self.idps: Dict[str, IdPConfig] = {}
        self._pending_codes: Dict[str, Dict[str, Any]] = {}
        self._pending_device: Dict[str, Dict[str, Any]] = {}

    # ── Registracija ────────────────────────────────────────────────────────
    def register_idp(self, config: IdPConfig) -> IdPConfig:
        """Registriraj IdP; vrne ga."""
        self.idps[config.name] = config
        return config

    def get_idp(self, name: str) -> IdPConfig:
        if name not in self.idps:
            raise FederationError(f"unknown IdP: {name}")
        return self.idps[name]

    # ── PKCE (authorization code) ───────────────────────────────────────────
    @staticmethod
    def new_pkce_pair() -> tuple[str, str]:
        """Ustvari (code_verifier, code_challenge = S256(verifier))."""
        verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = _b64url_encode(digest)
        return verifier, challenge

    def authorization_code_url(
        self,
        idp_name: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        """Zgradi avtorizacijski URL (OAuth2 authorization endpoint)."""
        idp = self.get_idp(idp_name)
        params = {
            "response_type": "code",
            "client_id": idp.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "openid profile email",
        }
        auth_endpoint = idp.token_url.replace("/token", "/authorize")
        return f"{auth_endpoint}?{urllib.parse.urlencode(params)}"

    def exchange_code(
        self,
        idp_name: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        scope: Optional[List[str]] = None,
    ) -> TokenContext:
        """Izmenjaj avtorizacijsko kodo za token (PKCE preverba challenge-ja)."""
        idp = self.get_idp(idp_name)
        pending = self._pending_codes.pop(code, None)
        if pending is None:
            raise FederationError("invalid or expired authorization code")
        # PKCE: preveri, da challenge izhaja iz verifierja.
        expected_challenge = _b64url_encode(hashlib.sha256(code_verifier.encode()).digest())
        if expected_challenge != pending.get("challenge"):
            raise FederationError("PKCE code_verifier does not match challenge")
        if pending.get("redirect_uri") != redirect_uri:
            raise FederationError("redirect_uri mismatch")
        return self._issue_token(idp, pending.get("sub", "federated-user"), scope)

    def store_code(self, idp_name: str, code: str, challenge: str, redirect_uri: str, sub: str) -> None:
        """Shrani avtorizacijsko kodo (simulacija avtorizacijskega endpointa)."""
        self._pending_codes[code] = {
            "idp": idp_name, "challenge": challenge, "redirect_uri": redirect_uri, "sub": sub,
        }

    # ── Client credentials ──────────────────────────────────────────────────
    def client_credentials_flow(self, idp_name: str, scope: Optional[List[str]] = None) -> TokenContext:
        """Machine-to-machine grant: izda token za client_id (brez človeka)."""
        idp = self.get_idp(idp_name)
        return self._issue_token(idp, f"client:{idp.client_id}", scope or ["api"])

    # ── Device flow ─────────────────────────────────────────────────────────
    def device_flow_start(self, idp_name: str, scope: Optional[List[str]] = None) -> Dict[str, Any]:
        """Začni device flow: vrni (device_code, user_code, verification_url)."""
        idp = self.get_idp(idp_name)
        device_code = secrets.token_urlsafe(16)
        user_code = secrets.token_hex(3).upper()[:8]
        self._pending_device[device_code] = {
            "idp": idp_name, "scope": scope or ["profile"], "approved": False,
        }
        return {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": idp.token_url.replace("/token", "/device"),
            "expires_in": 1800,
        }

    def device_flow_approve(self, device_code: str) -> bool:
        """Simulira človeško odobritev device flow-a."""
        if device_code not in self._pending_device:
            return False
        self._pending_device[device_code]["approved"] = True
        return True

    def device_flow_poll(self, idp_name: str, device_code: str) -> TokenContext:
        """Polling: če je odobren, izda token."""
        pending = self._pending_device.get(device_code)
        if pending is None:
            raise FederationError("invalid device code")
        if pending.get("idp") != idp_name:
            raise FederationError("device code IdP mismatch")
        if not pending.get("approved"):
            raise FederationError("authorization_pending")
        idp = self.get_idp(idp_name)
        self._pending_device.pop(device_code, None)
        return self._issue_token(idp, "device-user", pending.get("scope"))

    # ── Skupna izdaja + validacija ──────────────────────────────────────────
    def _issue_token(
        self, idp: IdPConfig, subject: str, scope: Optional[List[str]] = None
    ) -> TokenContext:
        now = time.time()
        claims = {
            "iss": idp.issuer,
            "sub": subject,
            "aud": idp.audience,
            "client_id": idp.client_id,
        }
        scopes = scope or ["openid"]
        raw = create_jwt(idp.client_secret or "dev-secret", {**claims, "scope": " ".join(scopes)})
        return TokenContext(
            idp=idp.name,
            subject=subject,
            claims=claims,
            scopes=scopes,
            issued_at=now,
            expires_at=now + 3600.0,
            raw_token=raw,
        )

    def validate(self, idp_name: str, token: str) -> Dict[str, Any]:
        """Verificira token: neveljaven podpis/exp → FederationError."""
        idp = self.get_idp(idp_name)
        return validate_jwt(idp.client_secret or "dev-secret", token, issuer=idp.issuer)


__all__ = [
    "IdPConfig",
    "TokenContext",
    "IdentityFederationRouter",
    "FederationError",
    "create_jwt",
    "parse_jwt",
    "validate_jwt",
]
