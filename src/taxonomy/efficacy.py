"""Zero-token outcome-based empirical efficacy telemetry and git attribution tracker.

Measures physical developer outcomes ($0 token cost, < 1ms execution):
- Commit vs Discard: Did the developer keep and commit code, keep it in working tree, or restore/discard?
- Test verification: Did automated tests (pytest, npm test) pass (exit 0) or fail?
- Telemetry: Aggregates real win rates, keep rates, discard rates, and net empirical scores per skill.
- Fail-Open: Never crashes the caller or breaks agent dispatch on any IO/Git error.
"""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("taxonomy.efficacy")

DEFAULT_GLOBAL_EFFICACY_PATH = Path("~/.gemini/antigravity/taxonomy_efficacy.json").expanduser()
WORKSPACE_EFFICACY_REL_PATH = Path(".taxonomy/efficacy.json")

OUTCOME_WEIGHTS = {
    "committed": 1.0,
    "retained": 0.5,
    "discarded": -2.0,
    "unknown": 0.0,
}

TEST_WEIGHTS = {
    "passed": 1.0,
    "failed": -1.0,
    "not_run": 0.0,
}


@dataclass
class SkillEfficacyRecord:
    """Aggregated empirical efficacy metrics for a single skill."""

    skill_name: str
    total_dispatches: int = 0
    evaluated_sessions: int = 0
    commits_count: int = 0
    retains_count: int = 0
    discards_count: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    net_score: float = 0.0
    last_dispatched: float = 0.0

    @property
    def total_evaluations(self) -> int:
        return self.commits_count + self.retains_count + self.discards_count

    @property
    def win_rate(self) -> float:
        """Win rate percentage: 100% for commits, 50% for retained, 0% for discards."""
        total = self.total_evaluations
        if total == 0:
            total_tests = self.tests_passed + self.tests_failed
            if total_tests > 0:
                return round((self.tests_passed / total_tests) * 100.0, 1)
            return 0.0
        win_points = self.commits_count + (0.5 * self.retains_count)
        return round((win_points / total) * 100.0, 1)

    @property
    def keep_rate(self) -> float:
        """Percentage of evaluated sessions where changes were retained or committed."""
        total = self.total_evaluations
        if total == 0:
            return 0.0
        return round(((self.commits_count + self.retains_count) / total) * 100.0, 1)

    @property
    def discard_rate(self) -> float:
        """Percentage of evaluated sessions where changes were discarded/reverted."""
        total = self.total_evaluations
        if total == 0:
            return 0.0
        return round((self.discards_count / total) * 100.0, 1)

    @property
    def test_pass_rate(self) -> float:
        """Percentage of automated test runs that passed."""
        total_tests = self.tests_passed + self.tests_failed
        if total_tests == 0:
            return 0.0
        return round((self.tests_passed / total_tests) * 100.0, 1)

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "total_dispatches": self.total_dispatches,
            "evaluated_sessions": self.evaluated_sessions,
            "commits_count": self.commits_count,
            "retains_count": self.retains_count,
            "discards_count": self.discards_count,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "net_score": round(self.net_score, 2),
            "win_rate": self.win_rate,
            "keep_rate": self.keep_rate,
            "discard_rate": self.discard_rate,
            "test_pass_rate": self.test_pass_rate,
            "last_dispatched": self.last_dispatched,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillEfficacyRecord":
        return cls(
            skill_name=data.get("skill_name", ""),
            total_dispatches=data.get("total_dispatches", 0),
            evaluated_sessions=data.get("evaluated_sessions", 0),
            commits_count=data.get("commits_count", 0),
            retains_count=data.get("retains_count", 0),
            discards_count=data.get("discards_count", 0),
            tests_passed=data.get("tests_passed", 0),
            tests_failed=data.get("tests_failed", 0),
            net_score=float(data.get("net_score", 0.0)),
            last_dispatched=float(data.get("last_dispatched", 0.0)),
        )


@dataclass
class AttributionSession:
    """Tracks a dispatch session from prompt evaluation to physical Git/test outcome."""

    session_id: str
    timestamp: float
    prompt: str
    dispatched_skills: List[str]
    workspace_root: str
    initial_commit: Optional[str] = None
    initial_dirty_files: List[str] = field(default_factory=list)
    files_touched: List[str] = field(default_factory=list)
    status: str = "active"  # "active", "evaluated"
    outcome: str = "unknown"  # "committed", "retained", "discarded", "unknown"
    test_outcome: str = "not_run"  # "passed", "failed", "not_run"
    score_delta: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "dispatched_skills": self.dispatched_skills,
            "workspace_root": self.workspace_root,
            "initial_commit": self.initial_commit,
            "initial_dirty_files": self.initial_dirty_files,
            "files_touched": self.files_touched,
            "status": self.status,
            "outcome": self.outcome,
            "test_outcome": self.test_outcome,
            "score_delta": round(self.score_delta, 2),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AttributionSession":
        return cls(
            session_id=data.get("session_id", ""),
            timestamp=float(data.get("timestamp", time.time())),
            prompt=data.get("prompt", ""),
            dispatched_skills=data.get("dispatched_skills", []),
            workspace_root=data.get("workspace_root", ""),
            initial_commit=data.get("initial_commit"),
            initial_dirty_files=data.get("initial_dirty_files", []),
            files_touched=data.get("files_touched", []),
            status=data.get("status", "active"),
            outcome=data.get("outcome", "unknown"),
            test_outcome=data.get("test_outcome", "not_run"),
            score_delta=float(data.get("score_delta", 0.0)),
            notes=data.get("notes", ""),
        )


class GitInspector:
    """Non-blocking, fail-open Git inspection utilities ($0 token cost)."""

    @staticmethod
    def is_git_repo(workspace: Union[str, Path]) -> bool:
        """Return True if workspace directory is inside an initialized Git worktree."""
        try:
            ws = Path(workspace)
            if not ws.exists():
                return False
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            return res.returncode == 0 and "true" in res.stdout.strip().lower()
        except Exception:
            return False

    @staticmethod
    def get_head(workspace: Union[str, Path]) -> Optional[str]:
        """Return the current HEAD commit hash, or None if not a git repo."""
        try:
            ws = Path(workspace)
            if not ws.exists():
                return None
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                out = res.stdout.strip()
                return out if out else None
        except Exception:
            pass
        return None

    @staticmethod
    def get_dirty_files(workspace: Union[str, Path]) -> List[str]:
        """Return list of modified/untracked files from git status porcelain."""
        files: List[str] = []
        try:
            ws = Path(workspace)
            if not ws.exists():
                return files
            res = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if len(line) >= 4:
                        # Git porcelain: XY filename (or XY orig -> new)
                        raw_path = line[3:].strip().strip('"')
                        if " -> " in raw_path:
                            raw_path = raw_path.split(" -> ")[-1].strip().strip('"')
                        if raw_path:
                            files.append(raw_path.replace("\\", "/"))
        except Exception:
            pass
        return sorted(list(set(files)))

    @staticmethod
    def get_committed_files(
        workspace: Union[str, Path], from_commit: str, to_commit: str = "HEAD"
    ) -> List[str]:
        """Return list of files modified in commits between from_commit and to_commit."""
        files: List[str] = []
        try:
            ws = Path(workspace)
            if not ws.exists():
                return files
            res = subprocess.run(
                ["git", "log", f"{from_commit}..{to_commit}", "--name-only", "--pretty=format:"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    clean = line.strip().strip('"')
                    if clean:
                        files.append(clean.replace("\\", "/"))
        except Exception:
            pass
        return sorted(list(set(files)))


class EfficacyTracker:
    """Tracks and evaluates skill attribution sessions and empirical telemetry."""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        workspace_root: Optional[Union[str, Path]] = None,
        max_session_history: int = 300,
    ):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.max_session_history = max_session_history

        if storage_path:
            self.storage_path = Path(storage_path).resolve()
        elif workspace_root is not None:
            self.storage_path = self.workspace_root / WORKSPACE_EFFICACY_REL_PATH
        else:
            # Check if current working directory has .taxonomy directory
            ws_efficacy = self.workspace_root / WORKSPACE_EFFICACY_REL_PATH
            if ws_efficacy.parent.is_dir() or ws_efficacy.exists():
                self.storage_path = ws_efficacy
            else:
                self.storage_path = DEFAULT_GLOBAL_EFFICACY_PATH

        self._skills: Dict[str, SkillEfficacyRecord] = {}
        self._sessions: List[AttributionSession] = []
        self._load()

    def _load(self) -> None:
        """Fail-open load of efficacy telemetry."""
        if not self.storage_path.is_file():
            return
        try:
            text = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(text)
            skills_data = data.get("skills", {})
            for name, sdata in skills_data.items():
                self._skills[name] = SkillEfficacyRecord.from_dict(sdata)

            sessions_data = data.get("sessions", [])
            for sess in sessions_data:
                self._sessions.append(AttributionSession.from_dict(sess))
        except Exception as e:
            logger.warning(f"Could not load efficacy database from {self.storage_path} (failing open): {e}")

    def _save(self) -> None:
        """Fail-open atomic save to storage path."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "last_updated": round(time.time(), 3),
                "skills": {k: v.to_dict() for k, v in self._skills.items()},
                "sessions": [s.to_dict() for s in self._sessions[-self.max_session_history :]],
            }
            content = json.dumps(data, indent=2)

            # Atomic write via tempfile rename
            tmp_fd, tmp_file = tempfile.mkstemp(dir=str(self.storage_path.parent), prefix="eff_", suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp_file, str(self.storage_path))
            except Exception:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
                raise
        except Exception as e:
            logger.warning(f"Failed to save efficacy database to {self.storage_path}: {e}")

    def start_session(
        self,
        skills: List[str],
        prompt: str = "",
        workspace_root: Optional[Union[str, Path]] = None,
        files_touched: Optional[List[str]] = None,
    ) -> AttributionSession:
        """Record the start of a dispatch session, capturing initial Git snapshot."""
        ws = Path(workspace_root).resolve() if workspace_root else self.workspace_root
        head_commit = GitInspector.get_head(ws)
        dirty_files = GitInspector.get_dirty_files(ws)

        now = time.time()
        session_id = uuid.uuid4().hex[:12]
        clean_skills = list(dict.fromkeys(skills))
        session = AttributionSession(
            session_id=session_id,
            timestamp=now,
            prompt=prompt,
            dispatched_skills=clean_skills,
            workspace_root=str(ws),
            initial_commit=head_commit,
            initial_dirty_files=dirty_files,
            files_touched=list(files_touched) if files_touched else [],
            status="active",
            outcome="unknown",
            test_outcome="not_run",
            score_delta=0.0,
            notes="",
        )

        for s_name in clean_skills:
            rec = self._skills.setdefault(s_name, SkillEfficacyRecord(skill_name=s_name))
            rec.total_dispatches += 1
            rec.last_dispatched = now

        self._sessions.append(session)
        self._save()
        return session

    def evaluate_session(
        self,
        session_id: str,
        test_passed: Optional[bool] = None,
        files_touched: Optional[List[str]] = None,
        notes: str = "",
        force_outcome: Optional[str] = None,
    ) -> Optional[AttributionSession]:
        """Evaluate physical Git and test outcome for an active or past session."""
        session: Optional[AttributionSession] = None
        for s in reversed(self._sessions):
            if s.session_id == session_id:
                session = s
                break

        if not session:
            logger.warning(f"Attribution session '{session_id}' not found.")
            return None

        ws = Path(session.workspace_root)
        if files_touched:
            session.files_touched = list(set(session.files_touched + files_touched))

        # 1. Determine Git Outcome
        outcome = "unknown"
        if force_outcome and force_outcome in OUTCOME_WEIGHTS:
            outcome = force_outcome
        elif not GitInspector.is_git_repo(ws):
            # Non-git workspace: Git cannot observe physical outcome
            outcome = "unknown"
        else:
            current_head = GitInspector.get_head(ws)
            current_dirty = GitInspector.get_dirty_files(ws)

            # Detect commit: HEAD changed OR repo started with 0 commits and now has initial commit
            head_advanced = bool(
                (session.initial_commit and current_head and session.initial_commit != current_head)
                or (session.initial_commit is None and current_head is not None)
            )

            if head_advanced:
                if session.initial_commit and current_head:
                    committed_files = GitInspector.get_committed_files(ws, session.initial_commit, current_head)
                else:
                    committed_files = []

                if session.files_touched and committed_files:
                    touched_set = {f.replace("\\", "/").lower() for f in session.files_touched}
                    if any(cf.lower() in touched_set for cf in committed_files):
                        outcome = "committed"
                    elif any(f.lower() in touched_set for f in current_dirty):
                        outcome = "retained"
                    else:
                        outcome = "discarded"
                else:
                    outcome = "committed"
            else:
                # HEAD did not move. Inspect working tree status.
                new_dirty = [f for f in current_dirty if f not in session.initial_dirty_files]
                if session.files_touched:
                    norm_touched = {f.replace("\\", "/").lower() for f in session.files_touched}
                    is_retained = any(f.lower() in norm_touched for f in current_dirty)
                    if is_retained:
                        outcome = "retained"
                    else:
                        # Files were touched during session, but are no longer dirty and no commit was made -> discarded!
                        outcome = "discarded"
                elif new_dirty:
                    outcome = "retained"
                else:
                    outcome = "unknown"

        # 2. Determine Test Outcome
        test_outcome = "not_run"
        if test_passed is True:
            test_outcome = "passed"
        elif test_passed is False:
            test_outcome = "failed"

        # 3. Calculate Score Delta
        score_delta = OUTCOME_WEIGHTS.get(outcome, 0.0) + TEST_WEIGHTS.get(test_outcome, 0.0)

        # 4. Update Dispatched Skills Aggregates (Idempotent update)
        prev_evaluated = session.status == "evaluated"
        prev_outcome = session.outcome if prev_evaluated else None
        prev_test = session.test_outcome if prev_evaluated else None
        prev_score_delta = session.score_delta if prev_evaluated else 0.0

        for s_name in session.dispatched_skills:
            rec = self._skills.setdefault(s_name, SkillEfficacyRecord(skill_name=s_name))
            if prev_evaluated:
                # Rollback previous counts before applying new values
                if prev_outcome == "committed":
                    rec.commits_count = max(0, rec.commits_count - 1)
                elif prev_outcome == "retained":
                    rec.retains_count = max(0, rec.retains_count - 1)
                elif prev_outcome == "discarded":
                    rec.discards_count = max(0, rec.discards_count - 1)

                if prev_test == "passed":
                    rec.tests_passed = max(0, rec.tests_passed - 1)
                elif prev_test == "failed":
                    rec.tests_failed = max(0, rec.tests_failed - 1)

                rec.net_score -= prev_score_delta
            else:
                rec.evaluated_sessions += 1

            if outcome == "committed":
                rec.commits_count += 1
            elif outcome == "retained":
                rec.retains_count += 1
            elif outcome == "discarded":
                rec.discards_count += 1

            if test_outcome == "passed":
                rec.tests_passed += 1
            elif test_outcome == "failed":
                rec.tests_failed += 1

            rec.net_score += score_delta

        # Update Session
        session.status = "evaluated"
        session.outcome = outcome
        session.test_outcome = test_outcome
        session.score_delta = score_delta
        if notes:
            session.notes = notes

        self._save()
        return session

    def record_direct_outcome(
        self,
        skills: List[str],
        outcome: str,
        test_passed: Optional[bool] = None,
        notes: str = "",
        prompt: str = "",
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> AttributionSession:
        """Directly record an evaluated outcome without an explicit prior start_session call."""
        ws = Path(workspace_root).resolve() if workspace_root else self.workspace_root
        session = self.start_session(skills=skills, prompt=prompt, workspace_root=ws)
        evaluated = self.evaluate_session(
            session_id=session.session_id,
            test_passed=test_passed,
            notes=notes,
            force_outcome=outcome,
        )
        return evaluated or session

    def get_skill_stats(self, skill_name: str) -> Optional[SkillEfficacyRecord]:
        """Return empirical efficacy stats for a skill, if recorded."""
        return self._skills.get(skill_name)

    def get_leaderboard(
        self, min_samples: int = 0, sort_by: str = "score"
    ) -> List[SkillEfficacyRecord]:
        """Return skills sorted by empirical efficacy leaderboard criteria."""
        records = [
            r for r in self._skills.values()
            if r.total_evaluations >= min_samples or r.total_dispatches >= min_samples
        ]

        if sort_by == "win_rate":
            records.sort(key=lambda r: (-r.win_rate, -r.net_score, -r.total_dispatches, r.skill_name))
        elif sort_by == "dispatches":
            records.sort(key=lambda r: (-r.total_dispatches, -r.net_score, r.skill_name))
        elif sort_by == "commits":
            records.sort(key=lambda r: (-r.commits_count, -r.net_score, r.skill_name))
        else:  # default: net score
            records.sort(key=lambda r: (-r.net_score, -r.win_rate, -r.total_dispatches, r.skill_name))

        return records

    def get_summary(self) -> Dict[str, Any]:
        """Return structured summary of telemetry across all sessions."""
        total_evals = sum(r.evaluated_sessions for r in self._skills.values())
        top_skills = self.get_leaderboard(min_samples=1, sort_by="score")
        top_skill = top_skills[0].skill_name if top_skills else None

        # Detect any skill with high discard rate
        high_discard = [
            r.skill_name
            for r in self._skills.values()
            if r.total_evaluations >= 3 and r.discard_rate >= 40.0
        ]

        return {
            "total_skills_tracked": len(self._skills),
            "total_sessions": len(self._sessions),
            "total_evaluated_sessions": total_evals,
            "top_skill": top_skill,
            "high_discard_skills": high_discard,
            "storage_path": str(self.storage_path),
        }

    def get_active_sessions(self) -> List[AttributionSession]:
        """Return all active (unevaluated) sessions."""
        return [s for s in self._sessions if s.status == "active"]

    def get_latest_session(self) -> Optional[AttributionSession]:
        """Return the most recent session regardless of status."""
        return self._sessions[-1] if self._sessions else None

    def reset(self) -> None:
        """Reset and wipe efficacy records."""
        self._skills.clear()
        self._sessions.clear()
        self._save()
