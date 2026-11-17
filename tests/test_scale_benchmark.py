"""Scale fuzzing, high-concurrency SRE benchmark, and memory profiling (ISS-34)."""

import gc
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Tuple
import pytest

from taxonomy.hook import dispatch_prompt
from taxonomy.indexer import SkillIndexer
from taxonomy.resolver import SkillResolver


def get_environment_metadata() -> Dict[str, str]:
    """Capture reproducible hardware and runtime environment metadata."""
    return {
        "os_platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_cores": str(os.cpu_count() or 1),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
    }


def generate_synthetic_skills(base_dir: Path, count: int, num_categories: int = 25) -> None:
    """Generate synthetic skill directories with realistic SKILL.md manifests."""
    base_dir.mkdir(parents=True, exist_ok=True)
    categories = [f"domain_{i // 10}.sub_{i % 10}" for i in range(num_categories)]

    for i in range(1, count + 1):
        cat = categories[i % len(categories)]
        skill_dir = base_dir / f"skill-{i:05d}"
        skill_dir.mkdir(exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"---\n"
            f"name: skill-{i:05d}\n"
            f"description: High-performance microservice tool {i} for distributed pipeline and {cat}\n"
            f"category: {cat}\n"
            f"tags:\n"
            f"  - tag_{i % 50}\n"
            f"  - pipeline_{i % 25}\n"
            f"  - automation\n"
            f"  - telemetry\n"
            f"status: active\n"
            f"priority: {50 + (i % 50)}\n"
            f"version: 1.0.0\n"
            f"trust_level: builtin\n"
            f"---\n\n"
            f"# skill-{i:05d}\nComprehensive documentation and instructions for skill {i}.\n",
            encoding="utf-8"
        )


@pytest.fixture(scope="module")
def multi_scale_skills_catalogs(tmp_path_factory):
    """Generate synthetic skill catalogs across 100, 1,000, 2,500, and 5,000 skills."""
    base = tmp_path_factory.mktemp("multi_scale_catalogs")
    catalogs = {
        8: base / "scale_8",
        100: base / "scale_100",
        1000: base / "scale_1000",
        2500: base / "scale_2500",
        5000: base / "scale_5000",
    }
    for count, path in catalogs.items():
        generate_synthetic_skills(path, count, num_categories=min(50, max(5, count // 10)))
    return catalogs


def test_scale_cold_and_warm_scan_with_memory_profiling(multi_scale_skills_catalogs):
    """Benchmark cold scan vs warm scan and measure peak heap memory via tracemalloc."""
    env = get_environment_metadata()
    print("\n" + "=" * 65)
    print("  SCALE BENCHMARK — ENVIRONMENT METADATA")
    print("=" * 65)
    for k, v in env.items():
        print(f"  {k:<22}: {v}")
    print("=" * 65)

    catalog_1000 = multi_scale_skills_catalogs[1000]
    indexer = SkillIndexer([catalog_1000])

    # 1. Cold Scan with tracemalloc memory profiling
    gc.collect()
    tracemalloc.start()
    start_cold = time.perf_counter()
    skills_cold = indexer.scan(force=True)
    cold_duration_ms = (time.perf_counter() - start_cold) * 1000
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(skills_cold) == 1000
    peak_mem_mb = peak_mem / (1024 * 1024)
    print(f"\n[Scale 1,000 Skills - Cold Scan]")
    print(f"  Duration : {cold_duration_ms:.2f} ms")
    print(f"  Peak RAM : {peak_mem_mb:.2f} MB")
    cold_max = 35000.0 if sys.platform == "win32" else 8000.0
    assert cold_duration_ms < cold_max
    assert peak_mem_mb < 30.0, f"Cold scan memory footprint ({peak_mem_mb:.2f} MB) exceeded 30 MB"

    # 2. Warm Scan (mtime check only, no file re-reads)
    tracemalloc.start()
    start_warm = time.perf_counter()
    skills_warm = indexer.scan(force=False)
    warm_duration_ms = (time.perf_counter() - start_warm) * 1000
    _, warm_peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(skills_warm) == 1000
    warm_peak_mb = warm_peak_mem / (1024 * 1024)
    print(f"[Scale 1,000 Skills - Warm Scan]")
    print(f"  Duration : {warm_duration_ms:.2f} ms")
    print(f"  Peak RAM : {warm_peak_mb:.2f} MB")
    warm_max = 1200.0 if sys.platform == "win32" else 500.0
    assert warm_duration_ms < warm_max


def test_scale_resolution_across_catalog_sizes(multi_scale_skills_catalogs):
    """Benchmark resolution latency and memory scaling across 8, 100, 1,000, 2,500, and 5,000 skills."""
    scale_points = [8, 100, 1000, 2500, 5000]
    results: List[Tuple[int, float, float, float, float, float]] = []

    print("\n" + "=" * 65)
    print("  SCALE CURVE BENCHMARK (8 to 5,000 Skills)")
    print("=" * 65)

    for n in scale_points:
        catalog_path = multi_scale_skills_catalogs[n]
        indexer = SkillIndexer([catalog_path])
        indexer.scan()
        resolver = SkillResolver(indexer, max_skills=3, enable_triad=False)

        # Warmup
        resolver.resolve("Warmup database pipeline query", force_route=True)
        gc.collect()

        # Measure peak memory on resolution
        tracemalloc.start()
        resolver.resolve("Memory profiling query for pipeline automation", force_route=True)
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak_mem / (1024 * 1024)

        # Measure 25 iterations of resolution latency cleanly (without tracemalloc instrumentation overhead)
        gc.collect()
        latencies = []
        for i in range(25):
            prompt = f"Optimize distributed pipeline_{i % 25} with tag_{i % 50} automation"
            res = resolver.resolve(prompt, force_route=True)
            assert len(res.selected_skills) <= 3
            latencies.append(res.total_latency_ms)

        sorted_lats = sorted(latencies)
        p50 = sorted_lats[int(len(sorted_lats) * 0.50)]
        p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
        p99 = sorted_lats[-1]
        avg = sum(latencies) / len(latencies)

        results.append((n, avg, p50, p95, p99, peak_mb))
        print(f"  N = {n:<5} | Avg: {avg:>6.3f} ms | p50: {p50:>6.3f} ms | p95: {p95:>6.3f} ms | Peak RAM: {peak_mb:>5.2f} MB")

        # Hard SLA assertions: sub-50ms p95 on Linux/Mac up to 1,000 skills; sub-80ms p95 on Windows; scale gracefully to 5,000
        sla_p95 = (45.0 + (n / 100.0)) if sys.platform == "win32" else (20.0 + (n / 200.0))
        assert p95 < sla_p95, f"p95 latency ({p95:.2f}ms) breached SLA for N={n}"

    print("=" * 65)


def test_in_process_hook_vs_cli_subprocess_latency(multi_scale_skills_catalogs, tmp_path, monkeypatch):
    """Compare in-process hook latency (< 1ms) against cold CLI subprocess startup latency."""
    usage_file = tmp_path / "scale_usage.json"
    monkeypatch.setenv("TAXONOMY_USAGE_PATH", str(usage_file))
    monkeypatch.setattr("taxonomy.tracker.DEFAULT_USAGE_PATH", usage_file)

    catalog_100 = multi_scale_skills_catalogs[100]
    prompt = "Optimize distributed pipeline_10 with automation"

    # 1. Warmup global dispatcher once so indexer and BM25 are loaded in-process
    dispatch_prompt("Warmup query", skills_roots=[catalog_100], max_skills=3)

    # In-Process Hook Latency (steady-state hot dispatch)
    in_proc_latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        res = dispatch_prompt(prompt, skills_roots=[catalog_100], max_skills=3)
        elapsed = (time.perf_counter() - t0) * 1000.0
        in_proc_latencies.append(elapsed)

    avg_in_proc = sum(in_proc_latencies) / len(in_proc_latencies)
    p50_in_proc = sorted(in_proc_latencies)[len(in_proc_latencies) // 2]

    # 2. CLI Subprocess Latency (full python interpreter boot)
    cli_latencies = []
    for _ in range(3):
        t0 = time.perf_counter()
        cmd = [
            sys.executable,
            "-m",
            "taxonomy.cli",
            "resolve",
            prompt,
            "--skills-dir",
            str(catalog_100),
            "--force",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = (time.perf_counter() - t0) * 1000.0
        cli_latencies.append(elapsed)

    avg_cli = sum(cli_latencies) / len(cli_latencies)

    print(f"\n[Hook vs Subprocess Latency Comparison]")
    print(f"  In-Process Hook (p50)   : {p50_in_proc:.3f} ms")
    print(f"  In-Process Hook (Avg)   : {avg_in_proc:.3f} ms")
    print(f"  CLI Subprocess (Avg)    : {avg_cli:.2f} ms")
    speedup = avg_cli / max(0.01, avg_in_proc)
    print(f"  In-Process Speedup      : {speedup:.1f}x faster than cold subprocess")

    # In-process hook must be fast (< 45ms on Windows with NTFS tracking, < 5ms on Linux)
    in_proc_max = 45.0 if sys.platform == "win32" else 5.0
    assert avg_in_proc < in_proc_max
    assert speedup > 8.0, f"In-process hook was not significantly faster than subprocess ({speedup:.1f}x)"
