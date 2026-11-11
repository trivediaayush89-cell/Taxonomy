"""Comprehensive unit tests for ISS-05, ISS-06, and ISS-07:
- ISS-05: Score margin dropoff candidate pruning.
- ISS-06: DAG Transitive dependency resolution and strict topological ordering.
- ISS-07: Category locking, visual authority exclusivity, and joint constraint checking.
"""

from pathlib import Path
import pytest
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver
from taxonomy.models import SkillMetadata
from taxonomy.dag import SkillDAG, CyclicDependencyError


def test_iss05_score_margin_dropoff_pruning(tmp_path):
    """Candidates falling below top_score * score_dropoff_ratio are pruned from pod selection."""
    # Top skill: matches prompt heavily
    d1 = tmp_path / "top-tool"
    d1.mkdir()
    (d1 / "SKILL.md").write_text(
        "---\nname: top-tool\ndescription: high priority rust systems compiler\ncategory: systems.rust\ntags: [rust, systems, compiler]\npriority: 100\n---\n",
        encoding="utf-8",
    )

    # Runner up skill: matches only 1 incidental word weakly
    d2 = tmp_path / "weak-tool"
    d2.mkdir()
    (d2 / "SKILL.md").write_text(
        "---\nname: weak-tool\ndescription: occasional rust scripts\ncategory: tooling.scripts\ntags: [script]\npriority: 20\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    resolver = SkillResolver(idx, max_skills=3, enable_triad=False, score_dropoff_ratio=0.50)

    res = resolver.resolve("Optimize rust systems compiler", force_route=True)
    assert len(res.selected_skills) == 1
    assert res.selected_skills[0].name == "top-tool"


def test_iss06_dag_transitive_requires_and_topological_order(tmp_path):
    """Transitive prerequisites (A -> B -> C) are fully resolved and topologically ordered [C, B, A]."""
    # Skill C: Base library
    d_c = tmp_path / "skill-c"
    d_c.mkdir()
    (d_c / "SKILL.md").write_text(
        "---\nname: skill-c\ndescription: low-level crypto primitives\ncategory: security.crypto\ntags: [crypto, primitives]\npriority: 70\n---\n",
        encoding="utf-8",
    )

    # Skill B: Middleware (requires C)
    d_b = tmp_path / "skill-b"
    d_b.mkdir()
    (d_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: authentication tokens middleware\ncategory: auth.tokens\ntags: [tokens]\nrequires: [skill-c]\npriority: 80\n---\n",
        encoding="utf-8",
    )

    # Skill A: High-level API (requires B)
    d_a = tmp_path / "skill-a"
    d_a.mkdir()
    (d_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: oauth login handler\ncategory: api.auth\ntags: [oauth, login]\nrequires: [skill-b]\npriority: 90\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    resolver = SkillResolver(idx, max_skills=5, enable_triad=False)

    # Resolve prompt matching only skill-a
    res = resolver.resolve("Build oauth login handler", force_route=True)
    selected_names = [s.name for s in res.selected_skills]

    # All three must be present
    assert selected_names == ["skill-c", "skill-b", "skill-a"], f"Expected [skill-c, skill-b, skill-a], got {selected_names}"

    # Verify order: prerequisite C before B, B before A
    idx_c = selected_names.index("skill-c")
    idx_b = selected_names.index("skill-b")
    idx_a = selected_names.index("skill-a")
    assert idx_c < idx_b < idx_a


def test_iss06_prerequisites_rejected_if_cannot_fit_budget(tmp_path):
    """If candidate A requires B and C, but budget cap is 2, A cannot be partially dispatched without dependencies."""
    d_c = tmp_path / "skill-c"
    d_c.mkdir()
    (d_c / "SKILL.md").write_text(
        "---\nname: skill-c\ndescription: primitive c\ncategory: base.c\ntags: [c]\n---\n",
        encoding="utf-8",
    )
    d_b = tmp_path / "skill-b"
    d_b.mkdir()
    (d_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: middleware b\ncategory: base.b\nrequires: [skill-c]\n---\n",
        encoding="utf-8",
    )
    d_a = tmp_path / "skill-a"
    d_a.mkdir()
    (d_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: application a\ncategory: base.a\ntags: [target]\nrequires: [skill-b]\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    # Set max_skills=2 (cannot fit all 3: skill-a, skill-b, skill-c)
    resolver = SkillResolver(idx, max_skills=2, enable_triad=False)

    res = resolver.resolve("build target", force_route=True)
    # Since skill-a requires 2 prerequisites (3 total skills), it cannot fit in budget of 2
    assert "skill-a" not in [s.name for s in res.selected_skills]


def test_iss07_category_locking_prevents_multiple_visual_authorities(tmp_path):
    """Single-authority categories lock out competing design skills even without explicit conflicts_with."""
    # Tool 1: Marketing design
    d1 = tmp_path / "design-marketing"
    d1.mkdir()
    (d1 / "SKILL.md").write_text(
        "---\nname: design-marketing\ndescription: marketing page design\ncategory: ui.marketing\ntags: [design, landing]\npriority: 90\n---\n",
        encoding="utf-8",
    )

    # Tool 2: Product UI design (competing visual authority in ui.product)
    d2 = tmp_path / "design-product"
    d2.mkdir()
    (d2 / "SKILL.md").write_text(
        "---\nname: design-product\ndescription: saas product design\ncategory: ui.product\ntags: [design, saas]\npriority: 80\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    resolver = SkillResolver(idx, max_skills=3, enable_triad=False)

    # Prompt matching both design skills
    res = resolver.resolve("Design landing page and saas design", force_route=True)
    selected_names = [s.name for s in res.selected_skills]

    # Only one visual authority should be chosen (the higher priority one)
    assert "design-marketing" in selected_names
    assert "design-product" not in selected_names
    assert len(selected_names) == 1


def test_iss07_prerequisite_conflict_cancels_dependent_candidate(tmp_path):
    """If Skill A requires Skill B, but Skill B conflicts with already selected Skill X, A is rejected."""
    # Skill X (Already matched and selected)
    dx = tmp_path / "skill-x"
    dx.mkdir()
    (dx / "SKILL.md").write_text(
        "---\nname: skill-x\ndescription: primary database engine\ncategory: db.primary\ntags: [database, sql]\npriority: 95\nconflicts_with: [skill-b]\n---\n",
        encoding="utf-8",
    )

    # Skill B (conflicted with X)
    db = tmp_path / "skill-b"
    db.mkdir()
    (db / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: legacy database adapter\ncategory: db.adapter\ntags: [adapter]\npriority: 50\n---\n",
        encoding="utf-8",
    )

    # Skill A (Requires B)
    da = tmp_path / "skill-a"
    da.mkdir()
    (da / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: migration runner\ncategory: db.migration\ntags: [database, migration]\nrequires: [skill-b]\npriority: 70\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    resolver = SkillResolver(idx, max_skills=3, enable_triad=False)

    res = resolver.resolve("database migration sql", force_route=True)
    selected = [s.name for s in res.selected_skills]

    assert "skill-x" in selected
    # skill-a requires skill-b which conflicts with skill-x, so neither skill-a nor skill-b can be selected
    assert "skill-b" not in selected
    assert "skill-a" not in selected


def test_prerequisite_in_avoid_skills_blocks_candidate(tmp_path):
    """If Skill A requires Skill B, and Skill B is in avoid_skills, Skill A must also be rejected."""
    from taxonomy.taste import TasteProfile

    db = tmp_path / "prereq-skill"
    db.mkdir()
    (db / "SKILL.md").write_text(
        "---\nname: prereq-skill\ndescription: base runtime\ncategory: backend.core\ntags: [core]\npriority: 60\n---\n",
        encoding="utf-8",
    )

    da = tmp_path / "dependent-skill"
    da.mkdir()
    (da / "SKILL.md").write_text(
        "---\nname: dependent-skill\ndescription: feature module needing base runtime\ncategory: backend.api\ntags: [api, feature]\nrequires: [prereq-skill]\npriority: 90\n---\n",
        encoding="utf-8",
    )

    idx = SkillIndexer([tmp_path])
    idx.scan()
    taste = TasteProfile(avoid_skills=["prereq-skill"])
    resolver = SkillResolver(idx, taste_profile=taste, max_skills=3, enable_triad=False)

    res = resolver.resolve("implement backend api feature module", force_route=True)
    selected = [s.name for s in res.selected_skills]
    assert "prereq-skill" not in selected
    assert "dependent-skill" not in selected

