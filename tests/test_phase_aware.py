"""Test phase-aware dispatch for development-director lifecycle stages."""

from pathlib import Path
from taxonomy.hook import dispatch_prompt, init_dispatcher

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


def test_phase_filtering():
    init_dispatcher([FIXTURES_DIR], max_skills=3)

    prompt = "Review and verify the distributed database architecture with tests and quality gates"

    # 1. Verification phase -> should select verification skills
    res_qa = dispatch_prompt(prompt, skills_roots=[FIXTURES_DIR], phase="verification")
    qa_skills = {s.name for s in res_qa.selected_skills}
    assert "engineering-quality-gate" in qa_skills
    # Implementation-only skills should not dominate
    assert "frontend-ui-engineering" not in qa_skills

    # 2. Review phase -> should prioritize independent-jury
    res_rev = dispatch_prompt(prompt, skills_roots=[FIXTURES_DIR], phase="review")
    rev_skills = {s.name for s in res_rev.selected_skills}
    assert "independent-jury" in rev_skills
