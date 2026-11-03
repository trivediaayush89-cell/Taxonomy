"""Comprehensive tests for Judge Guardrails 1, 2, and 3:
- Guardrail 1: Dynamic 5% Sizing Formula (scales 3 to 5, clamped at 5).
- Guardrail 2: Complementary Pod Pairing (The Triad / Pod Architecture).
- Guardrail 3: Strict Negative Selection & Exclusion Preservation.
"""

from pathlib import Path
import pytest

from taxonomy.hook import dispatch_prompt, init_dispatcher
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver, compute_dynamic_budget


def test_dynamic_5_percent_sizing_formula():
    """Verify dynamic 5% sizing math scales from min 3 up to max 5 (clamped)."""
    assert compute_dynamic_budget(0) == 3
    assert compute_dynamic_budget(1) == 3
    assert compute_dynamic_budget(10) == 3
    assert compute_dynamic_budget(25) == 3
    assert compute_dynamic_budget(60) == 3
    assert compute_dynamic_budget(61) == 4
    assert compute_dynamic_budget(80) == 4
    assert compute_dynamic_budget(100) == 5
    assert compute_dynamic_budget(150) == 5
    assert compute_dynamic_budget(1000) == 5


def test_marketing_portfolio_resolves_3_skill_triad():
    """Human brief 'Build and design a clean marketing portfolio page' must resolve a complete triad."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live catalog not available on this runner")

    resolver = SkillResolver(indexer)
    res = resolver.resolve("Build and design a clean marketing portfolio page")

    selected_names = [s.name for s in res.selected_skills]
    assert len(selected_names) == 3, f"Expected 3-skill pod triad, got {selected_names}"
    assert selected_names[0] == "design-taste-frontend"
    assert "frontend-ui-engineering" in selected_names
    assert "engineering-quality-gate" in selected_names

    # Guardrail 3: Conflict A mutual exclusion strictly preserved
    assert "impeccable" not in selected_names
    assert "unslop" not in selected_names
    assert "frontend-design" not in selected_names


def test_product_saas_dashboard_resolves_3_skill_triad():
    """SaaS dashboard brief must resolve impeccable + engineering + qa triad without visual conflicts."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live catalog not available on this runner")

    resolver = SkillResolver(indexer)
    res = resolver.resolve("Build a SaaS dashboard with user settings and analytics tables")

    selected_names = [s.name for s in res.selected_skills]
    assert len(selected_names) == 3, f"Expected 3-skill pod triad, got {selected_names}"
    assert selected_names[0] == "impeccable"
    assert "frontend-ui-engineering" in selected_names
    assert "engineering-quality-gate" in selected_names

    # Guardrail 3: Conflict A mutual exclusion strictly preserved
    assert "design-taste-frontend" not in selected_names
    assert "unslop" not in selected_names


def test_sloppy_ui_cleanup_resolves_3_skill_triad():
    """UI cleanup brief must resolve unslop + engineering + qa triad without visual conflicts."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live catalog not available on this runner")

    resolver = SkillResolver(indexer)
    res = resolver.resolve("Unslop and cleanup this messy AI-generated vibecoded screen")

    selected_names = [s.name for s in res.selected_skills]
    assert len(selected_names) == 3, f"Expected 3-skill pod triad, got {selected_names}"
    assert selected_names[0] == "unslop"
    assert "frontend-ui-engineering" in selected_names
    assert "engineering-quality-gate" in selected_names

    # Guardrail 3: Conflict A mutual exclusion strictly preserved
    assert "design-taste-frontend" not in selected_names
    assert "impeccable" not in selected_names


def test_pure_backend_resolves_backend_pod_without_ui_leakage():
    """Backend REST API brief must assemble backend pod with zero UI/frontend skills."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live catalog not available on this runner")

    resolver = SkillResolver(indexer)
    res = resolver.resolve("Create a high-performance REST API with FastAPI and PostgreSQL database")

    selected_names = [s.name for s in res.selected_skills]
    assert len(selected_names) >= 2, f"Expected at least 2 backend pod partners, got {selected_names}"
    assert "development-director" in selected_names
    assert "engineering-quality-gate" in selected_names

    # Guardrail 3: Strict Domain Negative Selection: NO UI categories or UI-tagged skills
    for s in res.selected_skills:
        assert not s.category.startswith(("ui.", "frontend.", "quality.animation")), f"UI category leaked: {s.category}"
        assert "ui" not in s.tags, f"UI tag leaked in {s.name}"
        assert "frontend" not in s.tags, f"Frontend tag leaked in {s.name}"


def test_explicit_max_skills_overrides_pod_size():
    """Caller explicitly passing max_skills=1 or max_skills=2 must override default triad sizing."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live catalog not available on this runner")

    # max_skills=1
    res1 = dispatch_prompt("Build and design a clean marketing portfolio page", max_skills=1)
    assert len(res1.selected_skills) == 1
    assert res1.selected_skills[0].name == "design-taste-frontend"

    # max_skills=2
    res2 = dispatch_prompt("Build and design a clean marketing portfolio page", max_skills=2)
    assert len(res2.selected_skills) == 2
    assert res2.selected_skills[0].name == "design-taste-frontend"
    assert res2.selected_skills[1].name == "frontend-ui-engineering"


def test_100_skills_catalog_scales_to_5_skills_budget(tmp_path):
    """A catalog with 100 skills automatically budgets up to 5 skills (capped at 5%)."""
    for i in range(1, 101):
        d = tmp_path / f"tool-{i:03d}"
        d.mkdir()
        cat = "frontend.engineering" if i % 2 == 0 else "orchestration.lead"
        (d / "SKILL.md").write_text(
            f"---\n"
            f"name: tool-{i:03d}\n"
            f"description: Scaled tool component {i} for frontend layout\n"
            f"category: {cat}\n"
            f"tags: [frontend, component, layout]\n"
            f"priority: {i}\n"
            f"---\n",
            encoding="utf-8",
        )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    assert len(indexer.all_skills) == 100

    resolver = SkillResolver(indexer)
    # Default max_skills must be dynamically computed as 5 (100 * 0.05 = 5)
    assert resolver.max_skills == 5

    res = resolver.resolve("Build and scaffold frontend layout components", force_route=True)
    assert len(res.selected_skills) == 5
    assert len(res.selected_skills) <= 5
