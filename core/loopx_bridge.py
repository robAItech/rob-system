import subprocess
import sys
import json
import os
import re
import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import settings
from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.llm_client import DeepSeekLLMClient, estimate_tokens


# Evropski spomin: prostorsko in po človeško berljivo; brez agresivne redukcije.
RSI_PROMPT_SYSTEM = """Ti si RSI Loop (Recursive Self-Improvement) v avtonomnem sistemu Rob AI Studio.

Prejel si traceback neuspelega testa in izvirno kodo modula. Tvoja naloga:

1. Identificiraj glavni vzrok napake (import / logika / pydantic shema / testi).
2. Vrni POPOLNO vsebino VSEH datotek, ki jih je treba popraviti — nikoli samo izsek.
3. Ohrani vse delujoče funkcije, ki jih napaka ne zadeva.
4. Po vsaki datoteki uporabi format:
   ### FILE: actions/<module>/<ime>.py
   (celotna popravljena koda)
5. Na koncu ena kratka vrstica: kaj je bilo narobe in kaj si popravil.

CILJ: ko spremembe zapišem in znova poženem pytest, mora biti izhod 100% zelen.
Nekateri deli sistema imajo številne `actions/<module>/` datoteke. Vrni samo tiste,
ki jih je treba spremeniti. Ne izmišljaj novih datotek razen če so nujno potrebne.

ZAŠČITA (Test-Locking, P1): NIKOLI ne vračaj sprememb testnih datotek —
nobena »test_*.py«, »*_test.py«, »conftest.py« ali datoteka v »tests/« se ne sme
pojaviti v tvojem odzivu z ### FILE:. Verifikacijo (pytest) šteješ za nedotakljivo
merilo napake; če test ne gre skozi, je napaka v KODI, ne v testu. Sprememba testov
za dosego zelene barve je prepovedana manipulacija.
"""


# ── Agentic tool-use (korak 1) ──────────────────────────────────────────── #
# LLM v heal zanki lahko kliče orodja (read_file/write_file/list_files/
# search_memory) in iterira, namesto da se zanaša samo na ### FILE: bloke.
AGENTIC_MAX_TOOL_STEPS = 8

AGENTIC_TOOL_GUIDANCE = """UPORABA ORODIJ (function calling):
Imaš na voljo orodja read_file, write_file, list_files, search_memory, skill.
Najprej RAZIŠČI kodo v actions/<proj>/ z list_files/read_file; po potrebi vprašaj
search_memory. Nato zapiši POPRAVLJENE datoteke z write_file
(path = samo basename, content = POPOLNA vsebina). Po koncu vrni končni odgovor;
ta lahko še vedno vsebuje ### FILE: bloke, ki se uporabijo, če write_file
ni pokril vseh datotek. Ne vračaj test datotek (Test-Locking velja tudi tu).

SKILL: ko naloga zahteva procesno znanje iz GStack skilla (npr. spec, review, qa,
investigate, ship), pokliči skill(name='<slug>') in uporabi vrnjen vodič kot
kontekst. Za eno sekcijo uporabi `section`. Ne kliči orodij iz skilla
(bash/AskUserQuestion) — nimaš jih; dobiš le procesno znanje. Ne preplavi
konteksta: kliči skill največ 1–2-krat na cikel."""

TOOLS = [
    {"type": "function", "function": {"name": "read_file",
        "description": "Preberi vsebino datoteke v actions/<project>/ (basename).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Basename datoteke, npr. main.py"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file",
        "description": "Zapiši POPOLNO vsebino datoteke v actions/<project>/ (basename). Spoštuje Test-Locking.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Basename datoteke, npr. main.py"},
            "content": {"type": "string", "description": "Celotna nova vsebina datoteke"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "list_files",
        "description": "Seznam datotek v actions/<project>/.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_memory",
        "description": "Poišči naučene napake (blacklist) in konsolidirane lekcije za poizvedbo.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "skill",
        "description": "Pridobi strnjen procesni vodič GStack skilla (frontmatter + "
                       "procesni del, ~6000 znakov, brez ponavljajočega boilerplate-a). "
                       "Uporabni: spec, review, qa, investigate, plan-eng-review, "
                       "plan-ceo-review, ship, autoplan, document-generate. "
                       "name='list' ali prazen → seznam vseh skillov. Opcijsko `section` "
                       "vrne samo eno H2 sekcijo (npr. 'Process', 'Step 4').",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Slug skilla, npr. 'spec'. 'list' → seznam."},
            "section": {"type": "string", "description": "Opcijsko: ime H2 sekcije za ciljan izsek."}},
            "required": ["name"]}}},
]


# ── Korak 3 — upravljanje konteksta (budget heal prompta + trim agentic) ── #
HEAL_SOURCES_PER_FILE_MAX = 8000    # per-file cap sources v znakih
HEAL_SOURCES_MIN_KEEP = 1000        # ne drži praznega ostanka
HEAL_CORE_ENTRY_FILES = ("main.py", "__init__.py", "app.py", "index.py")
AGENTIC_CONTEXT_MIN = 20000         # spodnja meja agentic budgeta

TEST_PREFIXES = ("test_", "tests_")
TEST_SUFFIX_E = ("_test",)          # za basenames (po odstranitvi .py)
TEST_HARDNAME = {"conftest.py"}

# Diagnose-first: iz pytest izhoda izlušči DEJANSKI vzrok, ne glavo (header).
_PYTEST_FAILURE_TAIL = 1200   # padec: konec izhoda (FAILURES blok + summary)
_PYTEST_FAILURE_MAX = 2000    # skupni cap (heal traceback budget je 8000)
_PYTEST_SUMMARY_MAX = 700     # cap 'short test summary info' sekcije


def is_test_filename(name: str) -> bool:
    """True, če je datoteka test (Test-Locking predikat — LLM je ne sme spreminjati)."""
    if name.endswith(".py"):
        base = name[:-3]             # odstrani končnico .py
        if base.startswith(TEST_PREFIXES) or base.endswith(TEST_SUFFIX_E):
            return True
        if name in TEST_HARDNAME:
            return True
    return False


def _pid_alive(pid: int) -> bool:
    """Ali PID še obstaja (stale per-target lock cleanup). Unix: os.kill(pid,0).
    Windows: OpenProcess probe (os.kill(pid,0) tam vrže WinError 87 za vsak PID)."""
    import os
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return True  # ne moremo preveriti → ne briši stale locka (varno)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True  # nismo prepričani → smatramo živega (varno)


class LoopXEngineBridge:
    """Avtonomna verifikacijska zanka z RSI (self-healing + mednáložni spomin).

    Načrt 3.1–3.5:
    3.1  LLM je povezan v zanko in popravlja kodo ob rdečem testu.
    3.2  RSI prompt (zgornja predloga) usmerja LLM k koherentnim, polnim datotekam.
    3.3  Naučeno se zapisuje v GBRAIN blacklist (mednáložni spomin).
    3.4  Popravki so omejeni na actions/{project}/ (varnostna meja).
    3.5  Zelen cikel je dokončan šele, ko record_task vpiše rekord (ne 0).
    """

    # ✅ prag: če se isto error_type ponovi tolikokrat znotraj teka → zgodnja
    #    prekinitev (učenje iz ponavljajočih se napak, ne slepo kurjenje LLM).
    REPEAT_ABORT_AFTER = 3

    def __init__(self, project: str, db_path: Optional[Path] = None):
        self.project = project
        self.target_dir = Path(f"actions/{project}")
        self.registry_file = Path(".loopx/registry.json")
        # db_path (opcijsko) omogoča izolacijo testov od realne memory.db.
        self.gbrain = GBrainBridge(db_path) if db_path else GBrainBridge()
        self.graphify = GraphifyBridge()
        self.llm = DeepSeekLLMClient()
        self.max_attempts = 5
        self.repeat_abort_after = self.REPEAT_ABORT_AFTER  # Zanka 3: samorazvojni prag
        self.llm_calls = 0   # F5: števec LLM klicev za revizijo in cost-zavarovanje
        self._heal_fail_count: Dict[str, int] = {}   # error_signature → štev ponovitev v teku
        self.last_traceback = ""   # Z2/C2: zadnji REALEN traceback (za fix nalogo)
        self.surgical = False      # SURGICAL FIX: minimalen diff, brez re-scaffolda
        self.target_test = None    # ime padlega testa za targeted verify (pytest -k)
        self.required_files: List[str] = []   # MODIFY: testi, ki jih direktiva zahteva
        self._prompt_registry = None  # Zanka 3: lazy prompt-register (verzioniran prompt)
        self._skill_bridge = None     # Korak 6: lazy GStack skill bralec
        self._rollback_had_target = False  # Korak 10: je modul obstajal pred buildom?

    def _rsisystem_prompt(self) -> str:
        """Zanka 3 — RSI prompt iz registra; P3 — operativna načela; padec na konstanto."""
        try:
            if self._prompt_registry is None:
                from core.prompt_registry import PromptRegistry
                self._prompt_registry = PromptRegistry(self.gbrain.db_path)
            active = self._prompt_registry.get_active("rsi_heal_system", RSI_PROMPT_SYSTEM) or RSI_PROMPT_SYSTEM
            principles = self._prompt_registry.get_active("rsi_principles", "")
            if principles:
                try:
                    arr = json.loads(principles)
                    block = "OPERATIVNA NAČELA (upoštevaj pri popravilih):\n" + "\n".join(
                        f"- {p.get('principle')}" + (f" — {p.get('rationale')}" if p.get("rationale") else "")
                        for p in arr if isinstance(p, dict) and p.get("principle"))
                except Exception:
                    block = "OPERATIVNA NAČELA (upoštevaj pri popravilih):\n" + principles
                if block.strip():
                    active = active + "\n\n" + block
            return active
        except Exception:
            return RSI_PROMPT_SYSTEM

    def _load_tuning(self) -> None:
        """Zanka 3 — preberi samorazvojne parametre iz registra (padec na privzeto)."""
        try:
            from core.tuning import Tuning
            t = Tuning(self.gbrain.db_path)
            self.max_attempts = int(t.get("max_attempts", self.max_attempts))
            self.repeat_abort_after = int(t.get("repeat_abort_after", self.repeat_abort_after))
        except Exception:
            pass  # ob napaki ostanemo pri privzetih vrednostih

    def _get_skill_bridge(self):
        """Korak 6 — lazy GStack skill bralec (testi zamenjajo z Fake/SkillBridge(tmp))."""
        if self._skill_bridge is None:
            from core.skill_bridge import SkillBridge
            self._skill_bridge = SkillBridge()
        return self._skill_bridge

    # ------------------------------------------------------------------ #
    #  Stanje zanke
    # ------------------------------------------------------------------ #

    def update_loopx_state(self, status: str, attempt: int) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "project": self.project,
            "status": status,
            "current_attempt": attempt,
            "max_attempts": self.max_attempts,
        }
        # Atomično (tmp + os.replace): paralelni daemon — N buildov piše globalni
        # registry.json; atomic write prepreči korupcijo (last-writer-wins je OK,
        # ker je observability-only).
        tmp = self.registry_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.registry_file)

    # ------------------------------------------------------------------ #
    #  Pomožne funkcije
    # ------------------------------------------------------------------ #

    def _read_module_sources(self, include_tests: Optional[bool] = None) -> Dict[str, str]:
        """Prebere .py datoteke modula za posredovanje LLM-ju.

        Korak 3: test datoteke (test_*.py, *_test.py, conftest.py) so privzeto
        izpuščene — Test-Locking LLM-ju prepoveduje spreminjanje, v promptu pa so
        čist balast (~55 % pri velikih modulih). `include_tests` preglasi settings.
        """
        include_tests = settings.llm_heal_include_tests if include_tests is None else include_tests
        sources = {}
        target = Path(f"actions/{self.project}")
        if target.exists():
            for p in target.glob("*.py"):
                if not include_tests and is_test_filename(p.name):
                    continue
                sources[p.name] = p.read_text(encoding="utf-8")
        return sources

    @staticmethod
    def _parse_patched_files(text: str) -> Dict[str, str]:
        """Iz LLM odziva izlušči datoteke v formatu `### FILE: <path>`.

        Enako formatu, kot ga uporablja HERMES/run_swarm — za konsistenco
        po celotnem sistemu.
        """
        files: Dict[str, str] = {}
        # F1: sprejmemo kateri koli jezikovni label v backtick bloku
        # (```python```, ```markdown```, ```html``` ... ali nič). `(raw)` zato.
        pattern = re.compile(
            r"### FILE:\s*([^\n]+)\n```(?:[a-zA-Z0-9_+-]*)\n(.*?)```",
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            # Path iz LLM lahko pride kot `actions/<proj>/<file>.py` ali `<file>.py`.
            # _apply_patch razrešuje samo goli basename (varnost path traversal),
            # zato tu izvlečemo zadnji segment (basename).
            base = m.group(1).strip().replace("\\", "/").split("/")[-1]
            files[base] = m.group(2).strip()
        return files

    def _apply_patch(self, files: Dict[str, str]) -> int:
        """Zapiše popravljene datoteke nazaj v actions/{project}/.

        Omejeno na target_dir (3.4): vsak ključ se razreši na absolutno pot
        in zapiše le, če ostane znotraj modula. Path-traversal (npr.
        ``../../etc/passwd`` ali ``/abs/path``) se zavrne — absolutna in
        izhodna poti nikoli ne pišejo izven modula.
        """
        allowed = self.target_dir.resolve()
        written = 0
        # F1: dovoljene končnice poleg .py — Markdown in HTML (dokumentni izdelki).
        ALLOWED_EXT = (".py", ".md", ".html", ".htm")
        # P1 — Test-Locking (niansirano): LLM ne sme spreminjati ŽE OBSTOJEČE
        # verifikacijske datoteke (test_*.py, *_test.py, conftest.py) — s tem bi
        # med samozdravljenjem ponaredil assert → lažno "100% zeleno" (Test
        # Tampering). AMPAK pri PRVOTNI gradnji novega modula LLM legitimno
        # USTVARI test (test ne obstaja) — to je dovoljeno, ker ni tamper.
        # Odločitev: test datoteka se zavrne le, če ŽE OBSTAJA na disku; če
        # ne obstaja (nova) → dovolimo pisanje, da RSI build lahko napiše test.
        for rel, content in files.items():
            # Veljavni ključi so goli basename (brez separatorja/traversal).
            # Vsak separator ali traversal ('.', '..', '/', '\') -> zavrni,
            # da nikoli ne pišemo izven target_dir (3.4).
            if "/" in rel or "\\" in rel or rel in (".", "..", "") or not rel.endswith(ALLOWED_EXT):
                continue
            cand = (allowed / rel).resolve()
            # P1 — Test-Locking: tamper z OBSTOJEČO, VREDNO test datoteko zavrni.
            # Glej tudi: HERMES `write_initial_stubs_if_missing` ustvari prazen
            # stub (npr. "def test_():\n    pass…"), ki je zgolj ogrodje —
            # LLM ob gradnji legitimno DOPOLNI ta stub, kar ni tamper. Zato
            # test datoteka se zavrne LE, če obstaja Z VSEBINO (> STUB_PRAH_BAJTOV);
            # prazen/nov stub se pusti dokončati.
            STUB_PRAH_BAJTOV = 30
            if is_test_filename(rel) and cand.exists():
                try:
                    _existing_ok = len(cand.read_text(encoding="utf-8")) > STUB_PRAH_BAJTOV
                except OSError:
                    _existing_ok = True
                if _existing_ok:
                    continue
            if cand.parent != allowed:
                continue
            cand.write_text(content, encoding="utf-8")
            written += 1
        return written

    # ------------------------------------------------------------------ #
    #  3.1–3.3  LLM popravek + RSI zanka + zapis v GBRAIN
    # ------------------------------------------------------------------ #

    def _heal_once(self, traceback: str, directive: str, kind: str = "python") -> Tuple[bool, str]:
        """Poskuša popraviti kodo/zdelek z LLM-jem (3.1, 3.2).

        Dispečer: zgradi prompt + system prompt, nato izbere pot — agentic
        (tool-use, če je vklopljeno) ali tekstovno (### FILE:). Vrni (uspeh, poročilo).
        """
        prompt = self._build_heal_prompt(traceback, directive, kind)
        system_prompt = self._rsisystem_prompt()
        if settings.llm_tool_use:
            return self._heal_agentic(prompt, system_prompt)
        return self._heal_text(prompt, system_prompt)

    def _gather_memory_notes(self, query: str, limit_learned: int = 10, limit_cons: int = 5) -> str:
        """F4/F4b — naučene napake (blacklists) + konsolidirane lekcije v en niz.

        Deterministično (token-overlap, brez LLM/embeddingov); uporabita ga tako
        prompt builder kot orodje `search_memory`. Ob napaki se varno preskoči.
        """
        try:
            learned = self.gbrain.get_blacklists(self.project)
        except Exception:
            learned = []
        learned_note = ""
        if learned:
            pats = "; ".join(
                f"{b.get('error_pattern','?')} → {b.get('mitigation','')[:60]}" for b in learned[:limit_learned]
            )
            learned_note = (
                "Naučeno iz prejšnjih poskusov (izogni se tem napakam):\n"
                f"{pats}\n\n"
            )
        try:
            from core.memory_consolidation import MemoryConsolidator
            consolidated = MemoryConsolidator(self.gbrain.db_path).recall(
                query, project=self.project, limit=limit_cons
            )
        except Exception:
            consolidated = []
        cons_note = ""
        if consolidated:
            lessons = "; ".join(f"{m['theme']}: {m['content'][:90]}" for m in consolidated)
            cons_note = (
                "Konsolidirane lekcije iz preteklih tekov (upoštevaj):\n"
                f"{lessons}\n\n"
            )
        return learned_note + cons_note

    def _safe_target_test(self) -> Optional[str]:
        """Samo varni test-names (identifiers) za `pytest -k`; sicer None → poln suite.

        Varnost: `-k` gre v shell (sh -c) v sandboxu — dovoli le [A-Za-z0-9_].
        """
        tt = (self.target_test or "").strip()
        return tt if tt and re.fullmatch(r"[A-Za-z0-9_]+", tt) else None

    def _module_fingerprint(self) -> str:
        """Prstni odtis actions/<project>/ (rel. pot + md5 vsebine) za zaznavo
        sprememb pri MODIFIKACIJAH. Izključi __pycache__/.pytest_cache/*.pyc."""
        import hashlib
        parts = []
        if self.target_dir.exists():
            for p in sorted(self.target_dir.rglob("*")):
                if (p.is_file() and not p.name.endswith(".pyc")
                        and "__pycache__" not in p.parts
                        and ".pytest_cache" not in p.parts):
                    try:
                        h = hashlib.md5(p.read_bytes()).hexdigest()[:12]
                    except OSError:
                        h = "?"
                    parts.append(f"{p.relative_to(self.target_dir)}:{h}")
        return "|".join(parts)

    def _module_changed(self) -> bool:
        """Ali se je actions/<project>/ spremenil od začetka tega teka.

        Uporablja se pri MODIFIKACIJAH (kind="modify"): če je build zelen, a nič
        ni spremenjeno → FALSE GREEN (zahtevana sprememba ni bila izvedena).
        """
        return self._module_fingerprint() != getattr(self, "_baseline_fingerprint", "")

    def _missing_required_files(self) -> List[str]:
        """MODIFY — zahtevani testi iz direktive, ki (še) ne obstajajo.

        Če direktiva imenuje npr. `test_truncate_start.py` (nov test za zahtevano
        funkcijo), mora heal zanka ta test USTVARITI — sicer je "zelen" le
        potrditev obstoječih testov, ne izvedba spremembe.
        """
        return [f for f in self.required_files if not (self.target_dir / f).exists()]

    def _surgical_note(self) -> str:
        """SURGICAL FIX: omejitev minimalnega diffa, vstavljena v heal prompt."""
        if not self.surgical:
            return ""
        tt = self.target_test or "(celoten suite)"
        return (
            "SURGICAL FIX NAČIN (OBVEZNO):\n"
            "To je POPRAVEK obstoječega modula, NE nova gradnja. "
            "Naredi MINIMALNO spremembo samo tistega dela kode, ki poganja padli test.\n"
            "- Vrni samo datoteke, ki se morajo SPREMENITI (obstoječe; NOBENE nove datoteke).\n"
            "- Ne prestrukturiraj modula in ne spreminjaj delujočih funkcij/uvozov/razredov, "
            "ki niso del napake.\n"
            "- Ne dodajaj novih datotek (npr. main.py, schemas.py, novih testov).\n"
            f"- Ciljni padli test: <{tt}>. Popravi SAMO njegovo kodno pot.\n"
            "- Zeleno merilo: ciljni test + CELOTEN obstoječi test suite ostaneta zelena.\n\n"
        )

    def _diagnose_first_note(self, traceback: str) -> str:
        """DIAGNOSTIKA PRED POPRAVKOM — ko vzrok ni razvrščen ali ni padlega
        testa (stub, import napaka, ruff), naj LLM NAJPREJ ugotovi dejanski
        vzrok, šele nato popravi. Ne ponavlja istega ugiba."""
        tb = traceback or ""
        has_test = bool(re.search(r"\btest_[A-Za-z0-9_]+\b", tb))
        if self._classify_error(tb) != "UNKNOWN" and has_test:
            return ""   # znan tip + znan padel test → normalen popravek
        return (
            "DIAGNOSTIKA PRED POPRAVKOM (OBVEZNO):\n"
            "Vzrok verifikacije ni jasno razvrščen ali ni prepoznanega padlega testa. "
            "Najprej PREBERI vse datoteke modula in identificiraj TOČEN vzrok: "
            "manjkajoč uvoz, struktura, stub/prazna datoteka, logika. "
            "Nato popravi. NE ponavljaj istega ugiba kot prejšnji poskus.\n\n"
        )

    def _build_heal_prompt(self, traceback: str, directive: str, kind: str = "python") -> str:
        """Sestavi heal prompt: sources + direktiva + spec/memory/graph/rag + traceback + out_note.

        Korak 3 — budget: celoten prompt ≤ `llm_heal_prompt_chars`; prioriteta
        traceback > directive > spec/memory/graph/rag > sources. Sources se skrčijo
        prek `_fit_sources` (relevanca na napako + entry-point + velikost).
        """
        sources = self._read_module_sources()
        # Navodilo za izhod glede na vrsto izdelka (F1).
        if kind == "markdown":
            out_note = "Vrni POPOLN Markdown dokument v formatu ### FILE: ime.md\\n```markdown\\n<vsebina>\\n``` (z naslovom #, brez placeholdoj)."
        elif kind == "html":
            out_note = "Vrni POPOLNO HTML stran v formatu ### FILE: ime.html\\n```html\\n<vsebina z </html>>\\n``` (veljavna, brez placeholdoj)."
        else:
            out_note = "Vrni POPOLNE, delujoča Python datoteko v formatu ### FILE: ime.py\\n```python\\n<koda>\\n``` (vse datoteke popolne, brez placeholdoj, dejanska implementacija)."
        # P2 — recall poizvedba brez [PLAN KONTEKST] prefiksa (prepreči dvojno
        # injiciranje spomina; direktiva za LLM obdrži poln tekst).
        from core.plan_context import strip_plan_context
        memory_note = self._gather_memory_notes(strip_plan_context(directive))
        # Graf-kontekst (graphify): LLM vidi dependency pregled za ciljni modul.
        # Varno: če render pade, nadaljujemo brez njega (ne blokiramo healinga).
        try:
            graph_ctx = self.graphify.render_context(self.project)
        except Exception:
            graph_ctx = ""
        graph_note = f"KODNI GRAF (dependency kontekst):\n{graph_ctx}\n\n" if graph_ctx else ""
        # Code-RAG: semantično najbolj relevantne kode po celem repu (referenca za LLM).
        try:
            relevant = self.graphify.retrieve_relevant(directive, limit=3)
        except Exception:
            relevant = []
        rag_note = ""
        if relevant:
            blocks = "\n\n".join(f"// {r['path']} (podobnost {r['overlap']})\n{r['snippet']}" for r in relevant)
            rag_note = f"RELEVANTNA KODA (podobni vzorci iz repa):\n{blocks}\n\n"
        # P0 — spec_hint: arhitekturna usmeritev iz GStack manifesta. Korak 3: cap 4000.
        spec_hint = getattr(self, "spec_hint", None) or ""
        spec_note = f"SPEC (arhitekturna usmeritev izvedbe):\n{spec_hint[:4000]}\n\n" if spec_hint else ""
        notes = (self._surgical_note() + self._diagnose_first_note(traceback)
                 + spec_note + memory_note + graph_note + rag_note)
        directive_note = f"DIREKTIVA (kaj naj izdelek dejansko vsebuje):\n{directive[:3000]}\n\n"
        traceback_note = f"Razlog verifikacije (doseči je treba zelen):\n{traceback[:8000]}\n\n"

        prompt_budget = max(2000, int(settings.llm_heal_prompt_chars))
        fixed = len(directive_note) + len(notes) + len(traceback_note) + len(out_note) + 300
        sources_budget = int(settings.llm_heal_sources_chars)
        sources_budget = min(sources_budget, max(0, prompt_budget - fixed))

        fitted: Dict[str, str] = sources
        omitted: List[str] = []
        truncated: List[str] = []
        for _ in range(4):                       # konvergenčna zanka na budget
            fitted, omitted, truncated = self._fit_sources(sources, sources_budget, traceback, directive)
            manifest_note = self._manifest_note(sources, omitted, truncated)
            sources_json = json.dumps(fitted, ensure_ascii=False, indent=2)
            prompt = (
                f"Izvirna vsebina modula `{self.project}` (trenutno ogrodje/stubs):\n"
                f"{sources_json}\n\n"
                f"{manifest_note}"
                f"{directive_note}"
                f"{notes}"
                f"{traceback_note}"
                f"{out_note}"
            )
            if len(prompt) <= prompt_budget:
                break
            sources_budget = max(0, int(sources_budget * 0.6) - 1000)

        if omitted or truncated:
            print(f"[LOOPX] heal prompt: {len(prompt)} znakov, ~{estimate_tokens(prompt)} tokenov "
                  f"(izpuščeno: {len(omitted)}, okršeno: {len(truncated)})", flush=True)
        return prompt

    @staticmethod
    def _fit_sources(sources: Dict[str, str], budget: int, traceback: str, directive: str):
        """Deterministično skrči sources na budget.

        Vrne (fitted, omitted, truncated). Ključ: relevantnost na napako
        (token-overlap s traceback/direktivo), nato entry-point, nato velikost.
        """
        if not sources:
            return sources, [], []
        if sum(len(v) for v in sources.values()) <= budget:
            return sources, [], []

        def _toks(text: str) -> set:
            return set(re.findall(r"[a-zA-Z_]\w{2,}", (text or "").lower()))
        _STOP = {"def", "class", "import", "from", "self", "return", "assert", "file", "line",
                 "in", "for", "while", "if", "else", "raise", "test", "none", "true", "false",
                 "and", "the", "with", "as", "is", "not", "or"}
        tb = _toks(traceback) - _STOP
        dv = _toks(directive) - _STOP

        def _score(name: str) -> int:
            content = sources[name].lower()
            base = 2 * len(tb & _toks(content)) + len(dv & _toks(content))
            if name in HEAL_CORE_ENTRY_FILES:
                base += 2                      # entry-point bonus
            return base

        ordered = sorted(sources, key=lambda n: (-_score(n), len(sources[n]), n))
        fitted: Dict[str, str] = {}
        omitted: List[str] = []
        truncated: List[str] = []
        remaining = budget
        for name in ordered:
            content = sources[name]
            per = min(HEAL_SOURCES_PER_FILE_MAX, remaining)
            if len(content) <= per:
                fitted[name] = content
                remaining -= len(content)
            elif remaining >= HEAL_SOURCES_MIN_KEEP and len(content) > HEAL_SOURCES_MIN_KEEP:
                tail = f"\n... [IZREZANO — {len(content)} znakov; preberi z read_file]"
                keep = max(200, min(per, remaining) - len(tail))
                if keep >= 200:
                    fitted[name] = content[:keep] + tail
                    truncated.append(name)
                    remaining = 0
                else:
                    omitted.append(name)
            else:
                omitted.append(name)
            if remaining <= 0:
                break
        return fitted, omitted, truncated

    @staticmethod
    def _manifest_note(sources: Dict[str, str], omitted: List[str], truncated: List[str]) -> str:
        """Seznam vseh datotek modula z oznako izpuščenih/okršenih — samo ko je kaj izpuščeno."""
        if not omitted and not truncated:
            return ""
        lines = []
        for name in sorted(sources):
            flag = " [IZPUŠČENO]" if name in omitted else (" [OKRŠENO]" if name in truncated else "")
            lines.append(f"- {name} ({len(sources[name])} B){flag}")
        return ("DATOTEKE MODULA (vse; vsebina označenih ni vključena — v agentic "
                "načinu preberi z read_file):\n" + "\n".join(lines) + "\n\n")

    def _agentic_context_budget(self) -> int:
        return max(AGENTIC_CONTEXT_MIN, int(settings.llm_heal_agentic_context_chars))

    @staticmethod
    def _trim_agentic_messages(messages: List[Dict[str, Any]], max_chars: int) -> List[Dict[str, Any]]:
        """Izloči NAJSTAREJŠE ZAKLJUČENE tool-cikle, dokler vsota ≤ max_chars.

        Vedno obdrži system+user+AKTIVNI cikel (zadnji assistant s tool_calls +
        njegovi tool odgovori), da tool_call_id nikoli ne visi brez predhodnika.
        """
        if not messages:
            return messages

        def _size(m: Dict[str, Any]) -> int:
            return len(json.dumps(m, ensure_ascii=False))

        if sum(_size(m) for m in messages) <= max_chars:
            return messages
        # head = system+user (defenzivno, če ni standardne oblike).
        head_end = 2
        if messages[0].get("role") != "system":
            head_end = 0
        elif len(messages) < 2:
            head_end = len(messages)
        # tail = aktivni cikel: od zadnjega assistant s tool_calls do konca.
        tail_start = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant" and messages[i].get("tool_calls"):
                tail_start = i
                break
        if tail_start is None:
            tail_start = max(head_end, len(messages) - 1)
        head, tail = messages[:head_end], messages[tail_start:]
        middle = messages[head_end:tail_start]
        fixed = sum(_size(m) for m in head) + sum(_size(m) for m in tail)
        if fixed > max_chars:
            return messages                     # varni padec: ne zlomi cikla
        budget_mid = max_chars - fixed
        # middle razdelimo na CELE cikle (assistant + njegovi tool odgovori).
        groups: List[List[Dict[str, Any]]] = []
        cur: List[Dict[str, Any]] = []
        for m in middle:
            if m.get("role") == "assistant" and cur:
                groups.append(cur)
                cur = [m]
            else:
                cur.append(m)
        if cur:
            groups.append(cur)
        keep: List[List[Dict[str, Any]]] = []
        kept = 0
        for g in reversed(groups):              # najnovejše cikle obdrži
            gs = sum(_size(x) for x in g)
            if kept + gs <= budget_mid:
                keep.append(g)
                kept += gs
            else:
                break
        keep.reverse()
        return head + [m for g in keep for m in g] + tail

    def _heal_text(self, prompt: str, system_prompt: str) -> Tuple[bool, str]:
        """Tekstovna pot: LLM vrne ### FILE: bloke → razreži → zapiši."""
        try:
            self.llm_calls += 1   # F5: revizijski števec LLM klicev
            # generate_completion je async korutina; zanko držimo sync,
            # zato LLM klic v tem kontekstu zaženemo prek asyncio.
            response = asyncio.run(
                self.llm.generate_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    use_coder_model=True,
                )
            )
        except Exception as e:
            print(f"[LOOPX] LLM napaka pri healingu: {e}", flush=True)
            return False, f"LLM napaka pri healingu: {e}"

        print(f"[LOOPX] LLM odziv ({len(response)} znakov): {response[:200]!r}", flush=True)
        files = self._parse_patched_files(response)
        print(f"[LOOPX] razčlenjeno datotek: {list(files.keys())}", flush=True)
        if not files:
            return False, "LLM ni vrnil datotek v formatu ### FILE: ..."

        written = self._apply_patch(files)
        print(f"[LOOPX] zapisanih datotek: {written}", flush=True)
        if written == 0:
            return False, "Uporabljene datoteke niso bile zapisane (omejitev 3.4)."

        return True, f"Uporaba {written} datotek(e)."

    def _heal_agentic(self, prompt: str, system_prompt: str) -> Tuple[bool, str]:
        """Agentic pot: LLM kliče orodja (read/write/list/search), iterira, nato
        vrne končni odgovor. Uspeh tudi, če so datoteke zapisane prek `write_file`
        brez ### FILE: blokov. Ob izjemi pade na tekstovno pot (`_heal_text`)."""
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{AGENTIC_TOOL_GUIDANCE}"},
            {"role": "user", "content": prompt},
        ]
        written_via_tool = 0
        for _step in range(AGENTIC_MAX_TOOL_STEPS):
            # Korak 3 — trim kumulativnega konteksta (obdrži aktivni cikel atomično).
            messages = self._trim_agentic_messages(messages, self._agentic_context_budget())
            self.llm_calls += 1
            try:
                # complete_with_tools je async korutina; zanko držimo sync.
                msg = asyncio.run(self.llm.complete_with_tools(
                    messages, TOOLS, tool_choice="auto", use_coder_model=True))
            except Exception as e:
                print(f"[LOOPX] agentic klic padel, padam na tekst: {e}", flush=True)
                if written_via_tool > 0:
                    return True, f"Zapisano prek orodij: {written_via_tool} datotek(e)."
                return self._heal_text(prompt, system_prompt)
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                # Končni odgovor: ### FILE: bloki kot rezervna pot; uspeh štejejo
                # tudi že zapisane datoteke prek write_file.
                content = msg.get("content") or ""
                files = self._parse_patched_files(content)
                if files:
                    written_via_tool += self._apply_patch(files)
                if written_via_tool == 0:
                    return False, "LLM ni vrnil uporabnih datotek (### FILE ali write_file)."
                return True, f"Uporaba {written_via_tool} datotek(e)."
            # Assistant message s tool_calls posredujemo NEDOTAKNJEN (ohrani
            # reasoning_content); nato serijsko izvedemo vsa orodja.
            messages.append(msg)
            for call in tool_calls:
                call_id = call.get("id")
                name = (call.get("function") or {}).get("name")
                raw_args = (call.get("function") or {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {}
                result = self._execute_tool(name, args)
                if name == "write_file" and result.get("ok"):
                    written_via_tool += int(result.get("written", 0))
                messages.append({"role": "tool", "tool_call_id": call_id,
                                 "content": json.dumps(result, ensure_ascii=False)})
        return False, f"Agentic zanka ni zaključila v {AGENTIC_MAX_TOOL_STEPS} korakih."

    def _safe_resolve(self, rel: str) -> Optional[str]:
        """Normalizira pot LLM-ja na goli basename (traversal se neutralizira);
        `_apply_patch` ostaja edini avtoritativen varnostni filter."""
        if not isinstance(rel, str) or not rel.strip():
            return None
        base = rel.strip().replace("\\", "/").split("/")[-1]
        if not base or base in (".", ".."):
            return None
        return base

    def _execute_tool(self, name, args: Dict[str, Any]) -> Dict[str, Any]:
        """Izvede orodje; NIKOLI ne dvigne — napake se vrnejo kot dict, da jih LLM vidi."""
        try:
            if name == "list_files":
                files = (sorted(p.name for p in self.target_dir.iterdir() if p.is_file())
                         if self.target_dir.exists() else [])
                return {"ok": True, "files": files}
            if name == "read_file":
                base = self._safe_resolve(str(args.get("path", "")))
                if base is None:
                    return {"ok": False, "error": "path manjka ali ni veljaven basename"}
                path = self.target_dir / base
                if not path.exists():
                    return {"ok": False, "error": f"datoteka ne obstaja: {base}"}
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > 20000:
                    text = text[:20000] + f"\n...[izrezano, skupaj {len(text)} znakov]"
                return {"ok": True, "path": base, "content": text}
            if name == "write_file":
                base = self._safe_resolve(str(args.get("path", "")))
                content = args.get("content", "")
                if not isinstance(content, str):
                    content = str(content) if content is not None else ""
                if base is None:
                    return {"ok": False, "error": "path manjka ali ni veljaven basename"}
                written = self._apply_patch({base: content})
                if written == 0:
                    return {"ok": False, "written": 0, "path": base,
                            "error": "zavrnjeno (test-lock / dovoljene končnice / traversal)"}
                return {"ok": True, "written": written, "path": base}
            if name == "search_memory":
                notes = self._gather_memory_notes(str(args.get("query", "")))
                return {"ok": True, "notes": notes or "(ni naučenih lekcij za poizvedbo)"}
            if name == "skill":
                slug = args.get("name", "") or ""
                section = args.get("section")
                if not isinstance(section, str) or not section.strip():
                    section = None
                bridge = self._get_skill_bridge()
                if str(slug).strip().lower() in ("", "list", "_list"):
                    skills = bridge.list_skills()
                    return {"ok": True, "count": len(skills), "skills": skills}
                skill = bridge.get_skill(str(slug), section=section)
                if skill is None:
                    names = ", ".join(s["name"] for s in bridge.list_skills()[:15])
                    return {"ok": False, "error": f"skill ni najden ali ni uporaben: {slug}",
                            "available": names}
                return {"ok": True, **skill}
            return {"ok": False, "error": f"neznano orodje: {name}"}
        except Exception as e:
            return {"ok": False, "error": f"napaka pri izvedbi orodja {name}: {e}"}

    @staticmethod
    def _classify_error(traceback: str) -> str:
        """Povzame tip napake (ExceptionName) iz tracebacka, sicer 'UNKNOWN'.

        Prepozna tudi pytest assert neuspehe ('assert X == Y'), ki nimajo
        eksplicitnega 'AssertionError:' vzorca.
        """
        tb = traceback or ""
        tb_lower = tb.lower()
        # Diagnose-first: modul brez testov (stub) je posebna, smiselna klasifikacija
        # — ne UNKNOWN. LLM razume: "modul nima pravega testa → implementiraj kodo+test".
        if ("no tests collected" in tb_lower or "no tests ran" in tb_lower
                or "collected 0 items" in tb_lower):
            return "NoTestsCollected"
        # Ruff F821 pre-gate: undefined name → NameError (namesto UNKNOWN).
        if "f821" in tb_lower or "undefined name" in tb_lower:
            return "NameError"
        m = re.search(r"\b(\w+(?:Error|Exception))\b", tb)
        if m:
            return m.group(1)
        if "assert" in tb.lower():
            return "AssertionError"
        return "UNKNOWN"

    @staticmethod
    def _extract_pytest_failure(msg: str, returncode: int) -> str:
        """Iz celotnega pytest izhoda izlušči DEJANSKI vzrok, ne glavo (header).

        - rc==0 (zelen)      → "" (klicatelj doda kratko ok-sporočilo)
        - rc==5 (ni testov)  → konec izhoda ('collected 0 items' / 'no tests ran'):
            LLM mora razumeti, da modul NIMA pravega testa (stub), ne da je koda padla.
        - rc!=0 (rdeč)       → prvi FAILURES blok (poln traceback + izvorna vrstica)
            + 'short test summary info' (vsi padli testi z izjemami). Padec na tail.
        """
        msg = msg or ""
        if returncode == 0:
            return ""
        if returncode == 5:
            tail = msg[-800:].strip()
            return tail or "pytest: no tests collected (stub / nobene testne datoteke)"
        parts = []
        # (1) prvi neuspeh blok: separator '____ test_x ____' → naslednji sep / summary
        sep = re.search(r"_{6,}\s+.+?\s+_{6,}", msg)
        if sep:
            rest = msg[sep.end():]
            nxt = re.search(r"_{6,}\s+.+?\s+_{6,}|short test summary info", rest)
            block = rest[: nxt.start()] if nxt else rest
            parts.append((msg[sep.start():sep.end()] + "\n" + block).strip()[:1000])
        # (2) kompakten seznam vseh padlih testov z izjemami
        sm = re.search(r"short test summary info", msg, re.IGNORECASE)
        if sm:
            parts.append(msg[sm.start():].strip()[:_PYTEST_SUMMARY_MAX])
        if parts:
            return "\n\n".join(parts)[:_PYTEST_FAILURE_MAX]
        return msg[-_PYTEST_FAILURE_TAIL:].strip()

    @staticmethod
    def _error_signature(reason: str) -> str:
        """Ostrejši podpis napake za repeat-abort: error_type + sidro (padel test).

        Samo resnično IDENTIČNE napake štejejo v `_heal_fail_count` — dve različni
        napaki istega tipa (npr. ValueError na različnih testih) se NE seštejeta,
        zato se ne prekine napredka. Sidro = zadnje `test_<ime>` iz tracebacka
        (stabilno čez heale, ki premikajo vrstice); če ni test okvirja (import/syntax
        napaka), padec na `file:line` zadnjega okvira (namerno ostro)."""
        tb = reason or ""
        error_type = LoopXEngineBridge._classify_error(tb[:2000])
        tests = re.findall(r"\b(test_[A-Za-z0-9_]+)\b", tb)
        anchor = tests[-1] if tests else ""
        if not anchor:
            frames = re.findall(r'File "([^"]+\.py)", line (\d+)', tb)
            if frames:
                fname = frames[-1][0].split("/")[-1].split("\\")[-1]
                anchor = f"{fname}:{frames[-1][1]}"
        return f"{error_type}|{anchor}"

    # F1 — prepozna vrsto izdelka iz direktive: python | markdown | html
    @staticmethod
    def _detect_kind(directive: str) -> str:
        # P2 — [PLAN KONTEKST] prefiks ne sme spremeniti klasifikacije (npr.
        # beseda "poročilo" v stari lekciji bi modul razglasila za markdown).
        from core.plan_context import strip_plan_context
        d = strip_plan_context(directive or "").lower()

        # Celobesedno ujemanje (NE podniz): npr. "sporočilom" NE sme sprožiti
        # "poročilo", "spletna stran" ne "spletni", itd.
        def has_word(word: str) -> bool:
            return re.search(rf"\b{re.escape(word)}\b", d) is not None

        # HTML najprej — HTML je lahko tudi »dokument«, zato ga prepoznamo prej.
        if any(has_word(w) for w in ("html", "dashboard", "spletni", "spletna")) \
                or ".html" in d or "<html" in d or "spletna stran" in d:
            return "html"
        if any(has_word(w) for w in ("markdown", "predlog", "poročilo", "roadmap")) \
                or ".md" in d or "md datoteko" in d or "markdown dokument" in d:
            return "markdown"
        return "python"  # privzeto: python modul / kaj drugega

    def _docker_available(self) -> bool:
        """Tier 1 — ali sta Docker CLI IN daemon na voljo (jek. docker info).

        `docker --version` pokaže le klient; za `docker run` potrebujemo
        daemon. Zato preverimo `docker info` (rc=0 → daemon deluje)."""
        try:
            r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20)
            return r.returncode == 0
        except Exception:
            return False

    def _verify_python_sandbox(self, targeted: bool = False) -> Tuple[bool, str]:
        """Tier 1 — izvedba pytest v efemernem Docker peskovniku.

        `targeted` (SURGICAL FIX): požene le ciljni test (`pytest -k <test>`);
        če `-k` ne ujame nič (rc=5, zastarelo ime), pade nazaj na poln suite za
        ta check, da se verifikacija ne ustavi.

        Varnostna meja: kontejner vidi SAMO ./actions, ima --network none
        (brez omrežja → ne more namestiti zlonamernih paketov / klicati ven),
        --read-only koren (ne more pisati po OS) in se uniči po teku (--rm).
        Če Docker ni na voljo → PADE NA HOST z jasno oznako »NI IZOLIRANO«.
        """
        test = self._safe_target_test() if targeted else None

        # ---- HOST fallback (NI IZOLIRANO) —------------------------------ #
        if not self._docker_available():
            env = {"PYTHONPATH": "."}
            for try_test in (test, None):
                cmd = [sys.executable, "-m", "pytest", "-v", str(self.target_dir)]
                if try_test:
                    cmd += ["-k", try_test]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        env=dict(subprocess.os.environ, **env))
                if try_test and result.returncode == 5:
                    # `-k` ni ujel testa (rc=5) → ponovi s polnim suiteom za ta check.
                    print(f"[LOOPX] -k {try_test} ni ujel testa (rc=5) → poln suite.",
                          flush=True)
                    continue
                raw = (result.stderr or "") + "\n" + (result.stdout or "")
                if result.returncode == 0:
                    return True, "[NI IZOLIRANO — host] pytest zelen"
                detail = self._extract_pytest_failure(raw, result.returncode) or "pytest ni zelen"
                return False, f"[NI IZOLIRANO — host] {detail}"
            return False, "[NI IZOLIRANO — host] pytest ni zelen (rc=5)"

        # ---- Sandbox ----------------------------------------------------- #
        # Slika 'rob-sandbox' zgrajena prek Dockerfile.sandbox (python:3.11-slim
        # + pytest). Runtime: brez omrežja, read-only, samo ./actions. Mount
        # ./actions → /work/actions (NE /work), da `from actions.<mod> import X`
        # deluje tudi znotraj sandboxa. `sh -c "cd /work && pytest ..."` (ne -w
        # /work — v Git Bash/MSYS pretvori /work v Windows path).
        cwd = Path.cwd()
        actions_abs = (cwd / "actions").resolve()
        target_name = self.target_dir.name  # e.g. 'sbtest' (zadnji segment)
        vol = f"{actions_abs}:/work/actions"
        for try_test in (test, None):
            shell_cmd = f"cd /work && python -m pytest -v /work/actions/{target_name}"
            if try_test:
                shell_cmd += f" -k {try_test}"
            cmd = [
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--security-opt", "no-new-privileges",
                "--memory", "512m",
                "--memory-swap", "512m",          # brez swap -> cgroups v RAM
                "--cpus", "1",
                "--ulimit", "nofile=256:256",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "-v", vol,
                "rob-sandbox:latest",
                "sh", "-c", shell_cmd,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except Exception as e:
                return False, f"[Docker sandbox napaka] {e}"
            if try_test and result.returncode == 5:
                print(f"[LOOPX] -k {try_test} ni ujel testa (rc=5) → poln suite.",
                      flush=True)
                continue
            raw = (result.stderr or "") + "\n" + (result.stdout or "")
            if result.returncode == 0:
                return True, "[sandbox] pytest zelen"
            detail = self._extract_pytest_failure(raw, result.returncode) or "pytest ni zelen"
            return False, f"[sandbox] {detail}"
        return False, "[sandbox] pytest ni zelen (rc=5)"

    # ------------------------------------------------------------------ #
    #  P3 — Ruff v verigo (F821 pre-gate pred pytest).
    # ------------------------------------------------------------------ #
    def _verify_ruff(self) -> Tuple[bool, str]:
        """P3 — Ruff pre-gate za F821 (undefined name → NameError).

        Požene se PRED pytest om, da ulovi kategorične pyflakes napake
        (npr. neobstoječ uvoz → ``Name ... is not defined``) ceneje in hitreje,
        brez ogrevanja Docker sandboxa. Omejeno na F821 (ne stilski E/W), zato
        ni preagresivno do LLM-generirane kode.

        VARNO NADOMESTILO: če Ruff ni na PATH, vrne ``(True, "")`` — t.j.
        veriga se NADALJUJE (pytest odloči), ne blokira. To je ključno, da P3
        nikoli ne zruši zelenega build-a samo zato, ker Ruff manjka.
        """
        ruff = shutil.which("ruff")
        if ruff is None:
            # Ne install-iraj zahtev — preskoči pre-gate; pytest je glavni ščit.
            return True, ""
        try:
            result = subprocess.run(
                [ruff, "check", str(self.target_dir), "--select", "F821", "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
        except Exception as e:
            # Če Ruff odpove tehnično, ne blokiraj — prevzame pytest.
            return True, f"[ruff] pre-gate opozorilo: {e}"
        if result.returncode == 0:
            return True, ""
        msg = (result.stdout or result.stderr or "F821 offline").strip()
        return False, f"[ruff:F821] nedefiniran(i) symbol(i) pred pytest: {msg[:1500]}"

    # F1 — verifikacija glede na vrsto izdelka. Vrne (pass, napis).
    # `targeted` (SURGICAL FIX): python → pytest -k <target_test> (samo padel test).
    def _verify(self, kind: str, targeted: bool = False) -> Tuple[bool, str]:
        if kind == "python":
            # P3 — Ruff pre-gate (F821) najprej; če pade, LLM dobi razlog brez
            # da bi se kuril Docker. Sicer gremo na pytest sandbox.
            ok, ruff_msg = self._verify_ruff()
            if not ok:
                return False, ruff_msg
            ok, msg = self._verify_python_sandbox(targeted=targeted)
            # MODIFY — zahtevan test file iz direktive mora obstajati; sicer je
            # "zelen" le potrditev obstoječih testov → rdeč, da heal ustvari test
            # + implementira zahtevano spremembo.
            if ok:
                missing = self._missing_required_files()
                if missing:
                    return False, (f"manjka zahtevan test file: {', '.join(missing)} "
                                   "(direktiva MODIFY zahteva, da ga ustvariš)")
            return ok, msg
        if kind == "markdown":
            # Zelen = obstaja vsaj ena .md datoteka z naslovom (ni prazen stub).
            mds = list(self.target_dir.glob("*.md"))
            if not mds:
                return False, "Ni Markdown datoteke v cilju."
            ok = any(len(p.read_text(encoding="utf-8").strip()) > 20 for p in mds)
            return ok, "MD datoteka je prazna/stb (manj kot 20 znakov)" if not ok else ""
        if kind == "html":
            htmls = list(self.target_dir.glob("*.html"))
            if not htmls:
                return False, "Ni HTML datoteke v cilju."
            ok = any("</html" in p.read_text(encoding="utf-8", errors="ignore") for p in htmls)
            return ok, "HTML datoteka ni veljavna (manjka </html>)" if not ok else ""
        return False, "Neznana vrsta izdelka."

    # ------------------------------------------------------------------ #
    #  Glavna zanka
    # ------------------------------------------------------------------ #

    # P2 — sočasnost: atomic file-lock na ciljni modul. Prepreči, da dva build-a
    # istega `actions/<target>/` pisanja in pytest-a v istem dir hkrati (race).
    # Uporabljen `os.open(... O_EXCL)` — atomic na filesystem; lock živi v
    # `.loopx/<target>.lock`.
    def _lock_path(self) -> Path:
        return Path(".loopx") / f"{self.project}.lock"

    def _acquire_target_lock(self, timeout: float = 2.0) -> bool:
        import os, time as _t
        p = self._lock_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        deadline = _t.monotonic() + timeout
        while True:
            try:
                fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                # P1/C2 — stale lock (lastnik mrtev, npr. daemon timeout kill):
                # zbriši in poskusi znova takoj, da fix naloga lahko znova požene target.
                if self._lock_is_stale(p):
                    try:
                        p.unlink()
                    except OSError:
                        pass
                    continue
                if _t.monotonic() >= deadline:
                    return False
                _t.sleep(0.15)

    def _lock_is_stale(self, p: Path) -> bool:
        """True, če lock datoteka vsebuje PID, ki ne obstaja več (ali je prazna)."""
        try:
            txt = p.read_text(encoding="utf-8").strip()
            if not txt:
                return True  # prazen/pokvarjen lock → stale
            return not _pid_alive(int(txt))
        except Exception:
            return False  # ne moremo prebrati → ne briši (varno)

    def _release_target_lock(self) -> None:
        import os
        p = self._lock_path()
        try:
            p.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    #  Korak 10 — avto-rollback ob neuspelem buildu
    # ------------------------------------------------------------------ #
    def _backup_dir(self) -> Path:
        """Rollback snapshot: .loopx/rollback/<project>/ (gitignoran, per-modul izoliran)."""
        return Path(".loopx") / "rollback" / self.project

    def _snapshot_project(self) -> None:
        """Pred-build kopija actions/<project>/ v .loopx/rollback/<project>/.

        Stale snapshot se pred kopijo počisti (samozdravljenje po krachu).
        `_rollback_had_target` loči »modul ni obstajal« od »modul je obstajal
        kot prazen/eksisten dir«.
        """
        backup = self._backup_dir()
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        backup.parent.mkdir(parents=True, exist_ok=True)
        self._rollback_had_target = self.target_dir.exists()
        if self._rollback_had_target:
            shutil.copytree(self.target_dir, backup, dirs_exist_ok=True)
        else:
            backup.mkdir(parents=True, exist_ok=True)   # marker: modul ni obstajal

    def _restore_project(self) -> None:
        """Povrne actions/<project>/ na pred-build stanje iz snapshota.

        Nov modul (ni obstajal) → v celoti odstranjen. Obstoječ modul → rmtree +
        kopija snapshota nazaj. Manjkajoč snapshot → no-op (defenzivno).
        """
        backup = self._backup_dir()
        if not backup.exists():
            print(f"[LOOPX] ROLLBACK: ni snapshota za '{self.project}' — preskočen.", flush=True)
            return
        if self.target_dir.exists():
            shutil.rmtree(self.target_dir)
        if self._rollback_had_target:
            shutil.copytree(backup, self.target_dir)
        print(f"[LOOPX] ROLLBACK: '{self.project}' povrnjen na pred-build stanje.", flush=True)

    def _cleanup_snapshot(self) -> None:
        """Po zelenem buildu ali po uspelem rollbacku počisti snapshot dir."""
        backup = self._backup_dir()
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    def execute_and_heal(self, directive: str, spec_hint: str = "") -> bool:
        """RSI zanka. `spec_hint` = arhitekturna usmeritev (P0) iz GStack manifesta,
        ki jo _heal_once vstavi v LLM prompt (če ni prazna).

        P2 — sočasnost: pred zanko vzame atomic target-lock; drugi build istega
        modula čaka kratek čas in ob časovni izteku vrne False (ne tekmuje).
        Lock se sprosti v `finally` ne glede na izid.

        Korak 10 — avto-rollback: pred zanko se snapshotira actions/<proj>/
        (.loopx/rollback/<proj>/); ob neuspelem buildu (ok=False, vklj. izjemo)
        se modul povrne na pred-build stanje; ob zelenem se snapshot počisti.
        """
        self.spec_hint = spec_hint  # P0 — usmeritev za _heal_once
        if not self._acquire_target_lock():
            print(f"[LOOPX] TARGET ZAKLENJEN: '{self.project}' — drug build že poteka. Preskočen.",
                  flush=True)
            return False
        ok = False
        try:
            try:
                self._snapshot_project()
            except Exception as e:
                # Snapshot ni kritičen za build: ob napaki gradnja teče naprej,
                # rollback je za ta tek le onemogočen.
                print(f"[LOOPX] snapshot preskočen ({e}) — rollback onemogočen za ta tek.", flush=True)
                self._rollback_had_target = False
            ok = self._heal_loop(directive)
            return ok
        finally:
            try:
                if not ok and settings.loopx_rollback_on_fail:
                    self._restore_project()
                self._cleanup_snapshot()
            except Exception as e:
                print(f"[LOOPX] rollback/cleanup opozorilo: {e}", flush=True)
            finally:
                self._release_target_lock()

    def _heal_loop(self, directive: str) -> bool:
        """Jedro RSI zanke (pod target-lockom). Vrača True ob zelenem, sicer False."""
        kind = self._detect_kind(directive)
        print(f"[LOOPX] vrsta izdelka: {kind}", flush=True)
        self._heal_fail_count = {}  # reset števca ponavljajočih napak za ta tek
        self.last_reason = ""       # Zanka 2: zadnji razlog (za post-run review)
        self.last_traceback = ""    # C2: zadnji REALEN traceback (za fix nalogo)
        self._baseline_fingerprint = self._module_fingerprint()  # MODIFY: false-green guard
        self._load_tuning()         # Zanka 3: samorazvojni parametri (max_attempts, prag)
        for attempt in range(1, self.max_attempts + 1):
            self.update_loopx_state("RUNNING", attempt)

            # F1: verifikacija glede na vrsto izdelka (python→pytest, md/html→struktura).
            # SURGICAL FIX: najprej TARGETED (samo padel test — hitro), nato poln
            # no-regression gate. Heal gre proti razlogu, ki je dejanski heal-target
            # (targeted failure ALI poln failure, če je targeted šel skozi).
            ok, reason = (self._verify(kind, targeted=True) if self.target_test
                          else self._verify(kind))
            if ok and self.target_test:
                full_ok, full_reason = self._verify(kind, targeted=False)
                if not full_ok:
                    ok = False
                    reason = full_reason
            if not ok:
                self.last_traceback = reason   # C2: zadnji realen traceback, vedno svež
            if ok:
                # 3.5 — zelen cikel + zabeležen rekord = resnično shipped
                self.update_loopx_state("VERIFIED_GREEN", attempt)
                self.gbrain.record_task(
                    self.project, directive, "VERIFIED GREEN", verified_code="Pass"
                )
                self.graphify.build_code_graph()
                # NEOBVEZEN vizualni QA (HTML artefakti): Gemma 4 pogleda UI in
                # zapiše kakovostno poročilo v GBRAIN. Nikoli ne blokira builda —
                # napaka QA je zgolj opozorilo.
                if kind == "html":
                    self._run_optional_visual_qa()
                self._audit("ok")
                return True

            # Rdeč → učenje iz ponavljajočih se napak: če se ista NAPAKA (ostri
            # podpis: tip + padel test) ponovi ≥ REPEAT_ABORT_AFTER-krat, zgodaj
            # prekini (ne kuri LLM naprej). Dve različni napaki istega tipa se
            # ne seštejeta → napredek se ne prekine.
            error_type = self._classify_error(reason[:2000])
            sig = self._error_signature(reason[:2000])
            self._heal_fail_count[sig] = self._heal_fail_count.get(sig, 0) + 1
            if self._heal_fail_count[sig] >= self.repeat_abort_after:
                print(f"[LOOPX] ista napaka {sig} po "
                      f"{self._heal_fail_count[sig]} poskusih — zgodnje prekinjeno.",
                      flush=True)
                self.update_loopx_state("FAILED", attempt)
                self.gbrain.record_task(
                    self.project, directive, "FAILED",
                    traceback=reason,  # C2: REALEN traceback v arhiv (ne povzetek)
                )
                self.last_reason = f"ista napaka {sig} po {self._heal_fail_count[sig]} poskusih"
                self._audit("failed")
                return False

            # RSI healing (3.1–3.3). `reason` je traceback oz. sporočilo.
            healed, report = self._heal_once(reason, directive, kind)

            # 3.3 — zapis učnih vzorcev v GBRAIN (mednáložni spomin)
            self.gbrain.add_blacklist_pattern(
                self.project,
                error_pattern=f"{self.project}.{error_type}",
                mitigation=f"RSI poskus {attempt}: {report}",
            )
            # Zanka 1 — refleksija: takoj strdi strukturirano lekcijo (ne čaka konsolidacije).
            self._reflect_and_store(error_type, report)

            if healed:
                self.update_loopx_state("HEALED_AFTER_ATTEMPT", attempt)
                # Po uspešnem popravku naslednji cikel znova požene pytest.
                continue

            if attempt == self.max_attempts:
                self.update_loopx_state("FAILED", attempt)
                self.gbrain.record_task(self.project, directive, "FAILED", traceback=reason)
                self.last_reason = reason
                self._audit("failed")
                return False

        self.last_reason = reason
        self._audit("failed")
        return False

    def _run_optional_visual_qa(self) -> None:
        """NEOBVEZEN vizualni QA za HTML artefakte (Gemma 4 + Playwright).

        Zajeme prvi .html v target_dir, Gemma pogleda UI, poročilo se zapiše v
        GBRAIN memory (key visual_qa/<target>). Nikoli ne blokira builda: vse
        napake se požrejo (opozorilo), build ostane zelen.
        """
        try:
            from core.visual_qa import review as visual_review
            htmls = sorted(self.target_dir.glob("*.html"))
            if not htmls:
                return
            report = visual_review(str(htmls[0]))
            self.gbrain.store_memory_node(
                key=f"visual_qa/{self.project}",
                data={"source": str(htmls[0]),
                      "verdict": report.get("ok"),
                      "summary": report.get("summary", ""),
                      "issues": report.get("issues", []),
                      "error": report.get("error", "")},
                tags=["visual_qa", "html", self.project],
            )
            print(f"[LOOPX] vizualni QA ob: {report.get('summary', '?')[:80]}", flush=True)
        except Exception as e:
            print(f"[WARN] vizualni QA preskočen (ni blokirno): {e}", flush=True)

    def _audit(self, status: str) -> None:
        """F5 — revizijski vnos ob koncu RSI teka (z LLM-klic števcem)."""
        try:
            from core.audit import record
            record(
                event="rsi-run", project=self.project, status=status,
                llm_calls=self.llm_calls, detail=f"max_attempts={self.max_attempts}",
            )
        except Exception:
            pass

    def _reflect_and_store(self, error_type: str, report: str) -> None:
        """Refleksija (Zanka 1): po neuspelem heal poskusu TAKOJ strdi
        strukturirano lekcijo (root cause + poskus) v semantic_memories —
        ne čaka periodične konsolidacije. Naslednji heal jo dobi prek recall().
        Nikoli ne blokira healinga (vse napake požre).
        """
        try:
            from core.memory_consolidation import MemoryConsolidator
            cons = MemoryConsolidator(self.gbrain.db_path)
            cons.store(
                theme=f"{self.project}: {error_type}",
                content=f"{error_type} v projektu '{self.project}' — poskus popravka: {report}",
                project=self.project,
                kind="pitfall",
                confidence=0.5,
            )
        except Exception as e:
            print(f"[LOOPX] refleksija preskočena (ni blokirno): {e}", flush=True)
