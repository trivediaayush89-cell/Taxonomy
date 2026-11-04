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
    """Verify that WorkbenchRequestHandler serves taste, fingerprint, skills, and resolve APIs."""
    import json
    import socketserver
    import threading
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
    user_file.write_text(json.dumps({"version": 1, "weights": {"impeccable": 1.5}}), encoding="utf-8")

    monkeypatch.setattr("taxonomy.taste.DEFAULT_USER_TASTE_PATH", user_file)
    monkeypatch.chdir(ws_dir)

    web_dir = Path(__file__).parent.parent / "src" / "taxonomy" / "web"
    handler = lambda *args, **kwargs: WorkbenchRequestHandler(*args, directory=str(web_dir), **kwargs)

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

            # 3. GET /api/skills
            req = urllib.request.urlopen(f"{base_url}/api/skills")
            assert req.status == 200
            skills_data = json.loads(req.read().decode("utf-8"))
            assert skills_data["total"] > 0
            assert "skills" in skills_data

            # 4. POST /api/resolve
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

            # 5. POST /api/taste (save workspace preferences)
            save_body = json.dumps({
                "scope": "workspace",
                "version": 1,
                "preferred_skills": {"frontend.visual": "impeccable"},
                "avoid_skills": ["unslop"],
                "weights": {"impeccable": 2.5}
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

            # 6. POST /api/fingerprint/apply
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
        finally:
            httpd.shutdown()
