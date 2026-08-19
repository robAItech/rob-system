"""core/self_improve.py — Faza 4e / Zanka 3: samorazvoj orkestracije (RSI nase).

Zapre tretjo zanko: sistem predlaga izboljšavo SVOJEGA prompta (npr. RSI heal
prompt), jo preveri s semantičnim GUARDOM (obdrži varnostne invariante) in z
regresijskimi VRATI (pytest zelen), ter jo promovira ali zavrne. Rollback je
vedno na voljo.

Meja varovanja: sistem spreminja LE prompte (instructional layer), NE strukturne
kode (runner/ledger zanka). Prompt je varen, ker je reverzibilen (verzioniran +
rollback) in ker ga pred promocijo drži guard + regresijska množica.

Uporaba:
  python core/self_improve.py --run        # en cikel: predlog → guard → test → promocija/zavrnitev
  python core/self_improve.py --run --dry-run
  python core/self_improve.py --rollback
  python core/self_improve.py --stats
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.prompt_registry import PromptRegistry

# Ime prompta, ki ga sistem sme samorazvijati, + njegova privzeta vsebina
# (fallback, če v registru še ni aktivne verzije).
PROMPT_NAME = "rsi_heal_system"

# Varnostne invariante: promoviran prompt MORA vsebovati vse te (case-insensitive).
# Če LLM predlaga prompt, ki jih opusti, ga guard zavrne — to je semantična meja
# samorazvoja (test-locking + izhodni format + cilj 100% zelene se ne smejo izgubiti).
REQUIRED_INVARIANTS = [
    "### FILE:",   # izhodni format (razrez v builderju)
    "test",        # prepoved spreminjanja testnih datotek (Test-Locking)
    "100%",        # cilj: 100% zelena verifikacija
]

# Privzeta regresijska množica, ki jo poganja vrata (podmnožica, ki pokriva RSI).
DEFAULT_TEST_TARGETS = ["tests/test_loopx_rsi.py", "tests/test_integration.py"]


class SelfImprover:
    """Samorazvojni cikel: predlog → guard → regresijska vrata → promocija/zavrnitev."""

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        self.registry = PromptRegistry(db_path)

    # ------------------------------------------------------------------ #
    #  Koraki cikla
    # ------------------------------------------------------------------ #
    def propose(self, name: str, current: str, context: str) -> Optional[Dict[str, Any]]:
        """LLM predlaga izboljšan prompt (ali None, če ni izboljšave)."""
        if not self._llm_available():
            return None
        system_prompt = (
            "Si samorazvojni inženir sistema. Predlagaj IZBOLJŠAN prompt, ki odpravi "
            "nedavne težave, ne da bi pokvaril obstoječe vedenje. Vrni SAMO nov prompt "
            "(brez uvoda, brez razlage) ali prazno, če ni izboljšave."
        )
        prompt = (
            f"TRENUTNI PROMPT:\n{current}\n\n"
            f"NEDAVNI KONTEKST (recenzije/napake):\n{context}\n\n"
            "Nov prompt (obdrži VSE varnostne zahteve, vključno s ### FILE: formatom "
            "in prepovedjo spreminjanja testov):"
        )
        from core.llm_client import DeepSeekLLMClient
        llm = DeepSeekLLMClient()
        raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        candidate = raw.strip()
        if len(candidate) < 20 or candidate == current.strip():
            return None
        version_id = self.registry.propose(name, candidate, note="auto-proposal (Zanka 3)")
        return {"version_id": version_id, "content": candidate}

    def guard(self, name: str, content: str) -> Dict[str, Any]:
        """Preveri, da prompt obdrži varnostne invariante. Vrne {ok, missing}."""
        invariants = REQUIRED_INVARIANTS if name == PROMPT_NAME else []
        missing = [inv for inv in invariants if inv.lower() not in content.lower()]
        return {"ok": not missing, "missing": missing}

    def evaluate(self, test_targets: Optional[List[str]] = None) -> bool:
        """Regresijska vrata: požene pytest podmnožico. True, če je zeleno."""
        targets = list(test_targets or DEFAULT_TEST_TARGETS)
        if not targets:
            return True
        cmd = [sys.executable, "-m", "pytest", *targets, "-q"]
        res = subprocess.run(cmd, capture_output=True, cwd=str(PROJECT_ROOT))
        return res.returncode == 0

    def promote(self, name: str, version_id: int) -> None:
        self.registry.promote(name, version_id)

    def reject(self, version_id: int) -> None:
        self.registry.mark(version_id, "rejected", tests_passed=0)

    def rollback(self, name: str) -> Optional[int]:
        return self.registry.rollback(name)

    # ------------------------------------------------------------------ #
    #  Cel cikel
    # ------------------------------------------------------------------ #
    def run_cycle(self, current: str, context: str = "", test_targets: Optional[List[str]] = None,
                  dry_run: bool = False) -> Dict[str, Any]:
        """En samorazvojni cikel: predlog → guard → vrata → promocija/zavrnitev."""
        proposal = self.propose(PROMPT_NAME, current, context)
        if proposal is None:
            return {"proposed": False, "reason": "LLM ni predlagal izboljšave (ali ni ključa)"}

        version_id = proposal["version_id"]
        guard = self.guard(PROMPT_NAME, proposal["content"])
        if not guard["ok"]:
            self.reject(version_id)
            return {"proposed": True, "version_id": version_id, "promoted": False,
                    "reason": f"guard: manjkajo invariante {guard['missing']}"}

        if dry_run:
            return {"proposed": True, "version_id": version_id, "guard_ok": True, "dry_run": True}

        passed = self.evaluate(test_targets)
        self.registry.mark(version_id, "proposed", tests_passed=1 if passed else 0)
        if passed:
            self.promote(PROMPT_NAME, version_id)
            return {"proposed": True, "version_id": version_id, "promoted": True, "tests_passed": True}
        self.reject(version_id)
        return {"proposed": True, "version_id": version_id, "promoted": False, "tests_passed": False}

    # ------------------------------------------------------------------ #
    #  Samorazvoj parametrov (Zanka 3, globlje)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            val = json.loads(text[start:end + 1])
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def propose_tuning(self, current: Dict[str, float], context: str) -> Optional[Dict[str, float]]:
        """LLM predlaga nove vrednosti parametrov orkestracije (ali None)."""
        if not self._llm_available():
            return None
        from core.tuning import BOUNDS
        system_prompt = (
            "Si samorazvojni inženir sistema. Na podlagi nedavnih recenzij/neuspehov "
            "predlagaj IZBOLJŠANE vrednosti parametrov orkestracije. Vrni SAMO JSON objekt "
            'oblike {"max_attempts": N, "repeat_abort_after": N} ali prazno, če ni izboljšave.'
        )
        prompt = (
            f"TRENUTNI PARAMETRI: {json.dumps(current)}\n"
            f"MEJE: {json.dumps(BOUNDS)}\n"
            f"NEDAVNI KONTEKST: {context}\n\n"
            "Nove vrednosti (v mejah):"
        )
        from core.llm_client import DeepSeekLLMClient
        llm = DeepSeekLLMClient()
        raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        obj = self._parse_json_object(raw)
        if not obj:
            return None
        out: Dict[str, float] = {}
        for name in current:
            if name in obj:
                try:
                    out[name] = float(obj[name])
                except (TypeError, ValueError):
                    pass
        return out if out else None

    def tune_cycle(self, context: str = "", test_targets: Optional[List[str]] = None,
                   dry_run: bool = False) -> Dict[str, Any]:
        """En cikel samorazvojnega uglaševanja: predlog → meje → vrata → promocija/zavrnitev."""
        from core.tuning import Tuning
        tuning = Tuning(self.registry.db_path)
        proposal = self.propose_tuning(tuning.all(), context)
        if proposal is None:
            return {"proposed": False, "reason": "LLM ni predlagal spremembe (ali ni ključa)"}

        try:
            version_ids = {}
            for name, value in proposal.items():
                version_ids[name] = tuning.set(name, value, note="auto-tune (Zanka 3)")
        except ValueError as e:
            return {"proposed": True, "promoted": False, "reason": f"guard: {e}"}

        if dry_run:
            return {"proposed": True, "dry_run": True, "params": proposal}

        if self.evaluate(test_targets):
            for name, vid in version_ids.items():
                tuning.promote(name, vid)
            return {"proposed": True, "promoted": True, "params": proposal, "tests_passed": True}
        return {"proposed": True, "promoted": False, "params": proposal, "tests_passed": False}

    # ------------------------------------------------------------------ #
    #  Kontekst iz spomina (za predlog)
    # ------------------------------------------------------------------ #
    def gather_context(self, limit: int = 8) -> str:
        """Zbere nedavni kontekst: recenzije (Zanka 2) + neuspeli teki."""
        parts: List[str] = []
        try:
            from core.run_review import RunReviewer
            reviews = RunReviewer(self.registry.db_path).recent(limit=limit)
            if reviews:
                parts.append("Nedavne recenzije:")
                for r in reviews:
                    parts.append(f"- [{r['outcome']} · {r['root_cause']}] {r['project']}: {r['lesson'] or ''}")
        except Exception:
            pass
        if not parts:
            parts.append("(ni nedavnega konteksta)")
        return "\n".join(parts)

    @staticmethod
    def _llm_available() -> bool:
        try:
            from core.config import settings
            return settings.is_real_key_available()
        except Exception:
            return False


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="self_improve", description="Zanka 3 — samorazvoj orkestracije.")
    p.add_argument("--run", action="store_true", help="en samorazvojni cikel (predlog → guard → test → promocija)")
    p.add_argument("--dry-run", action="store_true", help="predlog + guard brez promocije")
    p.add_argument("--rollback", action="store_true", help="vrni RSI prompt na prejšnjo verzijo")
    p.add_argument("--stats", action="store_true", help="statistika prompt-registra")
    p.add_argument("--tune", action="store_true", help="samorazvojno uglaševanje parametrov (Zanka 3, globlje)")
    args = p.parse_args(argv)

    imp = SelfImprover()
    if args.rollback:
        new_id = imp.rollback(PROMPT_NAME)
        print("rollback" if new_id is not None else "ni prejšnje verzije")
        return 0
    if args.stats:
        print(json.dumps(imp.registry.stats(), ensure_ascii=False, indent=2))
        return 0
    if args.run or args.dry_run:
        from core.loopx_bridge import RSI_PROMPT_SYSTEM
        current = imp.registry.get_active(PROMPT_NAME, RSI_PROMPT_SYSTEM)
        context = imp.gather_context()
        res = imp.run_cycle(current, context, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.tune:
        context = imp.gather_context()
        res = imp.tune_cycle(context, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
