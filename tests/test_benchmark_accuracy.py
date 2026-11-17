"""Accuracy benchmark test suite verifying empirical routing performance (ISS-33)."""

import json
from pathlib import Path
import pytest

from taxonomy.benchmark import BenchmarkRunner


BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks"
DATASET_PATH = BENCHMARKS_DIR / "labeled_routing_dataset.json"
CATALOG_PATH = BENCHMARKS_DIR / "catalog"


def test_benchmark_dataset_completeness_and_schema():
    """Verify that labeled routing dataset contains 100+ valid labeled prompts with complete schema."""
    assert DATASET_PATH.is_file(), f"Dataset file missing at {DATASET_PATH}"
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) >= 100, f"Expected at least 100 labeled evaluation prompts, got {len(data)}"

    seen_ids = set()
    categories = set()
    gated_count = 0
    casual_count = 0

    for item in data:
        assert "id" in item, "Item missing id"
        assert item["id"] not in seen_ids, f"Duplicate prompt id: {item['id']}"
        seen_ids.add(item["id"])

        assert "prompt" in item and len(item["prompt"].strip()) > 0
        assert "category" in item
        categories.add(item["category"])

        assert "expected_gate" in item
        assert isinstance(item["expected_gate"], bool)
        if item["expected_gate"]:
            gated_count += 1
        else:
            casual_count += 1

        assert "expected_tier" in item
        assert item["expected_tier"] in (0, 1, 2, 3)

        assert "expected_skills" in item
        assert isinstance(item["expected_skills"], list)

    assert len(categories) >= 8, f"Expected broad domain coverage, got categories: {categories}"
    assert gated_count >= 80, f"Expected at least 80 technical prompts, got {gated_count}"
    assert casual_count >= 15, f"Expected at least 15 casual/bypass prompts, got {casual_count}"


def test_benchmark_accuracy_metrics_meet_slas():
    """Execute evaluation benchmark and verify that all accuracy and token savings SLAs pass."""
    runner = BenchmarkRunner(
        dataset_path=DATASET_PATH,
        catalog_path=CATALOG_PATH,
        max_skills=3,
        enable_triad=False,
    )
    result = runner.run()

    # Routing Accuracy SLAs
    assert result.gate_accuracy >= 0.95, (
        f"Gate accuracy ({result.gate_accuracy * 100:.2f}%) fell below 95% SLA"
    )
    assert result.false_bypass_rate <= 0.05, (
        f"False bypass rate ({result.false_bypass_rate * 100:.2f}%) exceeded 5% limit"
    )
    assert result.false_trigger_rate <= 0.05, (
        f"False trigger rate ({result.false_trigger_rate * 100:.2f}%) exceeded 5% limit"
    )
    assert result.recall_at_k >= 0.85, (
        f"Recall@K ({result.recall_at_k * 100:.2f}%) fell below 85% SLA"
    )
    assert result.precision_at_k >= 0.70, (
        f"Precision@K ({result.precision_at_k * 100:.2f}%) fell below 70% SLA"
    )
    assert result.mrr >= 0.85, (
        f"MRR ({result.mrr:.4f}) fell below 0.85 SLA"
    )

    # Context Token Economics SLAs
    assert result.token_savings_pct_vs_naive >= 85.0, (
        f"Token savings vs naive catalog injection ({result.token_savings_pct_vs_naive:.1f}%) fell below 85%"
    )
    assert result.token_savings_pct_vs_progressive >= 65.0, (
        f"Token savings vs progressive discovery ({result.token_savings_pct_vs_progressive:.1f}%) fell below 65%"
    )
    assert (
        result.baseline_comparison["naive_total_tokens"]
        > result.baseline_comparison["progressive_total_tokens"]
        > result.baseline_comparison["taxonomy_total_tokens"]
    )

    # In-Process SRE Latency SLA (< 15ms p95)
    assert result.latency_p95_ms < 15.0, (
        f"p95 latency ({result.latency_p95_ms:.2f}ms) breached 15ms SLA"
    )


def test_benchmark_cli_invocation(capsys):
    """Verify that taxonomy benchmark CLI subcommand produces expected text summary and JSON."""
    from taxonomy.cli import main
    import sys

    # 1. Text output test
    sys.argv = ["taxonomy", "benchmark", "--max-skills", "3"]
    try:
        main()
    except SystemExit as exc:
        assert exc.code in (0, None)
    captured = capsys.readouterr().out
    assert "SKILL TAXONOMY DISPATCHER — ACCURACY & SRE BENCHMARK" in captured
    assert "ROUTING ACCURACY METRICS:" in captured
    assert "Gate Classification Accuracy:" in captured

    # 2. JSON output test
    sys.argv = ["taxonomy", "benchmark", "--json", "--max-skills", "3"]
    try:
        main()
    except SystemExit as exc:
        assert exc.code in (0, None)
    captured_json = capsys.readouterr().out
    data = json.loads(captured_json)
    assert "metrics" in data
    assert data["metrics"]["gate_accuracy"] >= 0.95
    assert data["metrics"]["mrr"] >= 0.85
    assert "baseline_comparison" in data
