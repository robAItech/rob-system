#!/usr/bin/env python3
"""
evaluate_autonomy.py — P5 SWE-bench stila samo-eval za avtonomnost RSI-GStack.

Dokaže trditev o "avtonomnem stroju": sistem mora SKOZI RSI zanko
(RobAIOrchestrator.run → LoopX pytest-v-sandboxu) rešiti lastne, preverljive
Python funkcijske zahteve, ne da bi človek posegal v kodo.

Zasnova:
- EVAL_CASES: representative "mini-bug" direktive. Vsaka zahteva, da RSI
  zgradi python modul s konkretno funkcijo.
- Po RSI zelenju eval ŠE preveri funkcijo z lastnimi (vhod→izhod) pari —
  neodvisno od LLM-napisanih testov — da se izognemo lažnemu zelenju
  (LLM, ki napiše slabe teste za lastno kodo).
- Score = passed/total. Eval se IZVAJA samo __main__ (ne v pytest),
  tudi v pravi performanci ne poganja skupin kot del `pytest tests/`.

UPORABA:
  python evaluate_autonomy.py            # izvede vse EVAL_CASES (pravi LLM + Docker)
  python evaluate_autonomy.py --limit 1  # samo prvi case (hitri smoke)
  python evaluate_autonomy.py --target fizzbuzz   # en konkretni case
  python evaluate_autonomy.py --dry-run # preveri samo strukturo EVAL_CASES (brez LLM)
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Repo koren na PYTHONPATH.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Vsili UTF-8 izhod (enako kot run_swarm.py), da emoji/šumniki ne crash-on
# Windows cp1250 (UnicodeEncodeError) v piped okoljih.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo


# ------------------------------------------------------------------ #
#  EVAL_CASES — representative Python bug zahteve
# ------------------------------------------------------------------ #
EVAL_CASES: List[Dict] = [
    {
        "name": "fizzbuzz",
        # Bug/feature: napačna deljiva logika. RSI mora izgraditi funkcijo,
        # ki pravilno vrača niz za deljiva s 3 (Fizz), 5 (Buzz), obema (FizzBuzz).
        "directive": (
            "Zgradi Python modul 'fizzbuzz' v actions/fizzbuzz/. "
            "Definiraj funkcijo `fizzbuzz(n: int) -> str`: vrača 'Fizz' če je n "
            "deljiv samo s 3, 'Buzz' če je n deljiv samo s 5, 'FizzBuzz' če je "
            "deljiv s 3 in 5, sicer string reprezentacijo n. Robni primer n=0 vrača 'FizzBuzz'. "
            "Napiši pytest test za potrditev. Vsi testi morajo biti 100% zeleni."
        ),
        # function_key = ime funkcije, ki jo eval import-uje in preveri (neodvisno
        # od LLM testov); checks = pari (vhod → pričakovani izhod).
        "function_key": "fizzbuzz",
        "checks": [
            (1, "1"),
            (3, "Fizz"),
            (5, "Buzz"),
            (15, "FizzBuzz"),
            (0, "FizzBuzz"),
            (2, "2"),
        ],
    },
    {
        "name": "divide_safe",
        # Bug/feature: deljenje z nič bi vrglo ZeroDivisionError; RSI mora
        # implementirati varno deljenje brez exceptiona.
        "directive": (
            "Zgradi Python modul 'divide_safe' v actions/divide_safe/. "
            "Definiraj funkcijo `divide_safe(a: float, b: float) -> float | None`: "
            "vrne a/b brez exceptiona; če je b == 0, vrne None. "
            "Napiši pytest test za potrditev (vključno z deljenjem z 0 → None). "
            "Vsi testi 100% zeleni."
        ),
        "function_key": "divide_safe",
        "checks": [
            (10, 2, 5.0),
            (9, 3, 3.0),
            (1, 0, None),
            (0, 0, None),
            (-8, 4, -2.0),
        ],
    },
    {
        "name": "count_words",
        # Bug/feature: naivno štetje besed z split() bi ločila štela kot besede.
        # RSI mora implementirati regex, ki ignorira ločila.
        "directive": (
            "Zgradi Python modul 'count_words' v actions/count_words/. "
            "Definiraj funkcijo `count_words(text: str) -> int`, ki šteje besede "
            "izključno s črkami/številkami (regex), ne šteje ločil in več presledkov. "
            "Napiši pytest test za potrditev. Vsi testi 100% zeleni."
        ),
        "function_key": "count_words",
        "checks": [
            ("hello world", 2),
            ("  hello   world  ", 2),
            ("one, two; three!", 3),
            ("", 0),
            ("  ", 0),
        ],
    },
]


# ------------------------------------------------------------------ #
#  Eval engine
# ------------------------------------------------------------------ #
class AutonomyEval:
    def __init__(self, cases: List[Dict]) -> None:
        self.cases = cases
        self.results: List[dict] = []

    # -- ujemi funkcijo iz actions/<name>/ (neodvisno od pokvarjenega imena) ---
    @staticmethod
    def _discover_module_dir(name: str) -> Path:
        return ROOT / "actions" / name

    @classmethod
    def _load_checkable_func(cls, name: str, func_name: str):
        """Poišči funkcijo v kateremkoli .py v actions/<name>/. Vrne funkcijo.

        Robustno: RSI-generirani moduli nimajo nujno `__init__.py`, zato
        paketni import lahko pade. Uporabimo `importlib.util` za neposredno
        nalaganje iz datoteke. Ne uvozi test_ datotek.
        """
        import importlib.util

        mod_dir = cls._discover_module_dir(name)
        if not mod_dir.exists():
            return None
        for py in sorted(mod_dir.glob("*.py")):
            if py.name.startswith("test_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py.stem, py)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn = getattr(mod, func_name, None)
                if callable(fn):
                    return fn
            except Exception:
                continue
        return None

    # -- en primer kot smoke (dry-run): samo zazna strukturo, ne kliče LLM --
    def smoke_check(self, case: Dict) -> bool:
        """Preveri, da je case dobro oblikovan (brez LLM/RSI). Vrne True."""
        d = case["directive"]
        assert case["name"] and case["name"].isidentifier(), "name mora biti veljaven identifikator"
        assert "function" not in case or callable(case.get("function")), "function mora biti klicljiv"
        return bool(d) and len(d) > 20

    # -- pokreni eval enega case (pravi RSI) -------------------------------
    def run_case(self, case: Dict) -> dict:
        name = case["name"]
        directive = case["directive"]
        res = {"name": name, "rsi_ok": False, "checks_ok": 0, "checks_total": len(case["checks"]),
               "func": case.get("function_key", name), "reason": ""}
        print(f"\n🎯 [P5] EVAL case: {name}")
        print(f"   direktiva: {directive[:120]}...")

        # 1) RSI zanka (gbrain→gstack→hermes→loopx/pytest).
        from core.orchestrator import RobAIOrchestrator
        rsi_ok = RobAIOrchestrator.run(name, directive)
        res["rsi_ok"] = rsi_ok
        if not rsi_ok:
            res["reason"] = "RSI ni zelen"
            self.results.append(res)
            return res

        # 2) Lastna verifikacija funkcije (neodvisna od LLM testov).
        fn = self._load_checkable_func(name, case["function_key"])
        if fn is None:
            res["reason"] = f"funkcija '{case['function_key']}' ni najdena v actions/{name}/"
            self.results.append(res)
            return res

        checks_ok = 0
        for check in case["checks"]:
            try:
                got = fn(*check[:-1]) if len(check) > 2 else fn(check[0])
                expected = check[-1]
                if got == expected or (expected is None and got is None):
                    checks_ok += 1
            except Exception:
                pass
        res["checks_ok"] = checks_ok
        if checks_ok == res["checks_total"]:
            res["reason"] = "vsi neodvisni preveri zeleni"
        else:
            res["reason"] = f"{checks_ok}/{res['checks_total']} neodvisnih preverov zelenih"
        self.results.append(res)
        print(f"   → neodvisni preveri: {checks_ok}/{res['checks_total']}")
        return res

    def run_all(self) -> Dict[str, float]:
        for c in self.cases:
            self.run_case(c)
        passed = sum(1 for r in self.results if r["rsi_ok"] and r["checks_ok"] == r["checks_total"])
        total = len(self.results)
        return {"passed": passed, "total": total, "rate": (passed / total) if total else 0.0}


# ------------------------------------------------------------------ #
#  main
# ------------------------------------------------------------------ #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rob eval",
        description="P5 SWE-bench stila samo-eval za avtonomnost RSI-GStack.",
    )
    p.add_argument("--limit", type=int, default=None, help="samo prvih N case-ov")
    p.add_argument("--target", metavar="NAME", default=None, help="samo en case po imenu")
    p.add_argument("--dry-run", action="store_true",
                   help="samo strukturna preverba EVAL_CASES (brez LLM/RSI)")
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    cases = list(EVAL_CASES)
    if args.target:
        cases = [c for c in cases if c["name"] == args.target]
        if not cases:
            print(f"[NAP] Ni case-a z imenom '{args.target}'.")
            return 1
    if args.limit:
        cases = cases[: args.limit]

    print("=" * 70)
    print("🤖 P5 — SWE-bench stila samo-eval za avtonomnost")
    print("=" * 70)

    if args.dry_run:
        evaluator = AutonomyEval(cases)
        ok = all(evaluator.smoke_check(c) for c in cases)
        print(f"Dry-run: {len(cases)} case-ov strukturno veljavnih: {ok}")
        return 0 if ok else 1

    # Potrdi prisotnost tipke in Dockerja pred dragim eval zagonom.
    evaluator = AutonomyEval(cases)
    summary = evaluator.run_all()
    print("\n" + "=" * 70)
    print(f"📊 PREHOD RATE: {summary['passed']}/{summary['total']} "
          f"({summary['rate'] * 100:.0f}%)")
    for r in evaluator.results:
        flag = "✅" if (r["rsi_ok"] and r["checks_ok"] == r["checks_total"]) else "❌"
        print(f"   {flag} {r['name']}: RSI={'ZELEN' if r['rsi_ok'] else 'X'} · "
              f"checks {r['checks_ok']}/{r['checks_total']} · {r['reason']}")
    print("=" * 70)
    return 0 if summary["rate"] >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
