"""fleet_security — remediacijski PR (config/network policy SAMO).

Trdi zidovi (CEO review 2026-08-31):
- **Firmware je report-only** — ta modul NIKOLI ne remediira ``firmware_*``
  najdb; če so edine odprte najdbe firmware → status ``error`` (fix skozi OEM).
- **PR se nikoli ne auto-merge-a** — tudi če ``fs_pr_auto_merge=True``,
  modul vrne error; PR transport nima merge parametra.
- **Brez placeholderjev** — generate_fix spremeni le tisto, kar je mehansko
  varno in znano: manjkajoče config ključe s konkretno pričakovano vrednostjo
  in booleanske insecure default-e (flip). Vrednosti, ki jih lahko nastavi
  samo operater (npr. gesla), ostanejo report-only.

Git subprocess vzorec: core/fleet.py ``commit_worker_actions`` (add → diff
--cached --quiet → commit → push retry 1×). PR transport je abstrahiran
(``gh`` CLI ali GitHub REST API prek httpx) — testi ga mock-ajo.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    ANY_VALUE,
    Baseline,
    Device,
    RemediationResult,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

_FIRMWARE_CATEGORIES = ("firmware_drift", "firmware_unknown")


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Fix generation (brez I/O, brez placeholderjev)
# ------------------------------------------------------------------ #
def _flip(insecure: Any) -> Any:
    """Mehanska varna vrednost: bool → obrni; sicer None = ni auto-fixable."""
    if isinstance(insecure, bool):
        return not insecure
    return None


def _desired_config(device: Device, baseline: Baseline | None) -> dict[str, Any]:
    desired = dict(device.config)
    if baseline is None:
        return desired
    for key, expected in baseline.required_config_keys.items():
        if expected is ANY_VALUE:
            continue  # vrednost pozna samo operater → report-only
        if key not in desired or desired[key] != expected:
            desired[key] = expected
    for key, insecure in baseline.secure_default_checks.items():
        if key in desired and desired[key] == insecure:
            fixed = _flip(insecure)
            if fixed is not None:
                desired[key] = fixed
    return desired


def _secure_network_policy() -> dict[str, Any]:
    """Deny-by-default egress + TLS obvezen (Phase 1 secure template)."""
    return {
        "version": 1,
        "ingress": "deny-all",
        "egress": {"default": "deny"},
        "tls": {"required": True},
        "allowlist": [],
    }


def _yaml_dump(data: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False)


def _diff(current_yaml: str, desired_yaml: str, device_id: str, kind: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            current_yaml.splitlines(),
            desired_yaml.splitlines(),
            fromfile=f"{device_id}/{kind} current",
            tofile=f"{device_id}/{kind} desired",
            lineterm="",
        )
    )


def generate_fix(
    device: Device, baseline: Baseline | None, kind: str
) -> tuple[str, str, list[str]]:
    """Ustvari desired-state + diff. Vrne (desired_yaml, diff, touched_files).

    ``kind`` je samo ``config`` ali ``network_policy``; drugo → ValueError.
    ``touched_files`` so repo-relativne poti pod ``settings.fs_desired_state_dir``.
    """
    if kind == "config":
        current = _yaml_dump(dict(device.config))
        desired = _yaml_dump(_desired_config(device, baseline))
        rel = f"{settings.fs_desired_state_dir}/{device.device_id}/config.yaml"
    elif kind == "network_policy":
        current = _yaml_dump(dict(device.config.get("network_policy") or {}))
        desired = _yaml_dump(_secure_network_policy())
        rel = f"{settings.fs_desired_state_dir}/{device.device_id}/network_policy.yaml"
    else:
        raise ValueError(f"kind must be 'config' or 'network_policy', got {kind!r}")
    return desired, _diff(current, desired, device.device_id, kind), [rel]


# ------------------------------------------------------------------ #
#  Git commit (vzorec: core/fleet.py commit_worker_actions)
# ------------------------------------------------------------------ #
def _commit_desired_state(branch: str, files: dict[str, str]) -> tuple[str, str | None]:
    """git branch + zapis + add → commit → push (retry 1×). Idempotentno.

    Vrne (branch, short_sha) ali (branch, None) ob brez-sprememb/neuspehu.
    """
    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args), cwd=PROJECT_ROOT, capture_output=True, text=True
        )

    _run("git", "checkout", "-b", branch)
    for rel, content in files.items():
        path = PROJECT_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for rel in files:
        _run("git", "add", rel)
    if _run("git", "diff", "--cached", "--quiet").returncode == 0:
        return branch, None  # ni sprememb → idempotentno preskoči
    commit = _run("git", "commit", "-m", f"fleet-security: desired-state for {branch}")
    if commit.returncode != 0:
        return branch, None
    # push retry enkrat (pre-push hook lahko naredi rebase in prekine).
    push = _run("git", "push", "--set-upstream", "origin", branch)
    if push.returncode != 0:
        _run("git", "push", "--set-upstream", "origin", branch)
    sha = _run("git", "rev-parse", "--short", "HEAD").stdout.strip()
    return branch, sha or None


# ------------------------------------------------------------------ #
#  PR transport (abstrahiran → testi mock-ajo)
# ------------------------------------------------------------------ #
class PRTransport(Protocol):
    def open_pr(self, *, branch: str, title: str, body: str) -> str | None:
        """Vrne PR URL ali None. NIKOLI ne merge-a."""


class GhCLITransport:
    """gh pr create — brez merge flagov (ni parametra za merge)."""

    def open_pr(self, *, branch: str, title: str, body: str) -> str | None:
        r = subprocess.run(
            [
                "gh", "pr", "create",
                "--base", settings.fs_pr_base_branch,
                "--head", branch,
                "--title", title,
                "--body", body,
            ],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        url = (r.stdout or "").strip()
        return url or None


class GitHubAPITransport:
    """GitHub REST fallback (httpx). Posta samo head/base/title/body."""

    def __init__(self, token: str, owner: str, repo: str, base: str = "main"):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base = base

    def open_pr(self, *, branch: str, title: str, body: str) -> str | None:
        import httpx

        resp = httpx.post(
            f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "head": branch, "base": self.base, "body": body},
            timeout=30,
        )
        if resp.status_code >= 300:
            return None
        return (resp.json() or {}).get("html_url")


def _default_transport() -> PRTransport | None:
    import shutil

    if shutil.which("gh"):
        return GhCLITransport()
    if settings.fs_pr_token:
        return GitHubAPITransport(
            settings.fs_pr_token,
            settings.fs_pr_owner,
            settings.fs_pr_repo,
            settings.fs_pr_base_branch,
        )
    return None


# ------------------------------------------------------------------ #
#  Orchestracija
# ------------------------------------------------------------------ #
def open_remediation_pr(
    store: FleetSecurityStore,
    device_id: str,
    kind: str = "config",
    dry_run: bool = True,
    transport: PRTransport | None = None,
    now: int | None = None,
) -> RemediationResult:
    """Odpri remediacijski PR (config/network SAMO) ali vrni dry-run diff.

    Pravila:
    - firmware-only najdbe → ``error`` (OEM pot, NIKOLI remediirano),
    - ni config najdb → ``no_change``,
    - ``dry_run=True`` → ``diff_generated`` (brez gita/PR),
    - ``dry_run=False`` → branch + commit + push + PR (transport),
    - ``fs_pr_auto_merge=True`` → ``error`` (CEO trdi zid).
    Vsak korak piše audit ``fleet-security-remediate``.
    """
    now = int(now) if now is not None else _now()
    result = RemediationResult(device_id=device_id, kind=kind, status="error")

    device = store.get_device(device_id)
    if device is None:
        result.message = "device not found"
        return result

    # Trdi zid: auto-merge je prepovedan.
    if settings.fs_pr_auto_merge:
        result.message = "auto-merge disabled by policy (CEO hard rule)"
        return result

    open_findings = store.list_open_findings(device_id)
    config_findings = [f for f in open_findings if f.category == "config_drift"]
    fw_findings = [f for f in open_findings if f.category in _FIRMWARE_CATEGORIES]

    # Firmware trdi zid.
    if fw_findings and not config_findings:
        result.message = (
            "firmware findings are report-only; remediation via OEM"
        )
        store.save_remediation(result, now)
        return result

    # Ni fixable config najdb → no_change (idempotentno).
    if not config_findings:
        result.status = "no_change"
        result.message = "no open config_drift findings"
        store.save_remediation(result, now)
        return result

    baseline = store.get_baseline(device.role)
    desired_yaml, diff, touched = generate_fix(device, baseline, kind)
    if not diff.strip():
        result.status = "no_change"
        result.message = "no mechanically-fixable drift"
        store.save_remediation(result, now)
        return result

    # Dry-run: diff brez gita.
    if dry_run:
        result.status = "diff_generated"
        result.diff = diff
        result.message = "dry-run (no git, no PR)"
        store.save_remediation(result, now)
        try:
            audit.record(
                event="fleet-security-remediate", project=device_id,
                status="ok", detail=f"{kind} dry-run diff generated",
            )
        except Exception:
            pass
        return result

    # Ze odprta remediacija → no_change.
    if store.has_open_remediation(device_id, kind):
        result.status = "no_change"
        result.message = "remediation already open"
        return result

    branch = f"fleet-security/{device_id}-{kind}"
    files = {touched[0]: desired_yaml}
    branch, sha = _commit_desired_state(branch, files)
    if sha is None:
        result.status = "error"
        result.message = "git commit/push failed (no diff or no changes)"
        store.save_remediation(result, now)
        try:
            audit.record(
                event="fleet-security-remediate", project=device_id,
                status="failed", detail=f"{kind} commit failed",
            )
        except Exception:
            pass
        return result

    trans = transport or _default_transport()
    pr_url: str | None = None
    if trans is not None:
        title = f"fleet-security: desired-state {kind} for {device_id}"
        body = (
            f"Automated remediation PR (Phase 1 passive core).\n\n"
            f"Device: {device_id}\nKind: {kind}\n\nChanges:\n```\n{diff}\n```\n\n"
            f"Human-in-the-loop: review and merge. Firmware fixes go through OEM."
        )
        pr_url = trans.open_pr(branch=branch, title=title, body=body)

    result.status = "pr_open"
    result.diff = diff
    result.branch = branch
    result.commit = sha
    result.pr_url = pr_url
    result.message = "PR opened (human-in-the-loop)" if pr_url else "commit pushed, PR pending"
    store.save_remediation(result, now)
    try:
        audit.record(
            event="fleet-security-remediate", project=device_id,
            status="ok" if pr_url else "failed",
            detail=f"{kind} branch={branch} pr={pr_url or 'none'}",
        )
    except Exception:
        pass
    return result
