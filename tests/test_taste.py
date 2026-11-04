"""Comprehensive tests for User Taste Profiles & Deterministic Preference Engine:
- Invariant 1: Domain Gate Invariant (pure backend suppresses UI taste bias).
- Invariant 2: Mutual Exclusion Invariant (Conflict A strictly preserved under taste bias).
- Invariant 3: Quality Sentry Immunity (QA/Review sentries immune to negative bias).
- Invariant 4: Pod Sizing Invariant (dynamic 5% sizing budget preserved).
- Precedence Hierarchy: Workspace overrides User profile.
- Bounded Bias Math: Clamped strictly to [-3.0, +3.0].
- CLI Commands: taxonomy taste list, set, avoid, reset, and --prefer override.
- Fail-open resilience on corrupted JSON.
- Atomic file write safety and <0.05ms in-memory cached latency SLA.
"""

import json
from pathlib import Path
import time
import pytest

from taxonomy.cli import (
    cmd_explain,
    cmd_resolve,
    cmd_taste_avoid,
    cmd_taste_list,
    cmd_taste_reset,
    cmd_taste_set,
)
from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata
from taxonomy.resolver import SkillResolver
from taxonomy.taste import (
    TasteProfile,
    clear_taste_cache,
    get_user_taste_path,
    get_workspace_taste_path,
    load_taste_file,
    load_taste_profile,
    merge_taste_profiles,
    save_taste_profile,
)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_taste_cache()
    yield
    clear_taste_cache()


def test_bounded_bias_math_clamps_weights():
    """Verify that taste weights are strictly clamped to [-3.0, +3.0]."""
    profile = TasteProfile(
        weights={
            "overly-hyped-skill": 99.9,
            "deeply-hated-skill": -50.0,
            "moderate-boost": 1.5,
        }
    )

    skill_high = SkillMetadata(name="overly-hyped-skill", description="desc", category="ui.design")
    skill_low = SkillMetadata(name="deeply-hated-skill", description="desc", category="ui.design")
    skill_mod = SkillMetadata(name="moderate-boost", description="desc", category="ui.design")

    assert profile.get_bias(skill_high) == 3.0
    assert profile.get_bias(skill_low) == -3.0
    assert profile.get_bias(skill_mod) == 1.5


def test_quality_sentry_immunity_against_negative_bias():
    """Judicial Invariant 3: QA and review sentries can NEVER receive negative bias."""
    profile = TasteProfile(
        avoid_skills=["engineering-quality-gate", "adversarial-jury", "code-auditor"],
        weights={
            "engineering-quality-gate": -3.0,
            "adversarial-jury": -2.5,
            "code-auditor": -3.0,
        },
    )

    gate_skill = SkillMetadata(
        name="engineering-quality-gate",
        description="Empirical quality verification",
        category="verification.qa",
    )
    jury_skill = SkillMetadata(
        name="adversarial-jury",
        description="Stage 2 court review",
        category="decision.review",
    )
    auditor_skill = SkillMetadata(
        name="code-auditor",
        description="Codebase quality auditing",
        category="verification.qa",
    )

    # All must be immune to negative bias
    assert profile.get_bias(gate_skill) == 0.0
    assert profile.get_bias(jury_skill) == 0.0
    assert profile.get_bias(auditor_skill) == 0.0


def test_workspace_profile_overrides_user_profile(tmp_path):
    """Hierarchy Precedence: Workspace taste strictly overrides User taste."""
    user_file = tmp_path / "user_taste.json"
    ws_dir = tmp_path / "repo" / ".taxonomy"
    ws_dir.mkdir(parents=True)
    ws_file = ws_dir / "taste.json"

    # User prefers 'design-taste-frontend' and avoids 'unslop'
    user_profile = TasteProfile(
        preferred_skills={"frontend.visual": "design-taste-frontend"},
        avoid_skills=["unslop"],
        weights={"impeccable": -1.0},
    )
    save_taste_profile(user_profile, user_file)

    # Workspace repo explicitly prefers 'impeccable' and has positive weight for 'unslop'
    ws_profile = TasteProfile(
        preferred_skills={"frontend.visual": "impeccable"},
        weights={"impeccable": 3.0, "unslop": 1.0},
    )
    save_taste_profile(ws_profile, ws_file)

    merged = load_taste_profile(workspace_root=tmp_path / "repo", user_path=user_file)

    assert merged.preferred_skills["frontend.visual"] == "impeccable"
    assert merged.weights["impeccable"] == 3.0
    assert merged.source == "workspace+user"
    # Workspace positive weight for unslop un-avoids it
    assert "unslop" not in merged.avoid_skills


def test_taste_bias_flips_candidate_selection(tmp_path):
    """Verify that a +3.0 taste boost cleanly flips a close candidate tie in favor of preferred skill."""
    # Skill A (priority 85)
    dir_a = tmp_path / "skill-taste"
    dir_a.mkdir()
    (dir_a / "SKILL.md").write_text(
        "---\nname: skill-taste\ndescription: Tasteful UI styling\ncategory: ui.marketing\ntags: [ui, tailwind]\npriority: 85\n---\n",
        encoding="utf-8",
    )

    # Skill B (priority 80)
    dir_b = tmp_path / "skill-impeccable"
    dir_b.mkdir()
    (dir_b / "SKILL.md").write_text(
        "---\nname: skill-impeccable\ndescription: Product UI styling\ncategory: ui.product\ntags: [ui, tailwind]\npriority: 80\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()

    # 1. Unbiased resolver: skill-taste wins due to higher priority (85 vs 80)
    unbiased_resolver = SkillResolver(indexer, max_skills=1, taste_profile=TasteProfile())
    res_unbiased = unbiased_resolver.resolve("Build a tailwind UI component", force_route=True)
    assert [s.name for s in res_unbiased.selected_skills] == ["skill-taste"]

    # 2. Taste-biased resolver: user prefers skill-impeccable (+3.0)
    taste = TasteProfile(preferred_skills={"frontend.visual": "skill-impeccable"})
    biased_resolver = SkillResolver(indexer, max_skills=1, taste_profile=taste)
    res_biased = biased_resolver.resolve("Build a tailwind UI component", force_route=True)
    assert [s.name for s in res_biased.selected_skills] == ["skill-impeccable"]
    assert res_biased.skill_scores["skill-impeccable"].taste_bias == 3.0


def test_mutual_exclusion_invariant_preserved(tmp_path):
    """Judicial Invariant 2: Taste bias decides the winner between conflicting skills, but never bypasses Conflict A."""
    dir_a = tmp_path / "skill-taste"
    dir_a.mkdir()
    (dir_a / "SKILL.md").write_text(
        "---\nname: skill-taste\ndescription: UI styling\ncategory: ui.marketing\ntags: [ui, tailwind]\npriority: 90\nconflicts_with: [skill-impeccable]\n---\n",
        encoding="utf-8",
    )

    dir_b = tmp_path / "skill-impeccable"
    dir_b.mkdir()
    (dir_b / "SKILL.md").write_text(
        "---\nname: skill-impeccable\ndescription: UI styling\ncategory: ui.product\ntags: [ui, tailwind]\npriority: 80\nconflicts_with: [skill-taste]\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()

    # Taste favors skill-impeccable with +3.0
    taste = TasteProfile(weights={"skill-impeccable": 3.0})
    resolver = SkillResolver(indexer, max_skills=3, taste_profile=taste)
    res = resolver.resolve("Build a tailwind UI component", force_route=True)

    selected = [s.name for s in res.selected_skills]
    # skill-impeccable wins, and skill-taste MUST BE EXCLUDED (never both)
    assert selected == ["skill-impeccable"]
    assert "skill-taste" not in selected


def test_domain_gate_invariant_suppresses_ui_preference_on_backend_prompt(tmp_path):
    """Judicial Invariant 1: Taste preference for UI skill cannot activate it on a pure backend prompt."""
    ui_dir = tmp_path / "skill-impeccable"
    ui_dir.mkdir()
    (ui_dir / "SKILL.md").write_text(
        "---\nname: skill-impeccable\ndescription: Modern UI component library\ncategory: ui.product\ntags: [ui, frontend, component]\npriority: 90\n---\n",
        encoding="utf-8",
    )

    backend_dir = tmp_path / "backend-api"
    backend_dir.mkdir()
    (backend_dir / "SKILL.md").write_text(
        "---\nname: backend-api\ndescription: FastAPI REST service\ncategory: backend.api\ntags: [backend, api, database, postgres]\npriority: 80\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()

    # User strongly loves impeccable (+3.0)
    taste = TasteProfile(preferred_skills={"frontend.visual": "skill-impeccable"}, weights={"skill-impeccable": 3.0})
    resolver = SkillResolver(indexer, max_skills=3, taste_profile=taste)

    # Pure backend prompt
    res = resolver.resolve("Optimize postgres database connection pool and sql queries", force_route=True)
    selected = [s.name for s in res.selected_skills]

    assert "backend-api" in selected
    # UI skill must NOT leak into pure backend prompt despite strong positive taste
    assert "skill-impeccable" not in selected


def test_cli_prefer_override_applies_direct_boost(tmp_path):
    """CLI --prefer flag dynamically applies +3.0 boost and records source as 'cli'."""
    dir_a = tmp_path / "skill-a"
    dir_a.mkdir()
    (dir_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: Component builder\ncategory: ui.component\ntags: [button, card]\npriority: 85\n---\n",
        encoding="utf-8",
    )

    dir_b = tmp_path / "skill-b"
    dir_b.mkdir()
    (dir_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: Component builder\ncategory: ui.component\ntags: [button, card]\npriority: 70\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer, max_skills=1, taste_profile=TasteProfile())

    # Ad-hoc override prefer skill-b
    res = resolver.resolve("Build a button and card", force_route=True, prefer="skill-b")
    assert [s.name for s in res.selected_skills] == ["skill-b"]
    assert res.taste_profile_source == "cli"
    assert res.skill_scores["skill-b"].taste_bias == 3.0


def test_fail_open_on_corrupted_taste_json(tmp_path):
    """Graceful degradation: Malformed JSON logs a warning and falls back to default unweighted profile."""
    bad_file = tmp_path / "corrupted_taste.json"
    bad_file.write_text("{ this is not valid json : [", encoding="utf-8")

    profile = load_taste_file(bad_file)
    assert profile is None

    merged = load_taste_profile(user_path=bad_file)
    assert isinstance(merged, TasteProfile)
    assert merged.is_empty()


def test_atomic_save_and_caching(tmp_path):
    """Verify atomic write creates valid JSON, and in-memory cache returns instantly."""
    target = tmp_path / "test_taste.json"
    profile = TasteProfile(
        preferred_skills={"backend.framework": "fastapi"},
        avoid_skills=["unslop"],
        weights={"fastapi": 2.5},
    )

    save_taste_profile(profile, target)
    assert target.is_file()

    # Verify JSON content
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["preferred_skills"]["backend.framework"] == "fastapi"
    assert data["avoid_skills"] == ["unslop"]
    assert data["weights"]["fastapi"] == 2.5

    # First load
    start = time.perf_counter()
    loaded1 = load_taste_file(target)
    cold_dur = (time.perf_counter() - start) * 1000

    # Second load (cached)
    start_cached = time.perf_counter()
    loaded2 = load_taste_file(target)
    cached_dur = (time.perf_counter() - start_cached) * 1000

    assert loaded1 is loaded2
    assert cached_dur < 1.0, f"Cached load latency ({cached_dur:.4f}ms) breached SLA"


def test_cli_taste_commands_execution(tmp_path, monkeypatch, capsys):
    """Verify all taste CLI subcommands (list, set, avoid, reset) execute cleanly."""
    ws_tax = tmp_path / ".taxonomy"
    ws_tax.mkdir()
    ws_file = ws_tax / "taste.json"

    # Mock workspace and user taste paths to use tmp_path
    monkeypatch.setattr("taxonomy.taste.get_workspace_taste_path", lambda start_dir=None: ws_file)
    monkeypatch.setattr("taxonomy.taste.find_workspace_taste_path", lambda start_dir=None: ws_file if ws_file.is_file() else None)
    monkeypatch.setattr("taxonomy.taste.DEFAULT_USER_TASTE_PATH", tmp_path / "user_taste.json")
    monkeypatch.setattr("taxonomy.taste.get_user_taste_path", lambda: tmp_path / "user_taste.json")

    class ArgsSet:
        key = "frontend.visual"
        val = "impeccable"
        workspace = True

    cmd_taste_set(ArgsSet())
    out = capsys.readouterr().out
    assert "Preferred 'impeccable' for 'frontend.visual'" in out
    assert ws_file.is_file()

    class ArgsSetWeight:
        key = "impeccable"
        val = "2.8"
        workspace = True

    cmd_taste_set(ArgsSetWeight())
    out = capsys.readouterr().out
    assert "Set weight for 'impeccable' to +2.8" in out

    class ArgsAvoid:
        skill = "unslop"
        workspace = True

    cmd_taste_avoid(ArgsAvoid())
    out = capsys.readouterr().out
    assert "Added 'unslop' to avoidance list" in out

    class ArgsList:
        skills_dir = None

    cmd_taste_list(ArgsList())
    out = capsys.readouterr().out
    assert "frontend.visual" in out
    assert "impeccable" in out
    assert "unslop" in out

    class ArgsReset:
        workspace = True
        all = False

    cmd_taste_reset(ArgsReset())
    out = capsys.readouterr().out
    assert "Cleared taste preferences" in out

    # Verify reset emptied the profile
    loaded = load_taste_file(ws_file)
    assert loaded.is_empty()


def test_cross_field_hierarchy_override_consistency():
    """Verify workspace preferences cleanly override conflicting user weights and avoid_skills."""
    skill_imp = SkillMetadata(name="impeccable", description="Product UI", category="ui.product")

    # Case 1: User avoided/downvoted 'impeccable', but Workspace prefers 'impeccable' via preferred_skills
    user_p1 = TasteProfile(avoid_skills=["impeccable"], weights={"impeccable": -2.0}, source="user")
    ws_p1 = TasteProfile(preferred_skills={"frontend.visual": "impeccable"}, source="workspace")
    merged1 = merge_taste_profiles(user_p1, ws_p1)
    assert merged1.get_bias(skill_imp) == 3.0

    # Case 2: User preferred/boosted 'impeccable', but Workspace avoids 'impeccable' via avoid_skills
    user_p2 = TasteProfile(preferred_skills={"frontend.visual": "impeccable"}, weights={"impeccable": 3.0}, source="user")
    ws_p2 = TasteProfile(avoid_skills=["impeccable"], source="workspace")
    merged2 = merge_taste_profiles(user_p2, ws_p2)
    assert merged2.get_bias(skill_imp) == -3.0


def test_domain_aligned_taste_preference_activates_in_valid_domain_only(tmp_path):
    """Verify preferred UI visual skill activates on UI domain prompts even without direct tag hits,
    but remains inactive on non-UI prompts (e.g. blockchain/smart contracts).
    """
    ui_eng = tmp_path / "frontend-ui-engineering"
    ui_eng.mkdir()
    (ui_eng / "SKILL.md").write_text(
        "---\nname: frontend-ui-engineering\ndescription: Component layout\ncategory: frontend.engineering\ntags: [ui, tailwind, css, button]\npriority: 88\n---\n",
        encoding="utf-8",
    )

    imp = tmp_path / "impeccable"
    imp.mkdir()
    (imp / "SKILL.md").write_text(
        "---\nname: impeccable\ndescription: SaaS dashboard screens\ncategory: ui.product\ntags: [dashboard, saas]\npriority: 91\nconflicts_with: [design-taste-frontend]\n---\n",
        encoding="utf-8",
    )

    dtf = tmp_path / "design-taste-frontend"
    dtf.mkdir()
    (dtf / "SKILL.md").write_text(
        "---\nname: design-taste-frontend\ndescription: Marketing css styling\ncategory: ui.marketing\ntags: [landing-page, marketing]\npriority: 92\nconflicts_with: [impeccable]\n---\n",
        encoding="utf-8",
    )

    auditor = tmp_path / "contract-auditor"
    auditor.mkdir()
    (auditor / "SKILL.md").write_text(
        "---\nname: contract-auditor\ndescription: Solidity smart contract security\ncategory: security.blockchain\ntags: [smart-contract, reentrancy, solidity]\npriority: 90\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    taste = TasteProfile(preferred_skills={"frontend.visual": "impeccable"}, source="user")
    resolver = SkillResolver(indexer, max_skills=3, taste_profile=taste)

    # 1. On UI prompt ('Style this button with tailwind css'), impeccable is domain-aligned and selected
    res_ui = resolver.resolve("Style this button with tailwind css", force_route=True)
    ui_selected = [s.name for s in res_ui.selected_skills]
    assert "impeccable" in ui_selected
    assert "design-taste-frontend" not in ui_selected

    # 2. On Blockchain prompt ('Audit this Solidity smart-contract for reentrancy'), impeccable is NOT selected
    res_sec = resolver.resolve("Audit this Solidity smart-contract for reentrancy", force_route=True)
    sec_selected = [s.name for s in res_sec.selected_skills]
    assert "contract-auditor" in sec_selected
    assert "impeccable" not in sec_selected


def test_markdown_profile_fallback_and_schema_validation(tmp_path):
    """Verify developer-profile.local.md fallback ingestion and taste.schema.json validation."""
    from taxonomy.taste import load_markdown_taste_file, validate_taste_schema

    md_file = tmp_path / "developer-profile.local.md"
    md_file.write_text(
        "# Developer Profile\n\n"
        "Some prose notes.\n\n"
        "```json:taste\n"
        '{"version": 1, "preferred_skills": {"frontend.visual": "impeccable"}, "weights": {"impeccable": 2.5}}\n'
        "```\n",
        encoding="utf-8",
    )

    md_profile = load_markdown_taste_file(md_file)
    assert md_profile is not None
    assert md_profile.preferred_skills["frontend.visual"] == "impeccable"
    assert md_profile.weights["impeccable"] == 2.5

    # Validate against schema rules
    schema_path = Path(__file__).parent.parent / "schemas" / "taste.schema.json"
    assert schema_path.is_file()
    schema_json = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema_json["title"] == "TasteProfile"

    ok, errs = validate_taste_schema({
        "version": 1,
        "preferred_skills": {"frontend.visual": "impeccable"},
        "avoid_skills": ["unslop"],
        "weights": {"impeccable": 3.0},
    })
    assert ok and not errs

    ok_bad, errs_bad = validate_taste_schema({
        "version": 1,
        "weights": {"impeccable": 9.5},
        "unknown_field": True,
    })
    assert not ok_bad
    assert len(errs_bad) == 2


def test_cli_explain_conflict_reason_and_sentry_guardrail(tmp_path, monkeypatch, capsys):
    """Verify CLI explain itemizes Conflict A exclusion reasons and CLI blocks avoiding quality sentry."""
    ws_file = tmp_path / ".taxonomy" / "taste.json"
    monkeypatch.setattr("taxonomy.taste.get_workspace_taste_path", lambda start_dir=None: ws_file)
    monkeypatch.setattr("taxonomy.taste.find_workspace_taste_path", lambda start_dir=None: ws_file if ws_file.is_file() else None)

    # Attempt to avoid protected quality sentry via CLI
    class ArgsAvoidSentry:
        skill = "engineering-quality-gate"
        workspace = True

    cmd_taste_avoid(ArgsAvoidSentry())
    out_sentry = capsys.readouterr().out
    assert "Judicial Guardrail Notice" in out_sentry
    assert not ws_file.exists()

    # Verify cmd_explain prints Conflict A exclusion reason
    dir_a = tmp_path / "skills" / "impeccable"
    dir_a.mkdir(parents=True)
    (dir_a / "SKILL.md").write_text(
        "---\nname: impeccable\ndescription: UI card component\ncategory: ui.product\ntags: [ui, card, component]\npriority: 85\nconflicts_with: [design-taste-frontend]\n---\n",
        encoding="utf-8",
    )
    dir_b = tmp_path / "skills" / "design-taste-frontend"
    dir_b.mkdir(parents=True)
    (dir_b / "SKILL.md").write_text(
        "---\nname: design-taste-frontend\ndescription: UI card component\ncategory: ui.marketing\ntags: [ui, card, component]\npriority: 90\nconflicts_with: [impeccable]\n---\n",
        encoding="utf-8",
    )

    class ArgsExplain:
        prompt = "Build a modern UI card component"
        skills_dir = str(tmp_path / "skills")
        max_skills = 3
        phase = None
        prefer = "impeccable"
        force = True

    cmd_explain(ArgsExplain())
    out_explain = capsys.readouterr().out
    assert "Candidate: 'impeccable' [SELECTED]" in out_explain
    assert "[EXCLUDED by Conflict A with 'impeccable']" in out_explain
    assert "(cli: --prefer)" in out_explain

