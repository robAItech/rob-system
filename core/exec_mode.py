"""core/exec_mode.py — avtomatska izbira izvajalnega načina naloge.

Daemon sam odloči, kdaj naloga uporabi multi-agent team swarm (plan→critique→
build→verify) namesto enojnega RSI loopa — brez uporabniškega vnosa.

Deterministično pravilo (konfigurabilno prek TEAM_AUTO_* v .env):
  1. ekspliciten `mode=team` ali `team=true` na nalogi → team,
  2. `kind` v TEAM_AUTO_KINDS (privzeto `autonomous`) → team,
     AMPAK dokumentne naloge (doc-guard) ostanejo single/run_autonomous
     (team gradi module; dokumenti gredo skozi spec→implement),
  3. sicer single (RSI).
"""

from __future__ import annotations

from typing import Any, Dict

# Besede, ki kažejo na dokumentno nalogo → team ni primeren (team gradi module).
_DOC_WORDS = (
    "markdown", "predlog", "poročilo", "roadmap", "dokument", "dokumentacija",
    "spletna stran", "dashboard", "html", "<html", "strategija", "poslovni",
    "analiza", "mail", "e-posta", "predstavitev",
)


def _looks_like_doc(goal: str) -> bool:
    g = (goal or "").lower()
    return any(w in g for w in _DOC_WORDS)


def decide_exec_mode(item: Dict[str, Any], settings) -> str:
    """Vrne `'team'` (multi-agent) ali `'single'` (RSI) za dano nalogo."""
    if not getattr(settings, "team_auto_enabled", True):
        return "single"
    # Eksplicitna izbira, ki prihaja z nalogo (creator se je odločil).
    if item.get("mode") == "team":
        return "team"
    if str(item.get("team", "")).strip().lower() in ("true", "1"):
        return "team"
    # Avtomatsko pravilo po kind-u (+ doc-guard za dokumentne naloge).
    kinds = {
        k.strip() for k in str(getattr(settings, "team_auto_kinds", "")).split(",")
        if k.strip()
    }
    if item.get("kind") in kinds and not _looks_like_doc(item.get("goal", "")):
        return "team"
    return "single"
