"""Zero-token outcome-based empirical efficacy telemetry and git attribution tracker.

Measures physical developer outcomes ($0 token cost, < 1ms execution):
- Commit vs Discard: Did the developer keep and commit code, keep it in working tree, or restore/discard?
- Test verification: Did automated tests (pytest, npm test) pass (exit 0) or fail?
- Telemetry: Aggregates real win rates, keep rates, discard rates, and net empirical scores per skill.
- Fail-Open: Never crashes the caller or breaks agent dispatch on any IO/Git error.
- Authentic Sigmoid Scaling ([-1.5, +1.5]): Bayesian Beta prior shrinkage & sample-size confidence (ISS-15/16).
- Role-Weighted Attribution: Primary vs. partner/guardrail weighting & file-extension domain matching (ISS-17).
- Domain Outcome Profiles: Category-aware outcomes ("consulted" +0.75 for advisory/audit, TDD red-phase protection) (ISS-18).
- Version & Hash Tracking: Historical version archiving and update decay on skill edits (ISS-19).
"""

from dataclasses import dataclass, field
import json
import logging
import math
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
DEFAULT_MAX_SESSION_HISTORY = 200

OUTCOME_WEIGHTS = {
    "committed": 1.0,
    "consulted": 0.75,
    "retained": 0.5,
    "discarded": -2.0,
    "unknown": 0.0,
}

TEST_WEIGHTS = {
    "passed": 1.0,
    "failed": -1.0,
    "tdd_red": 0.0,
    "not_run": 0.0,
}

ADVISORY_CATEGORIES = {
    "security.blockchain",
    "decision.review",
    "mentorship.learning",
    "architecture.system",
}

ADVISORY_SKILLS = {
    "smart-contract-auditor",
    "independent-jury",
    "code-mentor",
    "codebase-researcher",
    "development-director",
}

UI_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".tsx", ".jsx", ".vue", ".svelte", ".html"}
BACKEND_EXTENSIONS = {".py", ".rs", ".go", ".java", ".c", ".cpp", ".sql", ".prisma", ".rb", ".php"}
BLOCKCHAIN_EXTENSIONS = {".sol", ".vy"}


def _get_skill_domain(skill_name: str) -> str:
    """Infer coarse skill domain from name."""
    low = skill_name.lower()
    if any(k in low for k in ("react", "vue", "tailwind", "ui", "frontend", "css", "taste", "impeccable", "unslop")):
        return "frontend"
    if any(k in low for k in ("fastapi", "django", "flask", "backend", "db", "sql", "api", "server", "rust", "go")):
        return "backend"
    if any(k in low for k in ("solidity", "contract", "web3", "foundry", "hardhat")):
        return "blockchain"
    return "general"


@dataclass
class SkillEfficacyRecord:
    """Aggregated empirical efficacy metrics for a single skill."""

    skill_name: str
    total_dispatches: int = 0
    evaluated_sessions: int = 0
    commits_count: int = 0
    consulted_count: int = 0
    retains_count: int = 0
    discards_count: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    net_score: float = 0.0
    last_dispatched: float = 0.0
    version: str = "1.0.0"
    content_hash: str = ""
    version_history: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def total_evaluations(self) -> int:
        return self.commits_count + self.consulted_count + self.retains_count + self.discards_count

    @property
    def win_rate(self) -> float:
        """Win rate percentage: 100% for commits, 75% for consulted, 50% for retained, 0% for discards."""
        total = self.total_evaluations
        if total == 0:
            total_tests = self.tests_passed + self.tests_failed
            if total_tests > 0:
                return round((self.tests_passed / total_tests) * 100.0, 1)
            return 0.0
        win_points = self.commits_count + (0.75 * self.consulted_count) + (0.5 * self.retains_count)
        return round((win_points / total) * 100.0, 1)

    @property
    def keep_rate(self) -> float:
        """Percentage of evaluated sessions where changes were retained, committed, or consulted."""
        total = self.total_evaluations
        if total == 0:
            return 0.0
        return round(((self.commits_count + self.consulted_count + self.retains_count) / total) * 100.0, 1)

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

    def compute_bayesian_win_rate(self, alpha: float = 2.0, beta: float = 2.0) -> float:
        """Compute Bayesian posterior mean win rate with Beta(alpha, beta) prior shrinkage.

        Default prior Beta(2, 2) represents a neutral 50% expectation with 4 pseudo-observations.
        Prevents rich-get-richer runaway on 1-2 lucky evaluations (ISS-16).
        """
        total = self.total_evaluations
        if total == 0:
            total_tests = self.tests_passed + self.tests_failed
            if total_tests == 0:
                return 0.5
            w = float(self.tests_passed)
            l = float(self.tests_failed)
        else:
            w = float(self.commits_count) + (0.75 * self.consulted_count) + (0.5 * self.retains_count)
            l = float(self.discards_count)
            if self.tests_passed or self.tests_failed:
                w += 0.5 * self.tests_passed
                l += 0.5 * self.tests_failed

        return (w + alpha) / (w + l + alpha + beta)

    def compute_bias(
        self,
        max_bias: float = 1.5,
        alpha: float = 2.0,
        beta: float = 2.0,
        half_life_days: float = 30.0,
        current_time: Optional[float] = None,
    ) -> float:
        """Compute bounded sigmoid-normalized empirical efficacy bias in [-max_bias, +max_bias].

        Implements Pitch Deck Pillar 4 & ISS-15/16:
        1. Bayesian Beta prior shrinkage: shrinks win rate toward 50% neutral for small n.
        2. Sample-size confidence scaling: c(N) = N / (N + 4) so 2 lucky wins only give a
           gentle nudge (~0.35), while proven skills over 15+ sessions earn full bias (>1.2).
        3. Authentic Sigmoid transformation: mathematically tanh(x) mapping to [-max_bias, +max_bias].
        4. Exponential recency decay: decays older telemetry over a configurable half-life.
        """
        total = self.total_evaluations + self.tests_passed + self.tests_failed
        if total < 1:
            return 0.0

        # 1. Bayesian posterior mean win rate
        bayes_p = self.compute_bayesian_win_rate(alpha=alpha, beta=beta)
        win_margin = (bayes_p - 0.5) * 2.0  # in [-1.0, +1.0]

        # 2. Sample-size confidence scaling
        confidence = float(total) / (float(total) + 4.0)

        # Directional net score signal
        score_direction = 0.0
        if self.evaluated_sessions > 0:
            avg_score = self.net_score / self.evaluated_sessions
            score_direction = max(-1.0, min(1.0, avg_score / 2.0))

        evidence = (0.7 * win_margin + 0.3 * score_direction) * confidence

        # 3. Sigmoid (tanh) transformation into [-max_bias, +max_bias]
        scaled_bias = max_bias * math.tanh(2.5 * evidence)

        # 4. Exponential recency time-decay
        if self.last_dispatched > 0 and half_life_days > 0:
            now = current_time if current_time is not None else time.time()
            age_seconds = max(0.0, now - self.last_dispatched)
            age_days = age_seconds / 86400.0
            decay = math.pow(0.5, age_days / half_life_days)
            scaled_bias *= decay

        return round(max(-max_bias, min(max_bias, scaled_bias)), 2)

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "total_dispatches": self.total_dispatches,
            "evaluated_sessions": self.evaluated_sessions,
            "commits_count": self.commits_count,
            "consulted_count": self.consulted_count,
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
            "version": self.version,
            "content_hash": self.content_hash,
            "version_history": self.version_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillEfficacyRecord":
        return cls(
            skill_name=data.get("skill_name", ""),
            total_dispatches=data.get("total_dispatches", 0),
            evaluated_sessions=data.get("evaluated_sessions", 0),
            commits_count=data.get("commits_count", 0),
            consulted_count=data.get("consulted_count", 0),
            retains_count=data.get("retains_count", 0),
            discards_count=data.get("discards_count", 0),
            tests_passed=data.get("tests_passed", 0),
            tests_failed=data.get("tests_failed", 0),
            net_score=float(data.get("net_score", 0.0)),
            last_dispatched=float(data.get("last_dispatched", 0.0)),
            version=str(data.get("version", "1.0.0")),
            content_hash=str(data.get("content_hash", "")),
            version_history=dict(data.get("version_history", {})),
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
    outcome: str = "unknown"  # "committed", "consulted", "retained", "discarded", "unknown"
    test_outcome: str = "not_run"  # "passed", "failed", "tdd_red", "not_run"
    score_delta: float = 0.0
    notes: str = ""
    skill_weights: Dict[str, float] = field(default_factory=dict)
    session_mode: str = "standard"  # "standard", "tdd", "audit", "advisory", "review"
    skill_hashes: Dict[str, str] = field(default_factory=dict)
    skill_versions: Dict[str, str] = field(default_factory=dict)

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
            "skill_weights": self.skill_weights,
            "session_mode": self.session_mode,
            "skill_hashes": self.skill_hashes,
            "skill_versions": self.skill_versions,
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
            skill_weights=dict(data.get("skill_weights", {})),
            session_mode=str(data.get("session_mode", "standard")),
            skill_hashes=dict(data.get("skill_hashes", {})),
            skill_versions=dict(data.get("skill_versions", {})),
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
            # Fast check directory and parents for .git marker before invoking subprocess
            curr = ws.resolve()
            found_git = False
            while True:
                if (curr / ".git").exists():
                    found_git = True
                    break
                if curr.parent == curr:
                    break
                curr = curr.parent

            if not found_git:
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
            if not ws.exists() or not GitInspector.is_git_repo(ws):
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
            if not ws.exists() or not GitInspector.is_git_repo(ws):
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
        max_session_history: int = DEFAULT_MAX_SESSION_HISTORY,
    ):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.max_session_history = max_session_history

        if storage_path:
            self.storage_path = Path(storage_path).resolve()
        elif workspace_root is not None:
            self.storage_path = self.workspace_root / WORKSPACE_EFFICACY_REL_PATH
        else:
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
        skill_weights: Optional[Dict[str, float]] = None,
        session_mode: Optional[str] = None,
        skill_hashes: Optional[Dict[str, str]] = None,
        skill_versions: Optional[Dict[str, str]] = None,
    ) -> AttributionSession:
        """Record the start of a dispatch session, capturing initial Git snapshot and attribution roles."""
        ws = Path(workspace_root).resolve() if workspace_root else self.workspace_root
        head_commit = GitInspector.get_head(ws)
        dirty_files = GitInspector.get_dirty_files(ws)

        now = time.time()
        session_id = uuid.uuid4().hex[:12]
        clean_skills = list(dict.fromkeys(skills))

        # Default role weights (ISS-17): lead specialist 1.0, secondary/partners 0.5, sentry/guards 0.25
        resolved_weights: Dict[str, float] = {}
        for idx, s_name in enumerate(clean_skills):
            if skill_weights and s_name in skill_weights:
                resolved_weights[s_name] = float(skill_weights[s_name])
            elif idx == 0:
                resolved_weights[s_name] = 1.0
            elif s_name in ("engineering-quality-gate", "development-director"):
                resolved_weights[s_name] = 0.25
            else:
                resolved_weights[s_name] = 0.5

        # Infer session mode if not explicitly supplied (ISS-18)
        mode = session_mode or "standard"
        if not session_mode:
            low_p = prompt.lower()
            if "tdd" in low_p or "failing test" in low_p or "red phase" in low_p:
                mode = "tdd"
            elif any(s in ADVISORY_SKILLS for s in clean_skills):
                mode = "advisory"

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
            skill_weights=resolved_weights,
            session_mode=mode,
            skill_hashes=dict(skill_hashes) if skill_hashes else {},
            skill_versions=dict(skill_versions) if skill_versions else {},
        )

        for s_name in clean_skills:
            rec = self._skills.setdefault(s_name, SkillEfficacyRecord(skill_name=s_name))
            rec.total_dispatches += 1
            rec.last_dispatched = now
            if skill_hashes and s_name in skill_hashes and not rec.content_hash:
                rec.content_hash = skill_hashes[s_name]
                if skill_versions and s_name in skill_versions:
                    rec.version = skill_versions[s_name]

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
            session.files_touched = sorted(list(set(session.files_touched + files_touched)))

        # 1. Determine Git / Advisory Outcome (ISS-18)
        outcome = "unknown"
        if force_outcome and force_outcome in OUTCOME_WEIGHTS:
            outcome = force_outcome
        elif not GitInspector.is_git_repo(ws):
            # Non-git workspace: if advisory/review, mark consulted; else unknown
            if session.session_mode in ("advisory", "audit", "review") or any(s in ADVISORY_SKILLS for s in session.dispatched_skills):
                outcome = "consulted"
            else:
                outcome = "unknown"
        else:
            current_head = GitInspector.get_head(ws)
            current_dirty = GitInspector.get_dirty_files(ws)

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
                    elif session.session_mode in ("advisory", "audit", "review"):
                        outcome = "consulted"
                    else:
                        outcome = "discarded"
                else:
                    outcome = "committed"
            else:
                new_dirty = [f for f in current_dirty if f not in session.initial_dirty_files]
                if session.files_touched:
                    norm_touched = {f.replace("\\", "/").lower() for f in session.files_touched}
                    is_retained = any(f.lower() in norm_touched for f in current_dirty)
                    if is_retained:
                        outcome = "retained"
                    elif session.session_mode in ("advisory", "audit", "review"):
                        outcome = "consulted"
                    else:
                        outcome = "discarded"
                elif new_dirty:
                    outcome = "retained"
                elif session.session_mode in ("advisory", "audit", "review") or any(s in ADVISORY_SKILLS for s in session.dispatched_skills):
                    outcome = "consulted"
                else:
                    outcome = "unknown"

        # 2. Determine Test Outcome (ISS-18: TDD red phase protection)
        test_outcome = "not_run"
        if test_passed is True:
            test_outcome = "passed"
        elif test_passed is False:
            if session.session_mode == "tdd":
                test_outcome = "tdd_red"  # Failing test during TDD red phase is intentional (0.0 weight)
            else:
                test_outcome = "failed"

        # 3. Calculate Base Score Delta
        base_delta = OUTCOME_WEIGHTS.get(outcome, 0.0) + TEST_WEIGHTS.get(test_outcome, 0.0)

        # 4. Domain Extension Analysis for Per-Skill Attribution Weighting (ISS-17)
        effective_weights = dict(session.skill_weights)
        if len(session.dispatched_skills) > 1 and session.files_touched:
            touched_exts = {Path(f).suffix.lower() for f in session.files_touched if Path(f).suffix}
            has_ui_exts = bool(touched_exts & UI_EXTENSIONS)
            has_backend_exts = bool(touched_exts & BACKEND_EXTENSIONS)
            has_blockchain_exts = bool(touched_exts & BLOCKCHAIN_EXTENSIONS)

            domains_in_pod = {_get_skill_domain(s) for s in session.dispatched_skills}

            for s_name in session.dispatched_skills:
                s_dom = _get_skill_domain(s_name)
                curr_w = effective_weights.get(s_name, 1.0)
                # Dampen credit/penalty if files touched are exclusively in another domain and that domain is represented in the pod
                if s_dom == "frontend" and not has_ui_exts and (has_backend_exts or has_blockchain_exts) and ("backend" in domains_in_pod or "blockchain" in domains_in_pod):
                    effective_weights[s_name] = round(curr_w * 0.25, 2)
                elif s_dom == "backend" and not has_backend_exts and (has_ui_exts or has_blockchain_exts) and ("frontend" in domains_in_pod or "blockchain" in domains_in_pod):
                    effective_weights[s_name] = round(curr_w * 0.25, 2)
                elif s_dom == "blockchain" and not has_blockchain_exts and (has_ui_exts or has_backend_exts) and ("frontend" in domains_in_pod or "backend" in domains_in_pod):
                    effective_weights[s_name] = round(curr_w * 0.25, 2)

        session.skill_weights = effective_weights

        # 5. Update Dispatched Skills Aggregates (Idempotent update + Version Tracking ISS-19)
        prev_evaluated = session.status == "evaluated"
        prev_outcome = session.outcome if prev_evaluated else None
        prev_test = session.test_outcome if prev_evaluated else None
        prev_score_delta = session.score_delta if prev_evaluated else 0.0

        for s_name in session.dispatched_skills:
            rec = self._skills.setdefault(s_name, SkillEfficacyRecord(skill_name=s_name))
            skill_w = session.skill_weights.get(s_name, 1.0)

            # Rollback previous session impact if re-evaluating
            if prev_evaluated:
                if prev_outcome == "committed":
                    rec.commits_count = max(0, rec.commits_count - 1)
                elif prev_outcome == "consulted":
                    rec.consulted_count = max(0, rec.consulted_count - 1)
                elif prev_outcome == "retained":
                    rec.retains_count = max(0, rec.retains_count - 1)
                elif prev_outcome == "discarded":
                    rec.discards_count = max(0, rec.discards_count - 1)

                if prev_test == "passed":
                    rec.tests_passed = max(0, rec.tests_passed - 1)
                elif prev_test == "failed":
                    rec.tests_failed = max(0, rec.tests_failed - 1)

                rec.net_score -= prev_score_delta * skill_w
            else:
                rec.evaluated_sessions += 1

            # Version / Content Hash Update & Archiving (ISS-19)
            new_hash = session.skill_hashes.get(s_name)
            new_ver = session.skill_versions.get(s_name, "1.0.0")
            if new_hash and rec.content_hash and new_hash != rec.content_hash:
                archive_key = f"{rec.version}@{rec.content_hash[:8]}"
                rec.version_history[archive_key] = {
                    "version": rec.version,
                    "content_hash": rec.content_hash,
                    "commits_count": rec.commits_count,
                    "consulted_count": rec.consulted_count,
                    "retains_count": rec.retains_count,
                    "discards_count": rec.discards_count,
                    "tests_passed": rec.tests_passed,
                    "tests_failed": rec.tests_failed,
                    "net_score": round(rec.net_score, 2),
                    "archived_at": time.time(),
                }
                # Decay historical metrics by 50% on skill modification
                rec.commits_count = int(rec.commits_count * 0.5)
                rec.consulted_count = int(rec.consulted_count * 0.5)
                rec.retains_count = int(rec.retains_count * 0.5)
                rec.discards_count = int(rec.discards_count * 0.5)
                rec.tests_passed = int(rec.tests_passed * 0.5)
                rec.tests_failed = int(rec.tests_failed * 0.5)
                rec.net_score = round(rec.net_score * 0.5, 2)
                rec.content_hash = new_hash
                rec.version = new_ver
            elif new_hash and not rec.content_hash:
                rec.content_hash = new_hash
                rec.version = new_ver

            # Apply new outcome counts
            if outcome == "committed":
                rec.commits_count += 1
            elif outcome == "consulted":
                rec.consulted_count += 1
            elif outcome == "retained":
                rec.retains_count += 1
            elif outcome == "discarded":
                rec.discards_count += 1

            if test_outcome == "passed":
                rec.tests_passed += 1
            elif test_outcome == "failed":
                rec.tests_failed += 1

            rec.net_score += base_delta * skill_w

        # Update Session
        session.status = "evaluated"
        session.outcome = outcome
        session.test_outcome = test_outcome
        session.score_delta = base_delta
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

    def compute_efficacy_bias(
        self,
        skill_name: str,
        max_bias: float = 1.5,
        half_life_days: float = 30.0,
    ) -> float:
        """Compute empirical outcome efficacy bias [-max_bias, +max_bias] using sigmoid scaling (ISS-15/16)."""
        rec = self._skills.get(skill_name)
        if not rec:
            return 0.0
        return rec.compute_bias(max_bias=max_bias, half_life_days=half_life_days)

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
