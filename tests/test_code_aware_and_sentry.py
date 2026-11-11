"""Tests for Code-Aware Tokenization, Stemmer Protection, and Extensible Sentry Registry.

Validates:
- ISS-08: Code-aware tokenization (camelCase, snake_case, dotted frameworks, hyphenated standards).
- ISS-08: Protected technical vocabulary stemming (postgres, redis, docker, express, flutter).
- ISS-09: Decoupled paths and extensible registry (TAXONOMY_HOME, stack alignments).
- ISS-10: Centralized Quality Sentry registry with configurable override policy.
"""

import os
from pathlib import Path
import pytest

from taxonomy.resolver import (
    SkillResolver,
    normalize_stem,
    tokenize_code_aware,
    PROTECTED_TECH_TERMS,
)
from taxonomy.registry import (
    get_taxonomy_home,
    get_default_taste_path,
    get_protected_sentries,
    is_protected_sentry,
    register_protected_sentry,
    unregister_protected_sentry,
    reset_protected_sentries,
    get_stack_alignments,
    register_stack_alignment,
)
from taxonomy.taste import TasteProfile
from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata


def test_code_aware_tokenization_camel_and_snake():
    words, stems = tokenize_code_aware("Fix the handleButtonClick hook in format_currency_input")
    # camelCase splits
    assert "handlebuttonclick" in words
    assert "handle" in words
    assert "button" in words
    assert "click" in words
    # snake_case splits
    assert "format" in words
    assert "currency" in words
    assert "input" in words


def test_code_aware_tokenization_dotted_and_standards():
    words, stems = tokenize_code_aware("Upgrade next.js application with erc-20 contract tokens")
    # Dotted framework
    assert "nextjs" in words
    assert "next" in words
    assert "js" in words
    # Hyphenated standard
    assert "erc20" in words
    assert "erc" in words
    assert "20" in words


def test_code_aware_tokenization_error_symbols():
    words, stems = tokenize_code_aware("Encountered ERR_PNPM_OUT_OF_DATE during compile")
    assert "pnpm" in words
    assert "date" in words
    assert "compile" in words


def test_stemmer_protection_for_tech_terms():
    # Terms that standard naive suffix strippers mangle
    assert normalize_stem("postgres") == "postgres"
    assert normalize_stem("redis") == "redis"
    assert normalize_stem("docker") == "docker"
    assert normalize_stem("kubernetes") == "kubernetes"
    assert normalize_stem("express") == "express"
    assert normalize_stem("flutter") == "flutter"
    assert normalize_stem("server") == "server"
    assert normalize_stem("nextjs") == "nextjs"
    assert normalize_stem("solidity") == "solidity"
    assert normalize_stem("fastapi") == "fastapi"


def test_registry_taxonomy_home_env_override(monkeypatch, tmp_path):
    custom_home = tmp_path / "custom_taxonomy"
    monkeypatch.setenv("TAXONOMY_HOME", str(custom_home))
    assert get_taxonomy_home() == custom_home.resolve()
    assert get_default_taste_path() == (custom_home / "taste.json").resolve()


def test_sentry_registry_operations():
    try:
        reset_protected_sentries()
        assert is_protected_sentry("engineering-quality-gate")
        assert is_protected_sentry("independent-jury")

        # allow_override bypasses sentry immunity
        assert not is_protected_sentry("engineering-quality-gate", allow_override=True)
        assert not is_protected_sentry("independent-jury", allow_override=True)

        # Dynamic sentry registration
        register_protected_sentry("custom-security-sentinel")
        assert is_protected_sentry("custom-security-sentinel")
        assert not is_protected_sentry("custom-security-sentinel", allow_override=True)

        # Unregister
        unregister_protected_sentry("custom-security-sentinel")
        assert not is_protected_sentry("custom-security-sentinel")
    finally:
        reset_protected_sentries()


def test_taste_profile_sentry_immunity_and_override():
    taste = TasteProfile(
        weights={"engineering-quality-gate": -2.5, "independent-jury": -3.0},
        avoid_skills=["engineering-quality-gate"],
    )
    dummy_sentry = SkillMetadata(
        name="engineering-quality-gate",
        description="Empirical QA sentry",
        category="verification.qa",
        tags=["qa", "testing"],
    )

    # By default, immunity prevents negative bias
    bias_default = taste.get_bias(dummy_sentry, allow_sentry_override=False)
    assert bias_default == 0.0
    reason_default = taste.get_bias_reason(dummy_sentry, allow_sentry_override=False)
    assert reason_default == "immune: quality sentry"

    # When override is allowed, negative bias is honored
    bias_overridden = taste.get_bias(dummy_sentry, allow_sentry_override=True)
    assert bias_overridden == -2.5
    reason_overridden = taste.get_bias_reason(dummy_sentry, allow_sentry_override=True)
    assert "weight" in reason_overridden


def test_resolver_sentry_avoidance_with_and_without_override(tmp_path):
    sentry_dir = tmp_path / "engineering-quality-gate"
    sentry_dir.mkdir()
    (sentry_dir / "SKILL.md").write_text(
        "---\nname: engineering-quality-gate\ndescription: Empirical test and build verification gate\n"
        "category: verification.qa\ntags: [qa, verification, testing]\npriority: 100\n---\n",
        encoding="utf-8",
    )
    indexer = SkillIndexer([tmp_path])
    indexer.scan()

    taste = TasteProfile(avoid_skills=["engineering-quality-gate"])

    # 1. Without override: sentry is immune to avoidance
    resolver = SkillResolver(indexer, taste_profile=taste, allow_sentry_override=False, enable_triad=False)
    res = resolver.resolve("run quality verification tests", force_route=True)
    selected_names = [s.name for s in res.selected_skills]
    assert "engineering-quality-gate" in selected_names

    # 2. With override: sentry is actively excluded by avoidance
    resolver_override = SkillResolver(indexer, taste_profile=taste, allow_sentry_override=True, enable_triad=False)
    res_override = resolver_override.resolve("run quality verification tests", force_route=True)
    selected_names_override = [s.name for s in res_override.selected_skills]
    assert "engineering-quality-gate" not in selected_names_override


def test_extensible_stack_alignments():
    alignments = get_stack_alignments()
    assert "nextjs" in alignments
    assert "solidity" in alignments

    # Register custom alignment
    register_stack_alignment("elixir", "backend.otp", "phoenix-framework-pro", weight=2.5)
    updated = get_stack_alignments()
    assert "elixir" in updated
    assert updated["elixir"][0]["skill"] == "phoenix-framework-pro"
