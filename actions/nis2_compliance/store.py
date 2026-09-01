"""nis2_compliance — per-firm SQLite store (C4 tenant izolacija, child #2).

Vsaka firma ima SVOJO DB datoteko pri ``db_root/<firma_id>.db`` — tenant
izolacija je na nivoju datotečnega sistema, kolizije nemogoče (UUID4), v path
ni PII-ja. Povezava prevzame vzorec ``core/world_model.py._get_connection``
(retry 3×, ``row_factory=Row``, ``PRAGMA journal_mode=WAL``) in
``actions/fleet_security/store.py``. Vse JSON vrednosti so shranjene s
``json.dumps(..., sort_keys=True)``. Deterministično, brez LLM.
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

from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    IntakeAnswer,
    ScopeResult,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS firm_profile (
    firm_id     TEXT PRIMARY KEY,
    naziv       TEXT NOT NULL,
    sektor      TEXT NOT NULL,
    zaposleni   INTEGER NOT NULL,
    promet_mio  REAL NOT NULL,
    kontakt     TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS scope_result (
    firm_id       TEXT PRIMARY KEY,
    tier          TEXT NOT NULL,
    razlog        TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    checked_at    INTEGER NOT NULL,
    FOREIGN KEY (firm_id) REFERENCES firm_profile(firm_id)
);

CREATE TABLE IF NOT EXISTS intake_answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id     TEXT NOT NULL,
    question_id TEXT NOT NULL,
    odgovor     TEXT NOT NULL,
    answered_at INTEGER NOT NULL,
    FOREIGN KEY (firm_id) REFERENCES firm_profile(firm_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_firm ON intake_answers(firm_id, question_id);

CREATE TABLE IF NOT EXISTS evidence_draft (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id       TEXT NOT NULL,
    obligation_id TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    status        TEXT NOT NULL,
    evidence_ref  TEXT NOT NULL DEFAULT '',
    updated_at    INTEGER NOT NULL,
    FOREIGN KEY (firm_id) REFERENCES firm_profile(firm_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_firm ON evidence_draft(firm_id, obligation_id, item_id);
"""


def _now() -> int:
    return int(time.time())


class Nis2Store:
    """Per-firm SQLite store. Vsaka firma svoja DB datoteka (C4 tenant izolacija).

    Konvencija: retry 3×, ``row_factory=Row``, WAL (vzorec world_model/
    fleet_security). Vse JSON vrednosti shranjene s
    ``json.dumps(..., sort_keys=True)``.
    """

    def __init__(self, db_root: Path | str, firm_id: str):
        self.firm_id = firm_id
        self.db_root = Path(db_root)
        self.db_path = self.db_root / f"{firm_id}.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(_SCHEMA_SQL)

    def get_connection(self) -> sqlite3.Connection:
        """Povezava z retry 3×, WAL, Row — vzorec world_model._get_connection."""
        last_err: Optional[Exception] = None
        for _ in range(3):
            try:
                conn = sqlite3.connect(self.db_path, timeout=5)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                return conn
            except sqlite3.OperationalError as e:
                last_err = e
                time.sleep(0.3)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ------------------------------------------------------------------ #
    #  Firm profile
    # ------------------------------------------------------------------ #
    def create_firm(self, profile: FirmProfile) -> None:
        """Vstavi profil firme. Duplikat firm_id → IntegrityError (fail-loud)."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO firm_profile
                    (firm_id, naziv, sektor, zaposleni, promet_mio, kontakt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.firm_id,
                    profile.naziv,
                    profile.sektor,
                    profile.zaposleni,
                    profile.promet_mio,
                    profile.kontakt,
                    profile.created_at,
                ),
            )

    def get_firm(self, firm_id: str) -> FirmProfile | None:
        """SELECT profil firme (None = ne obstaja, ne crash)."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM firm_profile WHERE firm_id = ?", (firm_id,)
            ).fetchone()
        return self._row_to_firm(row) if row else None

    @staticmethod
    def _row_to_firm(row: sqlite3.Row) -> FirmProfile:
        return FirmProfile(
            firm_id=row["firm_id"],
            naziv=row["naziv"],
            sektor=row["sektor"],
            zaposleni=row["zaposleni"],
            promet_mio=row["promet_mio"],
            kontakt=row["kontakt"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------ #
    #  Scope
    # ------------------------------------------------------------------ #
    def save_scope_result(self, firm_id: str, result: ScopeResult) -> None:
        """Upsert scope rezultata za firmo."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scope_result
                    (firm_id, tier, razlog, evidence_json, checked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    firm_id,
                    result.tier,
                    result.razlog,
                    json.dumps(result.evidence, sort_keys=True),
                    result.checked_at,
                ),
            )

    def get_scope_result(self, firm_id: str) -> ScopeResult | None:
        """SELECT scope rezultat (None = še ni določen)."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM scope_result WHERE firm_id = ?", (firm_id,)
            ).fetchone()
        if not row:
            return None
        return ScopeResult(
            tier=row["tier"],
            razlog=row["razlog"],
            evidence=json.loads(row["evidence_json"] or "{}"),
            checked_at=row["checked_at"],
        )

    # ------------------------------------------------------------------ #
    #  Intake
    # ------------------------------------------------------------------ #
    def save_intake_answers(self, firm_id: str, answers: list[IntakeAnswer]) -> None:
        """Vstavi vse intake odgovore firme (append-only)."""
        with self.get_connection() as conn:
            for a in answers:
                conn.execute(
                    """
                    INSERT INTO intake_answers (firm_id, question_id, odgovor, answered_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (firm_id, a.question_id, a.answer, a.answered_at),
                )

    def get_intake_answers(self, firm_id: str) -> list[IntakeAnswer]:
        """Vrne vse intake odgovore firme (vrstni red vstavljanja)."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM intake_answers WHERE firm_id = ? ORDER BY id",
                (firm_id,),
            ).fetchall()
        return [
            IntakeAnswer(
                question_id=r["question_id"],
                answer=r["odgovor"],
                answered_at=r["answered_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    #  Evidence
    # ------------------------------------------------------------------ #
    def save_evidence_draft(
        self, firm_id: str, evidence: list[EvidenceDraft], now: int | None = None
    ) -> None:
        """Vstavi draft evidence postavke firme (append-only)."""
        ts = int(now) if now is not None else _now()
        with self.get_connection() as conn:
            for e in evidence:
                conn.execute(
                    """
                    INSERT INTO evidence_draft
                        (firm_id, obligation_id, item_id, status, evidence_ref, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (firm_id, e.obligation_id, e.item_id, e.status, e.evidence_ref, ts),
                )

    def get_evidence_draft(self, firm_id: str) -> list[EvidenceDraft]:
        """Vrne vse draft evidence postavke firme (deterministično urejeno)."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM evidence_draft
                WHERE firm_id = ?
                ORDER BY obligation_id, item_id
                """,
                (firm_id,),
            ).fetchall()
        return [
            EvidenceDraft(
                obligation_id=r["obligation_id"],
                item_id=r["item_id"],
                status=r["status"],
                evidence_ref=r["evidence_ref"],
            )
            for r in rows
        ]
