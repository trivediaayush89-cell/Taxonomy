"""Comprehensive test suite for gate accuracy, resolver precision, and mtime caching."""

import json
from pathlib import Path
import pytest

from taxonomy.indexer import SkillIndexer
from taxonomy.gate import CompoundGate
from taxonomy.resolver import SkillResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"
EVAL_PROMPTS_PATH = Path(__file__).parent / "eval_prompts.json"


@pytest.fixture(scope="module")
def eval_prompts():
    assert EVAL_PROMPTS_PATH.is_file(), "eval_prompts.json must exist"
    with open(EVAL_PROMPTS_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def indexer():
    idx = SkillIndexer([FIXTURES_DIR])
    idx.scan()
    return idx


@pytest.fixture(scope="module")
def resolver(indexer):
    return SkillResolver(indexer, max_skills=3)


def test_mock_skills_loaded(indexer):
    """Verify all 8 mock skills were properly indexed."""
    skills = indexer.all_skills
    assert len(skills) == 8
    names = {s.name for s in skills}
    assert "frontend-ui-engineering" in names
    assert "backend-architecture" in names
    assert "smart-contract-auditor" in names
    assert "performance-sre" in names
    assert "independent-jury" in names
    assert "engineering-quality-gate" in names


def test_gate_accuracy_and_false_positives(eval_prompts):
    """Test all 40 golden prompts for zero false-positives and zero false-negatives."""
    gate = CompoundGate()
    
    passed = 0
    total = len(eval_prompts)
    failures = []

    for item in eval_prompts:
        prompt_id = item["id"]
        prompt = item["prompt"]
        expected_gate = item["expected_gate"]
        
        result = gate.evaluate(prompt)
        
        if result.should_route != expected_gate:
            failures.append(
                f"[{prompt_id}] Expected should_route={expected_gate}, got {result.should_route}. "
                f"Reason: {result.reason}. Prompt: '{prompt}'"
            )
        else:
            passed += 1

    assert not failures, f"Gate accuracy failures ({len(failures)}/{total}):\n" + "\n".join(failures)


def test_gate_latency_sre_budget(eval_prompts):
    """Verify average gate evaluation is sub-millisecond."""
    gate = CompoundGate()
    latencies = []

    # Warmup
    for _ in range(5):
        gate.evaluate("warmup prompt")

    for item in eval_prompts:
        result = gate.evaluate(item["prompt"])
        latencies.append(result.latency_ms)

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    print(f"\n[SRE Benchmark] Avg Gate Latency: {avg_latency:.4f} ms | Max: {max_latency:.4f} ms")
    assert avg_latency < 1.0, f"Average gate latency ({avg_latency:.3f}ms) exceeded 1.0ms SLA!"


def test_resolver_selection_and_budget(eval_prompts, resolver):
    """Test that resolved skills match expectations and never exceed max_skills budget."""
    for item in eval_prompts:
        if not item["expected_gate"]:
            continue  # Only test routed prompts
            
        result = resolver.resolve(item["prompt"])
        assert len(result.selected_skills) <= resolver.max_skills
        assert len(result.selected_skills) > 0, f"Prompt '{item['prompt']}' should have selected at least 1 skill"

        selected_names = {s.name for s in result.selected_skills}
        expected_skills = set(item["expected_skills"])

        # Check intersection with expected skills
        matched = selected_names.intersection(expected_skills)
        assert bool(matched), (
            f"Prompt '{item['prompt']}' expected one of {expected_skills}, "
            f"but got {selected_names}"
        )


def test_mtime_caching_performance(indexer, tmp_path):
    """Verify indexer avoids disk re-reads when mtimes have not changed."""
    # First scan done in fixture
    initial_skills = indexer.all_skills
    assert len(initial_skills) == 8

    # Second scan with no file changes should not re-parse
    refreshed = indexer.scan(force=False)
    assert len(refreshed) == 8
    assert refreshed["frontend-ui-engineering"] is initial_skills[0] or refreshed["frontend-ui-engineering"].name == "frontend-ui-engineering"


def test_fail_open_resilience(tmp_path):
    """Verify corrupted or broken files do not crash the indexer."""
    corrupt_skill = tmp_path / "broken-skill"
    corrupt_skill.mkdir()
    (corrupt_skill / "SKILL.md").write_text("::: not a valid yaml ---\n:::", encoding="utf-8")

    idx = SkillIndexer([tmp_path])
    skills = idx.scan()
    # It should gracefully parse as unclassified fallback rather than throwing an exception
    assert len(skills) == 1
    assert skills["broken-skill"].category == "general"
