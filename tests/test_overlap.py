"""Tests for skill overlap and case-collision detection."""

from pathlib import Path
from taxonomy.indexer import SkillIndexer
from taxonomy.overlap import OverlapDetector


def test_overlap_detector_identifies_redundant_skills(tmp_path):
    # Two skills with nearly identical tags and descriptions
    s1_dir = tmp_path / "frontend-styler"
    s1_dir.mkdir()
    (s1_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontend-styler\n"
        "description: Visual UI design tokens styling and responsive css components\n"
        "category: ui.design\n"
        "tags: [ui, css, styling, tailwind, responsive]\n"
        "---\n",
        encoding="utf-8"
    )

    s2_dir = tmp_path / "frontend-designer"
    s2_dir.mkdir()
    (s2_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontend-designer\n"
        "description: Responsive UI components visual styling design tokens and css\n"
        "category: ui.design\n"
        "tags: [ui, css, styling, tailwind, tokens]\n"
        "---\n",
        encoding="utf-8"
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    detector = OverlapDetector(indexer, threshold=0.50)

    overlaps = detector.find_overlaps()
    assert len(overlaps) >= 1
    rep = overlaps[0]
    assert {rep.skill_a, rep.skill_b} == {"frontend-styler", "frontend-designer"}
    assert rep.similarity_score > 0.50
    assert "ui" in rep.shared_tags
    assert "styling" in rep.shared_tags


def test_case_collision_detection(tmp_path):
    indexer = SkillIndexer([tmp_path])
    from taxonomy.models import SkillMetadata
    indexer._skills_by_name = {
        "my-tool": SkillMetadata(name="my-tool", description="", category=""),
        "My-Tool": SkillMetadata(name="My-Tool", description="", category=""),
    }
    detector = OverlapDetector(indexer)
    collisions = detector.find_case_collisions()
    assert len(collisions) == 1
    assert set(collisions[0]) == {"my-tool", "My-Tool"}
