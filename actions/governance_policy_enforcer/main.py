"""FastAPI integration router for governance_policy_enforcer.

Endpoints (all responses are direct JSONResponse, 4xx/5xx handled explicitly):
  - POST /api/governance/policy    — replace the enforcer's rule set with a Policy,
  - POST /api/governance/evaluate  — evaluate role/action/resource/context -> Decision.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .governance_policy_enforcer import PolicyEnforcer
from .schemas import EvaluationRequest, Policy

router = APIRouter(prefix="/api/governance", tags=["governance"])

_enforcer = PolicyEnforcer()


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "detail": detail})


async def _read_json(request: Request):
    """Return (body_dict, None) or (None, JSONResponse) on invalid/non-object body."""
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return None, _error(422, "invalid_json", str(exc))
    except Exception as exc:  # noqa: BLE001 - non-JSON body
        return None, _error(422, "invalid_json", str(exc))
    if not isinstance(body, dict):
        return None, _error(422, "invalid_request", "request body must be a JSON object")
    return body, None


@router.post("/policy")
async def set_policy(request: Request) -> JSONResponse:
    body, err = await _read_json(request)
    if err is not None:
        return err
    try:
        policy = Policy(**body)
    except ValidationError as exc:
        return _error(422, "invalid_policy", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))
    _enforcer.set_policy(policy)
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "policy": policy.name, "rules": len(policy.rules)},
    )


@router.post("/evaluate")
async def evaluate(request: Request) -> JSONResponse:
    body, err = await _read_json(request)
    if err is not None:
        return err
    try:
        req = EvaluationRequest(**body)
    except ValidationError as exc:
        return _error(422, "invalid_request", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))
    try:
        decision = _enforcer.decide(req.role, req.action, req.resource, req.context)
    except Exception as exc:  # noqa: BLE001
        return _error(500, "internal_error", str(exc))
    return JSONResponse(status_code=200, content=decision.model_dump())