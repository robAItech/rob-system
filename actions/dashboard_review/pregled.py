"""actions/dashboard_review/pregled.py — determinističen pregled dashboarda.

Bere IZVORNE datoteke (brez omrežja, brez poganjanja strežnika):
  - src/server.ts        → API poti (stringi '/api/...') + števci
  - src/web/components/  → komponente frontenda v2

Vrne strukturiran slovar in/ali izpiše markdown povzetek. Robustno: manjkajoča
datoteka → prazen rezultat (CI-safe), nikoli ne dvigne.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

# actions/dashboard_review/pregled.py → koren projekta = tri nivoje gor.
ROOT = Path(__file__).resolve().parents[2]
SERVER_TS = ROOT / "src" / "server.ts"
WEB_DIR = ROOT / "src" / "web"

_API_RE = re.compile(r"['\"]/api/([A-Za-z0-9_/:.-]+)['\"]")


def endpoints(server_text: str | None = None) -> List[str]:
    """Razvrščen seznam API poti iz src/server.ts (unikati)."""
    if server_text is None:
        try:
            server_text = SERVER_TS.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    return sorted({f"/api/{m}" for m in _API_RE.findall(server_text)})


def components(web_dir: Path | None = None) -> List[str]:
    """Imena komponent frontenda v2 (src/web/components/*.ts)."""
    d = web_dir or (WEB_DIR / "components")
    try:
        return sorted(p.name for p in d.glob("*.ts"))
    except OSError:
        return []


def summarize() -> Dict[str, object]:
    """Povzetek površine dashboarda za poročilo."""
    eps = endpoints()
    comps = components()
    # Glavne skupine poti (po prvem segmentu po /api/).
    groups: Dict[str, int] = {}
    for e in eps:
        seg = e.split("/")[2] if len(e.split("/")) > 2 else e
        groups[seg] = groups.get(seg, 0) + 1
    return {
        "server_ts_lines": (SERVER_TS.read_text(encoding="utf-8",
                                                errors="replace").count("\n")
                            if SERVER_TS.exists() else 0),
        "api_endpoints": len(eps),
        "api_groups": dict(sorted(groups.items())),
        "frontend_components": comps,
        "frontend_files": sorted(p.name for p in (WEB_DIR / "components").glob("*"))
                          if (WEB_DIR / "components").exists() else [],
    }


def main() -> int:
    s = summarize()
    eps = endpoints()
    print("# Dashboard — površina (pregledovalnik)")
    print(f"\n`src/server.ts`: {s['server_ts_lines']} vrstic · "
          f"{s['api_endpoints']} API poti")
    if s["api_groups"]:
        print("\nAPI skupine:")
        for g, n in s["api_groups"].items():
            print(f"  - /api/{g}: {n}")
    print("\nFrontend v2 komponente: " + (", ".join(s["frontend_components"]) or "—"))
    if eps:
        print("\nVse API poti:")
        for e in eps:
            print(f"  {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
