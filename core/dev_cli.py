"""core/dev_cli.py — enotna Python orkestracija (P4).

Nadomešča dve PowerShell skripti (`dev.ps1`, `zagon.ps1`) z enim Python CLI.
Konsolidira na port 4010 (proxy) + 8787 (dashboard). Port 4000 se nikoli
ne dotakne (rezerviran za uporabnikov lastni proxy).

Samo standardna knjižnica (+ pyyaml, že instaliran) — brez dodatnih deps.
Vsi zunanji ukazi (litellm, bun, claude) se kličejo prek `subprocess`,
ker so CLI skripte na PATH, ne import-able Python moduli.

UPORABA (primarne vstopne točke):
  python core/dev_cli.py            # proxy :4010 + dashboard :8787 v ozadju, poveže claude
  python core/dev_cli.py --init     # dry-run preverba
  python core/dev_cli.py --proxy-only
  python core/dev_cli.py --dashboard-only
  python core/dev_cli.py --claude-only
  dev.bat ...                       # Windows wrapper → na ta modul
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import yaml

# ------------------------------------------------------------------ #
#  Konstante
# ------------------------------------------------------------------ #
PORT = 4010             # izoliran LiteLLM proxy port — NE 4000
DASH_PORT = 8787        # Command-Center (src/server.ts)
PROXY_TIMEOUT = 30      # sekund, čakanje na pripravo proxyja
DASH_TIMEOUT = 15       # sekund, čakanje na pripravo dashboarda
FALLBACK_MASTER_KEY = "sk-hermes-master-key"
HEALTH_TIMEOUT = 2      # sekund na en HTTP request
BANNER = "ROB AI STUDIO — EN UNKAZ ZAGON (proxy :4010 + Command-Center :8787)"


# ------------------------------------------------------------------ #
#  Stanje / konfiguracija
# ------------------------------------------------------------------ #
class Config:
    """Stanje orkestracije, prebrano enkrat iz repo korena."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_path = root / "bridges" / "litellm_config.yaml"
        self.env_path = root / ".env"
        self.server_ts = root / "src" / "server.ts"
        self.env: dict = parse_env(_read_optional(self.env_path))
        self.deepseek_key: str = self.env.get("DEEPSEEK_API_KEY", "")
        self.master_key: str = read_master_key(self.config_path) if self.config_path.exists() else FALLBACK_MASTER_KEY

    @staticmethod
    def from_root(root: Optional[Path] = None) -> "Config":
        root = root or Path.cwd()
        return Config(root.resolve())


def parse_env(text: str) -> dict:
    """Razčleni .env tekst v dict. Preskoči komentarje/prazne, trim quotes.

    Ekvivalent PowerShell `Get-Content` → hashtable v dev.ps1/zagon.ps1.
    """
    out: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq <= 0:
            continue
        name = line[:eq].strip()
        val = line[eq + 1:].strip().strip('"').strip("'")
        if name:
            out[name] = val
    return out


def read_master_key(config_path: Path) -> str:
    """Prebere `general_settings.master_key` iz YAML; sicer fallback.

    Reproducira zagon.ps1 (Python parser prebira general_settings).
    """
    try:
        data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        sec = data.get("general_settings") or {}
        key = sec.get("master_key")
        return str(key) if key else FALLBACK_MASTER_KEY
    except Exception:
        return FALLBACK_MASTER_KEY


def _read_optional(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# ------------------------------------------------------------------ #
#  Pomožne funkcije (enota testabilne)
# ------------------------------------------------------------------ #
def which(cmd: str) -> Optional[Path]:
    """Wrapper okoli shutil.which (mock-abilen v testih)."""
    p = shutil.which(cmd)
    return Path(p) if p else None


def _http_ok(url: str, token: Optional[str] = None, timeout: float = HEALTH_TIMEOUT) -> bool:
    """GET url → True če status 200. Opcijski Bearer glava."""
    req = urllib.request.Request(url, headers={})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def proxy_health(base_url: str, master_key: str, timeout: float = HEALTH_TIMEOUT) -> bool:
    """Proxy je pripravljen + avtenticiran (kot zagon.ps1 Test-ProxyHealth)."""
    if not _http_ok(base_url + "/health/liveliness", None, timeout):
        return False
    return _http_ok(base_url + "/v1/models", master_key, timeout + 1)


def dashboard_health(dash_url: str, timeout: float = HEALTH_TIMEOUT) -> bool:
    """Command-Center dashboard je pripravljen (kot zagon.ps1 Test-DashboardHealth)."""
    return _http_ok(dash_url + "/api/health", None, timeout)


def wait_health(check_fn: Callable[[], bool], seconds: int, on_each: Optional[Callable[[int], None]] = None) -> bool:
    """Počakaj na health (zanka 1s) do seconds. on_each(attempt) ob vsaki iteraciji."""
    for i in range(seconds):
        if check_fn():
            return True
        if on_each:
            on_each(i)
        time.sleep(1)
    return check_fn()


def port_listener(port: int) -> Optional[int]:
    """PID procesa, ki POSLUŠA na portu (Windows: netstat -ano). Unix → None.

    Uporablja se za cleanup: če je na portu že proces, ki ga NAŠA orkestracija
    ni zagnala, se NE ubije (`started_by_us` resp. to opisano v SpawnedServer).
    """
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, check=False,
            )
            for line in r.stdout.splitlines():
                parts = line.split()
                # Vrsta: TCP 0.0.0.0:4010 ... LISTENING 5992
                if len(parts) >= 5 and parts[-2] == "LISTENING":
                    if parts[1].endswith(f":{port}"):
                        try:
                            return int(parts[-1])
                        except ValueError:
                            pass
        except Exception:
            return None
    return None  # Unix: zanašamo se na Popen.kill(), ne netstat


class SpawnedServer:
    """Handle za proces, ki ga je orkestracija morda sama zagnala.

    `started_by_us` je Odločujoči ključ cleanupa: če je bil proces na portu že
    prisoten pred zagonom, ali če smo Popen ustvarili, ga čistimo samo takrat,
    ko smo ga res sami zagnali (nikoli tujega).
    """

    def __init__(self, started_by_us: bool, port: Optional[int] = None) -> None:
        self.started_by_us = started_by_us
        self.port = port
        self.popen: Optional[subprocess.Popen] = None

    def clean(self) -> None:
        if not self.started_by_us:
            return
        # Uniči proces na portu (če obstaja) — samo tistega, ki smo ga zagnali.
        if self.port is not None:
            pid = port_listener(self.port)
            if pid:
                _kill_pid(pid)
        if self.popen is not None and self.popen.poll() is None:
            try:
                self.popen.kill()
            except OSError:
                pass


def _kill_pid(pid: int) -> None:
    """Poskusi terminate, nato force kill."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


# ------------------------------------------------------------------ #
#  Zagonski ukazi (načini)
# ------------------------------------------------------------------ #
def _log_lines(path: Optional[Path], n: int = 30) -> str:
    if path is None or not path.exists():
        return "(ni log datoteke)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return "(log ni bilo mogoče prebrati)"


def cmd_init(cfg: Config) -> int:
    """Dry-run: preveri config, ključ, porta in PATH (ne zažene nič)."""
    print("Konfiguracija:")
    print(f"  config      : {cfg.config_path}")
    print(f"  DEEPSEEK    : {'nastavljen  [OK]' if cfg.deepseek_key else '[MANJKA] — v .env'}")
    print(f"  master_key  : {cfg.master_key}")

    for port, label in ((PORT, "proxy :4010"), (DASH_PORT, "dashboard :8787")):
        pid = port_listener(port)
        if pid:
            print(f"  port {PORT if port == PORT else DASH_PORT}   : ZASEDEN (PID {pid})")
        else:
            print(f"  port {PORT if port == PORT else DASH_PORT}   : PROST  [OK]")

    print("Okolje (PATH):")
    paths = {name: which(name) for name in ("claude", "litellm", "bun")}
    for name, p in paths.items():
        print(f"  {name:<8}: {p if p else '[MANJKA]'}")
    missing = [n for n, p in paths.items() if not p]
    if not cfg.deepseek_key:
        missing.append("DEEPSEEK_API_KEY")

    if missing:
        print("\n[NAP] Manjkajoči elementi: " + ", ".join(missing))
        return 1

    print("\nZagon:  dev.bat           (vse: proxy :4010 + dashboard :8787 + claude)")
    print("        dev.bat --proxy-only | --dashboard-only | --claude-only")
    print("Varnost: Port 4000 ni vpleten.")
    return 0


def _run_foreground(cmd: List[str], cfg: Config, env_add: Optional[dict] = None,
                    cwd: Optional[Path] = None) -> int:
    """Zaženi ukaz v ospredju (Ctrl+C propagira do procesa)."""
    env = dict(os.environ)
    env["DEEPSEEK_API_KEY"] = cfg.deepseek_key
    env["PYTHONIOENCODING"] = "utf-8"
    if env_add:
        env.update(env_add)
    return subprocess.call(cmd, env=env, cwd=str(cwd) if cwd else None)


def cmd_proxy_only(cfg: Config) -> int:
    litellm = which("litellm")
    if not litellm:
        print("[NAP] 'litellm' ni na PATH. Preveri:  python -m pip install litellm")
        return 1
    if not cfg.deepseek_key:
        print("[NAP] DEEPSEEK_API_KEY ni v .env.")
        return 1
    print(f"[PROXY] LiteLLM proxy v OSPREDJU na http://127.0.0.1:{PORT} (Ctrl+C za izhod)...")
    return _run_foreground([str(litellm), "--config", str(cfg.config_path), "--port", str(PORT)], cfg)


def cmd_dashboard_only(cfg: Config) -> int:
    bun = which("bun")
    if not bun:
        print("[NAP] 'bun' ni na PATH.")
        return 1
    print(f"[DASH] Command-Center v OSPREDJU na http://127.0.0.1:{DASH_PORT} (Ctrl+C za izhod)...")
    return _run_foreground([str(bun), "run", "src/server.ts"], cfg, cwd=cfg.root)


def _claude_commandline(args: Sequence[str]) -> List[str]:
    claude = which("claude")
    if not claude:
        print("[NAP] 'claude' ni na PATH. Dobro:  npm i -g @anthropic-ai/claude-code")
        return []
    return [str(claude), *list(args)]


def cmd_claude_only(cfg: Config, args: Sequence[str]) -> int:
    base = f"http://127.0.0.1:{PORT}"
    if not proxy_health(base, cfg.master_key):
        print(f"[NAP] Proxy na {base} ni dosegljiv. Najprej:  dev.bat --proxy-only")
        return 1
    print(f"[LINK] Uporabljam obstoječi proxy {base}")
    cmd = _claude_commandline(args)
    if not cmd:
        return 1
    return _run_foreground(cmd, cfg, env_add={
        "ANTHROPIC_BASE_URL": base,
        "ANTHROPIC_API_KEY": cfg.master_key,
    })


def _spawn(cmd: List[str], cfg: Config, extra_env: Optional[dict] = None,
           cwd: Optional[Path] = None) -> Optional[subprocess.Popen]:
    """Zaženi ukaz v ozadju; vrača Popen (ali None ob napaki)."""
    env = dict(os.environ)
    env["DEEPSEEK_API_KEY"] = cfg.deepseek_key
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    try:
        kwargs: dict = {"env": env}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    except OSError as e:
        print(f"[NAP] Zagon ni uspel ({cmd[0]}): {e}")
        return None


def cmd_all(cfg: Config, args: Sequence[str]) -> int:
    """Privzeti način: proxy + dashboard v ozadju, potem claude; cleanup."""
    proxy_base = f"http://127.0.0.1:{PORT}"
    dash_url = f"http://127.0.0.1:{DASH_PORT}"

    litellm = which("litellm")
    if not litellm:
        print("[NAP] 'litellm' ni na PATH.")
        return 1
    if not cfg.deepseek_key:
        print("[NAP] DEEPSEEK_API_KEY ni v .env.")
        return 1

    # --- Proxy ---
    already_proxy = proxy_health(proxy_base, cfg.master_key)
    sp_proxy = SpawnedServer(started_by_us=not already_proxy, port=PORT)
    if already_proxy:
        print(f"[LINK] Proxy že teče na {proxy_base} - uporabljam obstoječega.")
    else:
        print(f"[PROXY] Zaganjam lasten izoliran LiteLLM proxy ({proxy_base}) v OZADJU...")
        sp_proxy.popen = _spawn([str(litellm), "--config", str(cfg.config_path), "--port", str(PORT)], cfg)
        if sp_proxy.popen is None:
            return 1
        if not wait_health(lambda: proxy_health(proxy_base, cfg.master_key), PROXY_TIMEOUT):
            print("[NAP] Proxy se ni zagnal v 30s.")
            sp_proxy.clean()
            return 1

    # --- Dashboard ---
    already_dash = dashboard_health(dash_url)
    sp_dash = SpawnedServer(started_by_us=not already_dash, port=DASH_PORT)
    if already_dash:
        print(f"[LINK] Dashboard že teče na {dash_url} - uporabljam obstoječega.")
    else:
        print(f"[DASH] Zaganjam Command-Center ({dash_url}) v OZADJU (bun run src/server.ts)...")
        bun = which("bun")
        if bun:
            sp_dash.popen = _spawn([str(bun), "run", "src/server.ts"], cfg, cwd=cfg.root)
        if sp_dash.popen is None:
            print("[WARN] Dashboard ni bil zagnan; nadaljujem.")
        elif not wait_health(lambda: dashboard_health(dash_url), DASH_TIMEOUT):
            print("[WARN] Dashboard se ni odzval v 15s — nadaljujem.")

    # --- Claude ---
    cmd = _claude_commandline(args)
    if not cmd:
        sp_proxy.clean()
        sp_dash.clean()
        return 1
    print(f"[RUN] Zaganjam CLAUDE (Ctrl+C prekine samo claude)...")
    try:
        code = _run_foreground(cmd, cfg, env_add={
            "ANTHROPIC_BASE_URL": proxy_base,
            "ANTHROPIC_API_KEY": cfg.master_key,
        })
    finally:
        sp_proxy.clean()
        sp_dash.clean()
    print("[END] Konec. (Port 4000 ostaja nedotaknjen.)")
    return code


def cmd_serve(cfg: Config) -> int:
    """Avtonomen zagon: dvigne proxy+dashboard v OZADJU, brez claude-a.

    Namenjeno avtonomnemu zagonu (Task Scheduler / --serve): system teče 24/7,
    vnos nalog gre skozi dashboard UI. Idempotentno — če system že teče,
    ne duplicira. Vrne takoj (ne blokira, ne zažene claude). Tailscale check
    za remote dostop (če ni nameščen → opozorilo, ne fail).
    """
    proxy_base = f"http://127.0.0.1:{PORT}"
    dash_url = f"http://127.0.0.1:{DASH_PORT}"

    litellm = which("litellm")
    if not litellm:
        print("[NAP] 'litellm' ni na PATH.")
        return 1
    if not cfg.deepseek_key:
        print("[NAP] DEEPSEEK_API_KEY ni v .env.")
        return 1

    # --- Proxy (idempotentno) ---
    already_proxy = proxy_health(proxy_base, cfg.master_key)
    sp_proxy = SpawnedServer(started_by_us=not already_proxy, port=PORT)
    if already_proxy:
        print(f"[LINK] Proxy že teče na {proxy_base} - uporabljam obstoječega.")
    else:
        print(f"[PROXY] Zaganjam v OZADJU ({proxy_base})...")
        sp_proxy.popen = _spawn([str(litellm), "--config", str(cfg.config_path), "--port", str(PORT)], cfg)
        if sp_proxy.popen is None:
            return 1
        if not wait_health(lambda: proxy_health(proxy_base, cfg.master_key), PROXY_TIMEOUT):
            print("[NAP] Proxy se ni zagnal v 30s.")
            sp_proxy.clean()
            return 1

    # --- Dashboard (idempotentno) ---
    already_dash = dashboard_health(dash_url)
    sp_dash = SpawnedServer(started_by_us=not already_dash, port=DASH_PORT)
    if already_dash:
        print(f"[LINK] Dashboard že teče na {dash_url} - uporabljam obstoječega.")
    else:
        print(f"[DASH] Zaganjam Command-Center ({dash_url}) v OZADJU...")
        bun = which("bun")
        if bun:
            sp_dash.popen = _spawn([str(bun), "run", "src/server.ts"], cfg, cwd=cfg.root)
        if sp_dash.popen is None:
            print("[WARN] Dashboard ni bil zagnan; nadaljujem.")
        elif not wait_health(lambda: dashboard_health(dash_url), DASH_TIMEOUT):
            print("[WARN] Dashboard se ni odzval v 15s — nadaljujem.")

    # --- Tailscale (remote dostop) — preveri, poročaj, ne fail ---
    ts = which("tailscale")
    if ts:
        print(f"[TS] Tailscale nameščen. Dashboard dosegljiv tudi prek Tailscale IP "
              f"(preveri: tailscale status).")
    else:
        print("[WARN] 'tailscale' ni na PATH — remote dostop Z DRUGIH naprav ne bo deloval. "
              "Namesti Tailscale (tailscale.com) + 'tailscale up' za varen dostop prek omrežja. "
              "Lokalno dashboard deluje.")

    print(f"[OK] AVTONOMEN ZAGON pripravljen.")
    print(f"      Dashboard:  {dash_url}      (vnos nalog prek UI)")
    print(f"      Terminal/rescue:  rob dev   (ročni nadzor / claude)")
    return 0


# ------------------------------------------------------------------ #
#  Glavni vstop (argparse)
# ------------------------------------------------------------------ #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rob dev",
        description="En utemelj zagon: LiteLLM proxy :4010 + Command-Center :8787 + Claude (DeepSeek).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--init", action="store_true", help="dry-run preverba (ne zažene nič).")
    g.add_argument("--proxy-only", action="store_true", help="samo LiteLLM na 4010 v ospredju.")
    g.add_argument("--dashboard-only", action="store_true", help="samo Command-Center (bun src/server.ts) na 8787.")
    g.add_argument("--claude-only", action="store_true", help="samo claude ob že obstoječem proxyju na 4010.")
    g.add_argument("--serve", action="store_true",
                   help="AVTONOMEN zagon: proxy+dashboard v ozadju, brez claude (UI je vnos). "
                        "Za Task Scheduler / stalni server. Idempotentno.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    ns, rest = parser.parse_known_args(list(argv) if argv is not None else None)
    cfg = Config.from_root()

    print(BANNER)
    print("=" * len(BANNER))

    if ns.init:
        return cmd_init(cfg)
    if ns.proxy_only:
        return cmd_proxy_only(cfg)
    if ns.dashboard_only:
        return cmd_dashboard_only(cfg)
    if ns.claude_only:
        return cmd_claude_only(cfg, rest)
    if ns.serve:
        return cmd_serve(cfg)
    return cmd_all(cfg, rest)


if __name__ == "__main__":
    sys.exit(main())
