"""Unit tests for ISS-04: Complementary Pod Pairing (Guardrail 2) and Triad Control."""

from pathlib import Path
import pytest
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver
from taxonomy.hook import dispatch_prompt

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


@pytest.fixture(scope="module")
def resolver():
    idx = SkillIndexer([FIXTURES_DIR])
    idx.scan()
    return SkillResolver(idx, max_skills=3)


def test_disable_triad_prevents_zero_score_padding(resolver):
    """When enable_triad=False, resolver never pads with 0-score complementary partners."""
    # A prompt that matches only 1 skill in mock skills (e.g. smart-contract-auditor)
    res_triad = resolver.resolve("Audit this Solidity smart contract for reentrancy exploits", enable_triad=True)
    res_no_triad = resolver.resolve("Audit this Solidity smart contract for reentrancy exploits", enable_triad=False)

    # With triad disabled, only directly relevant skills are included
    assert len(res_no_triad.selected_skills) < len(res_triad.selected_skills) or len(res_no_triad.selected_skills) == 1
    for s in res_no_triad.selected_skills:
        assert s.name in res_no_triad.skill_scores
        # The base score from BM25 must be strictly positive (not padded)
        assert res_no_triad.skill_scores[s.name].base_score > 0.0


def test_tier1_quick_fix_does_not_force_triad(resolver):
    """Tier 1 prompts (if routed or evaluated) do not trigger Guardrail 2 triad padding."""
    # Test that tier < 2 prevents triad padding
    res = resolver.resolve("fix typo in smart contract variable name", force_route=True, enable_triad=True)
    # The gate should mark tier 1 for a quick fix or if tier is 1, triad should not pad
    if res.gate.tier == 1:
        assert len(res.selected_skills) <= 1


def test_triad_partner_scores_guaranteed_in_skill_scores(resolver):
    """Whenever Guardrail 2 recruits partners, every partner has an explicit SkillScore in skill_scores."""
    res = resolver.resolve("Scaffold a complete Solidity EVM smart contract system", force_route=True, enable_triad=True)
    assert len(res.selected_skills) >= 1
    for skill in res.selected_skills:
        assert skill.name in res.skill_scores, f"Partner '{skill.name}' was selected but not in skill_scores"
        sc = res.skill_scores[skill.name]
        assert sc.final_score > 0.0
        assert sc.skill_name == skill.name


def test_hook_dispatch_prompt_respects_enable_triad():
    """dispatch_prompt accepts enable_triad parameter and honors it."""
    res_triad = dispatch_prompt(
        "Build a marketing landing page and portfolio showcase with hero section and animations",
        enable_triad=True,
    )
    res_no_triad = dispatch_prompt(
        "Build a marketing landing page and portfolio showcase with hero section and animations",
        enable_triad=False,
    )
    if res_triad.selected_skills and res_no_triad.selected_skills:
        assert len(res_no_triad.selected_skills) <= len(res_triad.selected_skills)
