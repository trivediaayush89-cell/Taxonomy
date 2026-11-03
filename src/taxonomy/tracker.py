"""Persistent usage logging and stale/unpicked skill tracking."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_USAGE_PATH = Path("~/.gemini/antigravity/taxonomy_usage.json").expanduser()


class UsageTracker:
    """Tracks skill invocation hits across sessions to identify obsolete or unpicked skills."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or DEFAULT_USAGE_PATH
        self._data: Dict[str, dict] = self._load()

    def _load(self) -> Dict[str, dict]:
        if self.log_path.is_file():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except Exception:
                return {"skills": {}, "total_queries": 0}
        return {"skills": {}, "total_queries": 0}

    def _save(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass  # Fail-open: Never crash caller on write failure

    def record_hit(self, skill_name: str) -> None:
        """Record an invocation hit for a skill."""
        now = time.time()
        skills = self._data.setdefault("skills", {})
        entry = skills.setdefault(skill_name, {"hit_count": 0, "first_seen": now, "last_used": now})
        entry["hit_count"] += 1
        entry["last_used"] = now
        self._data["total_queries"] = self._data.get("total_queries", 0) + 1
        self._save()

    def get_hit_count(self, skill_name: str) -> int:
        skills = self._data.get("skills", {})
        return skills.get(skill_name, {}).get("hit_count", 0)

    def get_stale_skills(self, all_indexed_names: List[str]) -> List[str]:
        """Return skills that have never been hit or have zero invocations."""
        skills = self._data.get("skills", {})
        stale = []
        for name in all_indexed_names:
            if name not in skills or skills[name].get("hit_count", 0) == 0:
                stale.append(name)
        return sorted(stale)

    def get_stats_summary(self) -> dict:
        return self._data
