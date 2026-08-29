"""Pytest suite for governance_policy_enforcer (RBAC/ABAC, schemas, FastAPI)."""

import json

import pytest
from pydantic import ValidationError

# Import with fallback so the suite runs regardless of how actions/ is mounted.
try:
    from governance_policy_enforcer.governance_policy_enforcer import (
        PolicyEnforcer,
        Role,
        Rule,
        build_policy_from_roles,
    )
    from governance_policy_enforcer import schemas
    from governance_policy_enforcer.schemas import (
        Context,
        ContextCondition,
        Decision,
        EvaluationRequest,
        Policy,
        PolicyRule,
    )
except ImportError:  # pragma: no cover - repo-root import fallback
    from actions.governance_policy_enforcer.governance_policy_enforcer import (
        PolicyEnforcer,
        Role,
        Rule,
        build_policy_from_roles,
    )
    from actions.governance_policy_enforcer import schemas
    from actions.governance_policy_enforcer.schemas import (
        Context,
        ContextCondition,
        Decision,
        EvaluationRequest,
        Policy,
        PolicyRule,
    )

try:
    from governance_policy_enforcer import main as api
except ImportError:  # pragma: no cover - repo-root import fallback
    from actions.governance_policy_enforcer import main as api


# ---------------------------------------------------------------------------
# Schemas: Context / ContextCondition / PolicyRule / Policy / Decision
# ---------------------------------------------------------------------------

class TestContextSchema:
    def test_valid_context(self):
        ctx = Context(ip="10.0.0.5", time="09:30", attributes={"dept": "eng"})
        assert ctx.ip == "10.0.0.5"
        assert ctx.time == "09:30"
        assert ctx.attributes == {"dept": "eng"}

    def test_ipv6_context(self):
        assert Context(ip="::1").ip == "::1"

    def test_invalid_ip_rejected(self):
        with pytest.raises(ValidationError):
            Context(ip="999.1.1.1")

    def test_invalid_time_hour_rejected(self):
        with pytest.raises(ValidationError):
            Context(time="25:00")

    def test_invalid_time_minute_rejected(self):
        with pytest.raises(ValidationError):
            Context(time="12:99")

    def test_time_must_be_padded(self):
        with pytest.raises(ValidationError):
            Context(time="9:30")

    def test_roundtrip(self):
        ctx = Context(ip="10.0.0.5", time="09:30", attributes={"dept": "eng"})
        restored = schemas.Context.model_validate(ctx.model_dump())
        assert restored == ctx


class TestContextConditionSchema:
    def test_valid_condition(self):
        cond = ContextCondition(
            allowed_ips=["10.0.0.0/8", "192.168.1.1"],
            start_time="09:00",
            end_time="17:00",
            required_attributes={"clearance": "top"},
        )
        assert cond.allowed_ips == ["10.0.0.0/8", "192.168.1.1"]

    def test_invalid_ip_rejected(self):
        with pytest.raises(ValidationError):
            ContextCondition(allowed_ips=["nope"])

    def test_invalid_time_rejected(self):
        with pytest.raises(ValidationError):
            ContextCondition(start_time="24:00")

    def test_roundtrip(self):
        cond = ContextCondition(allowed_ips=["10.0.0.0/8"], start_time="09:00", end_time="17:00")
        restored = ContextCondition(**cond.model_dump())
        assert restored == cond


class TestPolicySchema:
    def test_valid_policy_roundtrip(self):
        policy = Policy(
            name="main",
            rules=[
                PolicyRule(role="admin", action="read", resource="docs"),
                PolicyRule(role="admin", action="delete", resource="docs", effect="deny"),
            ],
        )
        restored = Policy(**policy.model_dump())
        assert restored == policy

    def test_bad_effect_rejected(self):
        with pytest.raises(ValidationError):
            PolicyRule(role="a", action="b", resource="c", effect="maybe")

    def test_empty_role_rejected(self):
        with pytest.raises(ValidationError):
            PolicyRule(role="", action="b", resource="c")

    def test_empty_policy_name_rejected(self):
        with pytest.raises(ValidationError):
            Policy(name="", rules=[])

    def test_decision_roundtrip(self):
        decision = Decision(allowed=True, role="admin", action="read", resource="docs", reason="ok")
        restored = Decision(**decision.model_dump())
        assert restored == decision

    def test_evaluation_request_roundtrip(self):
        req = EvaluationRequest(role="admin", action="read", resource="docs")
        restored = EvaluationRequest(**req.model_dump())
        assert restored == req

    def test_evaluation_request_missing_role_rejected(self):
        with pytest.raises(ValidationError):
            EvaluationRequest(action="read", resource="docs")

    def test_evaluation_request_invalid_context_rejected(self):
        with pytest.raises(ValidationError):
            EvaluationRequest(role="admin", action="read", resource="docs", context={"ip": "nope"})


# ---------------------------------------------------------------------------
# ContextCondition.evaluate: IP / time window / ABAC attributes
# ---------------------------------------------------------------------------

class TestContextConditionEvaluate:
    def test_empty_condition_matches_without_context(self):
        assert ContextCondition().evaluate(None) is True

    def test_condition_requires_context(self):
        assert ContextCondition(allowed_ips=["10.0.0.1"]).evaluate(None) is False

    def test_ip_exact_match(self):
        cond = ContextCondition(allowed_ips=["10.0.0.1"])
        assert cond.evaluate(Context(ip="10.0.0.1")) is True
        assert cond.evaluate(Context(ip="10.0.0.2")) is False
        assert cond.evaluate(Context()) is False

    def test_ip_cidr_match(self):
        cond = ContextCondition(allowed_ips=["10.0.0.0/8"])
        assert cond.evaluate(Context(ip="10.20.30.40")) is True
        assert cond.evaluate(Context(ip="11.0.0.1")) is False

    def test_time_window_inclusive(self):
        cond = ContextCondition(start_time="09:00", end_time="17:00")
        assert cond.evaluate(Context(time="09:00")) is True
        assert cond.evaluate(Context(time="12:00")) is True
        assert cond.evaluate(Context(time="17:00")) is True
        assert cond.evaluate(Context(time="08:59")) is False
        assert cond.evaluate(Context(time="17:01")) is False
        assert cond.evaluate(Context()) is False

    def test_time_window_crosses_midnight(self):
        cond = ContextCondition(start_time="22:00", end_time="06:00")
        assert cond.evaluate(Context(time="23:30")) is True
        assert cond.evaluate(Context(time="05:00")) is True
        assert cond.evaluate(Context(time="12:00")) is False

    def test_abac_attributes(self):
        cond = ContextCondition(required_attributes={"dept": "eng"})
        assert cond.evaluate(Context(attributes={"dept": "eng"})) is True
        assert cond.evaluate(Context(attributes={"dept": "sales"})) is False
        assert cond.evaluate(Context()) is False

    def test_combined_condition_all_required(self):
        cond = ContextCondition(
            allowed_ips=["10.0.0.0/8"],
            start_time="09:00",
            end_time="17:00",
            required_attributes={"dept": "eng"},
        )
        ok = Context(ip="10.1.1.1", time="12:00", attributes={"dept": "eng"})
        assert cond.evaluate(ok) is True
        assert cond.evaluate(ok.model_copy(update={"ip": "192.168.1.1"})) is False
        assert cond.evaluate(ok.model_copy(update={"time": "18:00"})) is False
        assert cond.evaluate(ok.model_copy(update={"attributes": {"dept": "sales"}})) is False

    def test_accepts_dict_context(self):
        cond = ContextCondition(allowed_ips=["10.0.0.1"])
        assert cond.evaluate({"ip": "10.0.0.1"}) is True
        assert cond.evaluate({"ip": "10.0.0.2"}) is False


# ---------------------------------------------------------------------------
# Core domain logic: Role / Rule / PolicyEnforcer
# ---------------------------------------------------------------------------

class TestRole:
    def test_grant_and_can(self):
        role = Role("admin")
        role.grant("read", "docs")
        role.grant("write", "*")
        assert role.can("read", "docs") is True
        assert role.can("read", "secrets") is False
        assert role.can("write", "anything") is True

    def test_constructor_permissions(self):
        role = Role("guest", [("read", "public")])
        assert role.can("read", "public") is True
        assert role.can("read", "docs") is False

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            Role("")


class TestRule:
    def test_exact_match(self):
        rule = Rule("admin", "read", "docs")
        assert rule.matches("admin", "read", "docs") is True
        assert rule.matches("guest", "read", "docs") is False
        assert rule.matches("admin", "write", "docs") is False
        assert rule.matches("admin", "read", "reports") is False

    def test_wildcards(self):
        assert Rule("*", "*", "*").matches("anyone", "anything", "anywhere") is True
        assert Rule("admin", "*", "docs").matches("admin", "delete", "docs") is True
        assert Rule("admin", "*", "docs").matches("guest", "read", "docs") is False

    def test_bad_effect_rejected(self):
        with pytest.raises(ValueError):
            Rule("admin", "read", "docs", effect="bogus")

    def test_condition_gating(self):
        rule = Rule("admin", "read", "docs", condition=ContextCondition(allowed_ips=["10.0.0.1"]))
        assert rule.matches("admin", "read", "docs", Context(ip="10.0.0.1")) is True
        assert rule.matches("admin", "read", "docs", Context(ip="10.0.0.2")) is False

    def test_from_schema(self):
        rule = Rule.from_schema(PolicyRule(role="admin", action="read", resource="docs", effect="deny"))
        assert rule.effect == "deny"
        assert rule.matches("admin", "read", "docs") is True


class TestPolicyEnforcer:
    def test_default_deny(self):
        assert PolicyEnforcer().evaluate("admin", "read", "docs") is False

    def test_allow(self):
        enforcer = PolicyEnforcer([Rule("admin", "read", "docs")])
        assert enforcer.evaluate("admin", "read", "docs") is True

    def test_deny_overrides_allow(self):
        enforcer = PolicyEnforcer(
            [
                Rule("admin", "read", "docs", effect="allow"),
                Rule("admin", "read", "docs", effect="deny"),
            ]
        )
        assert enforcer.evaluate("admin", "read", "docs") is False

    def test_non_matching_deny_does_not_block(self):
        enforcer = PolicyEnforcer(
            [
                Rule("admin", "read", "docs", effect="allow"),
                Rule("admin", "read", "secrets", effect="deny"),
            ]
        )
        assert enforcer.evaluate("admin", "read", "docs") is True
        assert enforcer.evaluate("admin", "read", "secrets") is False

    def test_context_deny_via_default(self):
        enforcer = PolicyEnforcer(
            [Rule("admin", "read", "docs", condition=ContextCondition(allowed_ips=["10.0.0.0/8"]))]
        )
        assert enforcer.evaluate("admin", "read", "docs", Context(ip="10.1.2.3")) is True
        assert enforcer.evaluate("admin", "read", "docs", Context(ip="192.168.0.1")) is False

    def test_accepts_dict_context(self):
        enforcer = PolicyEnforcer(
            [Rule("admin", "read", "docs", condition=ContextCondition(allowed_ips=["10.0.0.1"]))]
        )
        assert enforcer.evaluate("admin", "read", "docs", {"ip": "10.0.0.1"}) is True
        assert enforcer.evaluate("admin", "read", "docs", {"ip": "10.0.0.2"}) is False

    def test_role_object_as_role(self):
        enforcer = PolicyEnforcer([Rule("admin", "read", "docs")])
        assert enforcer.evaluate(Role("admin"), "read", "docs") is True

    def test_decide_reasons(self):
        enforcer = PolicyEnforcer([Rule("admin", "read", "docs")])
        assert enforcer.decide("admin", "read", "docs").allowed is True
        assert "allowed" in enforcer.decide("admin", "read", "docs").reason
        denied = enforcer.decide("guest", "read", "docs")
        assert denied.allowed is False
        assert "default deny" in denied.reason

    def test_evaluate_async_matches_sync(self):
        enforcer = PolicyEnforcer([Rule("admin", "read", "docs")])
        assert enforcer.evaluate("admin", "read", "docs") is True

        async def _check():
            assert await enforcer.evaluate_async("admin", "read", "docs") is True
            assert await enforcer.evaluate_async("guest", "read", "docs") is False

        import asyncio

        asyncio.run(_check())

    def test_build_policy_from_roles(self):
        admin = Role("admin", [("read", "docs"), ("write", "reports")])
        guest = Role("guest", [("read", "public")])
        enforcer = build_policy_from_roles([admin, guest])
        assert enforcer.evaluate("admin", "read", "docs") is True
        assert enforcer.evaluate("admin", "write", "reports") is True
        assert enforcer.evaluate("guest", "read", "public") is True
        assert enforcer.evaluate("guest", "read", "docs") is False
        assert enforcer.evaluate("admin", "delete", "docs") is False

    def test_from_policy(self):
        policy = Policy(
            name="main",
            rules=[
                PolicyRule(role="admin", action="read", resource="docs"),
                PolicyRule(role="admin", action="delete", resource="docs", effect="deny"),
            ],
        )
        enforcer = PolicyEnforcer.from_policy(policy)
        assert enforcer.evaluate("admin", "read", "docs") is True
        assert enforcer.evaluate("admin", "delete", "docs") is False
        assert enforcer.evaluate("guest", "read", "docs") is False

    def test_set_policy_replaces_rules(self):
        enforcer = PolicyEnforcer([Rule("admin", "read", "docs")])
        enforcer.set_policy(Policy(name="other", rules=[PolicyRule(role="guest", action="read", resource="public")]))
        assert enforcer.evaluate("guest", "read", "public") is True
        assert enforcer.evaluate("admin", "read", "docs") is False

    def test_add_policy_and_clear(self):
        enforcer = PolicyEnforcer()
        enforcer.add_policy(Policy(name="p", rules=[PolicyRule(role="admin", action="read", resource="docs")]))
        assert enforcer.evaluate("admin", "read", "docs") is True
        assert len(enforcer.rules) == 1
        enforcer.clear()
        assert enforcer.evaluate("admin", "read", "docs") is False


# ---------------------------------------------------------------------------
# FastAPI endpoints (direct JSONResponse, explicit 4xx/5xx)
# ---------------------------------------------------------------------------

class FakeRequest:
    """Minimal stand-in for starlette Request with an async .json()."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body


class _ExplodingEnforcer:
    def decide(self, *args, **kwargs):
        raise RuntimeError("boom")


class TestAPI:
    def test_router_shape(self):
        assert api.router.prefix == "/api/governance"
        assert len(api.router.routes) >= 2

    async def test_set_policy_ok(self):
        resp = await api.set_policy(
            FakeRequest({"name": "api-policy", "rules": [{"role": "admin", "action": "read", "resource": "docs"}]})
        )
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data["status"] == "ok"
        assert data["policy"] == "api-policy"
        assert data["rules"] == 1

    async def test_evaluate_allowed(self):
        await api.set_policy(
            FakeRequest({"name": "p-allow", "rules": [{"role": "admin", "action": "read", "resource": "docs"}]})
        )
        resp = await api.evaluate(FakeRequest({"role": "admin", "action": "read", "resource": "docs"}))
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data["allowed"] is True
        assert data["role"] == "admin"

    async def test_evaluate_denied_default(self):
        await api.set_policy(FakeRequest({"name": "p-deny", "rules": []}))
        resp = await api.evaluate(FakeRequest({"role": "guest", "action": "read", "resource": "docs"}))
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data["allowed"] is False
        assert "default deny" in data["reason"]

    async def test_evaluate_context_deny(self):
        await api.set_policy(
            FakeRequest(
                {
                    "name": "p-ctx",
                    "rules": [
                        {
                            "role": "admin",
                            "action": "read",
                            "resource": "docs",
                            "condition": {"allowed_ips": ["10.0.0.0/8"]},
                        }
                    ],
                }
            )
        )
        denied = await api.evaluate(
            FakeRequest({"role": "admin", "action": "read", "resource": "docs", "context": {"ip": "192.168.0.1"}})
        )
        assert json.loads(denied.body)["allowed"] is False
        allowed = await api.evaluate(
            FakeRequest({"role": "admin", "action": "read", "resource": "docs", "context": {"ip": "10.1.2.3"}})
        )
        assert json.loads(allowed.body)["allowed"] is True

    async def test_evaluate_invalid_payload_422(self):
        resp = await api.evaluate(FakeRequest({"action": "read", "resource": "docs"}))
        assert resp.status_code == 422
        assert json.loads(resp.body)["error"] == "invalid_request"

    async def test_evaluate_invalid_context_422(self):
        resp = await api.evaluate(
            FakeRequest({"role": "admin", "action": "read", "resource": "docs", "context": {"ip": "nope"}})
        )
        assert resp.status_code == 422

    async def test_invalid_json_422(self):
        resp = await api.evaluate(FakeRequest("{not json"))
        assert resp.status_code == 422
        assert json.loads(resp.body)["error"] == "invalid_json"

    async def test_non_object_body_422(self):
        resp = await api.evaluate(FakeRequest([1, 2, 3]))
        assert resp.status_code == 422

    async def test_invalid_policy_422(self):
        resp = await api.set_policy(
            FakeRequest({"name": "bad", "rules": [{"role": "", "action": "read", "resource": "docs"}]})
        )
        assert resp.status_code == 422
        assert json.loads(resp.body)["error"] == "invalid_policy"

    async def test_internal_error_500(self):
        original = api._enforcer
        try:
            api._enforcer = _ExplodingEnforcer()
            resp = await api.evaluate(FakeRequest({"role": "admin", "action": "read", "resource": "docs"}))
            assert resp.status_code == 500
            assert json.loads(resp.body)["error"] == "internal_error"
        finally:
            api._enforcer = original
