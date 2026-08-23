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
import asyncio
import importlib
import inspect
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Repo koren na PYTHONPATH.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.eval_bugs import BUG_CASES, EvalBugError, check_bug_injectable, cleanup, inject_bug

# Vsili UTF-8 izhod (enako kot run_swarm.py), da emoji/šumniki ne crash-on
# Windows cp1250 (UnicodeEncodeError) v piped okoljih.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo


# ------------------------------------------------------------------ #
#  Tipi in načini eval case-ov (eval lestvica)
# ------------------------------------------------------------------ #
CASE_TYPES = ("function", "pydantic", "http", "bugfix")
CASE_MODES = ("single", "autonomous")
VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


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
    {
        "name": "text_stats",
        "type": "function",
        "mode": "single",
        "directive": (
            "Zgradi Python modul 'text_stats' v actions/text_stats/. "
            "Definiraj funkcijo `text_stats(text: str) -> dict`, ki vrne slovar s ključi "
            "'word_count' (število besed), 'char_count' (število znakov, ki NISO presledki; "
            "ločila štejejo) in 'sentence_count' (število povedi, ločenih z . ! ?). "
            "Prazno besedilo vrne same ničle. Primer: text_stats('Hello world.') mora vrniti "
            "{'word_count': 2, 'char_count': 11, 'sentence_count': 1}. "
            "Napiši pytest test za potrditev. Vsi testi 100% zeleni."
        ),
        "function_key": "text_stats",
        "checks": [
            ("Hello world.", {"word_count": 2, "char_count": 11, "sentence_count": 1}),
            ("", {"word_count": 0, "char_count": 0, "sentence_count": 0}),
            ("One. Two! Three?", {"word_count": 3, "char_count": 14, "sentence_count": 3}),
            ("  a   b  ", {"word_count": 2, "char_count": 2, "sentence_count": 0}),
        ],
    },
    {
        "name": "money_formatter",
        "type": "function",
        "mode": "single",
        "directive": (
            "Zgradi Python modul 'money_formatter' v actions/money_formatter/. "
            "Definiraj funkcijo `money_formatter(znesek: float) -> str`, ki znesek oblikuje "
            "v EUR niz po slovenski konvenciji: cela števila brez decimalk (5 -> '5 EUR'), "
            "drugače z dvema decimalkama in vejico (5.5 -> '5,50 EUR'), tisočice ločene s "
            "piko (1234567.89 -> '1.234.567,89 EUR'), negativni znesek ima predznak minus. "
            "Napiši pytest test za potrditev (vključno z robnimi primeri). Vsi testi 100% zeleni."
        ),
        "function_key": "money_formatter",
        "checks": [
            (5, "5 EUR"),
            (5.5, "5,50 EUR"),
            (0, "0 EUR"),
            (1234567.89, "1.234.567,89 EUR"),
            (-5.5, "-5,50 EUR"),
            (1000000, "1.000.000 EUR"),
        ],
    },
    {
        "name": "order_schema",
        "type": "pydantic",
        "mode": "single",
        "directive": (
            "Zgradi Python modul 'order_schema' v actions/order_schema/. "
            "V datoteki schemas.py definiraj Pydantic V2 razred `Order` s pravili: "
            "'id' je int večji od 0, 'customer' je neprazen str, 'items' je seznam "
            "slovarjev {'sku': str, 'quantity': int večje od 0}, 'total' je float >= 0. "
            "Uporabi Pydantic validacijo, da neveljavni podatki vržejo ValidationError. "
            "Napiši pytest test za potrditev. Vsi testi 100% zeleni."
        ),
        "schema_key": "Order",
        "valid_inputs": [
            {"id": 1, "customer": "Ana", "items": [{"sku": "A1", "quantity": 2}], "total": 10.0},
            {"id": 42, "customer": "B", "items": [], "total": 0.0},
        ],
        "invalid_inputs": [
            {"id": 0, "customer": "Ana", "items": [], "total": 1.0},
            {"id": 1, "customer": "", "items": [], "total": 1.0},
            {"id": 1, "customer": "Ana", "items": [{"sku": "A1", "quantity": 0}], "total": 1.0},
            {"id": 1, "customer": "Ana", "items": [], "total": -5.0},
        ],
    },
    {
        "name": "inventory_api",
        "type": "http",
        "mode": "single",
        "directive": (
            "Zgradi Python modul 'inventory_api' v actions/inventory_api/. "
            "Ustvari FastAPI aplikacijo s spremenljivko `app` in potmi: "
            "GET /health vrne {'status': 'ok'}; "
            "GET /items/{sku} vrne {'sku': ..., 'quantity': ...} za obstoječ sku, sicer HTTP 404; "
            "POST /items sprejme JSON {'sku': str, 'quantity': int >= 0} in vrne 201 z ustvarjenim "
            "artiklom. Uporabi trden spomin na nivoju modula (ni baze). "
            "Napiši pytest test za potrditev. Vsi testi 100% zeleni."
        ),
        "app_key": "app",
        "endpoint_checks": [
            ("GET", "/health", None, 200),
            ("GET", "/items/nepoznan", None, 404),
            ("POST", "/items", {"sku": "A1", "quantity": 5}, 201),
            ("GET", "/items/A1", None, 200),
        ],
    },
    {
        "name": "growth_report",
        "type": "function",
        "mode": "autonomous",
        "directive": (
            "Izracunaj rast podjetja in izdelaj Python modul 'growth_report' v actions/growth_report/. "
            "Definiraj funkcijo `growth_report(vrednosti: list[float]) -> dict`, ki iz seznama "
            "letnih vrednosti vrne slovar s ključi 'cagr' (sestavljena letna rast v odstotkih, "
            "zaokrožena na 2 decimalki) in 'growth_pct' (rast med zadnjim in prvim letom v odstotkih). "
            "Za prazen ali enoelementni seznam vrne {'cagr': 0.0, 'growth_pct': 0.0}. "
            "Napiši pytest test za potrditev. Vsi testi 100% zeleni."
        ),
        "function_key": "growth_report",
        "checks": [
            ([100.0, 110.0, 121.0], {"cagr": 10.0, "growth_pct": 21.0}),
            ([], {"cagr": 0.0, "growth_pct": 0.0}),
            ([50.0], {"cagr": 0.0, "growth_pct": 0.0}),
            ([100.0, 200.0], {"cagr": 100.0, "growth_pct": 100.0}),
        ],
    },
]


# P0 — idempotentna pripetev bugfix case-ov (real eval na zlatih modulih).
for _bc in BUG_CASES:
    if not any(c["name"] == _bc["name"] for c in EVAL_CASES):
        EVAL_CASES.append(_bc)


def validate_case(case: Dict) -> List[str]:
    """Vrne seznam napak strukture case-a; prazen seznam = veljaven.

    Type-aware: function zahteva function_key+checks; pydantic zahteva
    valid_inputs+invalid_inputs; http zahteva endpoint_checks; bugfix zahteva
    source_module + bug + function_key + total + checks|verify.
    """
    errs: List[str] = []
    name = case.get("name", "")
    if not name or not name.isidentifier():
        errs.append("'name' mora biti veljaven identifikator")
    d = case.get("directive", "")
    if not isinstance(d, str) or len(d) <= 20:
        errs.append("'directive' prekratka ali manjka")
    ctype = case.get("type", "function")
    if ctype not in CASE_TYPES:
        errs.append(f"neznan 'type': {ctype!r}")
    mode = case.get("mode", "single")
    if mode not in CASE_MODES:
        errs.append(f"neznan 'mode': {mode!r}")
    if ctype == "function":
        fk = case.get("function_key", name)
        if not fk or not fk.isidentifier():
            errs.append("'function_key' ni veljaven identifikator")
        checks = case.get("checks", [])
        if not isinstance(checks, list) or not checks:
            errs.append("'checks' mora biti neprazen seznam")
        else:
            for ch in checks:
                if not isinstance(ch, (tuple, list)) or len(ch) < 2:
                    errs.append(f"check {ch!r} mora imeti vsaj (vhod, izhod)")
    elif ctype == "pydantic":
        sk = case.get("schema_key")
        if sk is not None and not sk.isidentifier():
            errs.append("'schema_key' ni veljaven identifikator")
        for key in ("valid_inputs", "invalid_inputs"):
            val = case.get(key, [])
            if not isinstance(val, list) or not val:
                errs.append(f"pydantic case potrebuje neprazen '{key}'")
            else:
                for inp in val:
                    if not isinstance(inp, dict):
                        errs.append(f"vhod {inp!r} v '{key}' mora biti dict")
    elif ctype == "http":
        ak = case.get("app_key", "app")
        if not isinstance(ak, str) or not ak:
            errs.append("'app_key' mora biti str")
        ecs = case.get("endpoint_checks", [])
        if not isinstance(ecs, list) or not ecs:
            errs.append("'endpoint_checks' mora biti neprazen seznam")
        else:
            for ec in ecs:
                if not isinstance(ec, (tuple, list)) or len(ec) < 2:
                    errs.append(f"endpoint_check {ec!r} mora biti (method, path[, body][, status])")
                    continue
                if not isinstance(ec[0], str) or ec[0].upper() not in VALID_HTTP_METHODS:
                    errs.append(f"neveljaven HTTP method: {ec[0]!r}")
    elif ctype == "bugfix":
        sm = case.get("source_module")
        if not isinstance(sm, str) or not sm.isidentifier():
            errs.append("'source_module' mora biti veljaven identifikator")
        bugs = case.get("bug", [])
        if not isinstance(bugs, list) or not bugs:
            errs.append("'bug' mora biti neprazen seznam (file, old, new)")
        else:
            for b in bugs:
                if not isinstance(b, (tuple, list)) or len(b) != 3 or not all(isinstance(x, str) for x in b):
                    errs.append(f"bug {b!r} mora biti (file, old, new) — vsi str")
        fk = case.get("function_key", "")
        if not isinstance(fk, str) or not fk:
            errs.append("'bugfix' potrebuje 'function_key'")
        if not (isinstance(case.get("checks"), list) and case.get("checks")) and not callable(case.get("verify")):
            errs.append("'bugfix' potrebuje 'checks' (z extract) ali 'verify' callable")
        if not isinstance(case.get("total", 0), int) or case.get("total", 0) <= 0:
            errs.append("'bugfix' potrebuje 'total' > 0")
    if "function" in case and not callable(case.get("function")):
        errs.append("'function' mora biti klicljiv (ali odsoten)")
    return errs


# ------------------------------------------------------------------ #
#  Eval engine
# ------------------------------------------------------------------ #
class AutonomyEval:
    def __init__(self, cases: List[Dict], keep_artifacts: bool = False) -> None:
        self.cases = cases
        self.keep_artifacts = keep_artifacts
        self.results: List[dict] = []

    # -- ujemi funkcijo iz actions/<name>/ (neodvisno od pokvarjenega imena) ---
    @staticmethod
    def _discover_module_dir(name: str) -> Path:
        return ROOT / "actions" / name

    @classmethod
    def _import_module(cls, name: str, py: Path):
        """Paketni uvoz `actions.<name>.<stem>` (omogoča `from actions.<name>...`
        znotraj modulov), padec na goli `importlib.util` uvoz iz datoteke.

        Vrne modul ali None. Ne uvozi test_ datotek (kličejoč).
        """
        import importlib.util

        modname = f"actions.{name}.{py.stem}"
        if modname in sys.modules:
            return sys.modules[modname]
        try:
            return importlib.import_module(modname)
        except Exception:
            spec = importlib.util.spec_from_file_location(py.stem, py)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                return None
            return mod

    @classmethod
    def _load_checkable_func(cls, name: str, func_name: str):
        """Poišči funkcijo v kateremkoli .py v actions/<name>/. Vrne funkcijo.

        Robustno: poskusi paketni uvoz (za `from actions.<name>...` znotraj
        modulov), sicer goli uvoz iz datoteke. Ne uvozi test_ datotek.
        """
        mod_dir = cls._discover_module_dir(name)
        if not mod_dir.exists():
            return None
        for py in sorted(mod_dir.glob("*.py")):
            if py.name.startswith("test_"):
                continue
            mod = cls._import_module(name, py)
            if mod is None:
                continue
            fn = getattr(mod, func_name, None)
            if callable(fn):
                return fn
        return None

    # -- en primer kot smoke (dry-run): samo zazna strukturo, ne kliče LLM --
    def smoke_check(self, case: Dict) -> bool:
        """Preveri, da je case dobro oblikovan (brez LLM/RSI). Vrne True."""
        return not validate_case(case)

    @staticmethod
    def _expected_checks(case: Dict) -> int:
        """Število pričakovanih neodvisnih preverb glede na tip case-a."""
        ctype = case.get("type", "function")
        if ctype == "pydantic":
            return len(case.get("valid_inputs", [])) + len(case.get("invalid_inputs", []))
        if ctype == "http":
            return len(case.get("endpoint_checks", []))
        if ctype == "bugfix":
            return int(case.get("total", 0)) or len(case.get("checks", []))
        return len(case.get("checks", []))

    @classmethod
    def _load_schema_class(cls, name: str, schema_key: Optional[str] = None):
        """Najdi Pydantic BaseModel razred v actions/<name>/ (preskoči test_*).

        Če je `schema_key` podan, vrne razred s tem imenom ali None (ne ugiba).
        Brez njega vrne prvi najdeni BaseModel razred.
        """
        from pydantic import BaseModel
        mod_dir = cls._discover_module_dir(name)
        if not mod_dir.exists():
            return None
        candidates: List[type] = []
        for py in sorted(mod_dir.glob("*.py")):
            if py.name.startswith("test_"):
                continue
            mod = cls._import_module(name, py)
            if mod is None:
                continue
            for attr in vars(mod).values():
                if isinstance(attr, type) and issubclass(attr, BaseModel) and attr is not BaseModel:
                    if schema_key and attr.__name__ == schema_key:
                        return attr
                    candidates.append(attr)
        if not candidates:
            return None
        if schema_key:
            for c in candidates:
                if c.__name__ == schema_key:
                    return c
            return None  # specificen razred ni najden — ne ugibaj
        return candidates[0]

    @classmethod
    def _load_app(cls, name: str, app_key: str = "app"):
        """Najdi FastAPI instanco (ali APIRouter) v actions/<name>/.

        Najprej eksplicitni atribut `app_key`, nato skenira vse `.py` za katero
        koli FastAPI/APIRouter instanco. APIRouter se ovije v FastAPI.
        """
        from fastapi import FastAPI
        from fastapi.routing import APIRouter
        mod_dir = cls._discover_module_dir(name)
        if not mod_dir.exists():
            return None
        for py in sorted(mod_dir.glob("*.py")):
            if py.name.startswith("test_"):
                continue
            mod = cls._import_module(name, py)
            if mod is None:
                continue
            if app_key:
                val = getattr(mod, app_key, None)
                if isinstance(val, FastAPI):
                    return val
                if isinstance(val, APIRouter):
                    app = FastAPI()
                    app.include_router(val)
                    return app
            for val in vars(mod).values():
                if isinstance(val, FastAPI):
                    return val
                if isinstance(val, APIRouter):
                    app = FastAPI()
                    app.include_router(val)
                    return app
        return None

    def _verify_function_inline(self, name: str, case: Dict) -> dict:
        fk = case.get("function_key", name)
        fn = self._load_checkable_func(name, fk)
        total = len(case.get("checks", []))
        if fn is None:
            return {"checks_ok": 0, "checks_total": total,
                    "reason": f"funkcija '{fk}' ni najdena v actions/{name}/"}
        checks_ok = 0
        for check in case["checks"]:
            try:
                got = fn(*check[:-1]) if len(check) > 2 else fn(check[0])
                expected = check[-1]
                if got == expected or (expected is None and got is None):
                    checks_ok += 1
            except Exception:
                pass
        reason = ("vsi neodvisni preveri zeleni" if checks_ok == total
                  else f"{checks_ok}/{total} neodvisnih preverov zelenih")
        return {"checks_ok": checks_ok, "checks_total": total, "reason": reason}

    def _verify_pydantic_inline(self, name: str, case: Dict) -> dict:
        from pydantic import ValidationError
        cls = self._load_schema_class(name, case.get("schema_key"))
        if cls is None:
            return {"checks_ok": 0, "checks_total": self._expected_checks(case),
                    "reason": f"shema '{case.get('schema_key')}' ni najdena v actions/{name}/"}
        ok = total = 0
        for inp in case.get("valid_inputs", []):
            total += 1
            try:
                cls(**inp)
                ok += 1
            except Exception:
                pass
        for inp in case.get("invalid_inputs", []):
            total += 1
            try:
                cls(**inp)
            except ValidationError:
                ok += 1
            except Exception:
                pass  # vrgel napačno vrsto napake → šteje kot neuspeh
        reason = ("vsi pydantic preveri zeleni" if ok == total
                  else f"{ok}/{total} pydantic preverov zelenih")
        return {"checks_ok": ok, "checks_total": total, "reason": reason}

    def _verify_http_inline(self, name: str, case: Dict) -> dict:
        from fastapi.testclient import TestClient
        app = self._load_app(name, case.get("app_key", "app"))
        if app is None:
            return {"checks_ok": 0, "checks_total": self._expected_checks(case),
                    "reason": f"FastAPI app ni najden v actions/{name}/"}
        ok = total = 0
        try:
            with TestClient(app) as client:
                for ec in case.get("endpoint_checks", []):
                    total += 1
                    method = str(ec[0]).upper()
                    path = ec[1]
                    body = ec[2] if len(ec) > 2 else None
                    expected = int(ec[3]) if len(ec) > 3 else 200
                    try:
                        resp = client.request(method, path, json=body)
                        if resp.status_code == expected:
                            ok += 1
                    except Exception:
                        pass
        except Exception as e:
            return {"checks_ok": ok, "checks_total": max(total, 1),
                    "reason": f"TestClient zagon ni uspel: {e}"}
        reason = ("vsi HTTP preveri zeleni" if ok == total
                  else f"{ok}/{total} HTTP preverov zelenih")
        return {"checks_ok": ok, "checks_total": total, "reason": reason}

    def _verify_in_subprocess(self, name: str, case: Dict, timeout: int = 90) -> dict:
        """Pydantic/http verifier v podprocesu s trdim timeoutom.

        LLM-generiran modul lahko visi na importu (zanka, omrežni klic brez
        timeouta) — podproces se ob prekoračitvi prekine. Function verifier
        ostane in-process (ohranja obstoječi mock test).
        """
        import os
        import subprocess
        case_json = json.dumps(case, ensure_ascii=False)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--verify-only", name],
                input=case_json, capture_output=True, encoding="utf-8",
                timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return {"checks_ok": 0, "checks_total": self._expected_checks(case),
                    "reason": f"verifikacija prekinjena po {timeout}s (možen zanko uvoz)"}
        prefix = "EVALVERIFY:"
        for line in (r.stdout or "").splitlines():
            if line.startswith(prefix):
                try:
                    return json.loads(line[len(prefix):])
                except Exception:
                    break
        return {"checks_ok": 0, "checks_total": self._expected_checks(case),
                "reason": f"podproces verifikacije ni vrnil rezultata (rc={r.returncode})"}

    def _verify_inline_dispatch(self, name: str, case: Dict) -> dict:
        ctype = case.get("type", "function")
        if ctype == "pydantic":
            return self._verify_pydantic_inline(name, case)
        if ctype == "http":
            return self._verify_http_inline(name, case)
        return self._verify_function_inline(name, case)

    # -- pokreni eval enega case (pravi RSI) -------------------------------
    def run_case(self, case: Dict) -> dict:
        if case.get("type") == "bugfix":
            return self._run_bugfix_case(case)
        name = case["name"]
        directive = case["directive"]
        ctype = case.get("type", "function")
        mode = case.get("mode", "single")
        res = {"name": name, "type": ctype, "mode": mode,
               "rsi_ok": False, "checks_ok": 0,
               "checks_total": self._expected_checks(case),
               "func": case.get("function_key", name), "reason": "",
               "wall_seconds": 0.0}
        print(f"\n🎯 [P5] EVAL case: {name} ({ctype}/{mode})")
        print(f"   direktiva: {directive[:120]}...")

        # 1) RSI zanka (gbrain→gstack→hermes→loopx/pytest) — single ali autonomous.
        #    Korak 7: try/except — padec enega case-a ne sme zrušiti run_all.
        from core.orchestrator import RobAIOrchestrator
        t0 = time.monotonic()
        try:
            rsi_ok = (RobAIOrchestrator.run_autonomous(name, directive) if mode == "autonomous"
                      else RobAIOrchestrator.run(name, directive))
        except Exception as e:
            rsi_ok = False
            res["reason"] = f"RSI zanka je padla: {e!r}"
        res["wall_seconds"] = round(time.monotonic() - t0, 1)
        res["rsi_ok"] = rsi_ok
        if not rsi_ok:
            if not res["reason"]:
                res["reason"] = "RSI ni zelen"
            return res

        # Best-effort meritve iz eval podatkov (attempts, LLM klici).
        res["attempts"] = _read_attempts(name)
        res["llm_calls"] = _read_llm_calls(name)

        # 2) Lastna verifikacija (neodvisna od LLM testov). Pydantic/http tečeta
        #    v podprocesu s timeoutom — LLM modul lahko visi na importu.
        ver = (self._verify_in_subprocess(name, case)
               if ctype in ("pydantic", "http")
               else self._verify_function_inline(name, case))
        res["checks_ok"] = ver["checks_ok"]
        res["checks_total"] = ver["checks_total"]
        res["reason"] = ver["reason"]
        print(f"   → neodvisni preveri: {res['checks_ok']}/{res['checks_total']} ({res['reason']})")
        return res

    # -- P0: real bugfix (inject → RSI popravi → neodvisna verifikacija) ----
    def _run_bugfix_case(self, case: Dict) -> dict:
        """Bugfix case: inject bug → RSI popravi → neodvisna verifikacija."""
        name, directive = case["name"], case["directive"]
        res = {"name": name, "type": "bugfix", "mode": "single", "rsi_ok": False,
               "checks_ok": 0, "checks_total": self._expected_checks(case),
               "func": case.get("function_key", name), "reason": "", "wall_seconds": 0.0}
        print(f"\n🎯 [P0] EVAL bugfix: {name} (vir: {case['source_module']})")
        try:
            inject_bug(case)                      # (0) setup PRED RSI — RAISE ob nenajdeni bug string
        except Exception as e:
            res["reason"] = f"bug ni vnesen: {e!r}"
            return res
        from core.orchestrator import RobAIOrchestrator
        t0 = time.monotonic()
        try:
            rsi_ok = RobAIOrchestrator.run(name, directive)   # (1) RSI, mode=single
        except Exception as e:
            rsi_ok = False
            res["reason"] = f"RSI zanka je padla: {e!r}"
        res["wall_seconds"] = round(time.monotonic() - t0, 1)
        res["rsi_ok"] = rsi_ok
        if not rsi_ok:
            if not res["reason"]:
                res["reason"] = "RSI ni zelen (bug ostaja v actions/<name>/)"
            self._maybe_cleanup(case)
            return res
        res["attempts"] = _read_attempts(name)
        res["llm_calls"] = _read_llm_calls(name)
        ver = self._verify_bugfix_inline(name, case)          # (2) neodvisna verifikacija
        res["checks_ok"] = ver["checks_ok"]
        res["checks_total"] = ver["checks_total"]
        res["reason"] = ver["reason"]
        print(f"   → neodvisni preveri: {res['checks_ok']}/{res['checks_total']} ({ver['reason']})")
        self._maybe_cleanup(case)
        return res

    def _maybe_cleanup(self, case: Dict) -> None:
        if not self.keep_artifacts:
            cleanup(case)

    def _find_module_with(self, name: str, attr: str):
        """Poišči modul (v actions/<name>/) z atributom `attr` (preskoči test_*)."""
        mod_dir = self._discover_module_dir(name)
        if not mod_dir.exists():
            return None
        for py in sorted(mod_dir.glob("*.py")):
            if py.name.startswith("test_"):
                continue
            mod = self._import_module(name, py)
            if mod is not None and hasattr(mod, attr):
                return mod
        return None

    def _resolve_bugfix_target(self, name: str, case: Dict):
        """Razreši function_key: dotted 'Class.method' ali razred/funkcija."""
        fk = case["function_key"]
        if "." in fk:
            cls_name, method = fk.rsplit(".", 1)
            cls = self._load_checkable_func(name, cls_name)
            if cls is None:
                return None, self._find_module_with(name, cls_name)
            return getattr(cls(), method), self._find_module_with(name, cls_name)
        mod = self._find_module_with(name, fk)
        val = self._load_checkable_func(name, fk)
        if val is None:
            return None, mod
        if inspect.isclass(val):
            return val(), mod
        return val, mod

    def _run_function_checks(self, target, case: Dict, total: int) -> dict:
        """Data-driven bugfix checks: (args..., expected). Async/RAISE/extract aware."""
        extract = case.get("extract", lambda r: r)
        is_async = inspect.iscoroutinefunction(target) or (
            inspect.ismethod(target) and inspect.iscoroutinefunction(target.__func__))
        checks_ok = 0
        for check in case.get("checks", []):
            args, expected = check[:-1], check[-1]
            try:
                if isinstance(expected, str) and expected.startswith("RAISE:"):
                    try:
                        if is_async:
                            asyncio.run(target(*args))
                        else:
                            target(*args)
                    except Exception as e:
                        if type(e).__name__ == expected[6:]:
                            checks_ok += 1
                    continue
                if is_async:
                    got = asyncio.run(target(*args))
                else:
                    got = target(*args)
                if extract(got) == expected:
                    checks_ok += 1
            except Exception:
                pass
        reason = ("vsi neodvisni preveri zeleni" if checks_ok == total
                  else f"{checks_ok}/{total} neodvisnih preverov zelenih")
        return {"checks_ok": checks_ok, "checks_total": total, "reason": reason}

    def _verify_bugfix_inline(self, name: str, case: Dict) -> dict:
        """P0 — neodvisna verifikacija bugfix modula (funkcija ali verify callable)."""
        total = int(case.get("total", 0)) or len(case.get("checks", []))
        verify = case.get("verify")
        if verify is not None:
            target, mod = self._resolve_bugfix_target(name, case)
            if target is None:
                return {"checks_ok": 0, "checks_total": total,
                        "reason": f"target '{case['function_key']}' ni najden v actions/{name}/"}
            try:
                if inspect.iscoroutinefunction(verify):
                    res = asyncio.run(verify(target, mod))
                else:
                    res = verify(target, mod)
            except Exception as e:
                return {"checks_ok": 0, "checks_total": total, "reason": f"verify je padla: {e!r}"}
            if isinstance(res, dict):
                return {"checks_ok": int(res.get("checks_ok", 0)),
                        "checks_total": int(res.get("checks_total", total)),
                        "reason": res.get("reason", "")}
            if isinstance(res, (tuple, list)) and len(res) >= 3:
                return {"checks_ok": int(res[0]), "checks_total": int(res[1]), "reason": str(res[2])}
            ok = 1 if res else 0
            return {"checks_ok": ok, "checks_total": total,
                    "reason": "ok" if ok else "verify ni uspela"}
        target, _mod = self._resolve_bugfix_target(name, case)
        if target is None:
            return {"checks_ok": 0, "checks_total": total,
                    "reason": f"target '{case['function_key']}' ni najden v actions/{name}/"}
        return self._run_function_checks(target, case, total)

    def _run_case_guarded(self, case: Dict) -> dict:
        """Korak 7 — izolacija: vse izjeme posameznega case-a → dict, ne padec."""
        try:
            return self.run_case(case)
        except Exception as e:
            return {
                "name": case.get("name", "?"),
                "type": case.get("type", "function"),
                "mode": case.get("mode", "single"),
                "rsi_ok": False,
                "checks_ok": 0,
                "checks_total": self._expected_checks(case),
                "func": case.get("function_key", case.get("name", "?")),
                "reason": f"eval case je padel: {e!r}",
                "wall_seconds": 0.0,
            }

    def run_all(self, workers: int = 2) -> Dict[str, float]:
        """Korak 7 — vzporedno izvajanje case-ov.

        `executor.map` ohranja vrstni red vhodov → `self.results` po indeksu case-ov,
        neodvisno od tega, kdaj kateri thread konča. workers=1 → sekvenčno (a še
        vedno izolirano per-case).
        """
        if workers <= 1:
            self.results = [self._run_case_guarded(c) for c in self.cases]
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                self.results = list(ex.map(self._run_case_guarded, self.cases))
        passed = sum(1 for r in self.results if r["rsi_ok"] and r["checks_ok"] == r["checks_total"])
        total = len(self.results)
        return {"passed": passed, "total": total, "rate": (passed / total) if total else 0.0}


# ------------------------------------------------------------------ #
#  Meritveno sledenje (opazljivost avtonomnosti skozi čas)
# ------------------------------------------------------------------ #
HISTORY_FILE = ROOT / ".rob_ai" / "eval_history.json"


def _read_history() -> List[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _append_history(entry: dict) -> None:
    """Doda meritev v eval zgodovino (append). Tolerantno: napaka → opozorilo."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        hist = _read_history()
        hist.append(entry)
        HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] ni mogoče shraniti eval zgodovine: {e}")


def _read_attempts(name: str) -> Optional[int]:
    """Best-effort: zadnje število poskusov heala iz .loopx/registry.json."""
    try:
        reg = json.loads((ROOT / ".loopx" / "registry.json").read_text(encoding="utf-8"))
        if reg.get("project") == name and reg.get("current_attempt"):
            return int(reg["current_attempt"])
    except Exception:
        pass
    return None


def _read_llm_calls(name: str) -> Optional[int]:
    """Best-effort: število LLM klicev zadnjega RSI teka iz audit.jsonl."""
    try:
        lines = (ROOT / ".rob_ai" / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("event") == "rsi-run" and e.get("project") == name:
            v = e.get("llm_calls")
            return int(v) if isinstance(v, (int, float)) else None
    return None


def _render_markdown_report(results: List[dict], summary: Dict[str, float], started_iso: str) -> str:
    """Markdown poročilo teka: tabela case-ov + rezultat (za nočni CI artifact)."""
    lines = [
        f"# P5 Eval avtonomnosti — {started_iso}", "",
        f"**Rezultat: {summary['passed']}/{summary['total']} ({summary['rate'] * 100:.0f}%)**", "",
        "| Case | Tip | Mode | RSI | Preveri | Čas (s) | Opomba |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        rsi = "ZELEN" if r["rsi_ok"] else "FAIL"
        lines.append(
            f"| {r['name']} | {r.get('type', 'function')} | {r.get('mode', 'single')} | "
            f"{rsi} | {r['checks_ok']}/{r['checks_total']} | "
            f"{r.get('wall_seconds', 0)} | {r.get('reason', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rob eval",
        description="P5 SWE-bench stila samo-eval za avtonomnost RSI-GStack.",
    )
    p.add_argument("--limit", type=int, default=None, help="samo prvih N case-ov")
    p.add_argument("--target", metavar="NAME", default=None, help="samo en case po imenu")
    p.add_argument("--dry-run", action="store_true",
                   help="samo strukturna preverba EVAL_CASES (brez LLM/RSI)")
    p.add_argument("--history", type=int, nargs="?", const=5, metavar="N",
                   help="izpiši zadnjih N meritvenih vnosov (trend) iz eval zgodovine")
    p.add_argument("--report", metavar="PATH", default=None,
                   help="zapiši Markdown poročilo teka ('-' za stdout)")
    p.add_argument("--verify-only", metavar="NAME", default=None,
                   help="interno: preveri en case iz stdin (podprocesna izolacija)")
    p.add_argument("--workers", type=int, default=2,
                   help="število vzporednih eval tekov (1 = sekvenčno)")
    p.add_argument("--keep-artifacts", action="store_true",
                   help="ohrani bugfix kopije v actions/ (default: počiščene)")
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

    # Interno za podprocesno izolacijo pydantic/http verifierja: preveri en case
    # iz stdin in izpiše rezultat v eni vrstici s prefiksom EVALVERIFY:.
    if args.verify_only:
        # stdin OBDVEZNO UTF-8: case_json vsebuje šumnike (č/ž/š) — sys.stdin.read()
        # bi na Windows dekodiral s cp1252 → UnicodeDecodeError → rc=1 (lažni FAIL
        # order_schema/inventory_api v vsakem eval teku). Tudi stdout/err UTF-8.
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
        case = json.loads(sys.stdin.read())
        res = AutonomyEval([])._verify_inline_dispatch(args.verify_only, case)
        sys.stdout.write("EVALVERIFY:" + json.dumps(res, ensure_ascii=False) + "\n")
        return 0

    print("=" * 70)
    print("🤖 P5 — SWE-bench stila samo-eval za avtonomnost")
    print("=" * 70)

    # --history: izpiši trend meritvenih vnosov (brez ponovnega LLM teka).
    if args.history is not None:
        from datetime import datetime
        hist = _read_history()
        n = min(args.history, len(hist)) if hist else 0
        print(f"📈 Eval zgodovina (zadnjih {n} od {len(hist)} tekov):")
        if not hist:
            print("   (ni zabeleženih tekov)")
        for e in hist[-n:] if n else []:
            dt = e.get("date", "?")
            print(f"   {dt}  {e.get('passed','?')}/{e.get('total','?')}  "
                  f"({(e.get('rate',0)*100):.0f}%)")
        return 0

    if args.dry_run:
        evaluator = AutonomyEval(cases)
        ok = all(evaluator.smoke_check(c) for c in cases)
        # P0 — pre-flight bugfix: old stringi enolični v source (lovi drift).
        for c in cases:
            if c.get("type") == "bugfix":
                errs = check_bug_injectable(c)
                if errs:
                    ok = False
                    print(f"  [P0] {c['name']}: bug ni injektabilen → {errs}")
        print(f"Dry-run: {len(cases)} case-ov strukturno veljavnih: {ok}")
        return 0 if ok else 1

    # Potrdi prisotnost tipke in Dockerja pred dragim eval zagonom.
    evaluator = AutonomyEval(cases, keep_artifacts=args.keep_artifacts)
    summary = evaluator.run_all(workers=max(1, args.workers))
    print("\n" + "=" * 70)
    print(f"📊 PREHOD RATE: {summary['passed']}/{summary['total']} "
          f"({summary['rate'] * 100:.0f}%)")
    for r in evaluator.results:
        flag = "✅" if (r["rsi_ok"] and r["checks_ok"] == r["checks_total"]) else "❌"
        print(f"   {flag} {r['name']}: RSI={'ZELEN' if r['rsi_ok'] else 'X'} · "
              f"checks {r['checks_ok']}/{r['checks_total']} · {r['reason']}")
    print("=" * 70)

    # Meritveno sledenje: shrani ta tek v zgodovino (opazljivost skozi čas).
    from datetime import datetime, timezone
    started_iso = datetime.now(timezone.utc).isoformat()
    cases_out = {}
    for r in evaluator.results:
        entry = {"rsi_ok": r["rsi_ok"], "checks_ok": r["checks_ok"],
                 "checks_total": r["checks_total"]}
        for k in ("type", "mode", "wall_seconds", "attempts", "llm_calls"):
            if r.get(k) is not None:
                entry[k] = r[k]
        cases_out[r["name"]] = entry
    _append_history({
        "date": started_iso,
        "passed": summary["passed"],
        "total": summary["total"],
        "rate": summary["rate"],
        "cases": cases_out,
    })

    # Markdown poročilo teka (za nočni CI eval → artifact).
    if args.report:
        md = _render_markdown_report(evaluator.results, summary, started_iso)
        if args.report == "-":
            print(md)
        else:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(md, encoding="utf-8")
            print(f"📄 Poročilo zapisano: {args.report}")
    return 0 if summary["rate"] >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
