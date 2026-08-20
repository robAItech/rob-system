"""core/memory_consolidation.py — Faza 4b / Zanka 1: spominska konsolidacija.

PROBLEM, ki ga rešuje ta modul
------------------------------
GBRAIN danes hrani le SUROVE epizode (``task_history``), blacklist vzorce in
KV vozlišča (``agent_memory_nodes``). Nič od tega se ne strdi v PONOVNO
UPORABLJIVE abstrakcije — sistem se iz napak uči le lokalno (isti projekt,
ista napaka), ne pa splošno (načelo, ki velja tudi drugje).

KONSOLIDACIJA = periodični proces (poganjaš ga ročno ali prek Task Schedulerja),
ki:
  1. prebere nove epizode (``task_history`` od zadnjega cursorja),
  2. jih združi po projektu + izidu,
  3. prek LLM-a (DeepSeek) strdi v SEMANTIČNE lekcije (principle/pitfall/procedure),
  4. jih shrani (dedup po ``theme``+``project``, ``confidence`` se akumulira),
  5. pomakne cursor.

``recall()`` nato te lekcije vrne nazaj v RSI healing (glej ``loopx_bridge``),
da se sistem uči KUMULATIVNO — ne samo iz zadnjega teka.

Brez veljavnega ključa (ali ``--dry-run``) uporabi determinističen hevrističen
fallback, da ostane testabilen in ne kuri LLM-a po nepotrebnem.

Uporaba:
  python core/memory_consolidation.py --run          # konsolidiraj nove epizode
  python core/memory_consolidation.py --run --dry-run
  python core/memory_consolidation.py --recall "popravi tekst na strani"
  python core/memory_consolidation.py --stats
  python core/memory_consolidation.py --prune 30     # arhiviraj epizode starejše od 30 dni
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo

# Samostojna skripta (`python core/memory_consolidation.py`) mora imeti repo
# koren na sys.path, da `from core.X import Y` deluje (enako kot run_swarm.py).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Zelo majhen nabor besed, ki jih pri točkovanju iskanja ignoriramo (slov. + angl.).
_STOPWORDS = {
    "in", "the", "a", "an", "to", "of", "for", "and", "or", "is", "are", "be",
    "na", "za", "v", "z", "in", "ki", "je", "so", "se", "da", "ne", "pa", "po",
    "iz", "do", "ali", "kot", "ter", "kjer", "kako", "kaj",
}

# Prehodne sonde / testne naprave, ki jih LoopX ali pytest zapišejo v task_history,
# a NISO pravi moduli stranke. Njihove epizode so šum, ne signal — ne strjamo jih.
_PROBE_PROJECTS = frozenset({
    "_loopx_probe", "test_matrix", "test_sum2", "quicktest", "healtest",
    "test", "testna", "demo_service", "svc",
    "master_test", "demo_bug", "count_words", "divide_safe", "fizzbuzz",
})
_PROBE_PREFIXES = ("_", "test_")


class MemoryConsolidator:
    """Strja surove epizode tekov v semantične, ponovno uporabljive lekcije.

    Živi v isti bazi kot GBRAIN (``.rob_ai/memory.db``), a lasti svoje tabele:
    ``semantic_memories`` (lekcije) in ``consolidation_state`` (cursor).
    """

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        # Ista pravila poti kot GBrainBridge: relativna pot se razreši iz repo
        # korena, da sočasni buildi iz različnih cwd-jev vidijo ISTO bazo.
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    #  Povezava + shema
    # ------------------------------------------------------------------ #
    def _get_connection(self) -> sqlite3.Connection:
        """Retry na 'database is locked' + WAL (enako kot GBrainBridge)."""
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    theme TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'principle',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    hits INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Dedup po (theme, project) — '' = splošna lekcija (cross-project).
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_theme
                ON semantic_memories (theme, project);
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_task_id INTEGER NOT NULL DEFAULT 0,
                    last_run_at DATETIME
                );
            """)
            conn.execute("""
                INSERT OR IGNORE INTO consolidation_state (id, last_task_id)
                VALUES (1, 0);
            """)
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Konsolidacija
    # ------------------------------------------------------------------ #
    def consolidate(self, max_episodes: int = 300, dry_run: bool = False) -> Dict[str, Any]:
        """Strči vse epizode, novejše od zadnjega cursorja, v semantične lekcije.

        Vrne povzetek: koliko epizod je bilo prebranih, koliko lekcij je bilo
        ustvarjenih/posodobljenih in ali je šlo za LLM ali hevristiko.
        """
        last_task_id = self._last_cursor()
        episodes = self._new_episodes(last_task_id, max_episodes)
        if not episodes:
            return {"new_episodes": 0, "probes_skipped": 0, "created": 0, "updated": 0, "mode": "none"}

        by_project: Dict[str, List[Dict[str, Any]]] = {}
        probes_skipped = 0
        for ep in episodes:
            if self._is_probe_project(ep["project"]):
                probes_skipped += 1
                continue
            by_project.setdefault(ep["project"], []).append(ep)

        use_llm = self._llm_available() and not dry_run
        created = updated = 0
        for project, group in by_project.items():
            # Kakovost: strdi le projekte z vsaj eno napako (signal). Uspešni teki
            # brez napake nimajo česa strdit — LLM bi sicer generiral floskule.
            if not any(self._is_failure(ep) for ep in group):
                continue
            memories = self._distill(project, group, use_llm)
            for m in memories:
                if dry_run:
                    created += 1          # prikaz, kaj bi nastalo — brez pisanja
                elif self._upsert(m):
                    created += 1
                else:
                    updated += 1

        max_seen = max(ep["task_id"] for ep in episodes)
        if not dry_run:
            self._advance_cursor(max_seen)

        return {
            "new_episodes": len(episodes),
            "projects": len(by_project),
            "probes_skipped": probes_skipped,
            "created": created,
            "updated": updated,
            "mode": "llm" if use_llm else "heuristic",
        }

    def _last_cursor(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT last_task_id FROM consolidation_state WHERE id = 1").fetchone()
            return int(row["last_task_id"]) if row else 0

    def _advance_cursor(self, task_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE consolidation_state SET last_task_id = ?, last_run_at = CURRENT_TIMESTAMP WHERE id = 1",
                (task_id,),
            )
            conn.commit()

    def _new_episodes(self, last_task_id: int, limit: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_history WHERE task_id > ? ORDER BY task_id ASC LIMIT ?",
                (last_task_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _llm_available() -> bool:
        try:
            from core.config import settings
            return settings.is_real_key_available()
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Distilacija
    # ------------------------------------------------------------------ #
    def _distill(self, project: str, episodes: List[Dict[str, Any]], use_llm: bool) -> List[Dict[str, Any]]:
        if use_llm:
            try:
                return self._distill_via_llm(project, episodes)
            except Exception as e:
                print(f"[MEM-CONS] LLM konsolidacija ni uspela ({e}) — hevristika.", flush=True)
        return self._distill_heuristic(project, episodes)

    def _distill_via_llm(self, project: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summary = self._summarize(project, episodes)
        system_prompt = (
            "Si spominski konsolidator avtonomnega inženirskega sistema. "
            "Iz surovih epizod tekov izlušči le KONKRETNE, ponovno uporabljive lekcije: "
            "specifične vzorce, napake in tehnike. NE vračaj splošnih floskul ali "
            "očitnih nasvetov (npr. 'bodi previden', 'uporabi funkcije', 'testiraj kodo'). "
            "Če iz epizod ni mogoče izluščiti konkretne lekcije, vrni prazno tabelo []."
        )
        prompt = (
            f"Projekt: {project}\n\nPovzetek tekov:\n{summary}\n\n"
            "Vrni STROGO JSON array (nič drugega) v obliki:\n"
            '[{"theme": "kratek SPECIFIČEN naslov", "content": "ena natančna lekcija z vzorcem/tehniko", '
            '"kind": "principle|pitfall|procedure", "confidence": 0.0-1.0}]\n\n'
            "Pravila:\n"
            "- vsaka lekcija mora vsebovati SPECIFIČEN vzorec, napako ali tehniko;\n"
            "- brez splošnih nasvetov ali floskul;\n"
            "- če ni konkretne lekcije, vrni [];\n"
            "- največ 3 lekcije."
        )
        from core.llm_client import DeepSeekLLMClient
        llm = DeepSeekLLMClient()
        raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        parsed = self._parse_json_array(raw)
        out: List[Dict[str, Any]] = []
        for item in parsed:
            theme = str(item.get("theme", "")).strip()
            content = str(item.get("content", "")).strip()
            # Minimalna specifičnost: zavrni presplošne/privatne lekcije.
            if len(theme) < 8 or len(content) < 30:
                continue
            out.append({
                "theme": theme[:120],
                "content": content[:2000],
                "kind": item.get("kind", "principle") if item.get("kind") in ("principle", "pitfall", "procedure") else "principle",
                "confidence": float(item.get("confidence", 0.5)),
            })
        return out

    def _distill_heuristic(self, project: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Determinističen fallback: iz neuspelih tekov strči 'pitfall' lekcije.

        Za vsak neuspeh klasificira napako in poišče mitigacijo v blacklistu.
        Ne kuri LLM-a — primerno za teste in okolja brez ključa.
        """
        out: List[Dict[str, Any]] = []
        seen = set()
        for ep in episodes:
            tb = ep.get("traceback") or ""
            if not self._is_failure(ep):
                continue
            err = self._classify_error(tb)
            if not err or err == "UNKNOWN":
                continue
            key = (project, err)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "theme": f"{project}: {err}",
                "content": self._mitigation_for(project, err) or f"Ponavljajoča se napaka {err} v projektu {project}.",
                "kind": "pitfall",
                "confidence": 0.4,
            })
        return out

    @staticmethod
    def _classify_error(traceback: str) -> str:
        tb = traceback or ""
        m = re.search(r"\b(\w+(?:Error|Exception))\b", tb)
        if m:
            return m.group(1)
        if "assert" in tb.lower():
            return "AssertionError"
        return "UNKNOWN"

    @staticmethod
    def _is_failure(ep: Dict[str, Any]) -> bool:
        """True, če je epizoda neuspel tek (ima signal za lekcijo)."""
        status = (ep.get("status") or "").upper()
        tb = ep.get("traceback") or ""
        return "FAIL" in status or (bool(tb) and (ep.get("verified_code") or "").upper() != "PASS")

    @staticmethod
    def _is_probe_project(project: str) -> bool:
        """True, če je projekt prehodna sonda/testna naprava (ni pravi modul)."""
        p = (project or "").strip()
        return not p or p in _PROBE_PROJECTS or p.startswith(_PROBE_PREFIXES)

    def _mitigation_for(self, project: str, error_pattern: str) -> str:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT mitigation FROM blacklist_patterns WHERE project = ? AND error_pattern LIKE ? LIMIT 1",
                (project, f"%{error_pattern}%"),
            ).fetchone()
            return str(row["mitigation"]) if row else ""

    @staticmethod
    def _summarize(project: str, episodes: List[Dict[str, Any]]) -> str:
        ok = sum(1 for e in episodes if "FAIL" not in (e.get("status") or "").upper())
        fail = len(episodes) - ok
        errors: Dict[str, int] = {}
        for e in episodes:
            err = MemoryConsolidator._classify_error(e.get("traceback") or "")
            if err != "UNKNOWN":
                errors[err] = errors.get(err, 0) + 1
        lines = [f"Projekt {project}: {len(episodes)} tekov (uspešnih {ok}, neuspelih {fail})."]
        if errors:
            lines.append("Napake: " + ", ".join(f"{k}×{v}" for k, v in sorted(errors.items(), key=lambda x: -x[1])))
        # Konkretni vzorci iz neuspelih tekov — material za specifične lekcije.
        failures = [e for e in episodes if MemoryConsolidator._is_failure(e)]
        for e in failures[:5]:
            prompt = (e.get("prompt") or "").strip().replace("\n", " ")[:140]
            tb = (e.get("traceback") or "").strip().replace("\n", " ")[:200]
            lines.append(f"- direktiva: {prompt} | napaka: {tb}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json_array(text: str) -> List[Any]:
        """Izvleče prvi JSON array iz LLM odgovora (robustno proti okolici)."""
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            val = json.loads(text[start:end + 1])
            return val if isinstance(val, list) else []
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    #  Shranjevanje
    # ------------------------------------------------------------------ #
    def _upsert(self, m: Dict[str, Any]) -> bool:
        """Vstavi ali posodobi lekcijo. Vrne True, če je bila NOVA (insert)."""
        with self._get_connection() as conn:
            before = conn.execute(
                "SELECT id FROM semantic_memories WHERE theme = ? AND project = ?",
                (m["theme"], m.get("project", "")),
            ).fetchone()
            conn.execute("""
                INSERT INTO semantic_memories (theme, content, project, kind, confidence)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(theme, project) DO UPDATE SET
                    content = excluded.content,
                    kind = excluded.kind,
                    confidence = MIN(1.0, semantic_memories.confidence + excluded.confidence * 0.3),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["theme"], m["content"], m.get("project", ""),
                m.get("kind", "principle"), float(m.get("confidence", 0.5)),
            ))
            conn.commit()
            return before is None

    def store(self, theme: str, content: str, project: str = "", kind: str = "principle",
              confidence: float = 0.5) -> bool:
        """Javni vmesnik za vpis ene lekcije (npr. iz Zanke 2 post-run review).

        Vrne True, če je bila lekcija NOVA (insert); False, če je posodobila obstoječo.
        """
        return self._upsert({
            "theme": theme, "content": content, "project": project,
            "kind": kind, "confidence": confidence,
        })

    # ------------------------------------------------------------------ #
    #  Priklic (recall)
    # ------------------------------------------------------------------ #
    def recall(self, query: str, project: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Vrne najbolj relevantne konsolidirane lekcije za poizvedbo.

        Točkovanje = prekrivanje žetonov + confidence + recenzentnost + uporaba.
        Brez embeddingov — hiter, brez odvisnosti, determinističen.
        """
        q_tokens = self._tokenize(query)
        with self._get_connection() as conn:
            if project:
                rows = conn.execute(
                    "SELECT * FROM semantic_memories WHERE project = ? OR project = ''",
                    (project,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM semantic_memories").fetchall()

        scored = []
        for r in rows:
            mem = dict(r)
            text = f"{mem['theme']} {mem['content']}".lower()
            overlap = sum(1 for t in q_tokens if t in text)
            if overlap == 0:
                continue
            # Recenzentnost: mlajše lekcije dobijo rahlo prednost.
            recency = 1.0  # SQLite nima enostavnega starostnega dostopa brez izračuna; ohranimo 1.0
            score = overlap * 1.0 + float(mem["confidence"]) * 2.0 + math.log1p(int(mem["hits"]))
            mem["score"] = round(score, 3)
            scored.append(mem)

        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored[:limit]

    @staticmethod
    def _tokenize(text: str) -> set:
        tokens = re.findall(r"[a-zčšž0-9_]+", (text or "").lower())
        return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}

    # ------------------------------------------------------------------ #
    #  Arhiviranje / statistika
    # ------------------------------------------------------------------ #
    def prune(self, days: int = 30) -> int:
        """Arhivira surove epizode starejše od `days` v ločeno tabelo (ne briše).

        Konsolidacija ostane idempotentna, ker cursor živi v consolidation_state.
        Vrne število arhiviranih vrstic.
        """
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history_archive (
                    task_id INTEGER PRIMARY KEY,
                    project TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    traceback TEXT,
                    verified_code TEXT,
                    timestamp DATETIME
                );
            """)
            cur = conn.execute("""
                INSERT INTO task_history_archive
                SELECT task_id, project, prompt, status, traceback, verified_code, timestamp
                FROM task_history WHERE timestamp < datetime('now', ?)
            """, (f"-{days} days",))
            moved = cur.rowcount
            conn.execute("DELETE FROM task_history WHERE timestamp < datetime('now', ?)", (f"-{days} days",))
            conn.commit()
            return moved

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM semantic_memories").fetchone()["n"]
            by_kind = {r["kind"]: r["n"] for r in conn.execute(
                "SELECT kind, COUNT(*) AS n FROM semantic_memories GROUP BY kind"
            ).fetchall()}
            cursor = conn.execute("SELECT last_task_id, last_run_at FROM consolidation_state WHERE id = 1").fetchone()
            try:
                episodes = conn.execute("SELECT COUNT(*) AS n FROM task_history").fetchone()["n"]
            except sqlite3.OperationalError:
                episodes = 0  # task_history še ne obstaja (GBrainBridge ni bil inicializiran)
        return {
            "semantic_memories": total,
            "by_kind": by_kind,
            "episodes_raw": episodes,
            "cursor_last_task_id": cursor["last_task_id"] if cursor else 0,
            "last_run_at": cursor["last_run_at"] if cursor else None,
        }


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="memory_consolidation", description="Zanka 1 — spominska konsolidacija.")
    p.add_argument("--run", action="store_true", help="konsolidiraj nove epizode v semantične lekcije")
    p.add_argument("--dry-run", action="store_true", help="prikaži, kaj bi se strdilo, brez pisanja")
    p.add_argument("--recall", metavar="QUERY", help="vrni relevantne lekcije za poizvedbo")
    p.add_argument("--project", default=None, help="omeji recall na projekt")
    p.add_argument("--prune", type=int, metavar="DAYS", help="arhiviraj epizode starejše od N dni")
    p.add_argument("--stats", action="store_true", help="izpiši statistiko spomina")
    args = p.parse_args(argv)

    cons = MemoryConsolidator()

    if args.run or args.dry_run:
        res = cons.consolidate(dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.recall:
        for m in cons.recall(args.recall, project=args.project):
            print(f"[{m['score']:.2f} · {m['kind']}] {m['theme']}\n  {m['content']}\n")
    elif args.prune:
        n = cons.prune(args.prune)
        print(f"Arhiviranih epizod: {n}")
    elif args.stats:
        print(json.dumps(cons.stats(), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
