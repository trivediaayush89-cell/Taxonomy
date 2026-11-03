"""Tests for SRE telemetry collection and percentile calculations."""

from taxonomy.telemetry import TelemetryCollector


def test_telemetry_metrics_and_percentiles():
    t = TelemetryCollector()

    # Simulate 100 gate evaluations
    for i in range(1, 101):
        # Latency between 0.01ms and 1.00ms
        t.record_gate(tier=2 if i > 50 else 0, should_route=(i > 50), latency_ms=i * 0.01, reason="test")

    stats = t.get_stats()
    assert stats["total_queries"] == 100
    assert stats["routed"] == 50
    assert stats["bypassed"] == 50
    assert stats["route_ratio"] == 0.5

    gate_stats = stats["gate_latency_ms"]
    assert gate_stats["p50"] == 0.50
    assert gate_stats["p95"] == 0.95
    assert gate_stats["p99"] == 0.99
    assert gate_stats["max"] == 1.00


def test_telemetry_event_history_cap():
    t = TelemetryCollector(max_history=10)
    for i in range(25):
        t.record_resolution(["skill-a"], latency_ms=0.1)

    assert len(t._events) == 10
