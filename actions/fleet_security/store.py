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
    commit      TEXT,
    pr_url      TEXT,
    status      TEXT NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_remediations_device ON fs_remediations(device_id);
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
        self, findings: list[PostureFinding], now: int | None = None
    ) -> int:
        """Vstavi nove najdbe + resolve odprte, ki niso več v incoming.

        Dedup: če že obstaja odprta (device_id, category, detail), je ne
        podvaja. Vrne število vstavljenih.
        """
        now = int(now) if now is not None else _now()
        inserted = 0
        # Incoming (device_id, category, detail) seti po napravi.
        by_device: dict[str, set[tuple[str, str, str]]] = {}
        for f in findings:
            by_device.setdefault(f.device_id, set()).add(
                (f.category, f.detail, f.severity)
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
            # Resolve odprtih, ki niso več v incoming (isti device).
            for device_id, incoming in by_device.items():
                open_rows = conn.execute(
                    "SELECT * FROM fs_findings WHERE device_id = ? AND status = 'open'",
                    (device_id,),
                ).fetchall()
                for row in open_rows:
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
                    (device_id, kind, diff, branch, commit, pr_url, status,
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
