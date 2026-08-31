"""fleet_security — SQLite persistence (stdlib, WAL, deterministično).

Shranjuje: naprave (inventar), posture najdbe, score snapshote (časovna vrsta
za anomalije), baseline-e po role-u in remediacijske rezultate.

Vzorec povezave prevzame od ``core/world_model.py._get_connection`` (retry 3×,
``row_factory=Row``, ``PRAGMA journal_mode=WAL``). Vse JSON vrednosti so
shranjene s ``json.dumps(..., sort_keys=True)``. Brez LLM, brez omrežja.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.fleet_security.schemas import (  # noqa: E402
    Baseline,
    Device,
    FirmwareInfo,
    HostInfo,
    ModelInfo,
    OSInfo,
    PostureFinding,
    PostureScore,
    RemediationResult,
)

DEFAULT_DB_PATH = PROJECT_ROOT / ".rob_ai" / "fleet_security.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fs_devices (
    device_id    TEXT PRIMARY KEY,
    hostname     TEXT NOT NULL,
    role         TEXT NOT NULL,
    os_name      TEXT NOT NULL DEFAULT '',
    os_version   TEXT NOT NULL DEFAULT '',
    os_kernel    TEXT NOT NULL DEFAULT '',
    firmware_json TEXT NOT NULL DEFAULT '[]',
    model_json   TEXT,
    config_json  TEXT NOT NULL DEFAULT '{}',
    source       TEXT NOT NULL DEFAULT '',
    first_seen_ts INTEGER NOT NULL,
    last_seen_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fs_findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    category    TEXT NOT NULL,
    severity    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    detail      TEXT NOT NULL,
    detected_at INTEGER NOT NULL,
    resolved_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fs_findings_device ON fs_findings(device_id);
CREATE INDEX IF NOT EXISTS idx_fs_findings_status ON fs_findings(status);

CREATE TABLE IF NOT EXISTS fs_scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    score       INTEGER NOT NULL,
    grade       TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    assessed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_scores_device ON fs_scores(device_id, assessed_at);

CREATE TABLE IF NOT EXISTS fs_baselines (
    role          TEXT PRIMARY KEY,
    baseline_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fs_remediations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    diff        TEXT NOT NULL DEFAULT '',
    branch      TEXT,
    commit_sha  TEXT,
    pr_url      TEXT,
    status      TEXT NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_remediations_device ON fs_remediations(device_id);

CREATE TABLE IF NOT EXISTS fs_telemetry (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT NOT NULL,
    ts           INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'device',
    metrics_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fs_telemetry_device_ts ON fs_telemetry(device_id, ts);
CREATE INDEX IF NOT EXISTS idx_fs_telemetry_ts ON fs_telemetry(ts);

CREATE TABLE IF NOT EXISTS fs_network_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts        INTEGER NOT NULL,
    dst_host  TEXT,
    dst_ip    TEXT,
    dst_port  INTEGER,
    proto     TEXT
);
CREATE INDEX IF NOT EXISTS idx_fs_network_device_dst ON fs_network_events(device_id, dst_host);
CREATE INDEX IF NOT EXISTS idx_fs_network_device_ts ON fs_network_events(device_id, ts);
CREATE INDEX IF NOT EXISTS idx_fs_network_ts ON fs_network_events(ts);

CREATE TABLE IF NOT EXISTS fs_redteam_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL,
    payload_id        TEXT NOT NULL,
    payload_name      TEXT NOT NULL,
    vector_category   TEXT NOT NULL,
    decision          TEXT NOT NULL,
    judged_vulnerable INTEGER NOT NULL,
    severity          TEXT NOT NULL,
    ran_at            INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_redteam_device_ts ON fs_redteam_runs(device_id, ran_at);

CREATE TABLE IF NOT EXISTS fs_model_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    model_version TEXT NOT NULL,
    sha256        TEXT NOT NULL DEFAULT '',
    provider      TEXT NOT NULL DEFAULT '',
    pushed_by     TEXT,
    pushed_at     INTEGER,
    repo_url      TEXT,
    ts            INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_model_history_device_ts ON fs_model_history(device_id, ts);
"""


def _now() -> int:
    return int(time.time())


class FleetSecurityStore:
    """Persistenca pasivnega jedra fleet security. Deterministično, brez LLM."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    #  SQLite helper (vzorec: core/world_model.py._get_connection)
    # ------------------------------------------------------------------ #
    def _get_connection(self) -> sqlite3.Connection:
        last_err: Optional[Exception] = None
        for _ in range(3):
            try:
                conn = sqlite3.connect(self.db_path, timeout=5)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                return conn
            except sqlite3.OperationalError as e:
                last_err = e
                time.sleep(0.3)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(_SCHEMA_SQL)

    # ------------------------------------------------------------------ #
    #  Naprave (inventar)
    # ------------------------------------------------------------------ #
    def upsert_device(self, hostinfo: HostInfo, now: int | None = None) -> Device:
        """Upsert naprave; ohrani first_seen ob ponovnem ingestu."""
        now = int(now) if now is not None else _now()
        existing = self.get_device(hostinfo.device_id)
        first_seen = existing.first_seen_ts if existing else now
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fs_devices
                    (device_id, hostname, role, os_name, os_version, os_kernel,
                     firmware_json, model_json, config_json, source,
                     first_seen_ts, last_seen_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hostinfo.device_id,
                    hostinfo.hostname,
                    hostinfo.role,
                    hostinfo.os.name,
                    hostinfo.os.version,
                    hostinfo.os.kernel,
                    json.dumps(
                        [f.model_dump() for f in hostinfo.firmware], sort_keys=True
                    ),
                    json.dumps(hostinfo.model.model_dump(), sort_keys=True)
                    if hostinfo.model
                    else None,
                    json.dumps(hostinfo.config, sort_keys=True),
                    hostinfo.source,
                    first_seen,
                    now,
                ),
            )
        return self.get_device(hostinfo.device_id)  # type: ignore[return-value]

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> Device:
        firmware = [
            FirmwareInfo(**f) for f in json.loads(row["firmware_json"] or "[]")
        ]
        model = None
        if row["model_json"]:
            model = ModelInfo(**json.loads(row["model_json"]))
        return Device(
            device_id=row["device_id"],
            hostname=row["hostname"],
            role=row["role"],
            os=OSInfo(
                name=row["os_name"],
                version=row["os_version"],
                kernel=row["os_kernel"],
            ),
            firmware=firmware,
            model=model,
            config=json.loads(row["config_json"] or "{}"),
            source=row["source"],
            first_seen_ts=row["first_seen_ts"],
            last_seen_ts=row["last_seen_ts"],
        )

    def get_device(self, device_id: str) -> Device | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM fs_devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        return self._row_to_device(row) if row else None

    def list_devices(self, role: str | None = None) -> list[Device]:
        with self._get_connection() as conn:
            if role:
                rows = conn.execute(
                    "SELECT * FROM fs_devices WHERE role = ? ORDER BY device_id",
                    (role,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fs_devices ORDER BY device_id"
                ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def all_device_ids(self) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT device_id FROM fs_devices").fetchall()
        return [r["device_id"] for r in rows]

    # ------------------------------------------------------------------ #
    #  Posture najdbe
    # ------------------------------------------------------------------ #
    def upsert_findings(
        self,
        findings: list[PostureFinding],
        now: int | None = None,
        assessed: list[str] | None = None,
        resolve_categories: set[str] | None = None,
    ) -> int:
        """Vstavi nove najdbe + resolve odprte, ki niso več v incoming.

        Dedup: če že obstaja odprta (device_id, category, detail), je ne
        podvaja. Vrne število vstavljenih.

        Resolve: za vsako napravo v ``assessed`` (privzeto tiste, ki so v
        ``findings``) se odprte najdbe, ki NISO v incoming setu, označijo kot
        ``resolved`` — tudi če ima naprava v tem pass-u NIČ najdb (čista).

        ``resolve_categories`` scopa-ta resolve na podane kategorije (Phase 2:
        posture in monitor pisatelja resolve-ata vsak SVOJE kategorije in si
        tako ne clobber-ata najdb).
        """
        now = int(now) if now is not None else _now()
        inserted = 0
        # Incoming (device_id, category, detail, severity) seti po napravi.
        by_device: dict[str, set[tuple[str, str, str]]] = {}
        for f in findings:
            by_device.setdefault(f.device_id, set()).add(
                (f.category, f.detail, f.severity)
            )
        resolve_devices = (
            list(assessed) if assessed is not None else list(by_device.keys())
        )
        with self._get_connection() as conn:
            for f in findings:
                dup = conn.execute(
                    """
                    SELECT id FROM fs_findings
                    WHERE device_id = ? AND category = ? AND detail = ?
                      AND status = 'open'
                    LIMIT 1
                    """,
                    (f.device_id, f.category, f.detail),
                ).fetchone()
                if dup:
                    continue
                conn.execute(
                    """
                    INSERT INTO fs_findings
                        (device_id, category, severity, status, detail,
                         detected_at, resolved_at)
                    VALUES (?, ?, ?, 'open', ?, ?, NULL)
                    """,
                    (f.device_id, f.category, f.severity, f.detail, f.detected_at),
                )
                inserted += 1
            # Resolve odprtih, ki niso več v incoming (naprava je bila ocenjena).
            for device_id in resolve_devices:
                incoming = by_device.get(device_id, set())
                open_rows = conn.execute(
                    "SELECT * FROM fs_findings WHERE device_id = ? AND status = 'open'",
                    (device_id,),
                ).fetchall()
                for row in open_rows:
                    if (
                        resolve_categories is not None
                        and row["category"] not in resolve_categories
                    ):
                        continue
                    key = (row["category"], row["detail"], row["severity"])
                    if key not in incoming:
                        conn.execute(
                            """
                            UPDATE fs_findings SET status = 'resolved', resolved_at = ?
                            WHERE id = ?
                            """,
                            (now, row["id"]),
                        )
        return inserted

    def resolve_missing_for_roles(
        self, roles: list[str], now: int | None = None
    ) -> int:
        """Resolve sintetične ``missing_device`` najdbe (``<role>:missing``)
        za role, ki imajo zdaj dejansko napravo. Vrne število rešenih."""
        now = int(now) if now is not None else _now()
        resolved = 0
        with self._get_connection() as conn:
            for role in roles:
                cur = conn.execute(
                    """
                    UPDATE fs_findings SET status = 'resolved', resolved_at = ?
                    WHERE status = 'open' AND category = 'missing_device'
                      AND device_id = ?
                    """,
                    (now, f"{role}:missing"),
                )
                resolved += cur.rowcount or 0
        return resolved

    def list_open_findings(
        self, device_id: str | None = None
    ) -> list[PostureFinding]:
        with self._get_connection() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM fs_findings WHERE device_id = ? AND status = 'open' "
                    "ORDER BY id",
                    (device_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fs_findings WHERE status = 'open' ORDER BY id"
                ).fetchall()
        return [
            PostureFinding(
                id=r["id"],
                device_id=r["device_id"],
                category=r["category"],
                severity=r["severity"],
                status=r["status"],
                detail=r["detail"],
                detected_at=r["detected_at"],
                resolved_at=r["resolved_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    #  Posture score (časovna vrsta)
    # ------------------------------------------------------------------ #
    def save_score(
        self,
        device_id: str,
        score: int,
        grade: str,
        counts: dict[str, int],
        assessed_at: int,
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_scores (device_id, score, grade, counts_json, assessed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    score,
                    grade,
                    json.dumps(counts, sort_keys=True),
                    int(assessed_at),
                ),
            )
            return int(cur.lastrowid)

    def latest_score(self, device_id: str) -> PostureScore | None:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM fs_scores WHERE device_id = ?
                ORDER BY assessed_at DESC, id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        return self._row_to_score(row) if row else None

    def previous_scores(self, device_id: str, n: int = 2) -> list[PostureScore]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fs_scores WHERE device_id = ?
                ORDER BY assessed_at DESC, id DESC LIMIT ?
                """,
                (device_id, int(n)),
            ).fetchall()
        return [self._row_to_score(r) for r in rows]

    @staticmethod
    def _row_to_score(row: sqlite3.Row) -> PostureScore:
        return PostureScore(
            device_id=row["device_id"],
            score=row["score"],
            grade=row["grade"],
            counts=json.loads(row["counts_json"] or "{}"),
            assessed_at=row["assessed_at"],
        )

    # ------------------------------------------------------------------ #
    #  Baseline-i
    # ------------------------------------------------------------------ #
    def upsert_baseline(self, baseline: Baseline) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fs_baselines (role, baseline_json)
                VALUES (?, ?)
                """,
                (baseline.role, json.dumps(baseline.to_jsonable(), sort_keys=True)),
            )

    def get_baseline(self, role: str) -> Baseline | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT baseline_json FROM fs_baselines WHERE role = ?", (role,)
            ).fetchone()
        if not row:
            return None
        try:
            return Baseline.from_jsonable(json.loads(row["baseline_json"]))
        except Exception:
            return None

    def list_baselines(self) -> list[Baseline]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT baseline_json FROM fs_baselines").fetchall()
        out: list[Baseline] = []
        for r in rows:
            try:
                out.append(Baseline.from_jsonable(json.loads(r["baseline_json"])))
            except Exception:
                continue
        return out

    # ------------------------------------------------------------------ #
    #  Remediacije
    # ------------------------------------------------------------------ #
    def save_remediation(self, result: RemediationResult, created_at: int) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_remediations
                    (device_id, kind, diff, branch, commit_sha, pr_url, status,
                     message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.device_id,
                    result.kind,
                    result.diff,
                    result.branch,
                    result.commit,
                    result.pr_url,
                    result.status,
                    result.message,
                    int(created_at),
                ),
            )
            return int(cur.lastrowid)

    def has_open_remediation(self, device_id: str, kind: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM fs_remediations
                WHERE device_id = ? AND kind = ?
                  AND status IN ('diff_generated', 'pr_open')
                LIMIT 1
                """,
                (device_id, kind),
            ).fetchone()
        return row is not None

    def list_remediations(self, device_id: str | None = None) -> list[dict]:
        with self._get_connection() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM fs_remediations WHERE device_id = ? ORDER BY id",
                    (device_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fs_remediations ORDER BY id"
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    #  Phase 2 — telemetry (časovna vrsta)
    # ------------------------------------------------------------------ #
    def append_telemetry(
        self, device_id: str, ts: int, source: str, metrics: dict
    ) -> int:
        """Shrani en telemetry vzorec. Vrne id."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_telemetry (device_id, ts, source, metrics_json)
                VALUES (?, ?, ?, ?)
                """,
                (device_id, int(ts), source, json.dumps(metrics, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def recent_telemetry(
        self, device_id: str, metric: str | None = None, n: int = 20
    ) -> list[dict]:
        """Zadnjih ``n`` vzorcev naprave, ASC po ts (najnovejši nazadnje).

        Vrne dict-e s ``metrics`` že json.loads-ane; če je ``metric`` podan,
        se vzorci brez te metrike izpustijo.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, device_id, ts, source, metrics_json FROM fs_telemetry
                WHERE device_id = ? ORDER BY ts DESC, id DESC LIMIT ?
                """,
                (device_id, int(n)),
            ).fetchall()
        out = []
        for r in reversed(rows):
            metrics = json.loads(r["metrics_json"] or "{}")
            if metric is not None and metric not in metrics:
                continue
            out.append(
                {
                    "id": r["id"],
                    "device_id": r["device_id"],
                    "ts": r["ts"],
                    "source": r["source"],
                    "metrics": metrics,
                }
            )
        return out

    def telemetry_in_window(self, device_id: str, window_seconds: int) -> list[dict]:
        """Vzorci naprave z ``ts >= now - window_seconds`` (ASC)."""
        from time import time as _t

        cutoff = int(_t()) - int(window_seconds)
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, device_id, ts, source, metrics_json FROM fs_telemetry
                WHERE device_id = ? AND ts >= ? ORDER BY ts ASC
                """,
                (device_id, cutoff),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "device_id": r["device_id"],
                "ts": r["ts"],
                "source": r["source"],
                "metrics": json.loads(r["metrics_json"] or "{}"),
            }
            for r in rows
        ]

    def telemetry_device_count(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT device_id) AS n FROM fs_telemetry"
            ).fetchone()
        return int(row["n"]) if row else 0

    def monitor_device_ids(self) -> set[str]:
        """Unija device id-jev iz inventarja + telemetry + omrežnih opazk."""
        out: set[str] = set()
        with self._get_connection() as conn:
            for table in ("fs_devices", "fs_telemetry", "fs_network_events"):
                try:
                    rows = conn.execute(
                        f"SELECT DISTINCT device_id FROM {table}"
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                out.update(r["device_id"] for r in rows)
        return out

    # ------------------------------------------------------------------ #
    #  Phase 2 — omrežne opazke
    # ------------------------------------------------------------------ #
    def append_network_observation(
        self,
        device_id: str,
        ts: int,
        dst_host: str | None,
        dst_ip: str | None,
        dst_port: int | None,
        proto: str | None,
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_network_events
                    (device_id, ts, dst_host, dst_ip, dst_port, proto)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (device_id, int(ts), dst_host, dst_ip, dst_port, proto),
            )
            return int(cur.lastrowid)

    def recent_network_events(
        self, device_id: str, since_ts: int | None = None, n: int = 500
    ) -> list[dict]:
        """Nedavne omrežne opazke naprave (ASC po ts)."""
        with self._get_connection() as conn:
            if since_ts is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM fs_network_events
                    WHERE device_id = ? AND ts >= ? ORDER BY ts ASC LIMIT ?
                    """,
                    (device_id, int(since_ts), int(n)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM fs_network_events
                    WHERE device_id = ? ORDER BY ts ASC LIMIT ?
                    """,
                    (device_id, int(n)),
                ).fetchall()
        return [dict(r) for r in rows]

    def known_destinations(
        self, device_id: str, before_ts: int | None = None
    ) -> set[str]:
        """Vse znane dst destinacije (host ali ip) naprave do ``before_ts``."""
        with self._get_connection() as conn:
            if before_ts is not None:
                rows = conn.execute(
                    """
                    SELECT dst_host, dst_ip FROM fs_network_events
                    WHERE device_id = ? AND ts < ?
                    """,
                    (device_id, int(before_ts)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT dst_host, dst_ip FROM fs_network_events
                    WHERE device_id = ?
                    """,
                    (device_id,),
                ).fetchall()
        out: set[str] = set()
        for r in rows:
            if r["dst_host"]:
                out.add(r["dst_host"])
            if r["dst_ip"]:
                out.add(r["dst_ip"])
        return out

    def network_device_count(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT device_id) AS n FROM fs_network_events"
            ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------ #
    #  Phase 2 — retencija / pruning
    # ------------------------------------------------------------------ #
    def prune_telemetry(self, older_than_ts: int) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM fs_telemetry WHERE ts < ?", (int(older_than_ts),)
            )
            return cur.rowcount or 0

    def prune_network_events(self, older_than_ts: int) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM fs_network_events WHERE ts < ?", (int(older_than_ts),)
            )
            return cur.rowcount or 0

    # ------------------------------------------------------------------ #
    #  Phase 3 — red team run-i
    # ------------------------------------------------------------------ #
    def append_redteam_run(
        self,
        device_id: str,
        payload_id: str,
        payload_name: str,
        vector_category: str,
        decision: str,
        judged_vulnerable: bool,
        severity: str,
        ran_at: int,
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_redteam_runs
                    (device_id, payload_id, payload_name, vector_category,
                     decision, judged_vulnerable, severity, ran_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id, payload_id, payload_name, vector_category,
                    decision, 1 if judged_vulnerable else 0, severity, int(ran_at),
                ),
            )
            return int(cur.lastrowid)

    def list_redteam_runs(self, device_id: str | None = None) -> list[dict]:
        with self._get_connection() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM fs_redteam_runs WHERE device_id = ? ORDER BY id",
                    (device_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM fs_redteam_runs ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    #  Phase 3 — model provenance history
    # ------------------------------------------------------------------ #
    def append_model_record(
        self,
        device_id: str,
        model_name: str,
        model_version: str,
        sha256: str,
        provider: str,
        pushed_by: str | None,
        pushed_at: int | None,
        repo_url: str | None,
        ts: int,
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fs_model_history
                    (device_id, model_name, model_version, sha256, provider,
                     pushed_by, pushed_at, repo_url, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id, model_name, model_version, sha256, provider,
                    pushed_by, pushed_at, repo_url, int(ts),
                ),
            )
            return int(cur.lastrowid)

    def latest_model_record(self, device_id: str) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM fs_model_history WHERE device_id = ?
                ORDER BY ts DESC, id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_model_history(self, device_id: str | None = None) -> list[dict]:
        with self._get_connection() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM fs_model_history WHERE device_id = ? ORDER BY id",
                    (device_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM fs_model_history ORDER BY id").fetchall()
        return [dict(r) for r in rows]
