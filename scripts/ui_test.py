#!/usr/bin/env python
"""Playwright UI test — Command Center v2 (CI + lokalno).

Zažene lasten dashboard server (PORT 8797, ROB_API_TOKEN=ui-test-token) in
preveri, da /command v2 DEJANSKO deluje v brskalniku:
  - naslov "Command Center v2",
  - KPI je napolnjen (ne hardcoded / ne prazen),
  - fleet panel se renderira,
  - SSE dot je LIVE (povezava živa),
  - feed ima vsebino ali "čakam",
  - NI JavaScript napak.

Izhod: 0 = ok, 1 = padel. Brez pravih odvisnosti — samo playwright (že v
requirements-dev) + bun.
"""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

PORT = 8797          # izogib 8787 (smoke_server.sh)
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "ui-test-token"


def _wait_up(proc) -> bool:
    import urllib.request
    for _ in range(20):
        try:
            if urllib.request.urlopen(f"{BASE}/api/health", timeout=2).status == 200:
                return True
        except Exception:
            time.sleep(1)
    print("  ✗ server se ni zagnal")
    return False


def main() -> int:
    env = {**os.environ, "PORT": str(PORT), "ROB_API_TOKEN": TOKEN}
    proc = subprocess.Popen(["bun", "run", "src/server.ts"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_up(proc):
            return 1
        with sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page()
            js_errors: list = []
            pg.on("pageerror", lambda e: js_errors.append(str(e)[:120]))
            pg.goto(f"{BASE}/command", timeout=15000)
            # Avtentikacija prek fetch → session cookie, nato reload.
            pg.evaluate(
                f"fetch('/api/auth', {{method:'POST',headers:{{'Content-Type':'application/json'}},"
                f"body:JSON.stringify({{token:'{TOKEN}'}})}})")
            pg.wait_for_timeout(600)
            pg.reload()
            pg.wait_for_timeout(4000)

            checks = []

            title = pg.title()
            checks.append(("naslov v2", title == "Command Center v2", title))

            kpi = pg.query_selector("#kpi-tasks")
            kpi_val = kpi.inner_text().strip() if kpi else ""
            checks.append(("KPI napolnjen", kpi is not None and kpi_val not in ("", "—"), kpi_val or "—"))

            fleet = pg.query_selector("#fleet-body")
            ftxt = fleet.inner_text() if fleet else ""
            fleet_ok = fleet is not None and ("agenda" in ftxt or "spomin" in ftxt or "worker" in ftxt.lower() or "ni aktivnih" in ftxt)
            checks.append(("fleet panel", fleet_ok, ftxt[:40]))

            dot = pg.query_selector("#sse-dot")
            dot_cls = dot.get_attribute("class") or "" if dot else ""
            checks.append(("SSE dot LIVE", bool(dot) and "live" in dot_cls, dot_cls or "—"))

            feed = pg.query_selector("#feed")
            feed_ok = feed is not None and (feed.inner_text().strip() != "")
            checks.append(("feed ima vsebino", feed_ok, feed.inner_text()[:30] if feed else "—"))

            checks.append(("ni JS napak", not js_errors, js_errors[:1] if js_errors else "ok"))
            browser.close()

        ok = all(c[1] for c in checks)
        for name, passed, got in checks:
            print(f"  {'✓' if passed else '✗'} {name}: {str(got)[:70]}")
        print("✅ UI TEST OK" if ok else "❌ UI TEST PADEL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
