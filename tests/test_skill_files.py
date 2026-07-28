import re
from pathlib import Path

import pytest

SKILLS = sorted((Path(__file__).resolve().parent.parent / "skills").glob("*/SKILL.md"))


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, f"{path}: frontmatter 없음"
    return dict(
        line.split(":", 1) for line in m.group(1).splitlines() if ":" in line
    ), text


def test_at_least_retro_skill_exists():
    names = [p.parent.name for p in SKILLS]
    assert "retro" in names


@pytest.mark.parametrize("skill_md", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_valid(skill_md):
    meta, _ = _frontmatter(skill_md)
    assert meta.get("name", "").strip() == skill_md.parent.name
    assert len(meta.get("description", "").strip()) > 20


@pytest.mark.parametrize("skill_md", SKILLS, ids=lambda p: p.parent.name)
def test_referenced_local_paths_exist(skill_md):
    _, text = _frontmatter(skill_md)
    for ref in re.findall(r"`((?:scripts|assets|references)/[\w./-]+)`", text):
        assert (skill_md.parent / ref).exists(), f"{skill_md.parent.name}: {ref} 없음"
