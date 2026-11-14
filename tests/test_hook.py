"""Test the in-process integration hook."""

from pathlib import Path
import sys
from taxonomy.hook import dispatch_prompt, init_dispatcher

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


def test_hook_in_process_call():
    init_dispatcher([FIXTURES_DIR], max_skills=2)

    # 1. Casual greeting -> should bypass cleanly
    res1 = dispatch_prompt("Good morning, how are you?", skills_roots=[FIXTURES_DIR])
    assert not res1.gate.should_route
    assert len(res1.selected_skills) == 0

    # 2. Engineering feature request -> should route to backend
    res2 = dispatch_prompt("Add a login page with JWT authentication and refresh tokens", skills_roots=[FIXTURES_DIR])
    assert res2.gate.should_route
    assert len(res2.selected_skills) >= 1
    assert res2.selected_skills[0].name == "backend-architecture"

    # 3. Check latency under 1ms for in-process call (< 30ms conservative bound on Windows CI to account for 15.6ms OS quantum)
    bound = 30.0 if sys.platform == "win32" else 5.0
    assert res2.total_latency_ms < bound


def test_hook_fail_open_safety():
    # Pass completely non-existent directory
    bogus_path = Path("C:/definitely/not/a/real/path/to/skills")
    init_dispatcher([bogus_path])

    # Should not crash, should return fail-open empty result
    res = dispatch_prompt("Scaffold a full stack application", skills_roots=[bogus_path])
    assert isinstance(res.selected_skills, list)
