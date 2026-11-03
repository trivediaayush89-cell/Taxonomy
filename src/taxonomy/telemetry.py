"""SRE Telemetry, latency tracking, and structured metric aggregation."""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TelemetryEvent:
    timestamp: float
    event_type: str
    data: Dict[str, object]

    def to_dict(self) -> dict:
        return {
            "timestamp": round(self.timestamp, 3),
            "event_type": self.event_type,
            "data": self.data,
        }


class TelemetryCollector:
    """Collects structured latency and routing events for SRE verification."""

    def __init__(self, max_history: int = 5000):
        self.max_history = max_history
        self._gate_latencies: List[float] = []
        self._resolve_latencies: List[float] = []
        self._events: List[TelemetryEvent] = []
        self._routed_count = 0
        self._bypassed_count = 0

    def record_gate(self, tier: int, should_route: bool, latency_ms: float, reason: str) -> None:
        self._gate_latencies.append(latency_ms)
        if len(self._gate_latencies) > self.max_history:
            self._gate_latencies.pop(0)

        if should_route:
            self._routed_count += 1
        else:
            self._bypassed_count += 1

        self._record_event("gate_evaluation", {
            "tier": tier,
            "should_route": should_route,
            "latency_ms": round(latency_ms, 4),
            "reason": reason,
        })

    def record_resolution(self, selected_skills: List[str], latency_ms: float) -> None:
        self._resolve_latencies.append(latency_ms)
        if len(self._resolve_latencies) > self.max_history:
            self._resolve_latencies.pop(0)

        self._record_event("skills_resolved", {
            "selected_skills": selected_skills,
            "latency_ms": round(latency_ms, 4),
            "count": len(selected_skills),
        })

    def _record_event(self, event_type: str, data: Dict[str, object]) -> None:
        ev = TelemetryEvent(timestamp=time.time(), event_type=event_type, data=data)
        self._events.append(ev)
        if len(self._events) > self.max_history:
            self._events.pop(0)

    @staticmethod
    def _percentile(values: List[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = int(math.ceil((p / 100.0) * len(s))) - 1
        return s[max(0, min(idx, len(s) - 1))]

    def get_stats(self) -> Dict[str, object]:
        total = self._routed_count + self._bypassed_count
        return {
            "total_queries": total,
            "routed": self._routed_count,
            "bypassed": self._bypassed_count,
            "route_ratio": round(self._routed_count / max(1, total), 3),
            "gate_latency_ms": {
                "avg": round(sum(self._gate_latencies) / max(1, len(self._gate_latencies)), 4),
                "p50": round(self._percentile(self._gate_latencies, 50), 4),
                "p95": round(self._percentile(self._gate_latencies, 95), 4),
                "p99": round(self._percentile(self._gate_latencies, 99), 4),
                "max": round(max(self._gate_latencies) if self._gate_latencies else 0.0, 4),
            },
            "resolve_latency_ms": {
                "avg": round(sum(self._resolve_latencies) / max(1, len(self._resolve_latencies)), 4),
                "p50": round(self._percentile(self._resolve_latencies, 50), 4),
                "p95": round(self._percentile(self._resolve_latencies, 95), 4),
                "p99": round(self._percentile(self._resolve_latencies, 99), 4),
                "max": round(max(self._resolve_latencies) if self._resolve_latencies else 0.0, 4),
            }
        }


# Global singleton collector
telemetry = TelemetryCollector()
