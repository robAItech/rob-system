#!/usr/bin/env python
"""SSE stream test — /api/stream (Command Center v2).

Zažene svoj dashboard server (PORT 8796, ROB_API_TOKEN=sse-test-token), se
poveže na /api/stream (s session cookie) in preveri, da tok dejansko teče:
  1. prvi frame = {"type":"connected"},
  2. nato heartbeat (vsakih 5 s) ali realen event (iz audit.jsonl).

Izhod: 0 = ok, 1 = padel. Standardna knjižnica (urllib) — brez zunanjih dep.
"""
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = 8796          # izogib 8787 (smoke) in 8797 (ui_test)
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "sse-test-token"
READ_SECONDS = 10
NEED_FRAMES = 3


def _wait_up(proc) -> bool:
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

        # Avtentikacija → session cookie.
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(
            f"{BASE}/api/auth",
            data=json.dumps({"token": TOKEN}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        opener.open(req, timeout=5)

        # Odpri SSE tok in beri frame-e.
        resp = opener.open(f"{BASE}/api/stream", timeout=15)
        frames: list = []
        buf = b""
        start = time.time()
        while time.time() - start < READ_SECONDS and len(frames) < NEED_FRAMES:
            chunk = resp.read(128)
            if not chunk:
                time.sleep(0.1)
                continue
            buf += chunk
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                for line in frame.decode(errors="replace").splitlines():
                    if line.startswith("data:"):
                        try:
                            frames.append(json.loads(line[5:].strip()))
                        except Exception:
                            pass

        types = [f.get("type") for f in frames]
        print("  frames:", types)
        ok = bool(frames) and types[0] == "connected" and any(t in ("heartbeat", "event") for t in types[1:])
        print("✅ SSE TEST OK" if ok else "❌ SSE TEST PADEL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
