"""core/skill_bridge.py — GStack skilli kot kontekstno orodje za LLM (korak 6).

Skilli so ogromni procesni workflow-i za Claude Code (povprečno ~57 KB), ne
"orodja s parametri". Ta modul NE izvaja skillov (DeepSeek nima Claude/Bash
orodij) — vrne strnjen procesni vodič: frontmatter + skill-specifični del,
brez ponavljajočega boilerplate-a (Preamble bash blok, AskUserQuestion format,
telemetrija ...).

Robustno: NIKOLI ne dvigne izjeme. Missing dir / napaka → [] ali None.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # lazy-import opcijsko (v requirements-dev); ob napaki regex fallback
except ImportError:
    yaml = None

SKILL_CONTENT_CAP = 6000            # vzorec: read_file cap 20k iz loopx_bridge
ROUTER_SKILLS = {"gstack", "_gstack-command"}   # near-duplikata, 0 H1, samo routing

# Univerzalni scaffolding, ki ga DeepSeek ne more izvajati (bash/AskUserQuestion/
# harness/telemetry/Claude-voice). Ujemanje je na normaliziranem headerju.
DROP_SECTION_KEYS = {
    "preamble",
    "plan mode safe operations",
    "skill invocation during plan mode",
    "askuserquestion format",
    "artifacts sync",
    "model-specific behavioral patch",
    "voice",
    "context recovery",
    "telemetry",
    "first-run guidance",
    "plan status footer",
    "operational self-improvement",
    "writing style",
}
# Transverzalna pravila (Completeness Principle / Confusion Protocol / Search
# Before Building / Completion Status Protocol) NISO v DROP — ostanejo.


def _normalize_section(header: str) -> str:
    """Normalizira header za ujemanje: mala črka, brez oklepajnega sufiksa."""
    return re.sub(r"\s*\(.*?\)\s*$", "", header).strip().lower()


def _cap(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    marker = f"\n...[izrezano: {len(text)} znakov / prikazanih {cap}]"
    return text[:max(0, cap - len(marker))].rstrip() + marker


def _scan_sections(body: str) -> List[Tuple[int, str, int, int]]:
    """Vrne [(level, header, start_idx, end_idx)] za H1/H2, IZVEN code fence.

    Bash komentarji `# /sync-gbrain ...` znotraj ```bash blokov se NE štejejo
    (brez fence-aware parsanja bi H1 detekcija ujela napačen naslov).
    """
    out: List[Tuple[int, str, int, int]] = []
    lines = body.splitlines(keepends=True)
    in_fence = False
    fence = None
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln))
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*(```+|~~~+)", ln)
        if m:
            fm = m.group(1)[0] * 3
            if not in_fence:
                in_fence, fence = True, fm
            elif ln.strip().startswith(fence):
                in_fence, fence = False, None
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,2})\s+(.+?)\s*$", ln)
        if m:
            lvl = len(m.group(1))
            out.append((lvl, m.group(2), offsets[i], offsets[i + 1]))
    # end_idx vsakega = start naslednjega istega ali višjega nivoja.
    for j, (lvl, hdr, s, _e) in enumerate(out):
        end = len(body)
        for k in range(j + 1, len(out)):
            if out[k][0] <= lvl:
                end = out[k][2]
                break
        out[j] = (lvl, hdr, s, end)
    return out


def _remove_drop_sections(text: str) -> str:
    """Odstrani H2 sekcije, katerih normalize key je v DROP_SECTION_KEYS."""
    sections = _scan_sections(text)
    keep = [text[s:e] for (lvl, hdr, s, e) in sections
            if not (lvl == 2 and _normalize_section(hdr) in DROP_SECTION_KEYS)]
    return "\n\n".join(keep) if keep else text


class SkillBridge:
    """Bralec GStack skillov: list_skills() + get_skill() (distilled, capped)."""

    def __init__(self, skills_dir: Optional[Path] = None):
        self._skills_dir = self._resolve_dir(skills_dir)
        self._cache: Dict[Tuple[str, Optional[str]], Optional[dict]] = {}

    # ------------------------------------------------------------------ #
    #  Pot + robustnost
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_dir(skills_dir: Optional[Path]) -> Optional[Path]:
        raw = skills_dir
        if raw is None:
            from core.config import settings
            cfg = (getattr(settings, "gstack_skills_dir", "") or "")
            raw = Path(cfg) if cfg else Path.home() / ".claude" / "skills"
        p = Path(raw).expanduser()
        return p if p.is_dir() else None                # missing dir -> None (CI-safe)

    def _candidates(self) -> List[Path]:
        if self._skills_dir is None:
            return []
        return sorted(d for d in self._skills_dir.iterdir()
                      if d.is_dir() and (d / "SKILL.md").is_file())

    @staticmethod
    def _normalize_slug(slug: str) -> Optional[str]:
        """Sanitizacija slug-a: zavrne traversal/pot, vrne goli basename."""
        s = str(slug).strip().strip("/")
        if s.lower().endswith(".md"):
            s = s[:-3].strip("/")
        if not s or s in (".", "..") or "/" in s or "\\" in s:
            return None
        return s

    def _skill_path(self, name: str) -> Optional[Path]:
        if self._skills_dir is None:
            return None
        base = self._skills_dir.resolve()
        cand = (base / name / "SKILL.md").resolve()
        try:
            cand.relative_to(base)          # pot MORA ostati znotraj skills korena
        except ValueError:
            return None
        return cand if cand.is_file() else None

    @staticmethod
    def _safe_read(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    # ------------------------------------------------------------------ #
    #  Frontmatter
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_frontmatter(path: Path) -> Optional[dict]:
        text = SkillBridge._safe_read(path)
        if text is None:
            return None
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not m:
            return None
        block = m.group(1)
        if yaml is not None:
            try:
                data = yaml.safe_load(block)
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return SkillBridge._minimal_frontmatter(block)

    @staticmethod
    def _minimal_frontmatter(block: str) -> dict:
        fm: dict = {}
        for key in ("name", "description", "interactive"):
            m = re.search(rf"^{key}:\s*(.+)$", block, re.M)
            if m:
                fm[key] = m.group(1).strip().strip("\"'")
        return fm

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
        return text[m.end():] if m else text

    # ------------------------------------------------------------------ #
    #  Javni vmesnik
    # ------------------------------------------------------------------ #
    def list_skills(self) -> List[dict]:
        """Seznam {name, description, interactive}; izključi routerja. Sortirano."""
        out: List[dict] = []
        for d in self._candidates():
            slug = d.name
            if slug in ROUTER_SKILLS:
                continue
            fm = self._read_frontmatter(d / "SKILL.md")
            if fm is None:
                continue
            out.append({
                "name": slug,
                "description": str(fm.get("description", "")),
                "interactive": bool(fm.get("interactive", False)),
            })
        return out

    def get_skill(self, slug: str, section: Optional[str] = None,
                  cap: int = SKILL_CONTENT_CAP) -> Optional[dict]:
        """Prebere SKILL.md, vrne strnjen procesni vodič ali None."""
        if not isinstance(slug, str):
            return None
        name = self._normalize_slug(slug)
        if name is None or name in ROUTER_SKILLS:      # router nima procesnega znanja
            return None
        key = (name, section)
        if key in self._cache:
            return self._cache[key]
        path = self._skill_path(name)
        if path is None:
            return None
        text = self._safe_read(path)
        if text is None:
            return None
        fm = self._read_frontmatter(path) or {}
        body = self._strip_frontmatter(text)
        content = (self._extract_section(body, section, cap) if section
                   else self._distill(fm, body, cap))
        if content is None:
            return None
        result = {
            "name": str(fm.get("name", name)),
            "description": str(fm.get("description", "")),
            "triggers": fm.get("triggers", []) if isinstance(fm.get("triggers", []), list)
                        else [str(fm.get("triggers"))],
            "interactive": bool(fm.get("interactive", False)),
            "content": content,
        }
        self._cache[key] = result
        return result

    # ------------------------------------------------------------------ #
    #  Distilacija
    # ------------------------------------------------------------------ #
    def _distill(self, fm: dict, body: str, cap: int) -> str:
        sections = _scan_sections(body)
        if not sections:
            return _cap(body, cap)
        first_h1 = next((i for i, s in enumerate(sections) if s[0] == 1), None)

        parts: List[str] = []
        # 1. Frontmatter povzetek (kratek).
        head = f"# {fm.get('name', '?')}"
        if fm.get("description"):
            head += f"\n{fm['description']}"
        trg = fm.get("triggers")
        if trg:
            trg_list = trg if isinstance(trg, list) else [str(trg)]
            head += "\nTriggers: " + ", ".join(str(t) for t in trg_list)
        parts.append(head)

        # 2. H2 sekcije PRED H1 — obdrži ne-boilerplate (transverzalna pravila,
        #    When to invoke, Step 0 …).
        pre = sections if first_h1 is None else sections[:first_h1]
        kept_pre = []
        for lvl, hdr, s, e in pre:
            if lvl != 2:
                continue
            if _normalize_section(hdr) in DROP_SECTION_KEYS:
                continue
            kept_pre.append(body[s:e].rstrip())
        if kept_pre:
            parts.append("\n\n".join(kept_pre))

        # 3. Skill-specifični del = od prvega H1 do konca (ali celo telo); obrambno
        #    odstrani še morebitne DROP H2 sekcije znotraj tega obsega.
        if first_h1 is not None:
            s, e = sections[first_h1][2], sections[first_h1][3]
            tail = _remove_drop_sections(body[s:e])
        else:
            tail = _remove_drop_sections(body)
        if tail.strip():
            parts.append(tail)

        return _cap("\n\n".join(p for p in parts if p), cap)

    def _extract_section(self, body: str, section: str, cap: int) -> Optional[str]:
        target = _normalize_section(section)
        for lvl, hdr, s, e in _scan_sections(body):
            if lvl != 2:
                continue
            key = _normalize_section(hdr)
            if key == target or key.startswith(target + " "):
                return _cap(body[s:e].rstrip(), cap)
        return None
