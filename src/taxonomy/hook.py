"""In-process integration hook for development-director and Antigravity orchestrators."""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from taxonomy.indexer import DEFAULT_SKILL_ROOTS, SkillIndexer
from taxonomy.models import GateResult, ResolutionResult
from taxonomy.resolver import SkillResolver

logger = logging.getLogger("taxonomy.hook")

_GLOBAL_INDEXER: Optional[SkillIndexer] = None
_GLOBAL_RESOLVER: Optional[SkillResolver] = None
_GLOBAL_ROOTS_KEY: Optional[Tuple[str, ...]] = None


def _normalize_roots_key(skills_roots: Optional[List[Path | str]]) -> Tuple[str, ...]:
    roots = skills_roots if skills_roots is not None else DEFAULT_SKILL_ROOTS
    return tuple(str(Path(r).expanduser().resolve(strict=False)) for r in roots)


def init_dispatcher(
    skills_roots: Optional[List[Path | str]] = None,
    max_skills: Optional[int] = None,
    workspace_root: Optional[Path | str] = None,
) -> None:
    """Initialize or refresh the in-memory global dispatcher singleton."""
    global _GLOBAL_INDEXER, _GLOBAL_RESOLVER, _GLOBAL_ROOTS_KEY
    _GLOBAL_ROOTS_KEY = _normalize_roots_key(skills_roots)
    _GLOBAL_INDEXER = SkillIndexer(skills_roots)
    _GLOBAL_INDEXER.scan()
    _GLOBAL_RESOLVER = SkillResolver(_GLOBAL_INDEXER, max_skills=max_skills, workspace_root=workspace_root)


def dispatch_prompt(
    prompt: str,
    skills_roots: Optional[List[Path | str]] = None,
    max_skills: Optional[int] = None,
    force_route: bool = False,
    phase: Optional[str] = None,
    prefer: Optional[str | List[str]] = None,
    workspace_root: Optional[Path | str] = None,
) -> ResolutionResult:
    """Fail-open in-process library call to route user prompt to matching skills.

    Guarantees:
    - Never throws an unhandled exception (fails open).
    - Sub-millisecond gate execution on casual chat.
    - Respects dynamic skills_roots and max_skills changes across calls.
    - Phase-aware filtering when phase is specified ('architecture', 'implementation', 'verification', 'review').
    - Deterministic taste preferences and CLI prefer overrides.
    """
    global _GLOBAL_RESOLVER, _GLOBAL_INDEXER, _GLOBAL_ROOTS_KEY
    try:
        requested_key = _normalize_roots_key(skills_roots)
        if _GLOBAL_RESOLVER is None or _GLOBAL_INDEXER is None or _GLOBAL_ROOTS_KEY != requested_key:
            init_dispatcher(skills_roots, max_skills=max_skills, workspace_root=workspace_root)
        else:
            if max_skills is not None:
                _GLOBAL_RESOLVER.max_skills = max_skills
            else:
                from taxonomy.resolver import compute_dynamic_budget
                active_cnt = len([s for s in _GLOBAL_INDEXER.all_skills if s.status != "deprecated"])
                _GLOBAL_RESOLVER.max_skills = compute_dynamic_budget(active_cnt)
            # Quick check if mtime changed on disk (almost free in-memory)
            _GLOBAL_INDEXER.scan(force=False)
            from taxonomy.taste import load_taste_profile
            _GLOBAL_RESOLVER.taste_profile = load_taste_profile(workspace_root=workspace_root)

        return _GLOBAL_RESOLVER.resolve(prompt, force_route=force_route, phase=phase, prefer=prefer)
    except Exception as e:
        logger.error(f"Taxonomy dispatcher fail-open error: {e}", exc_info=True)
        return ResolutionResult(
            gate=GateResult(should_route=False, tier=1, reason="fail_open_exception"),
            selected_skills=[],
            category_scores={},
            total_latency_ms=0.0,
        )
