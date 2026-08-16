import subprocess
import sys
import json
import re
import asyncio
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
        pattern = re.compile(
            r"### FILE:\s*([^\n]+)\n```(?:python)?\n(.*?)```",
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            files[m.group(1).strip()] = m.group(2).strip()
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
        for rel, content in files.items():
            # Edini veljavni ključi so goli basename (.py v ploskvi modula).
            # Vsak separator ali traversal ('.', '..', '/', '\') -> zavrni,
            # da nikoli ne pišemo izven target_dir (3.4).
            if "/" in rel or "\\" in rel or rel in (".", "..", "") or not rel.endswith(".py"):
                continue
            cand = (allowed / rel).resolve()
            if cand.parent != allowed:
                continue
            cand.write_text(content, encoding="utf-8")
            written += 1
        return written

    # ------------------------------------------------------------------ #
    #  3.1–3.3  LLM popravek + RSI zanka + zapis v GBRAIN
    # ------------------------------------------------------------------ #

    def _heal_once(self, traceback: str) -> Tuple[bool, str]:
        """Poskuša popraviti kodo z LLM-jem (3.1, 3.2).

        Vrni (uspeh, poročilo).
        """
        sources = self._read_module_sources()
        prompt = (
            f"Izvirna koda modula `{self.project}`:\n"
            f"{json.dumps(sources, ensure_ascii=False, indent=2)}\n\n"
            "Traceback neuspelega testa:\n"
            f"{traceback[:8000]}\n\n"
            "Vrni popravljene datoteke v formatu ### FILE: ...:"
        )
        try:
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
            return False, f"LLM napaka pri healingu: {e}"

        files = self._parse_patched_files(response)
        if not files:
            return False, "LLM ni vrnil datotek v formatu ### FILE: ..."

        written = self._apply_patch(files)
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

    # ------------------------------------------------------------------ #
    #  Glavna zanka
    # ------------------------------------------------------------------ #

    def execute_and_heal(self, directive: str) -> bool:
        for attempt in range(1, self.max_attempts + 1):
            self.update_loopx_state("RUNNING", attempt)

            env = {"PYTHONPATH": "."}
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", str(self.target_dir)],
                capture_output=True,
                text=True,
                env=dict(subprocess.os.environ, **env),
            )

            if result.returncode == 0:
                # 3.5 — zelen cikel + zabeležen rekord = resnično shipped
                self.update_loopx_state("VERIFIED_GREEN", attempt)
                self.gbrain.record_task(
                    self.project, directive, "VERIFIED GREEN", verified_code="Pass"
                )
                self.graphify.build_code_graph()
                return True

            # Rdeč test → RSI healing (3.1–3.3)
            stderr = result.stderr or result.stdout
            healed, report = self._heal_once(stderr)

            # 3.3 — zapis učnih vzorcev v GBRAIN (mednáložni spomin)
            error_type = self._classify_error(stderr[:2000])
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
                self.gbrain.record_task(self.project, directive, "FAILED", traceback=stderr)
                return False

        return False
