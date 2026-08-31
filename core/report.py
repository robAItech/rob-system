"""core/report.py — tedenski readout (vsi izvedeni taski + kvaliteta + eval + fleet).

Generira markdown poročilo (privzeto `.rob_ai/weekly_report.md`):
- povzetek (število izvedenih nalog v obdobju, ok/failed, uspešnost),
- izvedene naloge (audit `daemon-task` + `fleet-result` v obdobju),
- kakovost po projektih (`core.quality.project_quality` + zaporedni neuspehi),
- eval trend (`.rob_ai/eval_history.json`),
- operativna načela / vzorci / lekcije (reuse `learning_dashboard` virov),
- fleet (workerji + spomin),
- odprte eskalacije + onemogočeni targeti.

Uporaba:
  python core/report.py [--weeks N] [--out PATH] [--show]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit, quality  # noqa: E402
from core.learning_dashboard import (  # noqa: E402
    _eval_trend_block,
    _patterns_block,
    _principles_block,
    _recent_lessons_block,
)

DEFAULT_DB = PROJECT_ROOT / ".rob_ai" / "memory.db"
DEFAULT_OUT = PROJECT_ROOT / ".rob_ai" / "weekly_report.md"
EVAL_HISTORY_DEFAULT = PROJECT_ROOT / ".rob_ai" / "eval_history.json"


# ------------------------------------------------------------------ #
#  Podatki
# ------------------------------------------------------------------ #
def _executed_tasks(start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    """Izvedene naloge v obdobju — samo KONČNI izidi.

    `daemon-task` ima tudi `started` markerje (isti task = 2 vnosa), zato
    štejemo samo `ok`/`done`/`failed` (konec), da readout ne podvaja.
    """
    return [
        e for e in audit.query(start_ts=start_ts, end_ts=end_ts)
        if e.get("event") in quality.TASK_EVENTS
        and e.get("status") in ("ok", "done", "failed")
    ]


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Renderji (markdown)
# ------------------------------------------------------------------ #
def _render_summary(tasks: List[Dict[str, Any]]) -> str:
    n = len(tasks)
    ok = sum(1 for t in tasks if t.get("status") in ("ok", "done"))
    failed = sum(1 for t in tasks if t.get("status") == "failed")
    rate = f"{ok / n:.0%}" if n else "n/a"
    return (f"**Povzetek:** {n} izvedenih nalog · {ok} ok · {failed} failed · "
            f"uspešnost {rate}")


def _render_tasks(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return "_ni izvedenih nalog v obdobju_"
    rows = ["| Čas | Target | Event | Status | Detail |",
            "|---|---|---|---|---|"]
    for t in tasks[-100:]:
        ts = time.strftime("%m-%d %H:%M", time.localtime(t.get("ts", 0)))
        detail = (t.get("detail") or "")[:60].replace("|", "/")
        rows.append(f"| {ts} | {t.get('project', '?')} | {t.get('event', '?')} | "
                    f"{t.get('status', '?')} | {detail} |")
    if len(tasks) > 100:
        rows.append(f"| … | _+{len(tasks) - 100} več_ | | | |")
    return "\n".join(rows)


def _render_quality(db: Path) -> str:
    q = quality.project_quality(db)
    if not q:
        return "_ni podatkov (run_reviews)_"
    rows = ["| Projekt | Tekov | Zelenih | Neuspehov | Uspešnost | Zaporedni neusp. |",
            "|---|---:|---:|---:|---:|---:|"]
    for proj, m in sorted(q.items(), key=lambda kv: kv[1]["success_rate"]):
        cf = quality.consecutive_fails(proj)
        flag = " 🔒" if quality.is_disabled(proj) else ""
        rows.append(f"| {proj}{flag} | {m['runs']} | {m['green']} | {m['failed']} | "
                    f"{m['success_rate']:.0%} | {cf} |")
    return "\n".join(rows)


def _render_fleet() -> str:
    lines: List[str] = []
    try:
        wf = json.loads((PROJECT_ROOT / ".rob_ai" / "fleet_workers.json")
                        .read_text(encoding="utf-8"))
        for w, meta in wf.items():
            last = time.strftime("%Y-%m-%d %H:%M",
                                 time.localtime(meta.get("last_seen", 0)))
            lines.append(f"  worker `{w}` · zadnji stik {last}")
    except Exception:
        lines.append("  (ni workerjev)")
    try:
        from core.memory_sync import count_memory
        mem = count_memory()
        lines.append("  spomin: " + ", ".join(f"{k}={v}" for k, v in mem.items()))
    except Exception:
        pass
    return "\n".join(lines) if lines else "  (ni podatkov)"


def _render_escalations() -> str:
    lines: List[str] = []
    esc = quality.open_escalations()
    if esc:
        for e in esc:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("ts", 0)))
            lines.append(f"  ⚠️ [{ts}] `{e['project']}` — {e['reason']} ({e['detail']})")
    else:
        lines.append("  ✓ ni odprtih eskalacij")
    dis = quality.list_disabled()
    if dis:
        lines.append("  **Onemogočeni targeti:** " +
                     ", ".join(f"`{d['project']}`" for d in dis))
    return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Glavni generator
# ------------------------------------------------------------------ #
def generate_weekly_report(db_path: Optional[Path | str] = None,
                           weeks: int = 1,
                           now: Optional[int] = None) -> str:
    """Sestavi markdown tedenskega readouta. `now` omogoča deterministične teste."""
    db = Path(db_path) if db_path else DEFAULT_DB
    now_ts = int(now) if now is not None else _now()
    period_s = max(1, int(weeks)) * 7 * 86400
    start_ts = now_ts - period_s
    tasks = _executed_tasks(start_ts, now_ts)

    fmt = lambda ts: time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))  # noqa: E731
    return "\n".join([
        "# ROB system — tedenski readout",
        "",
        f"_Obdobje: {fmt(start_ts)} → {fmt(now_ts)} · generirano {fmt(now_ts)}_",
        "",
        _render_summary(tasks),
        "",
        "## Izvedene naloge",
        _render_tasks(tasks),
        "",
        "## Kakovost po projektih",
        _render_quality(db),
        "",
        "## Eval trend",
        _eval_trend_block(EVAL_HISTORY_DEFAULT),
        "",
        "## Operativna načela (P3)",
        _principles_block(db),
        "",
        "## Dominantni vzorci (P5)",
        _patterns_block(db),
        "",
        "## Zadnje lekcije",
        _recent_lessons_block(db, 8),
        "",
        "## Fleet",
        _render_fleet(),
        "",
        "## Eskalacije in onemogočeni targeti",
        _render_escalations(),
        "",
    ])


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rob report", description="Tedenski readout.")
    p.add_argument("--weeks", type=int, default=1, help="obdobje v tednih (privzeto 1)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="pot do izhodne datoteke")
    p.add_argument("--show", action="store_true", help="izpiši celoten report na stdout")
    args = p.parse_args(argv)

    md = generate_weekly_report(weeks=args.weeks)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    summary = next((ln for ln in md.split("\n") if ln.startswith("**Povzetek:**")), "")
    print(f"Report zapisan: {out}")
    if summary:
        print(summary)
    if args.show:
        print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
