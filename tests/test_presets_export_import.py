"""Comprehensive tests for Curated Presets, Taste Export/Import, and Workbench REST APIs."""

import json
from pathlib import Path
import socketserver
import threading
import urllib.request
import urllib.error
import pytest
import yaml

from taxonomy.presets import get_preset, list_presets, CURATED_PRESETS
from taxonomy.taste import (
    TasteProfile,
    clear_taste_cache,
    export_taste_profile,
    import_taste_profile,
    load_taste_file,
    save_taste_profile,
)
from taxonomy.cli import WorkbenchRequestHandler


def test_presets_registry_structure():
    """Verify that all curated presets have required metadata and valid structure."""
    presets = list_presets()
    assert len(presets) >= 5

    names = {p["name"] for p in presets}
    assert "minimalist-backend" in names
    assert "solidity-auditor" in names
    assert "design-heavy-frontend" in names
    assert "product-saas-builder" in names
    assert "strict-qa-sre" in names

    for p in presets:
        assert isinstance(p["name"], str) and p["name"]
        assert isinstance(p["title"], str) and p["title"]
        assert isinstance(p["description"], str) and p["description"]
        assert p.get("version") == 1
        assert isinstance(p.get("preferred_skills", {}), dict)
        assert isinstance(p.get("avoid_skills", []), list)
        assert isinstance(p.get("weights", {}), dict)


def test_get_preset_case_insensitivity():
    """Verify get_preset lookup with various casing and whitespace."""
    p1 = get_preset("minimalist-backend")
    assert p1 is not None
    assert p1["name"] == "minimalist-backend"

    p2 = get_preset("  SOLIDITY-AUDITOR  ")
    assert p2 is not None
    assert p2["name"] == "solidity-auditor"

    assert get_preset("non-existent-preset-xyz") is None


def test_export_taste_profile_json_and_yaml(tmp_path):
    """Verify exporting taste profiles to JSON/YAML strings and files."""
    profile = TasteProfile(
        version=1,
        preferred_skills={"frontend.visual": "impeccable", "verification.qa": "engineering-quality-gate"},
        avoid_skills=["unslop", "animate"],
        weights={"impeccable": 2.5, "engineering-quality-gate": 1.5},
    )

    # 1. Export as JSON string
    json_str = export_taste_profile(profile, as_yaml=False)
    data = json.loads(json_str)
    assert data["version"] == 1
    assert data["preferred_skills"]["frontend.visual"] == "impeccable"
    assert data["avoid_skills"] == ["animate", "unslop"]
    assert data["weights"]["impeccable"] == 2.5

    # 2. Export as YAML string
    yaml_str = export_taste_profile(profile, as_yaml=True)
    yaml_data = yaml.safe_load(yaml_str)
    assert yaml_data["version"] == 1
    assert yaml_data["preferred_skills"]["frontend.visual"] == "impeccable"
    assert yaml_data["avoid_skills"] == ["animate", "unslop"]
    assert yaml_data["weights"]["impeccable"] == 2.5

    # 3. Export to JSON file
    json_file = tmp_path / "exported.json"
    export_taste_profile(profile, target_path=json_file)
    assert json_file.exists()
    assert json.loads(json_file.read_text(encoding="utf-8")) == data

    # 4. Export to YAML file (inferred by extension)
    yaml_file = tmp_path / "exported.yaml"
    export_taste_profile(profile, target_path=yaml_file)
    assert yaml_file.exists()
    assert yaml.safe_load(yaml_file.read_text(encoding="utf-8")) == yaml_data


def test_import_from_preset_slug(tmp_path):
    """Verify importing directly from a curated community preset name."""
    target_path = tmp_path / "imported_preset.json"
    profile, saved_path = import_taste_profile("minimalist-backend", target_path=target_path)

    assert saved_path == target_path
    assert target_path.exists()
    assert profile.preferred_skills["backend.api"] == "backend-architecture"
    assert "design-taste-frontend" in profile.avoid_skills
    assert profile.weights["engineering-quality-gate"] == 2.5


def test_import_from_file_json_and_yaml(tmp_path):
    """Verify importing taste profiles from files (JSON and YAML)."""
    # JSON source
    json_src = tmp_path / "source.json"
    json_src.write_text(
        json.dumps({
            "version": 1,
            "preferred_skills": {"orchestration.lead": "development-director"},
            "avoid_skills": ["animate"],
            "weights": {"development-director": 2.0},
        }),
        encoding="utf-8"
    )

    target = tmp_path / "active_taste.json"
    profile, saved = import_taste_profile(json_src, target_path=target)
    assert saved == target
    assert profile.preferred_skills["orchestration.lead"] == "development-director"

    # Overwrite protection without force
    with pytest.raises(FileExistsError):
        import_taste_profile(json_src, target_path=target, force=False)

    # Overwrite allowed with force=True
    yaml_src = tmp_path / "source.yaml"
    yaml_src.write_text(
        yaml.safe_dump({
            "version": 1,
            "preferred_skills": {"frontend.visual": "design-taste-frontend"},
            "avoid_skills": [],
            "weights": {"design-taste-frontend": 3.0},
        }),
        encoding="utf-8"
    )

    profile2, saved2 = import_taste_profile(yaml_src, target_path=target, force=True)
    assert profile2.preferred_skills["frontend.visual"] == "design-taste-frontend"


def test_quality_sentry_immunity_on_import(tmp_path):
    """Judicial Invariant Verification: Quality Sentries can NEVER be downvoted or avoided on import."""
    from taxonomy.models import SkillMetadata

    untrusted_payload = {
        "version": 1,
        "preferred_skills": {
            "security.blockchain": "smart-contract-auditor",
            "ui.framework": "vercel-react-best-practices",
            "ui.animation": "emil-design-eng",
        },
        "avoid_skills": ["engineering-quality-gate", "independent-jury", "unslop"],
        "weights": {
            "engineering-quality-gate": -3.0,  # Malicious downvote on QA sentry
            "independent-jury": -2.5,          # Malicious downvote on review sentry
            "unslop": -2.0,
        }
    }

    target = tmp_path / "sanitized_taste.json"
    profile, saved = import_taste_profile(untrusted_payload, target_path=target)

    # Sentries must be stripped from avoid_skills
    assert "engineering-quality-gate" not in profile.avoid_skills
    assert "independent-jury" not in profile.avoid_skills
    assert "unslop" in profile.avoid_skills

    # Sentry negative weights must be clamped to 0.0
    assert profile.weights["engineering-quality-gate"] == 0.0
    assert profile.weights["independent-jury"] == 0.0
    assert profile.weights["unslop"] == -2.0

    # Verify ui.framework and ui.animation category aliases match their respective skills
    react_skill = SkillMetadata(name="vercel-react-best-practices", description="React", category="frontend.react")
    emil_skill = SkillMetadata(name="emil-design-eng", description="Polish", category="ui.polish")
    assert profile.get_bias(react_skill) == 3.0
    assert profile.get_bias(emil_skill) == 3.0


def test_import_invalid_source_raises():
    """Verify that unparseable or schema-violating profiles raise ValueError."""
    with pytest.raises(ValueError, match="Could not import taste profile"):
        import_taste_profile("plain string without yaml mapping")

    with pytest.raises(ValueError, match="Invalid taste profile schema"):
        import_taste_profile({"version": "not-an-integer"})


def test_cli_presets_export_import_commands(tmp_path, capsys, monkeypatch):
    """Verify CLI subcommands: cmd_taste_presets, cmd_taste_export, cmd_taste_import."""
    from taxonomy.cli import cmd_taste_presets, cmd_taste_export, cmd_taste_import

    ws_file = tmp_path / "ws_taste.json"
    user_file = tmp_path / "user_taste.json"

    monkeypatch.setattr("taxonomy.taste.find_workspace_taste_path", lambda root=None: ws_file)
    monkeypatch.setattr("taxonomy.taste.get_workspace_taste_path", lambda root=None: ws_file)
    monkeypatch.setattr("taxonomy.taste.get_user_taste_path", lambda: user_file)

    clear_taste_cache()

    # 1. presets command
    cmd_taste_presets(None)
    captured = capsys.readouterr()
    assert "CURATED COMMUNITY TASTE PRESETS" in captured.out
    assert "minimalist-backend" in captured.out
    assert "solidity-auditor" in captured.out

    # 2. import command (imports solidity-auditor into workspace)
    class ImportArgs:
        source = "solidity-auditor"
        workspace = True
        user = False
        force = True

    cmd_taste_import(ImportArgs())
    captured = capsys.readouterr()
    assert "[Taste Imported]" in captured.out
    assert "solidity-auditor" in captured.out
    assert ws_file.exists()

    # 3. export command (JSON to stdout)
    class ExportArgsJSON:
        workspace = True
        user = False
        yaml = False
        file = None

    cmd_taste_export(ExportArgsJSON())
    captured = capsys.readouterr()
    assert '"smart-contract-auditor"' in captured.out

    # 4. export command (YAML to file)
    yaml_out = tmp_path / "exported_cli.yaml"
    class ExportArgsYAML:
        workspace = True
        user = False
        yaml = True
        file = str(yaml_out)

    cmd_taste_export(ExportArgsYAML())
    captured = capsys.readouterr()
    assert "[Exported]" in captured.out
    assert yaml_out.exists()
    assert "smart-contract-auditor" in yaml_out.read_text(encoding="utf-8")


def test_workbench_presets_and_export_import_api(tmp_path, monkeypatch):
    """Verify REST API endpoints: GET /api/presets, POST /api/presets/apply, GET /api/taste/export, POST /api/taste/import."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / ".git").mkdir()
    user_file = tmp_path / "user_taste.json"

    monkeypatch.setattr("taxonomy.taste.find_workspace_taste_path", lambda root=None: ws_dir / ".taxonomy" / "taste.json")
    monkeypatch.setattr("taxonomy.taste.get_workspace_taste_path", lambda root=None: ws_dir / ".taxonomy" / "taste.json")
    monkeypatch.setattr("taxonomy.taste.get_user_taste_path", lambda: user_file)

    clear_taste_cache()

    server = socketserver.TCPServer(("127.0.0.1", 0), WorkbenchRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/presets
        with urllib.request.urlopen(f"{base_url}/api/presets") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "presets" in data
            assert len(data["presets"]) >= 5
            names = [p["name"] for p in data["presets"]]
            assert "solidity-auditor" in names

        # 2. POST /api/presets/apply (workspace scope)
        apply_req = urllib.request.Request(
            f"{base_url}/api/presets/apply",
            data=json.dumps({"name": "solidity-auditor", "scope": "workspace"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(apply_req) as resp:
            assert resp.status == 200
            apply_res = json.loads(resp.read().decode("utf-8"))
            assert apply_res["status"] == "ok"
            assert apply_res["preset"] == "solidity-auditor"
            assert apply_res["profile"]["preferred_skills"]["security.blockchain"] == "smart-contract-auditor"

        # 3. GET /api/taste/export?scope=workspace&format=yaml
        with urllib.request.urlopen(f"{base_url}/api/taste/export?scope=workspace&format=yaml") as resp:
            assert resp.status == 200
            export_res = json.loads(resp.read().decode("utf-8"))
            assert export_res["format"] == "yaml"
            parsed_yaml = yaml.safe_load(export_res["content"])
            assert parsed_yaml["preferred_skills"]["security.blockchain"] == "smart-contract-auditor"

        # 4. POST /api/taste/import (raw JSON content)
        custom_import = {
            "version": 1,
            "preferred_skills": {"frontend.visual": "impeccable"},
            "avoid_skills": ["unslop"],
            "weights": {"impeccable": 3.0}
        }
        import_req = urllib.request.Request(
            f"{base_url}/api/taste/import",
            data=json.dumps({"content": json.dumps(custom_import), "scope": "workspace", "force": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(import_req) as resp:
            assert resp.status == 200
            import_res = json.loads(resp.read().decode("utf-8"))
            assert import_res["status"] == "ok"
            assert import_res["profile"]["preferred_skills"]["frontend.visual"] == "impeccable"

    finally:
        server.shutdown()
        server.server_close()
