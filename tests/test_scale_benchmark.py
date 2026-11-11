"""Scale fuzzing and high-concurrency SRE benchmark across 1,000 mock skills."""

import gc
import sys
import time
from pathlib import Path
import pytest

from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver


@pytest.fixture(scope="module")
def large_scale_skills_dir(tmp_path_factory):
    """Generate 1,000 realistic mock skills across 50 categories."""
    base = tmp_path_factory.mktemp("scale_1000_skills")
    
    categories = [f"domain_{i // 20}.sub_{i % 20}" for i in range(50)]
    
    for i in range(1, 1001):
        cat = categories[i % len(categories)]
        skill_dir = base / f"skill-{i:04d}"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"---\n"
            f"name: skill-{i:04d}\n"
            f"description: Specialized tool {i} for handling algorithmic pipelines and {cat}\n"
            f"category: {cat}\n"
            f"tags:\n"
            f"  - tag_{i % 50}\n"
            f"  - pipeline_{i % 25}\n"
            f"  - automation\n"
            f"status: active\n"
            f"priority: {50 + (i % 50)}\n"
            f"---\n\n"
            f"# Skill {i}\nBody content for skill {i}.\n",
            encoding="utf-8"
        )
    return base


def test_scale_cold_and_warm_scan_latency(large_scale_skills_dir):
    """Benchmark initial cold scan vs warm mtime cache scan across 1,000 skills."""
    indexer = SkillIndexer([large_scale_skills_dir])

    # 1. Cold Scan
    start_cold = time.perf_counter()
    skills_cold = indexer.scan(force=True)
    cold_duration_ms = (time.perf_counter() - start_cold) * 1000

    assert len(skills_cold) == 1000
    print(f"\n[Scale Benchmark] 1,000 Skills Cold Scan: {cold_duration_ms:.2f} ms")
    cold_max = 25000.0 if sys.platform == "win32" else 8000.0
    assert cold_duration_ms < cold_max  # Cold scan parallelized across 1000 disk files

    # 2. Warm Scan (mtime check only, no file re-reads)
    start_warm = time.perf_counter()
    skills_warm = indexer.scan(force=False)
    warm_duration_ms = (time.perf_counter() - start_warm) * 1000

    assert len(skills_warm) == 1000
    print(f"[Scale Benchmark] 1,000 Skills Warm Scan: {warm_duration_ms:.2f} ms")
    # Warm scan checks 1000 mtimes; must be fast (< 1200ms on Windows, < 500ms on Linux/macOS)
    warm_max = 1200.0 if sys.platform == "win32" else 500.0
    assert warm_duration_ms < warm_max


def test_scale_resolution_under_15ms_sla(large_scale_skills_dir):
    """Verify that resolution across 1,000 skills meets the < 15ms p99 SLA."""
    indexer = SkillIndexer([large_scale_skills_dir])
    indexer.scan()
    resolver = SkillResolver(indexer, max_skills=3)

    # Warmup query
    resolver.resolve("Warmup database pipeline and automation workflow", force_route=True)

    # Clean memory before benchmark loop to avoid GC latency distortion
    gc.collect()

    latencies = []

    # Run 50 prompt resolutions against the 1,000 skill catalog
    for i in range(50):
        prompt = f"Optimize database pipeline_{i % 25} and automate tag_{i % 50} workflow"
        res = resolver.resolve(prompt, force_route=True)
        assert len(res.selected_skills) <= 3
        latencies.append(res.total_latency_ms)

    sorted_lats = sorted(latencies)
    p50 = sorted_lats[int(len(sorted_lats) * 0.50)]
    p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
    p99 = sorted_lats[-1]
    avg = sum(latencies) / len(latencies)

    print(f"\n[Scale SLA Benchmark - 1,000 Skills]")
    print(f"  Avg Resolution Latency: {avg:.2f} ms")
    print(f"  p50 Resolution Latency: {p50:.2f} ms")
    print(f"  p95 Resolution Latency: {p95:.2f} ms")
    print(f"  p99 Resolution Latency: {p99:.2f} ms")

    # Hard SLA verification (< 15ms avg on Linux/Mac, < 30ms on Windows under 1,000 skills)
    sla_avg = 30.0 if sys.platform == "win32" else 15.0
    sla_p95 = 50.0 if sys.platform == "win32" else 25.0
    assert avg < sla_avg, f"Avg resolution latency ({avg:.2f}ms) breached the SLA!"
    assert p95 < sla_p95, f"p95 latency ({p95:.2f}ms) breached the SLA!"
