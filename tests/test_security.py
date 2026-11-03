"""Red-team tests for security containment and directory traversal protection."""

import os
from pathlib import Path
import pytest

from taxonomy.security import safe_resolve_skill_path, SecurityValidationError


def test_safe_path_valid_subfolder(tmp_path):
    sub = tmp_path / "my-skill"
    sub.mkdir()
    resolved = safe_resolve_skill_path(tmp_path, "my-skill")
    assert resolved == sub.resolve()


def test_traversal_double_dot_blocked(tmp_path):
    with pytest.raises(SecurityValidationError) as exc:
        safe_resolve_skill_path(tmp_path, "../../../Windows/System32")
    assert "Path traversal attempt blocked" in str(exc.value)


def test_traversal_absolute_escape_blocked(tmp_path):
    escape_target = "C:/Windows/System32/calc.exe" if os.name == "nt" else "/etc/passwd"
    with pytest.raises(SecurityValidationError) as exc:
        safe_resolve_skill_path(tmp_path, escape_target)
    assert "Path traversal attempt blocked" in str(exc.value)


def test_traversal_cross_platform_escape_blocked(tmp_path):
    cross_target = "/etc/shadow" if os.name == "nt" else "C:/Windows/System32/calc.exe"
    with pytest.raises(SecurityValidationError) as exc:
        safe_resolve_skill_path(tmp_path, cross_target)
    assert "Path traversal attempt blocked" in str(exc.value)


def test_null_byte_injection_blocked(tmp_path):
    with pytest.raises(SecurityValidationError) as exc:
        safe_resolve_skill_path(tmp_path, "my-skill\0/secret")
    assert "Null byte detected" in str(exc.value)
