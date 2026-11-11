"""Unit tests for Okapi BM25 and BM25F multi-field scoring engine."""

import math
from pathlib import Path
import pytest

from taxonomy.bm25 import BM25Index, BM25Params
from taxonomy.models import SkillMetadata


def create_mock_skill(
    name: str,
    description: str,
    category: str = "general",
    tags: list = None,
    priority: int = 50,
) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=description,
        category=category,
        tags=tags or [],
        priority=priority,
    )


def test_bm25_smoothed_idf_small_and_large_catalog():
    """Verify that smoothed Robertson-Spärck Jones IDF is strictly positive on catalogs of any size."""
    # Tiny catalog: N = 2
    s1 = create_mock_skill("react-tester", "Test react components", tags=["react", "testing"])
    s2 = create_mock_skill("solidity-auditor", "Audit smart contracts", tags=["solidity", "audit"])
    
    idx = BM25Index()
    idx.build([s1, s2])
    
    assert idx.total_docs == 2
    # Term appearing in 1 doc: n = 1, N = 2
    # (N - n + 0.5) / (n + 0.5) = (2 - 1 + 0.5) / 1.5 = 1.0 -> ln(1 + 1.0) = ln(2) ~ 0.693 + 0.5 floor = 1.193
    idf_solidity = idx.get_idf("solidity")
    assert idf_solidity > 1.0
    
    # Larger catalog: N = 50 where 1 doc has rare term, 45 docs have common term
    skills = [
        create_mock_skill(f"skill-{i}", f"Common pipeline tool {i}", tags=["pipeline", "common"])
        for i in range(49)
    ]
    skills.append(create_mock_skill("unique-crypto", "Zero knowledge cryptographic proofs", tags=["zkp", "crypto"]))
    
    idx_large = BM25Index()
    idx_large.build(skills)
    
    idf_zkp = idx_large.get_idf("zkp")
    idf_pipeline = idx_large.get_idf("pipeline")
    
    # Rare term must have significantly higher IDF than common term
    assert idf_zkp > idf_pipeline
    assert idf_zkp > 3.0
    assert idf_pipeline > 0.5  # Still non-zero and positive


def test_bm25_field_weighting_name_vs_tags_vs_desc():
    """Verify field weighting hierarchy: Name match > Tag match > Description match."""
    # s_name has 'postgres' in name
    s_name = create_mock_skill("postgres-optimizer", "Database utility", tags=["storage"])
    # s_tag has 'postgres' in tags
    s_tag = create_mock_skill("database-tuner", "Database utility", tags=["postgres"])
    # s_desc has 'postgres' only in description
    s_desc = create_mock_skill("general-helper", "Supports postgres databases", tags=["general"])
    
    idx = BM25Index()
    idx.build([s_name, s_tag, s_desc])

    from taxonomy.resolver import normalize_stem
    scores, hits = idx.score_query(
        prompt_words={"postgres"},
        prompt_stems={normalize_stem("postgres")},
        lower_prompt="postgres",
    )
    
    assert scores[s_name.name] > scores[s_tag.name], "Name match should score higher than Tag match"
    assert scores[s_tag.name] > scores[s_desc.name], "Tag match should score higher than Description match"


def test_bm25_length_normalization():
    """Verify document length normalization: bloated descriptions don't drown out concise descriptions."""
    # Concise skill
    s_concise = create_mock_skill(
        "auth-handler",
        "JWT authentication and token validation.",
        tags=["auth"],
    )
    # Verbose bloated skill that mentions JWT once in a 100-word paragraph
    verbose_desc = "This is a very long and comprehensive enterprise orchestration utility that contains numerous features across various modules and also mentions jwt once amidst extensive documentation of secondary systems."
    s_verbose = create_mock_skill(
        "enterprise-monolith",
        verbose_desc,
        tags=["orchestration"],
    )
    
    idx = BM25Index()
    idx.build([s_concise, s_verbose])
    
    scores, _ = idx.score_query(
        prompt_words={"jwt"},
        prompt_stems={"jwt"},
        lower_prompt="jwt",
    )
    
    assert scores[s_concise.name] > scores[s_verbose.name], (
        f"Concise skill ({scores[s_concise.name]:.2f}) should score higher than verbose bloated skill ({scores[s_verbose.name]:.2f})"
    )


def test_bm25_exact_name_and_compound_tag_boost():
    """Verify exact skill name match and compound tag phrase matches receive boosts."""
    s1 = create_mock_skill(
        "smart-contract-auditor",
        "Security audit for contracts",
        tags=["smart-contract", "security"],
    )
    s2 = create_mock_skill(
        "security-reviewer",
        "Security reviewer for web apps",
        tags=["security", "code-review"],
    )
    
    idx = BM25Index()
    idx.build([s1, s2])
    
    # Query with exact skill name
    scores, hits = idx.score_query(
        prompt_words={"use", "smart-contract-auditor", "now"},
        prompt_stems={"smart-contract-auditor"},
        lower_prompt="use smart-contract-auditor now",
    )
    
    # Direct name match should get massive boost (>= 8.0)
    assert scores["smart-contract-auditor"] >= 8.0
    assert scores["smart-contract-auditor"] > scores.get("security-reviewer", 0.0) + 5.0


def test_bm25_term_saturation():
    """Verify term frequency saturation via k1 (repeating a word has diminishing returns)."""
    # Skill 1 has 1 mention of 'docker'
    s1 = create_mock_skill("container-tool-1", "Deploy docker containers.", tags=["ops"])
    # Skill 2 keyword spams 'docker docker docker docker docker docker docker'
    s2 = create_mock_skill("container-tool-2", "docker docker docker docker docker docker docker", tags=["ops"])
    
    idx = BM25Index()
    idx.build([s1, s2])
    
    from taxonomy.resolver import normalize_stem
    stem_docker = normalize_stem("docker")
    scores, _ = idx.score_query(
        prompt_words={"docker"},
        prompt_stems={stem_docker},
        lower_prompt="docker",
    )
    
    # Because of k1 term saturation and length penalty, s2 score does NOT scale linearly 7x
    ratio = scores[s2.name] / max(0.1, scores[s1.name])
    assert ratio < 2.5, f"Term saturation failed: score ratio was {ratio:.2f} (expected < 2.5 due to k1 saturation)"
