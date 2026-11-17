"""Persistent usage logging and stale/unpicked skill tracking."""

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_USAGE_PATH = Path(
    os.getenv("TAXONOMY_USAGE_PATH", "~/.gemini/antigravity/taxonomy_usage.json")
).expanduser()


class UsageTracker:
    """Tracks skill invocation hits across sessions to identify obsolete or unpicked skills."""

    def __init__(self, log_path: Optional[Path] = None, storage_path: Optional[Path] = None):
        self.log_path = log_path or storage_path or DEFAULT_USAGE_PATH
        self._lock = threading.Lock()
        self._data: Dict[str, dict] = self._load()

    def _load(self) -> Dict[str, dict]:
        if self.log_path.is_file():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except Exception:
                return {"skills": {}, "total_queries": 0}
        return {"skills": {}, "total_queries": 0}

    def _save(self) -> None:
        """Atomically persist usage data using temporary file and os.replace."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._data, indent=2)
            tmp_path = self.log_path.with_name(
                f"{self.log_path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
            )
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, self.log_path)
        except Exception:
            try:
                if "tmp_path" in locals() and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def record_hit(self, skill_name: str) -> None:
        """Record an invocation hit for a skill."""
        with self._lock:
            now = time.time()
            self._data = self._load()
            skills = self._data.setdefault("skills", {})
            entry = skills.setdefault(skill_name, {"hit_count": 0, "first_seen": now, "last_used": now})
            entry["hit_count"] += 1
            entry["last_used"] = now
            self._data["total_queries"] = self._data.get("total_queries", 0) + 1
            self._save()

    def record_hits(self, skill_names: List[str]) -> None:
        """Record invocation hits for multiple skills in a single atomic save."""
        if not skill_names:
            return
        with self._lock:
            now = time.time()
            self._data = self._load()
            skills = self._data.setdefault("skills", {})
            for name in skill_names:
                clean = str(name).strip()
                if not clean:
                    continue
                entry = skills.setdefault(clean, {"hit_count": 0, "first_seen": now, "last_used": now})
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
