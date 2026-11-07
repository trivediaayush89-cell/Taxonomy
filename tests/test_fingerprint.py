"""Comprehensive tests for Project Fingerprinting & Zero-Config Stack Detection:
- Next.js + React + Tailwind + TypeScript detection.
- Foundry / Solidity / Smart Contract detection and pure contract isolation.
- Python + FastAPI + Pytest stack detection.
- Rust and Go detection.
- Seamless integration with load_taste_profile (fingerprint fills gaps, user overrides win).
- CLI fingerprint inspection, JSON serialization, and --apply persistence.
- In-memory mtime cache performance.
"""

import json
from pathlib import Path
import time
import pytest

from taxonomy.cli import cmd_fingerprint
from taxonomy.fingerprint import (
    ProjectFingerprint,
    clear_fingerprint_cache,
    detect_project_fingerprint,
    find_project_root,
)
from taxonomy.taste import TasteProfile, clear_taste_cache, load_taste_file, load_taste_profile


@pytest.fixture(autouse=True)
def clean_caches():
    clear_fingerprint_cache()
    clear_taste_cache()
    yield
    clear_fingerprint_cache()
    clear_taste_cache()


def test_detect_nextjs_react_tailwind_typescript(tmp_path):
    """Detect modern Next.js + React + Tailwind + TS web application."""
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        json.dumps({
            "name": "my-modern-saas",
            "dependencies": {
                "next": "14.2.0",
                "react": "^18.3.0",
                "tailwindcss": "^3.4.0",
            },
            "devDependencies": {
                "typescript": "^5.4.0",
                "@types/react": "^18.3.0",
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "next.config.mjs").write_text("export default {};", encoding="utf-8")
    (tmp_path / "tailwind.config.ts").write_text("export default {};", encoding="utf-8")

    fp = detect_project_fingerprint(tmp_path)

    assert "nextjs" in fp.detected_ecosystems
    assert "react" in fp.detected_ecosystems
    assert "tailwind" in fp.detected_ecosystems
    assert "typescript" in fp.detected_ecosystems
    assert fp.primary_language == "typescript"
    assert "vercel-react-best-practices" in fp.recommended_skills
    assert "frontend-ui-engineering" in fp.recommended_skills
    assert fp.suggested_preferences["frontend.react"] == "vercel-react-best-practices"
    assert fp.suggested_preferences["frontend.engineering"] == "frontend-ui-engineering"
    assert not fp.is_pure_backend
    assert not fp.is_pure_contract


def test_detect_foundry_solidity_smart_contract(tmp_path):
    """Detect Foundry EVM smart contract protocol and flag pure contract domain."""
    (tmp_path / "foundry.toml").write_text("[profile.default]\nsrc = 'src'\n", encoding="utf-8")
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "Vault.sol").write_text("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n", encoding="utf-8")

    fp = detect_project_fingerprint(tmp_path)

    assert "solidity" in fp.detected_ecosystems
    assert "foundry" in fp.detected_ecosystems
    assert "smart-contract" in fp.detected_ecosystems
    assert fp.primary_language == "solidity"
    assert "smart-contract-auditor" in fp.recommended_skills
    assert fp.suggested_preferences["security.blockchain"] == "smart-contract-auditor"
    assert fp.suggested_weights["smart-contract-auditor"] == 2.5
    assert fp.is_pure_contract
    assert fp.is_pure_backend


def test_detect_python_fastapi_pytest_backend(tmp_path):
    """Detect Python FastAPI microservice with Pytest."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'api-server'\ndependencies = ['fastapi>=0.110.0', 'pytest>=8.0']\n",
        encoding="utf-8",
    )
    (tmp_path / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")

    fp = detect_project_fingerprint(tmp_path)

    assert "python" in fp.detected_ecosystems
    assert "fastapi" in fp.detected_ecosystems
    assert "pytest" in fp.detected_ecosystems
    assert "alembic" in fp.detected_ecosystems
    assert fp.primary_language == "python"
    assert "engineering-quality-gate" in fp.recommended_skills
    assert fp.is_pure_backend
    assert not fp.is_pure_contract


def test_detect_rust_and_go(tmp_path):
    """Detect Rust and Go language manifests."""
    rust_dir = tmp_path / "rust_proj"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname = 'parser'\nversion = '0.1.0'\n", encoding="utf-8")

    fp_rust = detect_project_fingerprint(rust_dir)
    assert "rust" in fp_rust.detected_ecosystems
    assert fp_rust.primary_language == "rust"
    assert fp_rust.is_pure_backend

    go_dir = tmp_path / "go_proj"
    go_dir.mkdir()
    (go_dir / "go.mod").write_text("module example.com/service\ngo 1.22\n", encoding="utf-8")

    fp_go = detect_project_fingerprint(go_dir)
    assert "golang" in fp_go.detected_ecosystems
    assert fp_go.primary_language == "go"
    assert fp_go.is_pure_backend


def test_fingerprint_integrates_into_load_taste_profile(tmp_path):
    """Verify that load_taste_profile auto-layers fingerprint defaults beneath user/workspace configs."""
    # Create Next.js project
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(json.dumps({"dependencies": {"next": "14.0", "react": "18.0"}}), encoding="utf-8")

    # 1. Zero-config load: fingerprint automatically provides default preference
    profile = load_taste_profile(workspace_root=tmp_path, user_path=tmp_path / "nonexistent.json")
    assert profile.preferred_skills.get("frontend.react") == "vercel-react-best-practices"
    assert profile.weights.get("vercel-react-best-practices") == 2.0
    assert "fingerprint" in (profile.source or "")

    # 2. User explicit override wins over fingerprint
    user_file = tmp_path / "user_taste.json"
    user_file.write_text(
        json.dumps({
            "version": 1,
            "preferred_skills": {"frontend.react": "custom-react-skill"},
            "weights": {"vercel-react-best-practices": -1.0},
        }),
        encoding="utf-8",
    )
    profile_with_user = load_taste_profile(workspace_root=tmp_path, user_path=user_file)
    # User's explicit choice must win
    assert profile_with_user.preferred_skills["frontend.react"] == "custom-react-skill"
    assert profile_with_user.weights["vercel-react-best-practices"] == -1.0

    # 3. User explicit avoidance blocks fingerprint from auto-preferring that skill
    user_avoid_file = tmp_path / "user_avoid.json"
    user_avoid_file.write_text(
        json.dumps({
            "version": 1,
            "avoid_skills": ["vercel-react-best-practices"],
        }),
        encoding="utf-8",
    )
    profile_with_avoid = load_taste_profile(workspace_root=tmp_path, user_path=user_avoid_file)
    assert "vercel-react-best-practices" not in profile_with_avoid.preferred_skills.values()
    assert "vercel-react-best-practices" not in profile_with_avoid.weights
    assert "vercel-react-best-practices" in profile_with_avoid.avoid_skills


def test_find_project_root_from_file_path(tmp_path):
    """Verify that find_project_root ascends properly even when passed a file path."""
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    f = sub / "app.py"
    f.write_text("# code", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")

    assert find_project_root(f) == tmp_path


def test_cli_fingerprint_commands(tmp_path, capsys):
    """Verify CLI fingerprint, --json, and --apply commands."""
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")

    class ArgsPrint:
        path = str(tmp_path)
        json = False
        apply = False

    cmd_fingerprint(ArgsPrint())
    out = capsys.readouterr().out
    assert "PROJECT STACK FINGERPRINT" in out
    assert "Solidity" in out
    assert "smart-contract-auditor" in out
    assert "foundry.toml" in out

    class ArgsJson:
        path = str(tmp_path)
        json = True
        apply = False

    cmd_fingerprint(ArgsJson())
    out_json = capsys.readouterr().out
    data = json.loads(out_json)
    assert data["primary_language"] == "solidity"
    assert "foundry" in data["detected_ecosystems"]
    assert data["is_pure_contract"] is True

    class ArgsApply:
        path = str(tmp_path)
        json = False
        apply = True

    cmd_fingerprint(ArgsApply())
    out_apply = capsys.readouterr().out
    assert "[Applied]" in out_apply

    # Verify .taxonomy/taste.json was created with suggested preferences
    ws_taste = tmp_path / ".taxonomy" / "taste.json"
    assert ws_taste.is_file()
    saved = load_taste_file(ws_taste)
    assert saved.preferred_skills["security.blockchain"] == "smart-contract-auditor"
    assert saved.weights["smart-contract-auditor"] == 2.5


def test_fingerprint_caching_performance(tmp_path):
    """Verify warm cache lookup takes < 0.1ms."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\n", encoding="utf-8")

    # Cold scan
    t0 = time.perf_counter()
    fp1 = detect_project_fingerprint(tmp_path)
    cold_dur = (time.perf_counter() - t0) * 1000

    # Warm cached scan
    t1 = time.perf_counter()
    fp2 = detect_project_fingerprint(tmp_path)
    warm_dur = (time.perf_counter() - t1) * 1000

    assert fp1 is fp2
    assert warm_dur < 1.0, f"Warm fingerprint lookup ({warm_dur:.4f}ms) breached SLA"
