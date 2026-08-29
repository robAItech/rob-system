"""Core domain logic for governance_policy_enforcer (RBAC/ABAC).

Centralized authorization policy enforcement:
  - ``Role``: RBAC role holding a set of (action, resource) permissions,
  - ``Rule``: role/action/resource matcher with an optional ABAC context condition,
  - ``PolicyEnforcer``: evaluates requests with default-deny and deny-overrides
    semantics; ``evaluate(role, action, resource, context)`` returns ``bool``
    and an async variant is provided for async endpoints.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Set, Tuple

from .schemas import Context, ContextCondition, Decision, Policy, PolicyRule


class Role:
    """RBAC role: a named set of (action, resource) permissions."""

    def __init__(self, name: str, permissions: Optional[Iterable[Tuple[str, str]]] = None):
        if not name:
            raise ValueError("role name must not be empty")
        self.name = name
        self.permissions: Set[Tuple[str, str]] = set(permissions or ())

    def grant(self, action: str, resource: str) -> None:
        """Grant ``resource`` access for ``action`` (``"*"`` acts as a wildcard)."""
        self.permissions.add((action, resource))

    def can(self, action: str, resource: str) -> bool:
        return (action, resource) in self.permissions or (action, "*") in self.permissions

    def __repr__(self) -> str:
        return f"Role(name={self.name!r}, permissions={sorted(self.permissions)})"


class Rule:
    """A policy rule: role/action/resource matcher plus an optional ABAC condition."""

    def __init__(
        self,
        role: str,
        action: str,
        resource: str,
        effect: str = "allow",
        condition: Optional[ContextCondition] = None,
    ):
        if effect not in ("allow", "deny"):
            raise ValueError(f"effect must be 'allow' or 'deny', got {effect!r}")
        self.role = role
        self.action = action
        self.resource = resource
        self.effect = effect
        self.condition = condition

    def matches(
        self,
        role: str,
        action: str,
        resource: str,
        context: Optional[Context] = None,
    ) -> bool:
        """Return True iff this rule applies to the request (context condition included)."""
        if self.role != "*" and role != self.role:
            return False
        if self.action != "*" and action != self.action:
            return False
        if self.resource != "*" and resource != self.resource:
            return False
        if self.condition is not None and not self.condition.evaluate(context):
            return False
        return True

    @classmethod
    def from_schema(cls, rule: PolicyRule) -> "Rule":
        return cls(rule.role, rule.action, rule.resource, rule.effect, rule.condition)

    def __repr__(self) -> str:
        cond = "" if self.condition is None else f" condition={self.condition!r}"
        return f"Rule({self.role!r}, {self.action!r}, {self.resource!r}, {self.effect!r}{cond})"


class PolicyEnforcer:
    """Centralized authorization enforcer with default-deny and deny-overrides semantics."""

    def __init__(self, rules: Optional[Iterable[Rule]] = None):
        self._rules: List[Rule] = list(rules or ())

    # -- construction --------------------------------------------------------
    def add_rule(self, rule: Rule) -> "PolicyEnforcer":
        self._rules.append(rule)
        return self

    def add_policy(self, policy: Policy) -> "PolicyEnforcer":
        self._rules.extend(Rule.from_schema(r) for r in policy.rules)
        return self

    def set_policy(self, policy: Policy) -> None:
        """Replace all rules with the ones declared in ``policy``."""
        self._rules = [Rule.from_schema(r) for r in policy.rules]

    @classmethod
    def from_policy(cls, policy: Policy) -> "PolicyEnforcer":
        enforcer = cls()
        enforcer.set_policy(policy)
        return enforcer

    def clear(self) -> None:
        self._rules.clear()

    @property
    def rules(self) -> List[Rule]:
        return list(self._rules)

    # -- evaluation ----------------------------------------------------------
    def _role_name(self, role) -> str:
        return role.name if isinstance(role, Role) else str(role)

    def _matching_rules(self, role, action: str, resource: str, context: Optional[Context]):
        role_name = self._role_name(role)
        for rule in self._rules:
            if rule.matches(role_name, action, resource, context):
                yield rule

    def decide(
        self,
        role,
        action: str,
        resource: str,
        context: Optional[Context] = None,
    ) -> Decision:
        """Evaluate the request and return a full Decision (deny-overrides, default deny)."""
        if isinstance(context, dict):
            context = Context(**context)
        role_name = self._role_name(role)
        matched_allow: Optional[Rule] = None
        for rule in self._matching_rules(role, action, resource, context):
            if rule.effect == "deny":
                return Decision(
                    allowed=False,
                    role=role_name,
                    action=action,
                    resource=resource,
                    reason=f"denied by matching rule {rule!r}",
                    rule=repr(rule),
                )
            matched_allow = rule
        if matched_allow is not None:
            return Decision(
                allowed=True,
                role=role_name,
                action=action,
                resource=resource,
                reason=f"allowed by matching rule {matched_allow!r}",
                rule=repr(matched_allow),
            )
        return Decision(
            allowed=False,
            role=role_name,
            action=action,
            resource=resource,
            reason="no matching rule (default deny)",
        )

    def evaluate(
        self,
        role,
        action: str,
        resource: str,
        context: Optional[Context] = None,
    ) -> bool:
        """Return True iff the request is allowed (deny-overrides, default deny)."""
        return self.decide(role, action, resource, context).allowed

    async def evaluate_async(
        self,
        role,
        action: str,
        resource: str,
        context: Optional[Context] = None,
    ) -> bool:
        """Async variant of ``evaluate`` for use in async endpoints."""
        return self.evaluate(role, action, resource, context)


def build_policy_from_roles(roles: Iterable[Role]) -> PolicyEnforcer:
    """Build an allow-only RBAC enforcer from a collection of Role objects."""
    enforcer = PolicyEnforcer()
    for role in roles:
        for action, resource in sorted(role.permissions):
            enforcer.add_rule(Rule(role.name, action, resource, effect="allow"))
    return enforcer