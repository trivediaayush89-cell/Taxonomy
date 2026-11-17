"""SRE Telemetry, latency tracking, and persistent structured metric aggregation."""

import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

DEFAULT_TELEMETRY_PATH = Path(
    os.getenv("TAXONOMY_TELEMETRY_PATH", "~/.gemini/antigravity/taxonomy_telemetry.json")
).expanduser()


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
    """Collects, aggregates, and persists latency and routing events for SRE verification."""

    def __init__(
        self,
        log_path: Optional[Path] = None,
        max_history: int = 5000,
        persist: Optional[bool] = None,
    ):
        self.log_path = log_path or DEFAULT_TELEMETRY_PATH
        self.max_history = max_history
        self.persist = persist if persist is not None else (log_path is not None)
        self._lock = threading.Lock()

        self._gate_latencies: List[float] = []
        self._resolve_latencies: List[float] = []
        self._events: List[TelemetryEvent] = []
        self._routed_count = 0
        self._bypassed_count = 0
        self._tier_distribution: Dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0}
        self._shadow_predictions = 0
        self._user_overrides = 0
        self._cache_hits = 0
        self._overrides: List[dict] = []

        if self.persist:
            self._load()

    def _load(self) -> None:
        """Load persistent telemetry metrics from disk."""
        if not self.log_path.is_file():
            return
        try:
            raw = self.log_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            self._routed_count = int(data.get("routed", 0))
            self._bypassed_count = int(data.get("bypassed", 0))
            self._shadow_predictions = int(data.get("shadow_predictions", 0))
            self._user_overrides = int(data.get("user_overrides", 0))
            self._cache_hits = int(data.get("cache_hits", 0))
            loaded_tiers = data.get("tier_distribution", {})
            for k in ("0", "1", "2", "3"):
                self._tier_distribution[k] = int(loaded_tiers.get(k, 0))

            # Load recent latencies for percentiles calculation
            g_lat = data.get("gate_latencies", [])
            if isinstance(g_lat, list):
                self._gate_latencies = [float(x) for x in g_lat][-self.max_history:]
            r_lat = data.get("resolve_latencies", [])
            if isinstance(r_lat, list):
                self._resolve_latencies = [float(x) for x in r_lat][-self.max_history:]
            loaded_overrides = data.get("overrides", [])
            if isinstance(loaded_overrides, list):
                self._overrides = loaded_overrides[-50:]
        except Exception:
            pass

    def _save(self) -> None:
        """Atomically persist telemetry metrics using temporary file and os.replace."""
        if not self.persist:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "total_queries": self._routed_count + self._bypassed_count,
                "routed": self._routed_count,
                "bypassed": self._bypassed_count,
                "tier_distribution": self._tier_distribution,
                "shadow_predictions": self._shadow_predictions,
                "user_overrides": self._user_overrides,
                "cache_hits": self._cache_hits,
                "gate_latencies": self._gate_latencies[-self.max_history:],
                "resolve_latencies": self._resolve_latencies[-self.max_history:],
                "overrides": self._overrides[-50:],
                "last_updated": time.time(),
            }
            tmp_path = self.log_path.with_name(
                f"{self.log_path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
            )
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.log_path)
        except Exception:
            try:
                if "tmp_path" in locals() and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def record_gate(self, tier: int, should_route: bool, latency_ms: float, reason: str) -> None:
        with self._lock:
            self._gate_latencies.append(latency_ms)
            if len(self._gate_latencies) > self.max_history:
                self._gate_latencies.pop(0)

            tier_key = str(tier) if str(tier) in self._tier_distribution else "1"
            self._tier_distribution[tier_key] = self._tier_distribution.get(tier_key, 0) + 1

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
            self._save()

    def record_resolution(
        self,
        selected_skills: List[str],
        latency_ms: float,
        taste_applied: bool = False,
        profile_source: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._resolve_latencies.append(latency_ms)
            if len(self._resolve_latencies) > self.max_history:
                self._resolve_latencies.pop(0)

            data: Dict[str, object] = {
                "selected_skills": selected_skills,
                "latency_ms": round(latency_ms, 4),
                "count": len(selected_skills),
            }
            if taste_applied:
                data["taste_applied"] = True
                data["profile_source"] = profile_source

            self._record_event("skills_resolved", data)
            self._save()

    def record_shadow(
        self,
        prompt: str,
        shadow_skills: List[str],
        latency_ms: float,
    ) -> None:
        """Record a shadow evaluation prediction without disrupting the live agent."""
        with self._lock:
            self._shadow_predictions += 1
            self._resolve_latencies.append(latency_ms)
            if len(self._resolve_latencies) > self.max_history:
                self._resolve_latencies.pop(0)

            self._record_event("shadow_resolution", {
                "prompt": prompt[:120],
                "shadow_skills": shadow_skills,
                "latency_ms": round(latency_ms, 4),
                "count": len(shadow_skills),
            })
            self._save()

    def record_override(
        self,
        prompt: str,
        routed_skills: List[str],
        actual_skills: List[str],
        notes: str = "",
    ) -> None:
        """Record a developer override where actual selected skills differed from dispatcher prediction."""
        with self._lock:
            self._user_overrides += 1
            override_record = {
                "timestamp": time.time(),
                "prompt": prompt,
                "routed_skills": routed_skills,
                "actual_skills": actual_skills,
                "notes": notes,
            }
            self._overrides.append(override_record)
            if len(self._overrides) > 50:
                self._overrides.pop(0)

            self._record_event("user_override", override_record)
            self._save()

    def record_cache_hit(self) -> None:
        """Record an in-memory cache hit."""
        with self._lock:
            self._cache_hits += 1
            self._save()

    def reset(self) -> None:
        """Reset all in-memory and persisted telemetry metrics."""
        with self._lock:
            self._gate_latencies.clear()
            self._resolve_latencies.clear()
            self._events.clear()
            self._routed_count = 0
            self._bypassed_count = 0
            self._tier_distribution = {"0": 0, "1": 0, "2": 0, "3": 0}
            self._shadow_predictions = 0
            self._user_overrides = 0
            self._cache_hits = 0
            self._overrides.clear()
            if self.persist and self.log_path.is_file():
                try:
                    self.log_path.unlink()
                except Exception:
                    pass

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
            "tier_distribution": dict(self._tier_distribution),
            "shadow_predictions": self._shadow_predictions,
            "user_overrides": self._user_overrides,
            "cache_hits": self._cache_hits,
            "storage_path": str(self.log_path),
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
            },
            "recent_overrides": list(self._overrides[-10:]),
        }

    get_summary = get_stats


# Global singleton collector with disk persistence (auto-disabled during pytest unless TAXONOMY_TELEMETRY_PATH is set)
telemetry = TelemetryCollector(
    persist=("pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ)
    or bool(os.getenv("TAXONOMY_TELEMETRY_PATH"))
)
