"""Tests for mutual exclusion (conflicts_with), requirements (requires), and progressive disclosure."""

from pathlib import Path
from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata
from taxonomy.resolver import SkillResolver


def test_mutual_conflict_exclusion(tmp_path):
    # Skill A (Design Taste Frontend)
    dir_a = tmp_path / "skill-taste"
    dir_a.mkdir()
    (dir_a / "SKILL.md").write_text(
        "---\n"
        "name: skill-taste\n"
        "description: Tasteful UI styling\n"
        "category: ui.design\n"
        "tags: [ui, design, tailwind]\n"
        "priority: 90\n"
        "conflicts_with: [skill-impeccable]\n"
        "---\n# Body Taste\n",
        encoding="utf-8"
    )

    # Skill B (Impeccable UI)
    dir_b = tmp_path / "skill-impeccable"
    dir_b.mkdir()
    (dir_b / "SKILL.md").write_text(
        "---\n"
        "name: skill-impeccable\n"
        "description: Product UI refinement\n"
        "category: ui.design\n"
        "tags: [ui, design, tailwind]\n"
        "priority: 80\n"
        "conflicts_with: [skill-taste]\n"
        "---\n# Body Impeccable\n",
        encoding="utf-8"
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer, max_skills=3)

    # Prompt matches both skills equally
    res = resolver.resolve("Design a responsive tailwind UI", force_route=True)
    selected_names = [s.name for s in res.selected_skills]

    # Because skill-taste has higher priority (90 vs 80), it should win
    # and skill-impeccable MUST be excluded!
    assert "skill-taste" in selected_names
    assert "skill-impeccable" not in selected_names


def test_requires_dependency_auto_inclusion(tmp_path):
    # Skill A requires Skill B
    dir_a = tmp_path / "skill-jury"
    dir_a.mkdir()
    (dir_a / "SKILL.md").write_text(
        "---\n"
        "name: skill-jury\n"
        "description: Adversarial courtroom review\n"
        "category: decision.review\n"
        "tags: [courtroom, jury]\n"
        "priority: 85\n"
        "requires: [skill-director]\n"
        "---\n# Jury\n",
        encoding="utf-8"
    )

    dir_b = tmp_path / "skill-director"
    dir_b.mkdir()
    (dir_b / "SKILL.md").write_text(
        "---\n"
        "name: skill-director\n"
        "description: Orchestration coordinator\n"
        "category: orchestration.lead\n"
        "tags: [coordinator]\n"
        "priority: 95\n"
        "---\n# Director\n",
        encoding="utf-8"
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer, max_skills=3)

    # Prompt triggers jury, but doesn't mention director
    res = resolver.resolve("Run a courtroom jury review", force_route=True)
    selected_names = [s.name for s in res.selected_skills]

    # Director should be auto-included via requires!
    assert "skill-jury" in selected_names
    assert "skill-director" in selected_names


def test_progressive_disclosure_levels(tmp_path):
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: Demonstration skill for disclosure\n"
        "category: demo.test\n"
        "tags: [demo, test]\n"
        "priority: 60\n"
        "---\n"
        "# Demo Skill Instructions\n"
        "Line 1 of full instructions.\n"
        "Line 2 of full instructions.\n",
        encoding="utf-8"
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    skill = indexer.get_skill("demo-skill")
    assert skill is not None

    # Level 1: Pointer
    p = skill.to_pointer()
    assert p["name"] == "demo-skill"
    assert "Line 1" not in str(p)

    # Level 2: Summary
    s = skill.to_summary()
    assert s["description"] == "Demonstration skill for disclosure"
    assert "Line 1" not in str(s)

    # Level 3: Full Instructions
    full = skill.get_full_instructions()
    assert "Line 1 of full instructions." in full
    assert "Line 2 of full instructions." in full
