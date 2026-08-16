import subprocess
import sys
import json
import re
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Tuple

from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.llm_client import DeepSeekLLMClient


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


class LoopXEngineBridge:
    """Avtonomna verifikacijska zanka z RSI (self-healing + mednáložni spomin).

    Načrt 3.1–3.5:
    3.1  LLM je povezan v zanko in popravlja kodo ob rdečem testu.
    3.2  RSI prompt (zgornja predloga) usmerja LLM k koherentnim, polnim datotekam.
    3.3  Naučeno se zapisuje v GBRAIN blacklist (mednáložni spomin).
    3.4  Popravki so omejeni na actions/{project}/ (varnostna meja).
    3.5  Zelen cikel je dokončan šele, ko record_task vpiše rekord (ne 0).
    """

    def __init__(self, project: str):
        self.project = project
        self.target_dir = Path(f"actions/{project}")
        self.registry_file = Path(".loopx/registry.json")
        self.gbrain = GBrainBridge()
        self.graphify = GraphifyBridge()
        self.llm = DeepSeekLLMClient()
        self.max_attempts = 5
        self.llm_calls = 0   # F5: števec LLM klicev za revizijo in cost-zavarovanje

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
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    # ------------------------------------------------------------------ #
    #  Pomožne funkcije
    # ------------------------------------------------------------------ #

    def _read_module_sources(self) -> Dict[str, str]:
        """Prebere vse .py datoteke modula za posredovanje LLM-ju."""
        sources = {}
        target = Path(f"actions/{self.project}")
        if target.exists():
            for p in target.glob("*.py"):
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
        TEST_PREFIXES = ("test_", "tests_")
        TEST_SUFFIX_E = ("_test",)   # za basenames (po odstranitvi .py)
        TEST_HARDNAME = {"conftest.py"}
        def _is_test_file(name: str) -> bool:
            if name.endswith(".py"):
                base = name[:-3]  # odstrani končnico .py
                if base.startswith(TEST_PREFIXES) or base.endswith(TEST_SUFFIX_E):
                    return True
                if name in TEST_HARDNAME:
                    return True
            return False
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
            if _is_test_file(rel) and cand.exists():
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

        Vrni (uspeh, poročilo).
        """
        sources = self._read_module_sources()
        # Navodilo za izhod glede na vrsto izdelka (F1).
        if kind == "markdown":
            out_note = "Vrni POPOLN Markdown dokument v formatu ### FILE: ime.md\\n```markdown\\n<vsebina>\\n``` (z naslovom #, brez placeholdoj)."
        elif kind == "html":
            out_note = "Vrni POPOLNO HTML stran v formatu ### FILE: ime.html\\n```html\\n<vsebina z </html>>\\n``` (veljavna, brez placeholdoj)."
        else:
            out_note = "Vrni POPOLNE, delujoča Python datoteko v formatu ### FILE: ime.py\\n```python\\n<koda>\\n``` (vse datoteke popolne, brez placeholdoj, dejanska implementacija)."
        # F4 — trajni RSI spomin: naučene napake (blacklists) iz preteklih tekov.
        try:
            learned = self.gbrain.get_blacklists(self.project)
        except Exception:
            learned = []
        learned_note = ""
        if learned:
            pats = "; ".join(
                f"{b.get('error_pattern','?')} → {b.get('mitigation','')[:60]}" for b in learned[:10]
            )
            learned_note = (
                "Naučeno iz prejšnjih poskusov (izogni se tem napakam):\n"
                f"{pats}\n\n"
            )
        prompt = (
            f"Izvirna vsebina modula `{self.project}` (trenutno ogrodje/stubs):\n"
            f"{json.dumps(sources, ensure_ascii=False, indent=2)}\n\n"
            "DIREKTIVA (kaj naj izdelek dejansko vsebuje):\n"
            f"{directive[:3000]}\n\n"
            f"{learned_note}"
            "Razlog verifikacije (doseči je treba zelen):\n"
            f"{traceback[:8000]}\n\n"
            f"{out_note}"
        )
        try:
            self.llm_calls += 1   # F5: revizijski števec LLM klicev
            # generate_completion je async korutina; zanko držimo sync,
            # zato LLM klic v tem kontekstu zaženemo prek asyncio.
            response = asyncio.run(
                self.llm.generate_completion(
                    prompt=prompt,
                    system_prompt=RSI_PROMPT_SYSTEM,
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

    @staticmethod
    def _classify_error(traceback: str) -> str:
        """Povzame tip napake (ExceptionName) iz tracebacka, sicer 'UNKNOWN'."""
        m = re.search(r"\n(\w+Error|\w+Exception):", traceback)
        if m:
            return m.group(1)
        return "UNKNOWN"

    # F1 — prepozna vrsto izdelka iz direktive: python | markdown | html
    @staticmethod
    def _detect_kind(directive: str) -> str:
        d = directive.lower()
        # HTML najprej — HTML je lahko tudi »dokument«, zato ga prepoznamo prej.
        if any(w in d for w in ("html", ".html", "spletna stran", "dashboard", "<html", "spletni")):
            return "html"
        if any(w in d for w in ("markdown", ".md", "predlog", "poročilo", "roadmap", "md datoteko", "markdown dokument")):
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

    def _verify_python_sandbox(self) -> Tuple[bool, str]:
        """Tier 1 — izvedba pytest v efemernem Docker peskovniku.

        Varnostna meja: kontejner vidi SAMO ./actions, ima --network none
        (brez omrežja → ne more namestiti zlonamernih paketov / klicati ven),
        --read-only koren (ne more pisati po OS) in se uniči po teku (--rm).
        Če Docker ni na voljo → PADE NA HOST z jasno oznako »NI IZOLIRANO«.
        """
        if not self._docker_available():
            env = {"PYTHONPATH": "."}
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", str(self.target_dir)],
                capture_output=True, text=True,
                env=dict(subprocess.os.environ, **env),
            )
            msg = result.stderr or result.stdout or "pytest ni zelen"
            return result.returncode == 0, f"[NI IZOLIRANO — host] {msg[:400]}"

        # Sandbox: slika 'rob-sandbox' naj bo zgrajena prek Dockerfile.sandbox
        # (python:3.11-slim + pytest). Runtime: brez omrežja, read-only, samo ./actions.
        # mount ./actions → /work (V work JE actions koren, ne celoten projekt).
        # Uporabi `sh -c "cd /work && pytest ..."` namesto `-w /work`, ker -w /work
        # v nekaterih okoljih (Git Bash / MSYS) pretvori /work v Windows path.
        cwd = Path.cwd()
        actions_abs = (cwd / "actions").resolve()
        target_name = self.target_dir.name  # e.g. 'sbtest' (zadnji segment)
        vol = f"{actions_abs}:/work"
        shell_cmd = f"cd /work && python -m pytest -v /work/{target_name}"
        # --tmpfs /tmp:noexec,nosuid,size=64m → pytest lahko piše temp v RAM,
        # ampak tam ne izvaja kode (noexec) in ni persistent (tmpfs). Koren OS
        # ostane --read-only. (name izpustimo --user, ker na Windows-host volume
        # uid 1000 ne bi prebral datotek → 'collected 0 items'.)
        # P2 — Sandbox hardening: omeji porabo vira, da LLM-generirana koda ne
        # more povzročiti resource-exhaustion. 512 MB RAM, 1 CPU, nofile=256
        # (omejitev odprtih datotek), /tmp tmpfs še vedno noexec (nobene kode
        # iz RAM). GNU timeout podvojimo na 180 s za večje testne module, ampak
        # cgroups (--memory/--cpus) so glavni ščit pred divjo porabo.
        cmd = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--security-opt", "no-new-privileges",
            "--memory", "512m",
            "--memory-swap", "512m",          # brez swap -> cgroups mora delovati v RAM
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
        msg = result.stderr or result.stdout or "pytest ni zelen"
        return result.returncode == 0, f"[sandbox] {msg[:400]}"

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
        return False, f"[ruff:F821] nedefiniran(i) symbol(i) pred pytest: {msg[:500]}"

    # F1 — verifikacija glede na vrsto izdelka. Vrne (pass, napis).
    def _verify(self, kind: str) -> Tuple[bool, str]:
        if kind == "python":
            # P3 — Ruff pre-gate (F821) najprej; če pade, LLM dobi razlog brez
            # da bi se kuril Docker. Sicer gremo na pytest sandbox.
            ok, ruff_msg = self._verify_ruff()
            if not ok:
                return False, ruff_msg
            return self._verify_python_sandbox()
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

    def execute_and_heal(self, directive: str) -> bool:
        kind = self._detect_kind(directive)
        print(f"[LOOPX] vrsta izdelka: {kind}", flush=True)
        for attempt in range(1, self.max_attempts + 1):
            self.update_loopx_state("RUNNING", attempt)

            # F1: verifikacija glede na vrsto izdelka (python→pytest, md/html→struktura).
            ok, reason = self._verify(kind)
            if ok:
                # 3.5 — zelen cikel + zabeležen rekord = resnično shipped
                self.update_loopx_state("VERIFIED_GREEN", attempt)
                self.gbrain.record_task(
                    self.project, directive, "VERIFIED GREEN", verified_code="Pass"
                )
                self.graphify.build_code_graph()
                self._audit("ok")
                return True

            # Rdeč/celokupni fail → RSI healing (3.1–3.3). Direktiva in vrsta se preneseta
            # LLM-ju, da ve, kaj zdomiti. `reason` je traceback oz. sporočilo.
            healed, report = self._heal_once(reason, directive, kind)

            # 3.3 — zapis učnih vzorcev v GBRAIN (mednáložni spomin)
            error_type = self._classify_error(reason[:2000])
            self.gbrain.add_blacklist_pattern(
                self.project,
                error_pattern=f"{self.project}.{error_type}",
                mitigation=f"RSI poskus {attempt}: {report}",
            )

            if healed:
                self.update_loopx_state("HEALED_AFTER_ATTEMPT", attempt)
                # Po uspešnem popravku naslednji cikel znova požene pytest.
                continue

            if attempt == self.max_attempts:
                self.update_loopx_state("FAILED", attempt)
                self.gbrain.record_task(self.project, directive, "FAILED", traceback=reason)
                self._audit("failed")
                return False

        self._audit("failed")
        return False

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
