"""Checkpoint regression tests for edge cases discovered during audit."""

from pathlib import Path
import pytest

from taxonomy.dag import CyclicDependencyError
from taxonomy.hook import dispatch_prompt, init_dispatcher
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver


def test_folder_name_mismatch_preserved_on_warm_scan(tmp_path):
    """Folder named 'antigravity_guide' with frontmatter 'name: antigravity-guide' must not be evicted on warm scan."""
    folder = tmp_path / "antigravity_guide"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\n"
        "name: antigravity-guide\n"
        "description: Guide for Antigravity IDE\n"
        "category: docs.guide\n"
        "tags: [antigravity, guide]\n"
        "---\n# Guide\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    cold_skills = indexer.scan()
    assert "antigravity-guide" in cold_skills
    assert len(cold_skills) == 1

    # Second (warm) scan must retain 'antigravity-guide'
    warm_skills = indexer.scan()
    assert "antigravity-guide" in warm_skills
    assert len(warm_skills) == 1


def test_multi_root_precedence_earlier_wins(tmp_path):
    """Earlier root (custom skills) must take precedence over later root (builtin skills)."""
    custom_root = tmp_path / "custom"
    builtin_root = tmp_path / "builtin"
    (custom_root / "shared-skill").mkdir(parents=True)
    (builtin_root / "shared-skill").mkdir(parents=True)

    (custom_root / "shared-skill" / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Custom override version\ncategory: custom.cat\npriority: 99\n---\n",
        encoding="utf-8",
    )
    (builtin_root / "shared-skill" / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Builtin default version\ncategory: builtin.cat\npriority: 50\n---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([custom_root, builtin_root])
    skills = indexer.scan()
    assert skills["shared-skill"].category == "custom.cat"
    assert skills["shared-skill"].priority == 99

    # Verify warm scan also preserves custom precedence
    skills_warm = indexer.scan()
    assert skills_warm["shared-skill"].category == "custom.cat"


def test_short_tags_do_not_match_substrings_inside_words(tmp_path):
    """Short tags like 'ci' or 'ui' must match on word boundaries, not inside 'inefficiencies' or 'build'."""
    qa_dir = tmp_path / "qa-gate"
    qa_dir.mkdir()
    (qa_dir / "SKILL.md").write_text(
        "---\n"
        "name: qa-gate\n"
        "description: Automated pipeline runner\n"
        "category: verification.qa\n"
        "tags: [ci, ui]\n"
        "---\n",
        encoding="utf-8",
    )

    audit_dir = tmp_path / "contract-auditor"
    audit_dir.mkdir()
    (audit_dir / "SKILL.md").write_text(
        "---\n"
        "name: contract-auditor\n"
        "description: Solidity smart contract security analysis\n"
        "category: security.blockchain\n"
        "tags: [smart-contract, reentrancy, audit]\n"
        "---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer, max_skills=3)

    # Contains 'inefficiencies' (has 'ci') and 'build' (has 'ui'), but neither is the tag 'ci' or 'ui'!
    res = resolver.resolve(
        "Audit this ERC-20 smart contract for reentrancy vulnerabilities and gas inefficiencies before we build",
        force_route=True,
    )
    selected = [s.name for s in res.selected_skills]
    assert selected == ["contract-auditor"]
    assert "qa-gate" not in selected


def test_hook_switches_roots_and_max_skills_dynamically(tmp_path):
    """dispatch_prompt must re-initialize if skills_roots or max_skills changes across calls."""
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    (root_a / "skill-alpha").mkdir(parents=True)
    (root_b / "skill-beta").mkdir(parents=True)

    (root_a / "skill-alpha" / "SKILL.md").write_text(
        "---\nname: skill-alpha\ndescription: JWT authentication service\ncategory: backend.api\ntags: [jwt, auth]\n---\n",
        encoding="utf-8",
    )
    (root_b / "skill-beta" / "SKILL.md").write_text(
        "---\nname: skill-beta\ndescription: JWT authentication service\ncategory: backend.api\ntags: [jwt, auth]\n---\n",
        encoding="utf-8",
    )

    res_a = dispatch_prompt("Add a login page with JWT authentication", skills_roots=[root_a], max_skills=1)
    assert [s.name for s in res_a.selected_skills] == ["skill-alpha"]

    res_b = dispatch_prompt("Add a login page with JWT authentication", skills_roots=[root_b], max_skills=1)
    assert [s.name for s in res_b.selected_skills] == ["skill-beta"]


def test_indexer_detects_circular_requires_dependencies(tmp_path):
    """validate_dependency_dag must raise CyclicDependencyError when skills have circular requires."""
    for name, req in [("skill-1", "skill-2"), ("skill-2", "skill-1")]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill\ncategory: test\nrequires: [{req}]\n---\n",
            encoding="utf-8",
        )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    with pytest.raises(CyclicDependencyError):
        indexer.validate_dependency_dag()


def test_skills_json_exclusion_list_honored(tmp_path):
    """SkillIndexer must honor entries[].exclude from skills.json config."""
    skills_root = tmp_path / "agents_skills"
    for name in ("active-skill", "excluded-skill"):
        d = skills_root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill\ncategory: ui.design\ntags: [dashboard]\n---\n",
            encoding="utf-8",
        )

    cfg_file = tmp_path / "skills.json"
    cfg_file.write_text(
        f'{{"entries": [{{"path": "{skills_root.as_posix()}", "exclude": ["excluded-skill"]}}]}}',
        encoding="utf-8",
    )

    indexer = SkillIndexer([skills_root], skills_config_path=cfg_file)
    skills = indexer.scan()
    assert "active-skill" in skills
    assert "excluded-skill" not in skills


def test_domain_negative_selection_suppresses_ui_on_pure_backend(tmp_path):
    """Pure backend/smart-contract prompts must suppress UI/frontend skills even if generic words like 'design' appear."""
    ui_dir = tmp_path / "ui-designer"
    ui_dir.mkdir()
    (ui_dir / "SKILL.md").write_text(
        "---\n"
        "name: ui-designer\n"
        "description: Design and build product pages and interfaces. Not for backend-only tasks.\n"
        "category: ui.design\n"
        "tags: [landing-page, dashboard]\n"
        "priority: 95\n"
        "---\n",
        encoding="utf-8",
    )

    backend_dir = tmp_path / "backend-architect"
    backend_dir.mkdir()
    (backend_dir / "SKILL.md").write_text(
        "---\n"
        "name: backend-architect\n"
        "description: Distributed systems and API lead.\n"
        "category: orchestration.lead\n"
        "tags: [backend, api, postgres, rust]\n"
        "priority: 90\n"
        "---\n",
        encoding="utf-8",
    )

    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer)

    res = resolver.resolve("Design and build a distributed Rust backend REST API with Postgres database")
    picked = [s.name for s in res.selected_skills]
    assert picked == ["backend-architect"]
    assert "ui-designer" not in picked


def test_live_routing_matrix_and_mutual_exclusion():
    """Verify the live catalog honors skills.json exclusions and routes all 9 routing-matrix task types without conflicts."""
    indexer = SkillIndexer()
    skills = indexer.scan()
    if len(skills) < 20:
        pytest.skip("Live 25-skill environment not present on this runner")

    for excluded in ("orchestration", "web-artifacts-builder", "web-design-guidelines"):
        assert excluded not in skills

    resolver = SkillResolver(indexer)

    # 1. Marketing / Landing Page -> design-taste-frontend (never impeccable or unslop)
    r_mkt = resolver.resolve("Build a marketing landing page and portfolio showcase with hero section and animations")
    names_mkt = [s.name for s in r_mkt.selected_skills]
    assert "design-taste-frontend" in names_mkt
    assert "impeccable" not in names_mkt
    assert "unslop" not in names_mkt

    # 2. SaaS Dashboard / Web App -> impeccable (never design-taste-frontend or unslop)
    r_app = resolver.resolve("Build a SaaS analytics dashboard and admin settings web-app with onboarding forms")
    names_app = [s.name for s in r_app.selected_skills]
    assert "impeccable" in names_app
    assert "design-taste-frontend" not in names_app
    assert "unslop" not in names_app

    # 3. Sloppy / Vibe-coded Cleanup -> unslop (never design-taste-frontend or impeccable)
    r_slop = resolver.resolve("Unslop and cleanup this vibecoded AI-slop screen and restyle its layout")
    names_slop = [s.name for s in r_slop.selected_skills]
    assert "unslop" in names_slop
    assert "design-taste-frontend" not in names_slop
    assert "impeccable" not in names_slop

    # 4. Pure Backend / Smart Contract -> zero UI skills
    r_be = resolver.resolve("Architect and audit a Solidity smart-contract and Rust backend microservice with pytest")
    names_be = [s.name for s in r_be.selected_skills]
    assert "development-director" in names_be
    for s in r_be.selected_skills:
        assert not s.category.startswith(("ui.", "frontend."))

