"""chief/chief_of_staff.py — Chief of Staff, faza 1: zaprt dnevni krog.

Zakaj deterministično (brez LLM): cenen, testabilen, varen — infrastruktura
učnega kroga, ne še "pamet". LLM izbira/razlaga pride v fazi 2; tukaj je
pomembno, da je krog *zaprt in pošten*:

    model tebe → (dnevna aktivnost) → poročilo → tvoj popravek → v model

Ključne poštenosti:
  - nikoli ne izmišlja tvoje namere: če venture nima `next_action`, poročilo
    to pove ("čaka tvoj vnos") namesto da bi izumilo cilj;
  - "predlog za jutri" izhaja iz realnih signalov: modelovi `next_action` +
    današnji padli dogodki iz audit.jsonl;
  - `guard()` uveljavlja first_week_lock: pisanje/izvedba samo na nenevarnih
    delih (actions/tests/docs/chief), jedro sistema je zaklenjeno.

Varnost: nobena funkcija ne dvigne izjeme na manjkajoči datoteki — vrne
prazen/pravično stanje (CI-safe vzorec, kot skill_bridge).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Koren projekta = dve nivoja nad tem modulom (chief/chief_of_staff.py).
ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = ROOT / "chief" / "model.yaml"
DIGEST_DIR = ROOT / ".rob_ai" / "chief"
AUDIT_FILE = ROOT / ".rob_ai" / "audit.jsonl"

_DIGEST_TITLE = "Chief of Staff — dnevno poročilo"
_CORRECTION_HINT = "Popravke piši v chief/…/corrections/<datum>.md ali kar odgovori na poročilo."


# --------------------------------------------------------------------------- #
#  Model lastnika
# --------------------------------------------------------------------------- #
def load_model(path: Optional[Path] = None) -> dict:
    """Prebere model.yaml. Manjkajoč/neveljaven → {}. Nikoli ne dvigne."""
    p = Path(path) if path else MODEL_FILE
    try:
        import yaml  # PyYAML (v requirements-dev); brez njega pade spodaj
    except Exception:
        yaml = None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {}
    if yaml is not None:
        try:
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    # Fallback: minimalen regex preprostih "ključ: vrednost" vrstic.
    out: dict = {}
    for line in text.splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def ventures(model: dict) -> Dict[str, dict]:
    """Slovar aktivnih vložkov (venture) iz modela."""
    v = model.get("ventures", {})
    return v if isinstance(v, dict) else {}


def ventures_missing_next(model: dict) -> List[Tuple[str, str]]:
    """[(id, ime)] za vložke, ki čakajo na lastnikov naslednji korak."""
    out = []
    for vid, v in ventures(model).items():
        if isinstance(v, dict) and not (v.get("next_action") or "").strip():
            out.append((vid, str(v.get("name", vid))))
    return out


# --------------------------------------------------------------------------- #
#  Dnevna aktivnost (vir resnice: audit.jsonl)
# --------------------------------------------------------------------------- #
def _epoch_to_date(ts) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except Exception:
        return None


def audit_activity(audit_path: Optional[Path] = None,
                   date: Optional[str] = None) -> dict:
    """Povzetek aktivnosti za dan iz audit.jsonl: števci + padli projekti.

    Vrne {'total': n, 'by_status': {…}, 'ok': n, 'failed': n, 'failed_projects': [...]}.
    Manjkajoča datoteka → prazen povzetek (ni izjema).
    """
    p = Path(audit_path) if audit_path else AUDIT_FILE
    date = date or datetime.now().strftime("%Y-%m-%d")
    counts: Dict[str, int] = {}
    ok = failed = total = 0
    failed_projects: List[str] = []
    if not p.exists():
        return {"total": 0, "by_status": {}, "ok": 0, "failed": 0,
                "failed_projects": []}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"total": 0, "by_status": {}, "ok": 0, "failed": 0,
                "failed_projects": []}
    for ln in lines:
        if not ln.strip():
            continue
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        if _epoch_to_date(ev.get("ts")) != date:
            continue
        total += 1
        status = str(ev.get("status", "?") or "?")
        counts[status] = counts.get(status, 0) + 1
        if status == "ok":
            ok += 1
        else:
            failed += 1
            proj = str(ev.get("project", "?") or "?")
            if proj not in failed_projects:
                failed_projects.append(proj)
    return {"total": total, "by_status": counts, "ok": ok,
            "failed": failed, "failed_projects": failed_projects[:8]}


# --------------------------------------------------------------------------- #
#  Poročilo
# --------------------------------------------------------------------------- #
def propose_next(model: dict, activity: Optional[dict] = None) -> List[str]:
    """Predlogi za jutri — deterministično, samo iz resničnih signalov.

    1) venture z izpolnjenim next_action (po vrstnem redu v modelu),
    2) raziskava današnjih padlih dogodkov (če obstajajo).
    Nikoli ne izumlja cilja.
    """
    predlogi: List[str] = []
    for vid, v in ventures(model).items():
        if isinstance(v, dict):
            na = (v.get("next_action") or "").strip()
            if na:
                predlogi.append(f"[{vid}] {str(v.get('name', vid))}: {na}")
    act = activity or {}
    for proj in act.get("failed_projects", []):
        predlogi.append(f"Razišči današnje padle: {proj} (audit, samo branje).")
    return predlogi


def build_digest(model: dict, date: Optional[str] = None,
                 activity: Optional[dict] = None,
                 lessons: Optional[List[dict]] = None) -> str:
    """Sestavi dnevno poročilo (markdown). Ne piše na disk."""
    date = date or datetime.now().strftime("%Y-%m-%d")
    act = activity or {}
    lessons = lessons or []
    L: List[str] = [f"# {_DIGEST_TITLE} — {date}", ""]

    # 1) Zgodilo se je danes.
    L.append("## Zgodilo se je danes")
    total = act.get("total", 0)
    if total == 0:
        L.append("Danes ni zabeleženih dogodkov (audit prazen ali sistem ni tekel).")
    else:
        by = act.get("by_status", {})
        L.append(f"Skupaj {total} dogodkov: "
                 + ", ".join(f"{k}={by[k]}" for k in sorted(by)) + ".")
        if act.get("failed_projects"):
            L.append("Padli: " + ", ".join(act["failed_projects"]) + ".")
    L.append("")

    # 2) Posli iz modela — pošteno (tudi praznina).
    L.append("## Posli (model)")
    if not ventures(model):
        L.append("Model nima vložkov (chief/model.yaml je prazen).")
    else:
        for vid, v in ventures(model).items():
            if not isinstance(v, dict):
                continue
            name = str(v.get("name", vid))
            status = str(v.get("status", "?"))
            focus = (v.get("focus") or "").strip()
            next_a = (v.get("next_action") or "").strip()
            line = f"- **{name}** · {status}"
            if focus:
                line += f" · fokus: {focus}"
            if next_a:
                line += f" · naprej: {next_a}"
            else:
                line += " · ⏳ čaka tvoj vnos"
            L.append(line)
    L.append("")

    # 3) Predlog za jutri.
    L.append("## Predlog za jutri")
    predlogi = propose_next(model, act)
    if predlogi:
        for p_ in predlogi[:5]:
            L.append(f"- {p_}")
    else:
        L.append("Model nima naslednjih korakov in danes ni padlih dogodkov — "
                 "dopolni `next_action` v chief/model.yaml ali odgovori na to poročilo.")
    L.append("")

    # 4) Naučeno do zdaj (iz popravkov) — učenje, ki vpliva na naprej.
    L.append("## Naučeno do zdaj")
    if lessons:
        for le in lessons[:3]:
            L.append(f"- ({le.get('date')}) {str(le.get('lesson'))[:200]}")
        if len(lessons) > 3:
            L.append(f"… + {len(lessons) - 3} več (skupaj {len(lessons)} lekcij).")
    else:
        L.append("Ni še lekcij — tvoji popravki poročil postanejo učenje.")
    L.append("")

    # 5) Od tebe rabim.
    L.append("## Od tebe rabim")
    missing = ventures_missing_next(model)
    if missing:
        for vid, name in missing:
            L.append(f"- {name} ({vid}): določi naslednji korak (chief/model.yaml).")
    else:
        L.append("Nič — model ima naslednje korake za vse vložke.")
    L.append("")

    # 5) Učenje + varovalke.
    L.append("## Učenje in meja")
    L.append(_CORRECTION_HINT)
    L.append("- Prvi teden: pisanje/izvedba samo na actions/, tests/, docs/, chief/ "
             "— jedro (daemon/orchestrator/agenda) zaklenjeno.")
    return "\n".join(L)


def write_digest(digest_dir: Optional[Path] = None, date: Optional[str] = None,
                 model: Optional[dict] = None,
                 activity: Optional[dict] = None) -> Optional[Path]:
    """Zapiše poročilo v <dir>/<datum>.md + <dir>/latest.md (atomično).

    Vrne pot do datoteke ali None ob napaki (nikoli ne dvigne).
    """
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    date = date or datetime.now().strftime("%Y-%m-%d")
    model = model if model is not None else load_model()
    text = build_digest(model, date, activity)
    try:
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{date}.md"
        tmp = d / f"{date}.md.{os.getpid()}.tmp"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)                       # atomično (Windows-safe)
        (d / "latest.md").write_text(text, encoding="utf-8")
        return target
    except OSError:
        return None


# --------------------------------------------------------------------------- #
#  Učenje: popravki → lekcije, zgodovina poročil
# --------------------------------------------------------------------------- #
def _lessons_file(digest_dir: Path) -> Path:
    return digest_dir / "lessons.jsonl"


def _history_file(digest_dir: Path) -> Path:
    return digest_dir / "history.jsonl"


def load_lessons(digest_dir: Optional[Path] = None, limit: int = 50) -> List[dict]:
    """Lekcije (učni signal) iz .rob_ai/chief/lessons.jsonl, novejše prve."""
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    out: List[dict] = []
    f = _lessons_file(d)
    if f.exists():
        try:
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if not ln.strip():
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
        except OSError:
            pass
    out.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    return out[:limit]


def fold_corrections(digest_dir: Optional[Path] = None) -> int:
    """Popravke iz corrections/*.md strni v lessons.jsonl (idempotentno).

    Vsaka vrstica '— <iso>: <besedilo>' postane lekcija {date, lesson}.
    Vrne število na novo dodanih lekcij. Nikoli ne dvigne.
    """
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    cdir = d / "corrections"
    if not cdir.exists():
        return 0
    existing = load_lessons(d, limit=10 ** 6)
    have = {(str(x.get("date")), str(x.get("lesson"))) for x in existing}
    added = 0
    new_rows: List[dict] = []
    try:
        for mdf in sorted(cdir.glob("*.md")):
            date = mdf.stem
            for ln in mdf.read_text(encoding="utf-8", errors="replace").splitlines():
                s = ln.strip()
                if not s.startswith("- "):
                    continue
                rest = s[2:].strip()
                # Format: "- <iso>: <besedilo>" → ločilo je ": " (presledek za
                # dvopičjem), da se minuta v iso-času ne prilepi na lekcijo.
                idx = rest.find(": ")
                if idx < 0:
                    continue
                text = rest[idx + 2:].strip()
                if not text:
                    continue
                key = (date, text)
                if key in have:
                    continue
                have.add(key)
                new_rows.append({"date": date, "lesson": text,
                                 "ts": int(time.time())})
                added += 1
        if new_rows:
            with _lessons_file(d).open("a", encoding="utf-8") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        return 0
    return added


def record_history(digest_dir: Optional[Path] = None, date: Optional[str] = None,
                   model: Optional[dict] = None,
                   activity: Optional[dict] = None) -> bool:
    """Zgodovina poročil (za 7-dnevno meritev): datum, ok/failed, predlogi."""
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    date = date or datetime.now().strftime("%Y-%m-%d")
    model = model if model is not None else load_model()
    act = activity or {}
    predlogi = propose_next(model, act)
    try:
        d.mkdir(parents=True, exist_ok=True)
        row = {"date": date, "ok": act.get("ok", 0), "failed": act.get("failed", 0),
               "proposals": predlogi[:5], "ts": int(time.time())}
        with _history_file(d).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read_history(digest_dir: Optional[Path] = None, limit: int = 14) -> List[dict]:
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    out: List[dict] = []
    f = _history_file(d)
    if f.exists():
        try:
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if not ln.strip():
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
        except OSError:
            pass
    return out[-limit:]


def week_summary(digest_dir: Optional[Path] = None, days: int = 7) -> str:
    """Kratek povzetek zadnjih `days` dni (za oceno po prvem tednu)."""
    rows = read_history(digest_dir)
    if not rows:
        return "(ni še zgodovine poročil — zaženi `python -m chief --report` vsak dan)"
    recent = rows[-days:]
    ok = sum(int(r.get("ok", 0)) for r in recent)
    failed = sum(int(r.get("failed", 0)) for r in recent)
    days_run = len(recent)
    return (f"Zadnjih {days_run} dni: {ok} ok / {failed} failed dogodkov. "
            f"Dnevi: {', '.join(str(r.get('date')) for r in recent)}")


def append_correction(digest_dir: Optional[Path] = None, date: Optional[str] = None,
                      text: str = "") -> Optional[Path]:
    """Shrani lastnikov popravek (učni signal) v corrections/<datum>.md."""
    if not (text or "").strip():
        return None
    d = Path(digest_dir) if digest_dir else DIGEST_DIR
    date = date or datetime.now().strftime("%Y-%m-%d")
    try:
        cdir = d / "corrections"
        cdir.mkdir(parents=True, exist_ok=True)
        f = cdir / f"{date}.md"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"- {datetime.now().isoformat(timespec='minutes')}: "
                     f"{text.strip()}\n")
        return f
    except OSError:
        return None


# --------------------------------------------------------------------------- #
#  Varovalka prvega tedna
# --------------------------------------------------------------------------- #
def guard(rel_path: str, model: Optional[dict] = None) -> Tuple[bool, str]:
    """Ali sme chief pisati/izvajati na tej poti (prvi teden)?

    `rel_path` je pot, relativna na koren projekta (npr. "core/daemon.py").
    Dovoljeno: znotraj `allowed_write` in ne pod `locked`.
    Vrne (True, "ok") ali (False, razlog).
    """
    model = model if model is not None else load_model()
    lock = model.get("first_week_lock", {}) if isinstance(model, dict) else {}
    allowed = [str(x) for x in lock.get("allowed_write", [])]
    locked = [str(x) for x in lock.get("locked", [])]
    p = str(rel_path or "").replace("\\", "/").lstrip("./")

    for bad in locked:
        if p == bad or p.startswith(bad.rstrip("/") + "/"):
            return False, f"zaklenjeno v prvem tednu: {bad}"
    if not allowed:
        return False, "model nima first_week_lock.allowed_write"
    for a in allowed:
        if p.startswith(a.rstrip("/")):
            return True, "ok"
    return False, f"izven dovoljenih con: {', '.join(allowed)}"


# --------------------------------------------------------------------------- #
#  CLI (python -m chief)
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m chief",
                                 description="Chief of Staff — faza 1 (prvi teden).")
    ap.add_argument("--report", action="store_true",
                    help="Sestavi in zapiši dnevno poročilo ter ga izpiši.")
    ap.add_argument("--date", default=None, help="Datum poročila (YYYY-MM-DD).")
    ap.add_argument("--model", action="store_true", help="Izpiši model lastnika.")
    ap.add_argument("--guard", metavar="POT", default=None,
                    help="Preveri varovalko za pot (npr. core/daemon.py).")
    ap.add_argument("--correct", metavar="BESEDILO", default=None,
                    help="Shrani lastnikov popravek (učni signal).")
    ap.add_argument("--lessons", action="store_true",
                    help="Prikaži naučene lekcije (iz popravkov).")
    ap.add_argument("--history", action="store_true",
                    help="Prikaži zgodovino poročil.")
    ap.add_argument("--week", action="store_true",
                    help="Povzetek zadnjih 7 dni (meritev prvega tedna).")
    args = ap.parse_args(argv)

    if args.model:
        import yaml
        print(yaml.safe_dump(load_model(), allow_unicode=True, sort_keys=False)
              or "(model prazen)")
    if args.guard:
        ok, why = guard(args.guard)
        print(f"guard {args.guard}: {'DOVOLJENO' if ok else 'ZAVRNJENO'} — {why}")
    if args.correct:
        f = append_correction(date=args.date, text=args.correct)
        print(f"popravek shranjen: {f}" if f else "(popravek ni bil shranjen)")
    if args.lessons:
        for le in load_lessons():
            print(f"- ({le.get('date')}) {le.get('lesson')}")
        if not load_lessons():
            print("(ni še lekcij — popravki poročil postanejo lekcije)")
    if args.history:
        for r in read_history():
            print(f"- {r.get('date')}: ok={r.get('ok')} failed={r.get('failed')} "
                  f"| predlogi: {len(r.get('proposals', []))}")
        if not read_history():
            print("(ni še zgodovine poročil)")
    if args.week:
        print(week_summary())
    if args.report:
        added = fold_corrections()          # popravki → lekcije (idempotentno)
        if added:
            print(f"(v model vključenih {added} novih lekcij iz popravkov)")
        model = load_model()
        act = audit_activity(date=args.date)
        f = write_digest(date=args.date, model=model, activity=act)
        record_history(date=args.date, model=model, activity=act)
        print(build_digest(model, args.date, act, load_lessons()))
        print("\n" + ("zapisano: " + str(f) if f else "(zapis ni uspel)"))
    if not (args.report or args.model or args.guard or args.correct
            or args.lessons or args.history or args.week):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
