"""Lifecycle State Machine & Mid-Session Dynamic Re-Routing (ISS-14).

Provides:
- TaskLifecycleStage and TaskLifecycleStateMachine with forward progression and backward transition on test failure.
- Canonical phase aliases and normalized category mappings for all development stages.
- Observation-driven dynamic re-dispatch (redispatch_on_observation) responding to touched files, test results, and error logs.
"""

from enum import Enum
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Canonical lifecycle stages
class TaskLifecycleStage(str, Enum):
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    EVALUATION = "evaluation"
    COMPLETED = "completed"


# Phase string normalization aliases
PHASE_ALIASES: Dict[str, str] = {
    # Understanding / Exploration
    "understand": "understanding",
    "understanding": "understanding",
    "discovery": "understanding",
    "discover": "understanding",
    "explore": "understanding",
    "exploration": "understanding",
    # Planning / Architecture / Design
    "plan": "planning",
    "planning": "planning",
    "design": "design",
    "architecture": "architecture",
    "arch": "architecture",
    # Implementation
    "impl": "implementation",
    "implement": "implementation",
    "implementation": "implementation",
    "code": "implementation",
    "coding": "implementation",
    "build": "implementation",
    "fix": "implementation",
    # Verification / QA / Testing
    "verify": "verification",
    "verification": "verification",
    "test": "verification",
    "testing": "verification",
    "qa": "verification",
    # Evaluation / Review / Courtroom
    "review": "review",
    "eval": "evaluation",
    "evaluate": "evaluation",
    "evaluation": "evaluation",
    "audit": "review",
    "jury": "review",
}

# Canonical phase category mappings
LIFECYCLE_PHASE_CATEGORY_MAP: Dict[str, Set[str]] = {
    "understanding": {
        "mentorship.learning", "orchestration.lead", "decision.review",
        "general", "agy.guide",
    },
    "planning": {
        "orchestration.lead", "decision.review", "mentorship.learning",
        "ui.design", "ui.reference", "general", "agy.customization", "agy.guide",
    },
    "design": {
        "ui.design", "ui.taste", "ui.reference", "ui.marketing", "ui.product",
        "ui.component", "orchestration.lead", "decision.review", "general",
    },
    "architecture": {
        "orchestration.lead", "decision.review", "mentorship.learning",
        "general", "agy.customization", "agy.guide",
    },
    "implementation": {
        "ui.frontend", "ui.design", "ui.marketing", "ui.product", "ui.cleanup",
        "ui.component", "ui.animation", "ui.polish", "ui.reference",
        "frontend.engineering", "frontend.react", "backend.api",
        "security.blockchain", "ops.performance", "orchestration.lead",
        "agy.automation", "agy.ui", "agy.plugin", "agy.github", "agy.skills",
    },
    "verification": {
        "verification.qa", "quality.animation", "ops.performance",
        "security.blockchain", "decision.review",
    },
    "review": {
        "decision.review", "orchestration.lead", "verification.qa",
        "quality.animation", "mentorship.learning", "security.blockchain",
    },
    "evaluation": {
        "decision.review", "orchestration.lead", "verification.qa",
        "quality.animation", "mentorship.learning", "security.blockchain",
    },
}


def normalize_phase_name(phase: Optional[str]) -> Optional[str]:
    """Map any phase string or alias to its canonical phase name."""
    if not phase:
        return None
    cleaned = phase.lower().strip()
    return PHASE_ALIASES.get(cleaned, cleaned)


def get_categories_for_phase(phase: Optional[str]) -> Optional[Set[str]]:
    """Return the set of allowed skill categories for a normalized phase."""
    canonical = normalize_phase_name(phase)
    if not canonical:
        return None
    return LIFECYCLE_PHASE_CATEGORY_MAP.get(canonical)


class TaskLifecycleStateMachine:
    """Manages progression across task lifecycle stages with backward transitions on failure."""

    FORWARD_PROGRESSION: Tuple[TaskLifecycleStage, ...] = (
        TaskLifecycleStage.UNDERSTANDING,
        TaskLifecycleStage.PLANNING,
        TaskLifecycleStage.IMPLEMENTATION,
        TaskLifecycleStage.VERIFICATION,
        TaskLifecycleStage.EVALUATION,
        TaskLifecycleStage.COMPLETED,
    )

    def __init__(self, initial_stage: TaskLifecycleStage = TaskLifecycleStage.PLANNING):
        self.current_stage: TaskLifecycleStage = initial_stage
        self.stage_history: List[Dict[str, Any]] = [
            {
                "stage": initial_stage.value,
                "timestamp": round(time.time(), 3),
                "reason": "initialized",
            }
        ]

    def advance(self, reason: str = "stage_completed") -> TaskLifecycleStage:
        """Advance to the next sequential lifecycle stage."""
        try:
            curr_idx = self.FORWARD_PROGRESSION.index(self.current_stage)
            if curr_idx < len(self.FORWARD_PROGRESSION) - 1:
                next_stage = self.FORWARD_PROGRESSION[curr_idx + 1]
                return self.transition_to(next_stage, reason=reason)
        except ValueError:
            pass
        return self.current_stage

    def transition_to(self, new_stage: TaskLifecycleStage, reason: str) -> TaskLifecycleStage:
        """Explicitly transition to a target stage with reason recording."""
        self.current_stage = new_stage
        self.stage_history.append({
            "stage": new_stage.value,
            "timestamp": round(time.time(), 3),
            "reason": reason,
        })
        return self.current_stage

    def on_test_failure(self, error_summary: str = "") -> TaskLifecycleStage:
        """Backward transition: regress from verification/evaluation back to implementation on test failure."""
        reason = f"test_failure: {error_summary.strip()}" if error_summary else "test_failure"
        return self.transition_to(TaskLifecycleStage.IMPLEMENTATION, reason=reason)

    def on_review_objection(self, objection: str = "") -> TaskLifecycleStage:
        """Backward transition: regress from evaluation back to planning or implementation."""
        reason = f"review_objection: {objection.strip()}" if objection else "review_objection"
        return self.transition_to(TaskLifecycleStage.PLANNING, reason=reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_stage": self.current_stage.value,
            "stage_history": list(self.stage_history),
        }


# File extension heuristics for mid-session domain detection
FILE_EXTENSION_DOMAIN_HINTS: Dict[str, Tuple[str, ...]] = {
    ".sql": ("backend.api", "database", "sql"),
    ".prisma": ("backend.api", "database", "prisma"),
    ".tsx": ("ui.frontend", "frontend.react", "frontend.engineering"),
    ".jsx": ("ui.frontend", "frontend.react"),
    ".vue": ("ui.frontend", "frontend.engineering"),
    ".svelte": ("ui.frontend", "frontend.engineering"),
    ".css": ("ui.frontend", "styling"),
    ".scss": ("ui.frontend", "styling"),
    ".tailwind": ("ui.frontend", "tailwind"),
    ".sol": ("security.blockchain", "smart-contract", "solidity"),
    ".vy": ("security.blockchain", "vyper"),
    ".py": ("backend.api", "python"),
    ".rs": ("backend.api", "rust"),
    ".go": ("backend.api", "golang"),
    ".dockerfile": ("devops.ci", "docker"),
}


def detect_domains_from_files(files_touched: List[str]) -> Tuple[Set[str], Set[str]]:
    """Inspect modified files to extract relevant technical keywords and target categories."""
    keywords: Set[str] = set()
    categories: Set[str] = set()

    for file_path in files_touched:
        p_lower = file_path.lower().replace("\\", "/")
        # Extension matching
        for ext, (primary_cat, *kws) in FILE_EXTENSION_DOMAIN_HINTS.items():
            if p_lower.endswith(ext):
                categories.add(primary_cat)
                keywords.update(kws)
        # Path segment matching
        if "/components/" in p_lower or "/ui/" in p_lower or "/views/" in p_lower:
            keywords.add("ui")
            keywords.add("frontend")
            categories.add("ui.frontend")
        elif "/migrations/" in p_lower or "/db/" in p_lower:
            keywords.add("database")
            keywords.add("migration")
            categories.add("backend.api")
        elif "/tests/" in p_lower or "/test_" in p_lower or ".spec." in p_lower:
            keywords.add("verification")
            keywords.add("testing")
            categories.add("verification.qa")

    return keywords, categories


def redispatch_on_observation(
    resolver: Any,
    current_result: Optional[Any] = None,
    files_touched: Optional[List[str]] = None,
    test_passed: Optional[bool] = None,
    error_output: Optional[str] = None,
    observation: Optional[str] = None,
    phase: Optional[str] = None,
    lifecycle_state: Optional[TaskLifecycleStateMachine] = None,
) -> Any:
    """Mid-session dynamic re-routing responding to test failures, file reads, or error logs (ISS-14)."""
    effective_phase = phase

    # 1. Handle test failure backward transition
    if test_passed is False or (error_output and ("fail" in error_output.lower() or "error" in error_output.lower())):
        if lifecycle_state:
            lifecycle_state.on_test_failure(error_output or "tests failed")
        if not effective_phase:
            effective_phase = "implementation"

    # 2. Extract technical hints from touched files
    domain_kws: Set[str] = set()
    if files_touched:
        kws, _ = detect_domains_from_files(files_touched)
        domain_kws.update(kws)

    # 3. Formulate the dynamic prompt
    prompt_parts: List[str] = []
    if observation:
        prompt_parts.append(observation)
    elif error_output:
        summary = error_output.strip().splitlines()[-1] if error_output.strip() else error_output
        prompt_parts.append(f"Fix error: {summary[:120]}")
    elif files_touched:
        files_str = ", ".join(files_touched[:3])
        prompt_parts.append(f"Update and verify files: {files_str}")
    elif current_result and current_result.gate:
        prompt_parts.append("Continue implementation and verification")
    else:
        prompt_parts.append("Update implementation")

    if domain_kws:
        prompt_parts.append(" ".join(sorted(domain_kws)))

    combined_prompt = " - ".join(prompt_parts)

    # 4. Re-dispatch through resolver with updated phase and observations
    return resolver.resolve(
        combined_prompt,
        force_route=True,
        phase=effective_phase,
    )
