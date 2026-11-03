"""Test taxonomy doctor and self-healing --fix functionality."""

from pathlib import Path
from taxonomy.cli import cmd_doctor


class MockArgs:
    def __init__(self, skills_dir, fix=False):
        self.skills_dir = str(skills_dir)
        self.fix = fix


def test_doctor_detects_and_fixes(tmp_path):
    # Create a bare skill without category, tags, status, priority
    skill_dir = tmp_path / "my-custom-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: my-custom-skill\n"
        "description: Simple skill for testing doctor\n"
        "---\n\n"
        "# Content\nThis is untouched content.\n",
        encoding="utf-8"
    )

    # 1. Run doctor without --fix
    args_nofix = MockArgs(tmp_path, fix=False)
    cmd_doctor(args_nofix)

    # File should still have only 2 fields
    text_before = skill_md.read_text(encoding="utf-8")
    assert "category" not in text_before

    # 2. Run doctor with --fix
    args_fix = MockArgs(tmp_path, fix=True)
    cmd_doctor(args_fix)

    text_after = skill_md.read_text(encoding="utf-8")
    assert "category: general" in text_after
    assert "status: active" in text_after
    assert "priority: 50" in text_after
    assert "This is untouched content." in text_after  # Body was preserved!
