"""Unit testi za core/dev_cli.py (P4 orkestracija).

Ni pravih zunanjih klicev (litellm/bun/claude/docker) — vse se mocka na
`core.dev_cli._http_ok`, `subprocess` in `shutil.which`. Vzorec skladen z
obstoječim tests/test_loopx_rsi.py (tmp_path + monkeypatch.chdir + mock).
"""
from pathlib import Path
from unittest import mock

import pytest

from core import dev_cli
from core.dev_cli import (
    Config,
    SpawnedServer,
    parse_env,
    port_listener,
    read_master_key,
)


# ------------------------------------------------------------------ #
#  parse_env
# ------------------------------------------------------------------ #
def test_parse_env_razcleni_kljuce_vrednosti():
    out = parse_env(
        "A=1\n"
        "# komentar\n"
        "B = \"x\"  \n"
        "\n"
        "C='quoted'\n"
        "EMPTY=\n"
    )
    assert out == {"A": "1", "B": "x", "C": "quoted", "EMPTY": ""}


def test_parse_env_ignorira_komentarje_in_prazno():
    assert parse_env("# vse\n\n NONE=\n") == {"NONE": ""}


# ------------------------------------------------------------------ #
#  read_master_key
# ------------------------------------------------------------------ #
def test_read_master_key_iz_yaml(monkeypatch, tmp_path):
    cfg = tmp_path / "litellm_config.yaml"
    cfg.write_text("general_settings:\n  master_key: abc-123\n", encoding="utf-8")
    assert read_master_key(cfg) == "abc-123"


def test_read_master_key_fallback_ob_odsotnosti(tmp_path):
    cfg = tmp_path / "x.yaml"
    cfg.write_text("general_settings:\n  drop_params: true\n", encoding="utf-8")
    assert read_master_key(cfg) == dev_cli.FALLBACK_MASTER_KEY


def test_read_master_key_fallback_ob_missing_file():
    assert read_master_key(Path("neobstoji.yaml")) == dev_cli.FALLBACK_MASTER_KEY


# ------------------------------------------------------------------ #
#  port_listener (Windows netstat parse)
# ------------------------------------------------------------------ #
def _netstat_like(ports):
    lines = []
    for port, pid in ports:
        lines.append(f"  TCP    0.0.0.0:{port}           0.0.0.0:0              LISTENING       {pid}")
    lines.append("  TCP    0.0.0.0:5000           0.0.0.0:0              TIME_WAIT        0")
    return "\n".join(lines) + "\n"


@pytest.mark.skipif(not dev_cli.os.name == "nt", reason="netstat-parse je Windows-logika")
def test_port_listener_parsira_netstat(monkeypatch):
    mock_run = mock.MagicMock()
    mock_run.stdout = _netstat_like([(4010, 5992), (8787, 8152)])
    with mock.patch.object(dev_cli.subprocess, "run", return_value=mock_run):
        assert port_listener(4010) == 5992
        assert port_listener(8787) == 8152
        assert port_listener(4000) is None


def test_port_listener_unix_vrne_none(monkeypatch):
    monkeypatch.setattr(dev_cli.os, "name", "posix")
    assert port_listener(4010) is None


# ------------------------------------------------------------------ #
#  SpawnedServer cleanup
# ------------------------------------------------------------------ #
def test_spawned_server_cleanup_starts_by_us(monkeypatch):
    killed = []

    class FakeProc:
        def poll(self):
            return None
        def kill(self):
            killed.append("proc")

    sp = SpawnedServer(started_by_us=True, port=4010)
    sp.popen = FakeProc()
    monkeypatch.setattr(dev_cli, "port_listener", lambda port: 9999)
    monkeypatch.setattr(dev_cli, "_kill_pid", lambda pid: killed.append(f"pid:{pid}"))
    sp.clean()
    assert killed == ["pid:9999", "proc"]


def test_spawned_server_cleanup_not_started_by_us(monkeypatch):
    killed = []
    sp = SpawnedServer(started_by_us=False, port=4010)
    sp.popen = mock.MagicMock()
    monkeypatch.setattr(dev_cli, "port_listener", lambda port: killed.append("LISTENER") or 1111)
    sp.clean()
    assert killed == []
    sp.popen.kill.assert_not_called()


# ------------------------------------------------------------------ #
#  Health-checki
# ------------------------------------------------------------------ #
def test_proxy_health_zahteva_liveliness_in_models(monkeypatch):
    calls = []

    def fake_http(url, token=None, timeout=2):
        calls.append((url, token))
        return url.endswith("/health/liveliness") or url.endswith("/v1/models")

    with mock.patch.object(dev_cli, "_http_ok", side_effect=fake_http):
        ok = dev_cli.proxy_health("http://127.0.0.1:4010", "key")
    assert ok is True
    # liveliness brez token, v1/models z Bearer
    assert ("http://127.0.0.1:4010/health/liveliness", None) in calls
    assert any(u.endswith("/v1/models") and t == "key" for u, t in calls)


def test_proxy_health_false_ko_ni_liveliness(monkeypatch):
    with mock.patch.object(dev_cli, "_http_ok", return_value=False):
        assert dev_cli.proxy_health("http://x:4010", "key") is False


def test_wait_health_loop(monkeypatch):
    booleans = iter([False, False, True])
    assert dev_cli.wait_health(lambda: next(booleans), seconds=5) is True


def test_wait_health_timeout():
    assert dev_cli.wait_health(lambda: False, seconds=2) is False


# ------------------------------------------------------------------ #
#  cmd_init / cmd_claude_only — port 4000 nikoli ni v igri
# ------------------------------------------------------------------ #
def test_cmd_init_izpise_varnostno_opombo_o_4000(tmp_path, monkeypatch):
    """cmd_init v opombi poudari, da 4000 ni v uporabi (info, ne health)."""
    monkeypatch.chdir(tmp_path)
    cfg = Config(Path(tmp_path))
    cfg.deepseek_key = "sekret"
    monkeypatch.setattr(dev_cli, "which", lambda n: Path("C:/x/" + n))
    checked_ports = []
    monkeypatch.setattr(dev_cli, "port_listener",
                        lambda port: checked_ports.append(port) or None)
    captured = get_output(monkeypatch, lambda: dev_cli.cmd_init(cfg))
    assert "4000" in captured  # varnostna opomba omenja 4000 (samo tekst)
    # port_listener se preverja le na 4010 in 8787, NIKOLI 4000
    assert set(checked_ports) <= {dev_cli.PORT, dev_cli.DASH_PORT}
    assert 4000 not in checked_ports


def test_cmd_claude_only_napaka_ko_proxy_nedostopen(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cfg = dev_cli.Config(Path(tmp_path))
    cfg.deepseek_key = "x"
    monkeypatch.setattr(dev_cli, "which", lambda n: Path("C:/x/claude"))
    monkeypatch.setattr(dev_cli, "proxy_health", lambda base, key: False)
    with mock.patch.object(dev_cli.subprocess, "call") as call:
        rc = dev_cli.cmd_claude_only(cfg, [])
        call.assert_not_called()
    assert rc == 1


# ------------------------------------------------------------------ #
#  Port 4000 nikoli ni target health-checka ali listenerja v cmd_all
# ------------------------------------------------------------------ #
def test_cmd_all_ne_klico_porta_4000(monkeypatch, tmp_path):
    """cmd_all sme klicati le 4010/8787 v health-checkih; nikoli 4000.

    Simuliramo: proxy že teče (`_http_ok` zelen za 4010), dashboard ne
    (`_http_ok` rdeč za 8787) → cmd_all ne zažene proxyja, dashboard poskusi,
    nato claude (mock, brez izvedbe). Zajamemo vse health URL-je.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dev_cli.Config, "from_root",
                        lambda root=None: Config(Path(tmp_path)))
    cfg = dev_cli.Config(Path(tmp_path))
    cfg.deepseek_key = "sekret"
    monkeypatch.setattr(dev_cli, "which", lambda n: Path("C:/x/" + n))

    http_urls = []
    def fake_http(url, token=None, timeout=2):
        http_urls.append(url)
        # proxy 4010 je "gor"; dashboard 8787 žal ne (da testira spawn+cleanup)
        return ":4010" in url

    monkeypatch.setattr(dev_cli, "_http_ok", fake_http)
    # Ne želimo dejanskega Popen za dashboard → mock._spawn naj vrne FakeProc
    fake_proc = mock.MagicMock()
    fake_proc.poll.return_value = None
    monkeypatch.setattr(dev_cli, "_spawn", lambda *a, **k: fake_proc)
    monkeypatch.setattr(dev_cli, "wait_health", lambda ck, seconds, **k: True)  # ne čakaj 15s
    monkeypatch.setattr(dev_cli, "port_listener", lambda port: None)
    # claude: _claude_commandline vrne pravi ukaz, _run_foreground mock
    monkeypatch.setattr(dev_cli.subprocess, "call", lambda *a, **k: 0)

    rc = dev_cli.cmd_all(cfg, [])

    assert http_urls, "pričakovali smo health requeste"
    bad = [u for u in http_urls if ":4000" in u]
    assert not bad, f"cmd_all je poklical port 4000: {bad}"
    # return 0 (claude je "odšel", cleanup no-op ker port_listener→None)
    assert rc == 0

# ------------------------------------------------------------------ #
#  cmd_serve — avtonomen zagon (--serve), idempotentno, brez claude
# ------------------------------------------------------------------ #
def test_cmd_serve_idempotentno_ne_duplicira_ne_claude(monkeypatch, tmp_path):
    """System že teče (proxy+dashboard zelena) → --serve NE zažene novega, NE kliče claude."""
    monkeypatch.chdir(tmp_path)
    cfg = dev_cli.Config(Path(tmp_path))
    cfg.deepseek_key = "sekret"
    monkeypatch.setattr(dev_cli, "which", lambda n: Path("C:/x/" + n))

    spawned = []
    monkeypatch.setattr(dev_cli, "_spawn", lambda *a, **k: spawned.append(a) or mock.MagicMock())
    monkeypatch.setattr(dev_cli, "proxy_health", lambda base, key: True)    # žе teče
    monkeypatch.setattr(dev_cli, "dashboard_health", lambda url: True)      # žе teče

    rc = dev_cli.cmd_serve(cfg)

    assert rc == 0
    assert spawned == [], "--serve idempotentno: NE zažene duplikata, ko system žе teče"
    # NE kliče claude (subprocess.call / _claude_commandline ne smeta it naprej) — cmd_serve
    # se ne dotika claude; preverimo, da ni bilo nobenega _spawn-a (proxy/dashboard žе sta).


def test_cmd_serve_ne_zazene_claude_ampak_dvigne_system(monkeypatch, tmp_path):
    """System NE teče → --serve dvigne proxy+dashboard v ozadju, ampak NIKOLI claude."""
    monkeypatch.chdir(tmp_path)
    cfg = dev_cli.Config(Path(tmp_path))
    cfg.deepseek_key = "sekret"
    monkeypatch.setattr(dev_cli, "which", lambda n: Path("C:/x/" + n))

    fake_proc = mock.MagicMock()
    fake_proc.poll.return_value = None
    monkeypatch.setattr(dev_cli, "_spawn", lambda *a, **k: fake_proc)
    monkeypatch.setattr(dev_cli, "proxy_health", lambda base, key: False)   # ni gor → dvigni
    monkeypatch.setattr(dev_cli, "dashboard_health", lambda url: False)
    monkeypatch.setattr(dev_cli, "wait_health", lambda ck, seconds, **k: True)  # ne čakaj
    monkeypatch.setattr(dev_cli, "port_listener", lambda port: None)
    call = mock.MagicMock()
    monkeypatch.setattr(dev_cli.subprocess, "call", call)

    rc = dev_cli.cmd_serve(cfg)

    assert rc == 0
    call.assert_not_called()   # NI claude izvedbe (za razliko od cmd_all)


# ------------------------------------------------------------------ #
#  Pomožni: ujemi stdout
# ------------------------------------------------------------------ #
def get_output(monkeypatch, fn):
    import io
    buf = io.StringIO()
    with mock.patch("sys.stdout", new=buf):
        fn()
    return buf.getvalue()
