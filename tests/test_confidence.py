"""Unit tests for ISS-03: Routing Confidence, Score Margins, and Abstention."""

from pathlib import Path
import pytest
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


@pytest.fixture(scope="module")
def resolver():
    idx = SkillIndexer([FIXTURES_DIR])
    idx.scan()
    return SkillResolver(idx, max_skills=3)


def test_high_confidence_resolution(resolver):
    """Clear, strong matches yield high confidence and non-abstention."""
    res = resolver.resolve("Audit this Solidity smart contract for reentrancy and flash loan exploits")
    assert not res.abstained
    assert res.confidence in ("high", "medium")
    assert res.confidence_score > 0.5
    assert len(res.selected_skills) > 0
    assert any(s.name == "smart-contract-auditor" for s in res.selected_skills)
    assert res.abstention_reason is None

    # Check to_dict() serialization
    data = res.to_dict()
    assert "confidence" in data
    assert "confidence_score" in data
    assert "margin" in data
    assert "abstained" in data
    assert "abstention_reason" in data
    assert data["abstained"] is False


def test_gate_bypass_abstention(resolver):
    """Non-engineering prompts bypassed by the gate abstain with a gate_bypassed reason."""
    res = resolver.resolve("What is the recipe for chocolate cake with strawberry frosting?")
    assert res.abstained is True
    assert res.confidence == "none"
    assert len(res.selected_skills) == 0
    assert res.abstention_reason is not None
    assert "gate_bypassed" in res.abstention_reason


def test_low_score_threshold_abstention(resolver):
    """Engineering prompts routed by gate but lacking high relevance scores abstain due to low confidence."""
    # 'optimize detection' triggers gate action verb ('optimize') but only weakly matches description
    # in performance-sre and smart-contract-auditor with scores ~2.6 < 3.0 threshold.
    res = resolver.resolve("optimize detection")
    assert res.abstained is True
    assert res.confidence == "low"
    assert len(res.selected_skills) == 0
    assert res.abstention_reason is not None
    assert "low_confidence" in res.abstention_reason


def test_abstention_bypass_flags(resolver):
    """--allow-low-confidence and --force bypass score-threshold abstention."""
    prompt = "optimize detection"

    # Should abstain normally
    normal_res = resolver.resolve(prompt)
    assert normal_res.abstained is True
    assert len(normal_res.selected_skills) == 0

    # --allow-low-confidence bypasses abstention and returns candidate skills
    bypassed_res = resolver.resolve(prompt, allow_low_confidence=True)
    assert bypassed_res.abstained is False
    assert len(bypassed_res.selected_skills) > 0
    assert bypassed_res.confidence == "low"

    # --force bypasses abstention
    forced_res = resolver.resolve(prompt, force_route=True)
    assert forced_res.abstained is False
    assert len(forced_res.selected_skills) > 0


def test_confidence_margin_calculation(resolver):
    """Margin between top-1 and top-2 candidate is accurately recorded."""
    res = resolver.resolve("optimize detection", allow_low_confidence=True, enable_triad=False)
    assert res.margin >= 0.0
    scores_desc = sorted(res.skill_scores.values(), key=lambda s: s.final_score, reverse=True)
    assert len(scores_desc) >= 2
    expected_margin = round(scores_desc[0].final_score - scores_desc[1].final_score, 2)
    assert abs(res.margin - expected_margin) < 1e-4


def test_triad_partner_scores_recorded_without_keyerror(resolver):
    """Every selected skill (including triad partners) has a valid SkillScore entry."""
    res = resolver.resolve("Audit this Solidity smart contract for reentrancy and flash loan exploits")
    assert len(res.selected_skills) > 0
    for s in res.selected_skills:
        assert s.name in res.skill_scores, f"Selected skill '{s.name}' missing from res.skill_scores"
        sc = res.skill_scores[s.name]
        assert sc.final_score > 0.0
