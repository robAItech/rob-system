"""Testi za GStack skilli kot LLM orodje (korak 6) — CI-safe, BREZ ~/.claude.

Vsi testi injicirajo `tmp_path` skills dir — nobene odvisnosti od resničnega
`~/.claude/skills/` (v CI ga ni). Preverijo: list_skills (izključi routerja),
get_skill distilled (preskoči boilerplate), cap, traversal varnost, section
param, loopx `_execute_tool` integracijo.
"""
from pathlib import Path

from core.config import settings
from core.loopx_bridge import LoopXEngineBridge
from core.skill_bridge import SKILL_CONTENT_CAP, SkillBridge


def _write_skill(root: Path, slug: str, description: str = "desc", process: str = "# /slug — P\n\n## Process\nfaze",
                 boilerplate: bool = True, interactive: bool = False) -> None:
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    fm = [f"---\nname: {slug}\nversion: 0.1.0\ndescription: {description}"]
    if interactive:
        fm.append("interactive: true")
    fm.append("triggers:\n  - use " + slug)
    fm.append("---\n")
    bp = ""
    if boilerplate:
        bp = ("## Preamble (run first)\n```bash\necho prevara\n```\n"
              "## AskUserQuestion Format\nlong interaktivni blok\n"
              "## Voice\nClaude voice\n## Telemetry (run last)\nanalytics\n")
    (d / "SKILL.md").write_text("\n".join(fm) + bp + process, encoding="utf-8")


def _make_skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    _write_skill(root, "spec", description="Turn vague intent into a precise, executable spec.")
    _write_skill(root, "qa", description="Systematically QA test a web application.")
    _write_skill(root, "gstack")          # router — mora biti izključen
    _write_skill(root, "_gstack-command")  # router — mora biti izključen
    return root


def test_list_skills_vrne_imena_in_izkljuci_ruterje(tmp_path):
    bridge = SkillBridge(_make_skills_dir(tmp_path))
    names = [s["name"] for s in bridge.list_skills()]
    assert names == ["qa", "spec"]           # sortirano
    assert "gstack" not in names and "_gstack-command" not in names


def test_list_skills_missing_dir(tmp_path):
    bridge = SkillBridge(tmp_path / "ni" / "tam")
    assert bridge.list_skills() == []


def test_get_skill_distilled_brez_boilerplate(tmp_path):
    bridge = SkillBridge(_make_skills_dir(tmp_path))
    skill = bridge.get_skill("spec")
    assert skill is not None
    assert "Turn vague intent" in skill["description"]
    content = skill["content"]
    assert "## Process" in content
    assert "Preamble (run first)" not in content
    assert "AskUserQuestion" not in content
    assert "Telemetry" not in content


def test_get_skill_frontmatter(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "spec", interactive=True)
    _write_skill(root, "plain")
    bridge = SkillBridge(root)
    s = bridge.get_skill("spec")
    assert s["name"] == "spec"
    assert s["triggers"] == ["use spec"]
    assert s["interactive"] is True
    assert bridge.get_skill("plain")["interactive"] is False


def test_get_skill_cap(tmp_path):
    root = tmp_path / "skills"
    big = "# /big — P\n\n## Process\n" + ("x" * 15000)
    _write_skill(root, "big", process=big)
    content = SkillBridge(root).get_skill("big")["content"]
    assert len(content) <= SKILL_CONTENT_CAP
    assert "...[izrezano" in content


def test_get_skill_missing(tmp_path):
    bridge = SkillBridge(_make_skills_dir(tmp_path))
    assert bridge.get_skill("nope") is None


def test_get_skill_traversal_slug(tmp_path):
    bridge = SkillBridge(_make_skills_dir(tmp_path))
    for bad in ("../x", "a/b", "", "/", "..", "spec/../qa"):
        assert bridge.get_skill(bad) is None, bad


def test_get_skill_section(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "spec", process="# /spec — P\n\n## Process\nfaze\n## Step 4\nkritika\n")
    bridge = SkillBridge(root)
    sec = bridge.get_skill("spec", section="Process")
    assert sec is not None
    assert sec["content"].startswith("## Process")
    assert "Step 4" not in sec["content"]


def test_get_skill_yaml_napaka(tmp_path):
    root = tmp_path / "skills"
    d = root / "broken"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\ndescription: [neveljaven\ntriggers:\n  - x\n---\n## Process\nfaze\n", encoding="utf-8")
    bridge = SkillBridge(root)
    # Ne sme dvigniti; ali None ali deluje prek regex fallbacka.
    skill = bridge.get_skill("broken")
    assert skill is None or skill.get("content") is not None


def test_loopx_execute_skill_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    engine = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    engine._skill_bridge = SkillBridge(_make_skills_dir(tmp_path))
    ok = engine._execute_tool("skill", {"name": "spec"})
    assert ok["ok"] is True
    assert "## Process" in ok["content"]
    bad = engine._execute_tool("skill", {"name": "nope"})
    assert bad["ok"] is False
    assert "available" in bad
    lst = engine._execute_tool("skill", {"name": "list"})
    assert lst["ok"] is True and lst["count"] >= 2


def test_loopx_skill_brez_bridge_ci(tmp_path, monkeypatch):
    """CI-safe: če skills dir ne obstaja → error dict, brez crasha."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "gstack_skills_dir", str(tmp_path / "ni" / "tam"))
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    engine = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    assert engine._execute_tool("skill", {"name": "spec"})["ok"] is False
    assert engine._execute_tool("skill", {"name": "list"})["ok"] is True
