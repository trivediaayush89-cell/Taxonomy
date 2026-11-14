"""Phase 4 Comprehensive Test Suite (ISS-20, ISS-21, ISS-22):
- ISS-20: Monorepo Root Discovery & Workspace Subpackage Scanning
  - find_project_root ascends to .git root from nested subpackage (apps/web).
  - find_project_root ascends to monorepo config (pnpm-workspace.yaml, package.json workspaces).
  - detect_project_fingerprint scans nested workspaces (apps/*, packages/*, services/*, crates/*, contracts/*, frontend, backend).
  - Full-stack & polyglot detection across multiple nested workspaces.
  - Manifest file deduplication in ProjectFingerprint.
- ISS-21: Soft UI Suppression & Expanded Frontend Signals
  - Expanded UI_FRONTEND_SIGNALS (view, page, dialog, tab, nav, menu, card, table, avatar, input, etc.).
  - "Fix the API endpoint error state in the user profile view" does NOT suppress UI categories.
  - Soft suppression in fullstack repositories dampens rather than hard-locking out UI skills.
  - Zero-score soft suppression priority guard preventing dampened UI skills from surviving on raw priority.
- ISS-22: Manifest File Mtime Cache Invalidation
  - In-place modification of package.json invalidates cache immediately even if directory mtime is unchanged.
  - In-place modification of nested apps/web/package.json invalidates parent root cache immediately.
  - In-place modification of contracts/Vault.sol and next.config.mjs invalidates cache immediately.
"""

import json
from pathlib import Path
import time
import pytest

from taxonomy.fingerprint import (
    ProjectFingerprint,
    clear_fingerprint_cache,
    detect_project_fingerprint,
    find_project_root,
)
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import (
    BACKEND_ONLY_SIGNALS,
    UI_FRONTEND_SIGNALS,
    SkillResolver,
    tokenize_code_aware,
)
from taxonomy.taste import clear_taste_cache

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


@pytest.fixture(autouse=True)
def clean_caches():
    clear_fingerprint_cache()
    clear_taste_cache()
    yield
    clear_fingerprint_cache()
    clear_taste_cache()


# =========================================================================
# ISS-20: Monorepo Root Discovery & Workspace Subpackage Scanning
# =========================================================================

def test_iss20_find_project_root_ascends_to_git_root(tmp_path):
    """Verify find_project_root ascends past nested package.json to the true .git root."""
    repo_root = tmp_path / "my_monorepo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    web_pkg = repo_root / "apps" / "web"
    web_pkg.mkdir(parents=True)
    (web_pkg / "package.json").write_text(json.dumps({"name": "web"}), encoding="utf-8")

    api_pkg = repo_root / "services" / "api"
    api_pkg.mkdir(parents=True)
    (api_pkg / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")

    # Ascending from apps/web directory
    assert find_project_root(web_pkg) == repo_root

    # Ascending from file within apps/web
    assert find_project_root(web_pkg / "package.json") == repo_root

    # Ascending from services/api
    assert find_project_root(api_pkg) == repo_root


def test_iss20_find_project_root_workspace_markers_without_git(tmp_path):
    """Verify find_project_root discovers monorepo roots via workspace markers without .git."""
    # 1. pnpm-workspace.yaml
    pnpm_mono = tmp_path / "pnpm_mono"
    pnpm_mono.mkdir()
    (pnpm_mono / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n", encoding="utf-8")
    sub_pkg = pnpm_mono / "packages" / "ui"
    sub_pkg.mkdir(parents=True)
    (sub_pkg / "package.json").write_text(json.dumps({"name": "ui"}), encoding="utf-8")

    assert find_project_root(sub_pkg) == pnpm_mono

    # 2. Root package.json with "workspaces"
    npm_mono = tmp_path / "npm_mono"
    npm_mono.mkdir()
    (npm_mono / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["apps/*"]}), encoding="utf-8"
    )
    app_pkg = npm_mono / "apps" / "client"
    app_pkg.mkdir(parents=True)
    (app_pkg / "package.json").write_text(json.dumps({"name": "client"}), encoding="utf-8")

    assert find_project_root(app_pkg) == npm_mono


def test_iss20_detect_nested_monorepo_workspaces(tmp_path):
    """Verify detect_project_fingerprint scans nested workspaces (apps, services, contracts)."""
    root = tmp_path / "fullstack_monorepo"
    root.mkdir()
    (root / ".git").mkdir()

    # 1. apps/web: Next.js + React + Tailwind + TypeScript
    web_dir = root / "apps" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "package.json").write_text(
        json.dumps({
            "name": "web",
            "dependencies": {
                "next": "14.2.0",
                "react": "18.3.0",
                "tailwindcss": "3.4.0",
            },
            "devDependencies": {
                "typescript": "5.4.0",
            },
        }),
        encoding="utf-8",
    )
    (web_dir / "tsconfig.json").write_text("{}", encoding="utf-8")

    # 2. services/api: Python + FastAPI + SQLAlchemy + Pytest
    api_dir = root / "services" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "pyproject.toml").write_text(
        "[project]\nname='api'\ndependencies=['fastapi>=0.110.0', 'sqlalchemy>=2.0', 'pytest>=8.0']\n",
        encoding="utf-8",
    )
    (api_dir / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")

    # 3. contracts: Foundry EVM Smart Contracts
    contracts_dir = root / "contracts"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (contracts_dir / "Vault.sol").write_text("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n", encoding="utf-8")

    # Run fingerprint from root
    fp = detect_project_fingerprint(root)

    # All ecosystems detected across all workspaces
    assert "nextjs" in fp.detected_ecosystems
    assert "react" in fp.detected_ecosystems
    assert "tailwind" in fp.detected_ecosystems
    assert "typescript" in fp.detected_ecosystems
    assert "fastapi" in fp.detected_ecosystems
    assert "sqlalchemy" in fp.detected_ecosystems
    assert "pytest" in fp.detected_ecosystems
    assert "python" in fp.detected_ecosystems
    assert "solidity" in fp.detected_ecosystems
    assert "foundry" in fp.detected_ecosystems
    assert "smart-contract" in fp.detected_ecosystems
    assert "full-stack" in fp.detected_ecosystems

    # Monorepo classification
    assert fp.is_fullstack is True
    assert fp.is_pure_backend is False
    assert fp.is_pure_contract is False

    # Relative manifest paths recorded
    assert any("apps/web/package.json" in m for m in fp.manifest_files)
    assert any("services/api/pyproject.toml" in m for m in fp.manifest_files)
    assert any("contracts/foundry.toml" in m for m in fp.manifest_files)

    # Comprehensive skill recommendations across frontend, blockchain, and quality
    assert "vercel-react-best-practices" in fp.recommended_skills
    assert "frontend-ui-engineering" in fp.recommended_skills
    assert "smart-contract-auditor" in fp.recommended_skills
    assert "engineering-quality-gate" in fp.recommended_skills

    assert fp.suggested_preferences["frontend.react"] == "vercel-react-best-practices"
    assert fp.suggested_preferences["frontend.engineering"] == "frontend-ui-engineering"
    assert fp.suggested_preferences["security.blockchain"] == "smart-contract-auditor"
    assert fp.suggested_preferences["verification.qa"] == "engineering-quality-gate"

    # Invoking detect_project_fingerprint from nested directory yields root monorepo fingerprint
    fp_nested = detect_project_fingerprint(web_dir)
    assert fp_nested.root == root
    assert fp_nested.is_fullstack is True


def test_iss20_manifest_files_deduplication(tmp_path):
    """Verify manifest_files in ProjectFingerprint contains no duplicate entries."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    contracts_dir = root / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (contracts_dir / "Vault.sol").write_text("// contract", encoding="utf-8")

    fp = detect_project_fingerprint(root)
    assert len(fp.manifest_files) == len(set(fp.manifest_files))


# =========================================================================
# ISS-21: Soft UI Category Suppression & Expanded Frontend Signals
# =========================================================================

def test_iss21_expanded_frontend_vocabulary():
    """Verify expanded UI_FRONTEND_SIGNALS covers view, page, dialog, card, table, etc."""
    essential_terms = {
        "view", "views", "page", "pages", "dialog", "dialogs", "tab", "tabs",
        "nav", "navbar", "navigation", "menu", "menus", "sidebar", "sidebars",
        "card", "cards", "table", "tables", "avatar", "avatars", "badge", "badges",
        "input", "inputs", "select", "selects", "checkbox", "checkboxes",
        "style", "styles", "styled", "icon", "icons", "canvas", "tooltip",
        "sheet", "drawer", "banner", "header", "footer", "button", "screen",
    }
    missing = essential_terms - UI_FRONTEND_SIGNALS
    assert not missing, f"Missing essential UI frontend signals: {missing}"

    assert "endpoint" in BACKEND_ONLY_SIGNALS
    assert "endpoints" in BACKEND_ONLY_SIGNALS


def test_iss21_polyglot_prompt_view_not_suppressed():
    """Verify 'Fix the API endpoint error state in the user profile view' does not suppress UI."""
    prompt = "Fix the API endpoint error state in the user profile view"
    words, stems = tokenize_code_aware(prompt)

    # Backend signals present: "api", "endpoint"
    assert bool(words.intersection(BACKEND_ONLY_SIGNALS))

    # UI signal present: "view"
    assert bool(words.intersection(UI_FRONTEND_SIGNALS))

    indexer = SkillIndexer([FIXTURES_DIR])
    indexer.scan()
    resolver = SkillResolver(indexer=indexer)

    res = resolver.resolve(prompt, force_route=True)
    assert not res.abstained
    selected_names = [s.name for s in res.selected_skills]
    assert len(selected_names) > 0


def test_iss21_fullstack_fingerprint_soft_suppression():
    """Verify full-stack project fingerprint prevents hard lockout of UI categories."""
    indexer = SkillIndexer([FIXTURES_DIR])
    indexer.scan()

    fullstack_fp = ProjectFingerprint(
        root=Path.cwd(),
        detected_ecosystems=["nextjs", "fastapi", "full-stack"],
        is_fullstack=True,
    )

    resolver = SkillResolver(indexer=indexer, fingerprint=fullstack_fp)

    # 1. Fullstack prompt with UI intent ("view") -> UI fully eligible
    res1 = resolver.resolve("Fix the API error state in user profile view", force_route=True)
    assert len(res1.selected_skills) > 0

    # 2. Pure backend prompt in fullstack repo ("Optimize postgresql query execution plan")
    # Soft suppression dampens UI rather than crashing or throwing false exclusions
    res2 = resolver.resolve("Optimize the database postgresql query execution plan", force_route=True)
    assert len(res2.selected_skills) > 0
    # Selected skills should be backend/qa/engineering, not aesthetic UI design
    for s in res2.selected_skills:
        assert not s.category.startswith("ui.visual")


def test_iss21_zero_score_soft_suppression_priority_guard():
    """Verify a UI skill dampened to zero relevance cannot survive on raw priority."""
    indexer = SkillIndexer([FIXTURES_DIR])
    indexer.scan()

    fullstack_fp = ProjectFingerprint(
        root=Path.cwd(),
        detected_ecosystems=["nextjs", "fastapi", "full-stack"],
        is_fullstack=True,
    )
    resolver = SkillResolver(indexer=indexer, fingerprint=fullstack_fp)

    # Prompt with purely backend signals and words that might hit generic description words
    res = resolver.resolve("Fix the postgresql database transaction deadlock bug", force_route=True)
    for s in res.selected_skills:
        assert not s.category.startswith(("frontend.", "ui."))


# =========================================================================
# ISS-22: Manifest File Mtime Cache Invalidation
# =========================================================================

def test_iss22_single_project_manifest_mtime_invalidation(tmp_path):
    """Verify editing package.json in place invalidates cache without touching directory."""
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {"react": "18.0"}}), encoding="utf-8")

    fp1 = detect_project_fingerprint(tmp_path)
    assert "react" in fp1.detected_ecosystems
    assert "vue" not in fp1.detected_ecosystems

    # Warm cache test
    fp_warm = detect_project_fingerprint(tmp_path)
    assert fp_warm is fp1

    # Edit package.json in place: switch to vue
    # Sleep 20ms to guarantee distinct mtime on NTFS/FAT filesystems
    time.sleep(0.02)
    pkg.write_text(json.dumps({"dependencies": {"vue": "3.4.0"}}), encoding="utf-8")

    # Invalidate and re-scan
    fp2 = detect_project_fingerprint(tmp_path)
    assert fp2 is not fp1
    assert "vue" in fp2.detected_ecosystems
    assert "react" not in fp2.detected_ecosystems


def test_iss22_nested_workspace_manifest_mtime_invalidation(tmp_path):
    """Verify editing nested apps/web/package.json invalidates monorepo root cache."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()

    web_pkg = root / "apps" / "web"
    web_pkg.mkdir(parents=True)
    pkg_file = web_pkg / "package.json"
    pkg_file.write_text(json.dumps({"dependencies": {"react": "18.0"}}), encoding="utf-8")

    fp1 = detect_project_fingerprint(root)
    assert "react" in fp1.detected_ecosystems
    assert "tailwind" not in fp1.detected_ecosystems

    # Warm cache hit
    assert detect_project_fingerprint(root) is fp1

    # In-place edit of nested manifest
    time.sleep(0.02)
    pkg_file.write_text(
        json.dumps({"dependencies": {"react": "18.0", "tailwindcss": "3.4.0"}}),
        encoding="utf-8",
    )

    fp2 = detect_project_fingerprint(root)
    assert fp2 is not fp1
    assert "tailwind" in fp2.detected_ecosystems
    assert "react" in fp2.detected_ecosystems


def test_iss22_contract_and_config_cache_invalidation(tmp_path):
    """Verify editing .sol contract or next.config.mjs invalidates fingerprint cache."""
    root = tmp_path / "web3_app"
    root.mkdir()
    (root / ".git").mkdir()

    contracts_dir = root / "contracts"
    contracts_dir.mkdir()
    sol_file = contracts_dir / "Vault.sol"
    sol_file.write_text("// initial contract", encoding="utf-8")

    fp1 = detect_project_fingerprint(root)
    assert "solidity" in fp1.detected_ecosystems

    # Edit Vault.sol in place
    time.sleep(0.02)
    sol_file.write_text("// updated contract", encoding="utf-8")

    fp2 = detect_project_fingerprint(root)
    assert fp2 is not fp1

    # Add next.config.mjs to root
    time.sleep(0.02)
    (root / "next.config.mjs").write_text("export default {};", encoding="utf-8")
    fp3 = detect_project_fingerprint(root)
    assert fp3 is not fp2
    assert "nextjs" in fp3.detected_ecosystems


def test_iss22_nested_workspace_new_manifest_cache_invalidation(tmp_path):
    """Verify adding a new config file inside a nested workspace directory invalidates cache via dir_tokens."""
    root = tmp_path / "nested_mono"
    root.mkdir()
    (root / ".git").mkdir()

    web_pkg = root / "apps" / "web"
    web_pkg.mkdir(parents=True)
    (web_pkg / "package.json").write_text(json.dumps({"dependencies": {"react": "18.0"}}), encoding="utf-8")

    fp1 = detect_project_fingerprint(root)
    assert "react" in fp1.detected_ecosystems
    assert "tailwind" not in fp1.detected_ecosystems

    # Warm cache hit
    assert detect_project_fingerprint(root) is fp1

    # Add tailwind.config.js inside apps/web without touching root or package.json
    time.sleep(0.02)
    (web_pkg / "tailwind.config.js").write_text("module.exports = {};", encoding="utf-8")

    fp2 = detect_project_fingerprint(root)
    assert fp2 is not fp1
    assert "tailwind" in fp2.detected_ecosystems

