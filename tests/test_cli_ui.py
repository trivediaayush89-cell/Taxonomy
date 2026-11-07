"""Tests for taxonomy ui CLI command."""

from pathlib import Path
from unittest.mock import patch
import pytest

from taxonomy.cli import cmd_ui


def test_cmd_ui_handles_missing_assets(tmp_path, capsys):
    class Args:
        port = 9999
        no_open = True

    with patch("taxonomy.cli.Path") as mock_path:
        # Simulate missing index.html
        fake_file = tmp_path / "fake_file.py"
        mock_path.return_value.parent = tmp_path
        cmd_ui(Args())
        captured = capsys.readouterr()
        assert "[ERROR] UI assets not found" in captured.out or "[ERROR] Could not start server" in captured.out or "" == captured.out


def test_ui_index_html_exists():
    pkg_web = Path(__file__).parent.parent / "src" / "taxonomy" / "web" / "index.html"
    assert pkg_web.exists(), "src/taxonomy/web/index.html must exist"
    assert pkg_web.stat().st_size > 1000, "src/taxonomy/web/index.html must contain UI markup"


def test_workbench_api_endpoints(tmp_path, monkeypatch):
    """Verify that WorkbenchRequestHandler serves taste, fingerprint, skills, presets, efficacy, and resolve APIs."""
    import json
    import socketserver
    import threading
    import urllib.error
    import urllib.request
    from taxonomy.cli import WorkbenchRequestHandler

    # Isolate user and workspace paths in tmp_path
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / ".git").mkdir()
    (ws_dir / "package.json").write_text(
        json.dumps({
            "dependencies": {"next": "14.0", "react": "18.0"},
            "devDependencies": {"typescript": "5.0"}
        }),
        encoding="utf-8"
    )
    (ws_dir / "tsconfig.json").write_text("{}", encoding="utf-8")

    user_file = tmp_path / "user_taste.json"
    user_file.write_text(json.dumps({"version": 1, "weights": {"frontend-ui-engineering": 1.5}}), encoding="utf-8")

    monkeypatch.setattr("taxonomy.taste.DEFAULT_USER_TASTE_PATH", user_file)
    monkeypatch.chdir(ws_dir)

    web_dir = Path(__file__).parent.parent / "src" / "taxonomy" / "web"
    mock_skills_dir = Path(__file__).parent / "fixtures" / "mock_skills"
    handler = lambda *args, **kwargs: WorkbenchRequestHandler(
        *args, directory=str(web_dir), skills_dir=str(mock_skills_dir), **kwargs
    )

    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. GET /api/fingerprint
            req = urllib.request.urlopen(f"{base_url}/api/fingerprint")
            assert req.status == 200
            fp_data = json.loads(req.read().decode("utf-8"))
            assert "nextjs" in fp_data["detected_ecosystems"]
            assert fp_data["primary_language"] in ("typescript", "typescript/javascript")

            # 2. GET /api/taste
            req = urllib.request.urlopen(f"{base_url}/api/taste")
            assert req.status == 200
            taste_data = json.loads(req.read().decode("utf-8"))
            assert "active" in taste_data
            assert "fingerprint" in taste_data

            # 3. GET /api/presets
            req = urllib.request.urlopen(f"{base_url}/api/presets")
            assert req.status == 200
            presets_data = json.loads(req.read().decode("utf-8"))
            assert presets_data["total"] >= 5
            assert any(p["name"] == "product-saas-builder" for p in presets_data["presets"])

            # 4. GET /api/skills (hermetically isolated via mock_skills)
            req = urllib.request.urlopen(f"{base_url}/api/skills")
            assert req.status == 200
            skills_data = json.loads(req.read().decode("utf-8"))
            assert skills_data["total"] > 0
            assert "frontend-ui-engineering" in skills_data["skills"]

            # 5. GET /api/efficacy
            req = urllib.request.urlopen(f"{base_url}/api/efficacy")
            assert req.status == 200
            eff_data = json.loads(req.read().decode("utf-8"))
            assert "leaderboard" in eff_data
            assert "summary" in eff_data

            # 6. POST /api/resolve
            resolve_body = json.dumps({"prompt": "Build a React component dashboard"}).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/resolve",
                data=resolve_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req)
            assert resp.status == 200
            res_data = json.loads(resp.read().decode("utf-8"))
            assert len(res_data["selected_skills"]) > 0
            assert res_data["total_latency_ms"] >= 0.0

            # 7. POST /api/taste (save workspace preferences)
            save_body = json.dumps({
                "scope": "workspace",
                "version": 1,
                "preferred_skills": {"frontend.visual": "design-taste-frontend"},
                "avoid_skills": ["backend-architecture"],
                "weights": {"frontend-ui-engineering": 2.5}
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/taste",
                data=save_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req)
            assert resp.status == 200
            save_res = json.loads(resp.read().decode("utf-8"))
            assert save_res["status"] == "ok"
            assert save_res["scope"] == "workspace"
            assert (ws_dir / ".taxonomy" / "taste.json").is_file()

            # 8. POST /api/presets/apply
            apply_preset_body = json.dumps({"name": "product-saas-builder", "scope": "workspace"}).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/api/presets/apply",
                data=apply_preset_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req)
            assert resp.status == 200
            apply_preset_res = json.loads(resp.read().decode("utf-8"))
            assert apply_preset_res["status"] == "ok"

            # 9. GET /api/taste/export
            req = urllib.request.urlopen(f"{base_url}/api/taste/export?scope=workspace&format=json")
            assert req.status == 200
            export_data = json.loads(req.read().decode("utf-8"))
            assert "content" in export_data

            # 10. POST /api/fingerprint/apply
            req = urllib.request.Request(
                f"{base_url}/api/fingerprint/apply",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req)
            assert resp.status == 200
            apply_res = json.loads(resp.read().decode("utf-8"))
            assert apply_res["status"] == "ok"

            # 11. Malformed JSON handling returns HTTP 400
            malformed_req = urllib.request.Request(
                f"{base_url}/api/resolve",
                data=b"not-json-content",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(malformed_req)
            assert exc_info.value.code == 400
        finally:
            httpd.shutdown()
