"""Evaluation runner and accuracy benchmarking for skill routing and gating."""

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from taxonomy.indexer import SkillIndexer
from taxonomy.models import ResolutionResult, SkillMetadata
from taxonomy.resolver import SkillResolver


class BenchmarkResult:
    """Aggregated evaluation metrics across a labeled benchmark dataset."""

    def __init__(
        self,
        total_prompts: int,
        gate_accuracy: float,
        false_bypass_rate: float,
        false_trigger_rate: float,
        precision_at_k: float,
        strict_precision_at_k: float,
        recall_at_k: float,
        mrr: float,
        over_dispatch_rate: float,
        token_savings_pct_vs_naive: float,
        token_savings_pct_vs_progressive: float,
        latency_p50_ms: float,
        latency_p95_ms: float,
        latency_p99_ms: float,
        latency_avg_ms: float,
        baseline_comparison: Dict[str, Any],
        query_details: List[Dict[str, Any]],
    ):
        self.total_prompts = total_prompts
        self.gate_accuracy = gate_accuracy
        self.false_bypass_rate = false_bypass_rate
        self.false_trigger_rate = false_trigger_rate
        self.precision_at_k = precision_at_k
        self.strict_precision_at_k = strict_precision_at_k
        self.recall_at_k = recall_at_k
        self.mrr = mrr
        self.over_dispatch_rate = over_dispatch_rate
        self.token_savings_pct_vs_naive = token_savings_pct_vs_naive
        self.token_savings_pct_vs_progressive = token_savings_pct_vs_progressive
        self.latency_p50_ms = latency_p50_ms
        self.latency_p95_ms = latency_p95_ms
        self.latency_p99_ms = latency_p99_ms
        self.latency_avg_ms = latency_avg_ms
        self.baseline_comparison = baseline_comparison
        self.query_details = query_details

    def to_dict(self) -> dict:
        return {
            "total_prompts": self.total_prompts,
            "metrics": {
                "gate_accuracy": round(self.gate_accuracy, 4),
                "false_bypass_rate": round(self.false_bypass_rate, 4),
                "false_trigger_rate": round(self.false_trigger_rate, 4),
                "precision_at_k": round(self.precision_at_k, 4),
                "strict_precision_at_k": round(self.strict_precision_at_k, 4),
                "recall_at_k": round(self.recall_at_k, 4),
                "mrr": round(self.mrr, 4),
                "over_dispatch_rate": round(self.over_dispatch_rate, 4),
                "token_savings_pct_vs_naive": round(self.token_savings_pct_vs_naive, 2),
                "token_savings_pct_vs_progressive": round(self.token_savings_pct_vs_progressive, 2),
            },
            "latencies_ms": {
                "p50": round(self.latency_p50_ms, 3),
                "p95": round(self.latency_p95_ms, 3),
                "p99": round(self.latency_p99_ms, 3),
                "avg": round(self.latency_avg_ms, 3),
            },
            "baseline_comparison": self.baseline_comparison,
            "query_details": self.query_details,
        }

    def print_summary(self) -> None:
        print("\n" + "=" * 65)
        print("  SKILL TAXONOMY DISPATCHER — ACCURACY & SRE BENCHMARK")
        print("=" * 65)
        print(f"Total Evaluated Prompts      : {self.total_prompts}")
        print("-" * 65)
        print("ROUTING ACCURACY METRICS:")
        print(f"  Gate Classification Accuracy: {self.gate_accuracy * 100:>6.2f}%")
        print(f"  False Bypass Rate (Missed)  : {self.false_bypass_rate * 100:>6.2f}%")
        print(f"  False Trigger Rate (Casual) : {self.false_trigger_rate * 100:>6.2f}%")
        print(f"  Precision@K (Lenient)       : {self.precision_at_k * 100:>6.2f}%")
        print(f"  Precision@K (Strict)        : {self.strict_precision_at_k * 100:>6.2f}%")
        print(f"  Recall@K                    : {self.recall_at_k * 100:>6.2f}%")
        print(f"  Mean Reciprocal Rank (MRR)  : {self.mrr:>6.4f}")
        print(f"  Over-Dispatch Rate          : {self.over_dispatch_rate * 100:>6.2f}%")
        print("-" * 65)
        print("TOKEN ECONOMICS & CONTEXT SAVINGS:")
        print(f"  Net Savings vs Naive All-Skills : {self.token_savings_pct_vs_naive:>6.2f}%")
        print(f"  Net Savings vs Progressive Disc: {self.token_savings_pct_vs_progressive:>6.2f}%")
        naive_tok = self.baseline_comparison.get("naive_total_tokens", 0)
        prog_tok = self.baseline_comparison.get("progressive_total_tokens", 0)
        tax_tok = self.baseline_comparison.get("taxonomy_total_tokens", 0)
        print(f"    - Naive Full-Catalog Injection: {naive_tok:,} total prompt tokens")
        print(f"    - Progressive Summary Headers : {prog_tok:,} total prompt tokens")
        print(f"    - Taxonomy Gated Dispatch     : {tax_tok:,} total prompt tokens")
        print("-" * 65)
        print("LATENCY DISTRIBUTION (Local In-Process):")
        print(f"  p50 Resolution Latency      : {self.latency_p50_ms:>6.3f} ms")
        print(f"  p95 Resolution Latency      : {self.latency_p95_ms:>6.3f} ms")
        print(f"  p99 Resolution Latency      : {self.latency_p99_ms:>6.3f} ms")
        print(f"  Average Resolution Latency  : {self.latency_avg_ms:>6.3f} ms")
        print("=" * 65 + "\n")


def estimate_tokens(text: str) -> int:
    """Fast deterministic token approximation (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class BenchmarkRunner:
    """Executes evaluation benchmarks over labeled dataset and skill catalogs."""

    def __init__(
        self,
        dataset_path: Path,
        catalog_path: Path,
        max_skills: int = 3,
        enable_triad: bool = False,
    ):
        self.dataset_path = Path(dataset_path)
        self.catalog_path = Path(catalog_path)
        self.max_skills = max_skills
        self.enable_triad = enable_triad

        self.indexer = SkillIndexer([self.catalog_path])
        self.indexer.scan()
        self.resolver = SkillResolver(
            self.indexer,
            max_skills=self.max_skills,
            enable_triad=self.enable_triad,
        )

        # Precompute empirical token footprints for the catalog
        self.skill_body_tokens: Dict[str, int] = {}
        self.skill_summary_tokens: Dict[str, int] = {}
        for skill in self.indexer.all_skills:
            body = skill.get_full_instructions()
            summary = json.dumps(skill.to_summary())
            self.skill_body_tokens[skill.name] = estimate_tokens(body)
            self.skill_summary_tokens[skill.name] = estimate_tokens(summary)

        self.total_catalog_body_tokens = sum(self.skill_body_tokens.values())
        self.total_catalog_summary_tokens = sum(self.skill_summary_tokens.values())

    def run(self) -> BenchmarkResult:
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        total_prompts = len(dataset)
        gate_correct = 0
        false_bypasses = 0
        false_triggers = 0
        total_expected_gated = 0
        total_expected_casual = 0

        routed_queries = 0
        precision_sum = 0.0
        strict_precision_sum = 0.0
        recall_sum = 0.0
        mrr_sum = 0.0
        mrr_count = 0
        over_dispatch_count = 0

        latencies: List[float] = []
        query_details: List[Dict[str, Any]] = []

        naive_total_tokens = 0
        progressive_total_tokens = 0
        taxonomy_total_tokens = 0

        from taxonomy.telemetry import telemetry
        prev_persist = telemetry.persist
        telemetry.persist = False
        try:
            for item in dataset:
                prompt = item["prompt"]
                expected_gate = bool(item.get("expected_gate", True))
                expected_skills = set(item.get("expected_skills", []))
                acceptable_fallbacks = set(item.get("acceptable_fallbacks", []))
                valid_targets = expected_skills | acceptable_fallbacks

                if expected_gate:
                    total_expected_gated += 1
                else:
                    total_expected_casual += 1

                start_t = time.perf_counter()
                res = self.resolver.resolve(prompt)
                duration_ms = (time.perf_counter() - start_t) * 1000.0
                latencies.append(duration_ms)

                # A query is actively routed if gate said should_route and resolver did not abstain
                actual_gate = res.gate.should_route and not res.abstained
                selected_names = [s.name for s in res.selected_skills]

                # 1. Gate Accuracy Metrics
                if actual_gate == expected_gate:
                    gate_correct += 1
                if expected_gate and not actual_gate:
                    false_bypasses += 1
                if not expected_gate and actual_gate:
                    false_triggers += 1

                # 2. Token Calculations
                # Baseline 1 (Naive): Injects all skills in catalog regardless of prompt
                naive_tokens = self.total_catalog_body_tokens
                naive_total_tokens += naive_tokens

                # Baseline 2 (Progressive): Injects all skill summaries, plus full body for routed skills
                prog_tokens = self.total_catalog_summary_tokens + sum(
                    self.skill_body_tokens.get(name, 500) for name in selected_names
                )
                progressive_total_tokens += prog_tokens

                # Taxonomy: 0 tokens if bypassed; if routed, only body of selected skills (0 routing tokens)
                if actual_gate and selected_names:
                    tax_tokens = sum(self.skill_body_tokens.get(name, 500) for name in selected_names)
                else:
                    tax_tokens = 0
                taxonomy_total_tokens += tax_tokens

                # 3. Routing Quality Metrics (for queries expected to be routed)
                p_lenient = 1.0 if not expected_gate and not actual_gate else 0.0
                p_strict = 1.0 if not expected_gate and not actual_gate else 0.0
                r = 1.0 if not expected_gate and not actual_gate else 0.0
                query_mrr = 0.0

                if expected_gate:
                    if actual_gate and selected_names:
                        routed_queries += 1

                        # Lenient Precision (expected or acceptable fallbacks)
                        valid_hits = sum(1 for s in selected_names if s in valid_targets)
                        p_lenient = valid_hits / len(selected_names)
                        precision_sum += p_lenient

                        # Strict Precision (expected skills only)
                        strict_hits = sum(1 for s in selected_names if s in expected_skills)
                        p_strict = strict_hits / len(selected_names)
                        strict_precision_sum += p_strict

                        # Recall (proportion of expected target skills captured in selected_names)
                        if expected_skills:
                            selected_set = set(selected_names)
                            captured = len(selected_set & valid_targets)
                            r = min(1.0, captured / len(expected_skills))
                            recall_sum += r

                        # Over-dispatch: selected more skills than valid targets matched (extraneous skills dispatched)
                        if any(s not in valid_targets for s in selected_names) and len(selected_names) > len(expected_skills):
                            over_dispatch_count += 1
                    elif actual_gate and not selected_names:
                        # Routed but no skills selected
                        routed_queries += 1

                    # MRR: Check rank of first relevant skill across candidate scores
                    if expected_skills:
                        mrr_count += 1
                        # Candidate ranking: selected skills first, followed by scored candidates in score-descending order
                        scored_candidates = sorted(
                            res.skill_scores.keys(),
                            key=lambda k: res.skill_scores[k].final_score,
                            reverse=True,
                        )
                        ranked_candidates = selected_names + [
                            k for k in scored_candidates if k not in selected_names
                        ]
                        for rank_idx, candidate in enumerate(ranked_candidates, start=1):
                            if candidate in valid_targets:
                                query_mrr = 1.0 / rank_idx
                                mrr_sum += query_mrr
                                break

                query_details.append({
                    "prompt": prompt,
                    "expected_gate": expected_gate,
                    "actual_gate": actual_gate,
                    "expected_skills": list(expected_skills),
                    "selected_skills": selected_names,
                    "precision": round(p_lenient, 3),
                    "recall": round(r, 3),
                    "mrr": round(query_mrr, 3),
                    "latency_ms": round(duration_ms, 3),
                })
        finally:
            telemetry.persist = prev_persist

        # Aggregation
        gate_accuracy = gate_correct / total_prompts if total_prompts > 0 else 0.0
        false_bypass_rate = (
            false_bypasses / total_expected_gated if total_expected_gated > 0 else 0.0
        )
        false_trigger_rate = (
            false_triggers / total_expected_casual if total_expected_casual > 0 else 0.0
        )
        avg_precision = precision_sum / routed_queries if routed_queries > 0 else 0.0
        avg_strict_precision = strict_precision_sum / routed_queries if routed_queries > 0 else 0.0
        avg_recall = recall_sum / total_expected_gated if total_expected_gated > 0 else 0.0
        avg_mrr = mrr_sum / mrr_count if mrr_count > 0 else 0.0
        over_dispatch_rate = (
            over_dispatch_count / routed_queries if routed_queries > 0 else 0.0
        )

        savings_vs_naive = (
            ((naive_total_tokens - taxonomy_total_tokens) / naive_total_tokens * 100.0)
            if naive_total_tokens > 0
            else 0.0
        )
        savings_vs_progressive = (
            ((progressive_total_tokens - taxonomy_total_tokens) / progressive_total_tokens * 100.0)
            if progressive_total_tokens > 0
            else 0.0
        )

        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)] if sorted_latencies else 0.0
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0.0
        p99 = sorted_latencies[min(len(sorted_latencies) - 1, int(len(sorted_latencies) * 0.99))] if sorted_latencies else 0.0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        baseline_comparison = {
            "naive_total_tokens": naive_total_tokens,
            "progressive_total_tokens": progressive_total_tokens,
            "taxonomy_total_tokens": taxonomy_total_tokens,
            "savings_vs_naive_pct": round(savings_vs_naive, 2),
            "savings_vs_progressive_pct": round(savings_vs_progressive, 2),
        }

        return BenchmarkResult(
            total_prompts=total_prompts,
            gate_accuracy=gate_accuracy,
            false_bypass_rate=false_bypass_rate,
            false_trigger_rate=false_trigger_rate,
            precision_at_k=avg_precision,
            strict_precision_at_k=avg_strict_precision,
            recall_at_k=avg_recall,
            mrr=avg_mrr,
            over_dispatch_rate=over_dispatch_rate,
            token_savings_pct_vs_naive=savings_vs_naive,
            token_savings_pct_vs_progressive=savings_vs_progressive,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            latency_avg_ms=avg_lat,
            baseline_comparison=baseline_comparison,
            query_details=query_details,
        )
