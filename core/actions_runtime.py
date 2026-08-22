"""core/actions_runtime.py — actions/ kot enotna runtime app (korak 5).

Mount-a vseh 18 Action modulov (vsak `actions.<name>.main.app`) pod `/api/<name>/`
v eno FastAPI "control plane" app + middleware veriga: auth (AuthVault) →
rate-limit (RateLimiter) → audit (AuditTrail, objavi na DELJENI EventBus).
Moduli ostanejo nespremenjeni — katalog je zdaj tudi runtime.

Zagon:
  python -m core.actions_runtime --port 8788

Omejitve v1: WebSocket (nexus /ws) gre mimo verige (BaseHTTPMiddleware);
`/api/runtime/keys/issue` je public (izda ADMIN ključ) — enako kot samostojni
auth_vault; v produkciji zakleni za bootstrap-secret.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.actions_scan import list_action_modules
from actions.auth_vault.auth_vault import AuthVault
from actions.auth_vault.schemas import ApiKeyCreate, Role, TokenVerifyRequest
from actions.rate_limiter.rate_limiter import RateLimiter
from actions.rate_limiter.schemas import RateLimitConfig
from actions.audit_trail.audit_trail import AuditTrail
from actions.audit_trail.schemas import AuditRecordCreate
from actions.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)

_VALID_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _all_module_names(actions_dir: Path = Path("actions")) -> List[str]:
    return [d.name for d in list_action_modules(actions_dir)]


@dataclass
class RuntimeConfig:
    """Nastavitve runtime verige (auth/rate-limit/audit) in allowlista public poti."""
    auth_enabled: bool = True
    rate_limit_enabled: bool = True
    audit_enabled: bool = True
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)
    allowlist_exact: Tuple[str, ...] = ("/", "/favicon.ico")
    allowlist_prefixes: Tuple[str, ...] = ("/health", "/api/runtime", "/docs", "/redoc", "/openapi.json")
    allowlist_suffixes: Tuple[str, ...] = ("/health", "/docs", "/redoc", "/openapi.json", "/keys/issue", "/keys/verify")


class RuntimeServices:
    """Zasebne instance middleware verige (NE modul-level singletoni — brez kontaminacije)."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.bus = EventBus()                              # DELJEN EventBus
        self.auth = AuthVault()
        self.limiter = RateLimiter(config=config.rate_limit_config)
        self.audit = AuditTrail(event_bus=self.bus)
        self.mounted: Dict[str, FastAPI] = {}
        self.skipped: List[str] = []


def is_allowlisted(path: str, cfg: RuntimeConfig) -> bool:
    """Ali je pot public (preskoči celotno verigo)? Exact / prefix / suffix."""
    if path in cfg.allowlist_exact:
        return True
    if any(path.startswith(p) for p in cfg.allowlist_prefixes):
        return True
    if any(path.endswith(s) for s in cfg.allowlist_suffixes):
        return True
    return False


class ActionsRuntimeMiddleware(BaseHTTPMiddleware):
    """Auth → rate-limit → audit → call_next. Public/OPTIONS → mimo verige."""

    def __init__(self, app, services: RuntimeServices):
        super().__init__(app)
        self.services = services
        self.cfg = services.config

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or is_allowlisted(path, self.cfg):
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if self.cfg.auth_enabled:
            valid, code, _msg = self.services.auth.verify_api_key(key)
            if not valid:
                status = 403 if code == "FORBIDDEN" else 401
                return JSONResponse(status_code=status, content={"error": code})
        if self.cfg.rate_limit_enabled:
            rl_key = key or (request.client.host if request.client else "anon")
            allowed, _remaining, reset_in = self.services.limiter.is_allowed(rl_key)
            if not allowed:
                resp = JSONResponse(status_code=429,
                                    content={"error": "RATE_LIMIT_EXCEEDED", "reset_in_seconds": reset_in})
                resp.headers["Retry-After"] = str(max(1, int(reset_in)))
                return resp
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            if self.cfg.audit_enabled:
                try:
                    await self.services.audit.record_event(AuditRecordCreate(
                        actor=key[:16] or "anonymous", action=request.method, target=path,
                        payload={"status": status}))
                    self.services.bus.publish("requests",
                                              {"method": request.method, "path": path, "status": status})
                except Exception:
                    logger.warning("audit failed", exc_info=True)
        return response


def _load_module(name: str):
    """Import `actions.<name>.main`; toleranto (broken modul → None)."""
    if not _VALID_MODULE_RE.match(name):
        return None
    try:
        return importlib.import_module(f"actions.{name}.main")
    except Exception as e:
        logger.warning("actions.%s.main ni uvozen: %s", name, e)
        return None


def _app_from_module(mod):
    """Iz modula vzemi FastAPI `app`; currency_converter izvaža le `router` → synth-app."""
    if mod is None:
        return None
    app = getattr(mod, "app", None)
    if isinstance(app, FastAPI):
        return app
    router = getattr(mod, "router", None)
    if router is not None:
        synth = FastAPI(title=f"actions/{mod.__name__} (synth)")
        synth.include_router(router)
        return synth
    return None


def load_module_app(name: str) -> Optional[FastAPI]:
    """Javni loader enega modula (za teste/reuse)."""
    return _app_from_module(_load_module(name))


def _add_runtime_routes(app: FastAPI, services: RuntimeServices) -> None:
    @app.get("/")
    def root():
        return {"service": "Rob AI Studio — Actions Runtime",
                "modules": sorted(services.mounted), "skipped": services.skipped}

    @app.get("/api/runtime/health")
    def runtime_health():
        return {"status": "UP", "modules": len(services.mounted), "skipped": services.skipped}

    @app.get("/api/runtime/modules")
    def runtime_modules():
        return ([{"name": n, "mounted": True} for n in sorted(services.mounted)] +
                [{"name": n, "mounted": False} for n in services.skipped])

    @app.post("/api/runtime/keys/issue")
    def runtime_key_issue(body: ApiKeyCreate):
        resp = services.auth.generate_api_key(body)
        return {"client_id": resp.client_id, "api_key": resp.api_key,
                "role": resp.role.value, "created_at": resp.created_at.isoformat()}

    @app.post("/api/runtime/keys/verify")
    def runtime_key_verify(body: TokenVerifyRequest):
        valid, code, msg = services.auth.verify_api_key(body.api_key, body.required_role)
        return {"valid": valid, "code": code, "message": msg}


def build_runtime_app(modules: Optional[List[str]] = None,
                      config: Optional[RuntimeConfig] = None) -> FastAPI:
    """Enotna runtime app: middleware veriga + root rute + mount vseh modulov."""
    cfg = config or RuntimeConfig()
    services = RuntimeServices(cfg)
    app = FastAPI(title="Rob AI Studio — Actions Runtime", version="1.0.0")
    app.add_middleware(ActionsRuntimeMiddleware, services=services)
    _add_runtime_routes(app, services)
    names = modules if modules is not None else _all_module_names()
    names = [n for n in names if _VALID_MODULE_RE.match(n)]
    for name in names:
        sub = _app_from_module(_load_module(name))
        if sub is None:
            services.skipped.append(name)
            continue
        app.mount(f"/api/{name}", sub)
        services.mounted[name] = sub
    app.state.runtime_services = services
    return app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.actions_runtime",
                                description="Rob AI Studio — Actions Runtime (enotna app vseh 18 modulov).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8788)
    args = p.parse_args(argv)
    import uvicorn
    uvicorn.run(build_runtime_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
