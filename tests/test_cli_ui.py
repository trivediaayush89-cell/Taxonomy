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
