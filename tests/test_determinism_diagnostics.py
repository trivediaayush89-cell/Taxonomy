"""Tests for Determinism & Reproducibility Diagnostics (ISS-31).

Validates:
- Catalog hashing: SHA-256 digest of active skill catalog state.
- Taste hashing: SHA-256 digest of user/workspace preference state.
- Config hashing: SHA-256 digest of resolver configuration state.
- ResolutionResult integration: hashes present on both routed and bypassed decisions.
- Cross-instance reproducibility: identical configurations yield bit-for-bit identical hashes and rankings.
"""

from pathlib import Path
import pytest

from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata
from taxonomy.resolver import SkillResolver
from taxonomy.taste import TasteProfile


def test_catalog_hash_deterministic(tmp_path):
    # Setup test skill
    skill_dir = tmp_path / "skill-a"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: Test skill A\ncategory: backend.api\ntags: [api, rest]\npriority: 80\n---\n",
        encoding="utf-8",
    )

    indexer1 = SkillIndexer([tmp_path])
    indexer1.scan()
    hash1 = indexer1.compute_catalog_hash()
    assert len(hash1) == 16

    indexer2 = SkillIndexer([tmp_path])
    indexer2.scan()
    hash2 = indexer2.compute_catalog_hash()
    assert hash1 == hash2

    # Adding a new skill changes the catalog hash
    skill_b = tmp_path / "skill-b"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: Test skill B\ncategory: ui.frontend\ntags: [ui]\npriority: 70\n---\n",
        encoding="utf-8",
    )
    indexer1.scan()
    hash3 = indexer1.compute_catalog_hash()
    assert hash3 != hash1


def test_taste_hash_deterministic():
    t1 = TasteProfile(
        preferred_skills={"frontend.visual": "impeccable"},
        avoid_skills=["unslop"],
        weights={"animate": 2.0},
    )
    t2 = TasteProfile(
        preferred_skills={"frontend.visual": "impeccable"},
        avoid_skills=["unslop"],
        weights={"animate": 2.0},
    )
    assert t1.compute_hash() == t2.compute_hash()
    assert len(t1.compute_hash()) == 16

    # Empty taste profile
    t_empty = TasteProfile()
    assert t_empty.compute_hash() == "empty_taste_0000"

    # Modifying weights changes taste hash
    t3 = TasteProfile(
        preferred_skills={"frontend.visual": "impeccable"},
        avoid_skills=["unslop"],
        weights={"animate": 1.5},
    )
    assert t3.compute_hash() != t1.compute_hash()


def test_config_hash_deterministic(tmp_path):
    skill_dir = tmp_path / "s1"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: s1\ndescription: Skill one\ncategory: backend.api\ntags: [api]\npriority: 80\n---\n",
        encoding="utf-8",
    )
    indexer = SkillIndexer([tmp_path])
    indexer.scan()

    taste1 = TasteProfile(weights={"s1": 1.0})
    r1 = SkillResolver(indexer, taste_profile=taste1, max_skills=3, enable_triad=True)
    r2 = SkillResolver(indexer, taste_profile=taste1, max_skills=3, enable_triad=True)

    cfg_h1 = r1.compute_config_hash()
    cfg_h2 = r2.compute_config_hash()
    assert cfg_h1 == cfg_h2
    assert len(cfg_h1) == 16

    # Changing max_skills changes config hash
    r3 = SkillResolver(indexer, taste_profile=taste1, max_skills=5, enable_triad=True)
    assert r3.compute_config_hash() != cfg_h1

    # Changing phase in query changes config hash
    assert r1.compute_config_hash(phase="implementation") != cfg_h1

    # Overriding sentries changes config hash
    assert r1.compute_config_hash(allow_sentry_override=True) != cfg_h1


def test_resolution_result_contains_hashes(tmp_path):
    skill_dir = tmp_path / "api-worker"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: api-worker\ndescription: Backend API worker\ncategory: backend.api\ntags: [api, server]\npriority: 80\n---\n",
        encoding="utf-8",
    )
    indexer = SkillIndexer([tmp_path])
    indexer.scan()
    resolver = SkillResolver(indexer)

    # 1. Routed resolution
    res_routed = resolver.resolve("implement a REST API worker endpoint", force_route=True)
    assert res_routed.catalog_hash is not None
    assert len(res_routed.catalog_hash) == 16
    assert res_routed.config_hash is not None
    assert len(res_routed.config_hash) == 16

    # Dictionary serialization check
    d = res_routed.to_dict()
    assert "catalog_hash" in d
    assert "config_hash" in d
    assert d["catalog_hash"] == res_routed.catalog_hash
    assert d["config_hash"] == res_routed.config_hash

    # 2. Gate-bypassed resolution (casual prompt)
    res_bypassed = resolver.resolve("hello how are you")
    assert res_bypassed.abstained is True
    assert res_bypassed.catalog_hash is not None
    assert res_bypassed.config_hash is not None


def test_cross_instance_reproducibility(tmp_path):
    """Verify that independent resolver instances yield identical hashes and rankings."""
    for i in range(3):
        d = tmp_path / f"service-{i}"
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: service-{i}\ndescription: Microservice module {i}\ncategory: backend.api\ntags: [api, service]\npriority: {80 + i}\n---\n",
            encoding="utf-8",
        )

    prompt = "Create a new microservice endpoint with tests"

    # Instance 1
    idx1 = SkillIndexer([tmp_path])
    idx1.scan()
    res1 = SkillResolver(idx1, max_skills=3).resolve(prompt, force_route=True)

    # Instance 2 (completely separate process simulation)
    idx2 = SkillIndexer([tmp_path])
    idx2.scan()
    res2 = SkillResolver(idx2, max_skills=3).resolve(prompt, force_route=True)

    assert res1.catalog_hash == res2.catalog_hash
    assert res1.config_hash == res2.config_hash
    assert [s.name for s in res1.selected_skills] == [s.name for s in res2.selected_skills]
    assert res1.confidence == res2.confidence
    assert res1.confidence_score == res2.confidence_score


def test_no_matching_skills_still_returns_hashes(tmp_path):
    """Verify that when no skills match (empty catalog or phase filter), hashes are still populated."""
    idx = SkillIndexer([tmp_path])
    idx.scan()
    resolver = SkillResolver(idx)
    res = resolver.resolve("implement a REST API worker endpoint", force_route=True)
    assert res.abstained is True
    assert res.abstention_reason == "no_matching_skills"
    assert res.catalog_hash == "empty_catalog000"
    assert res.config_hash is not None
    assert len(res.config_hash) == 16

