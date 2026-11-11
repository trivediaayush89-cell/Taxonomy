"""Central extensible registry and cross-platform path resolution for Skill Taxonomy Dispatcher.

Decouples core engine from hardcoded personal skill names, local paths, and environment bindings:
- Standard XDG / TAXONOMY_HOME / ~/.gemini path hierarchy.
- Pluggable Quality Sentry registry with configurable override policy.
- Extensible stack-to-skill ecosystem mapping registry.
- Pluggable meta-tooling and category registration.
"""

import os
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Union


# =====================================================================
# 1. Cross-Platform Directory & Configuration Paths
# =====================================================================

def get_taxonomy_home() -> Path:
    """Resolve the base configuration and data directory.

    Priority:
    1. TAXONOMY_HOME environment variable
    2. ~/.gemini/taxonomy (if directory exists, for backward compatibility)
    3. XDG_CONFIG_HOME/taxonomy (standard Linux/macOS)
    4. ~/.config/taxonomy (standard default)
    """
    if "TAXONOMY_HOME" in os.environ and os.environ["TAXONOMY_HOME"].strip():
        return Path(os.environ["TAXONOMY_HOME"]).expanduser().resolve()

    gemini_path = Path("~/.gemini/taxonomy").expanduser().resolve()
    if gemini_path.is_dir():
        return gemini_path

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config and xdg_config.strip():
        return (Path(xdg_config).expanduser() / "taxonomy").resolve()

    return Path("~/.config/taxonomy").expanduser().resolve()


def get_default_taste_path() -> Path:
    """Resolve the default user taste.json configuration path."""
    if "TAXONOMY_HOME" in os.environ and os.environ["TAXONOMY_HOME"].strip():
        return (Path(os.environ["TAXONOMY_HOME"]).expanduser() / "taste.json").resolve()

    gemini_file = Path("~/.gemini/taxonomy/taste.json").expanduser().resolve()
    if gemini_file.is_file():
        return gemini_file

    return get_taxonomy_home() / "taste.json"


# =====================================================================
# 2. Quality Sentry Registry & Judicial Guardrail Policy
# =====================================================================

DEFAULT_PROTECTED_SENTRIES: FrozenSet[str] = frozenset({
    "engineering-quality-gate",
    "independent-jury",
})

DEFAULT_SENTRY_CATEGORIES: FrozenSet[str] = frozenset({
    "decision.review",
    "verification.qa",
})

_ACTIVE_PROTECTED_SENTRIES: Set[str] = set(DEFAULT_PROTECTED_SENTRIES)
_ACTIVE_SENTRY_CATEGORIES: Set[str] = set(DEFAULT_SENTRY_CATEGORIES)


def get_protected_sentries() -> Set[str]:
    """Return a copy of currently registered protected quality sentries."""
    return set(_ACTIVE_PROTECTED_SENTRIES)


def get_sentry_categories() -> Set[str]:
    """Return a copy of currently registered protected Quality Sentry categories."""
    return set(_ACTIVE_SENTRY_CATEGORIES)


def register_protected_sentry(skill_name: str) -> None:
    """Register an additional skill as a protected Quality Sentry."""
    clean = skill_name.strip().lower()
    if clean:
        _ACTIVE_PROTECTED_SENTRIES.add(clean)


def unregister_protected_sentry(skill_name: str) -> None:
    """Remove a skill from the protected Quality Sentry registry."""
    _ACTIVE_PROTECTED_SENTRIES.discard(skill_name.strip().lower())


def register_sentry_category(category: str) -> None:
    """Register an additional category as protected sentries."""
    clean = category.strip().lower()
    if clean:
        _ACTIVE_SENTRY_CATEGORIES.add(clean)


def unregister_sentry_category(category: str) -> None:
    """Remove a category from protected sentries."""
    _ACTIVE_SENTRY_CATEGORIES.discard(category.strip().lower())


def reset_protected_sentries() -> None:
    """Reset the Quality Sentry registry to system defaults."""
    global _ACTIVE_PROTECTED_SENTRIES, _ACTIVE_SENTRY_CATEGORIES
    _ACTIVE_PROTECTED_SENTRIES = set(DEFAULT_PROTECTED_SENTRIES)
    _ACTIVE_SENTRY_CATEGORIES = set(DEFAULT_SENTRY_CATEGORIES)


def is_protected_sentry(skill: Union[str, Any], allow_override: bool = False) -> bool:
    """Check if a skill is an active protected Quality Sentry.

    If allow_override=True (e.g. caller passed --force or allow_sentry_override=True),
    the sentry immunity is bypassed and this returns False.
    """
    if allow_override:
        return False

    if isinstance(skill, str):
        name = skill.strip().lower()
    elif hasattr(skill, "name"):
        name = str(skill.name).strip().lower()
    else:
        return False

    return name in _ACTIVE_PROTECTED_SENTRIES


# =====================================================================
# 3. Stack-to-Skill Ecosystem Alignment Registry
# =====================================================================

DEFAULT_STACK_ALIGNMENTS: Dict[str, List[Dict[str, Any]]] = {
    "nextjs": [
        {"category": "frontend.react", "skill": "vercel-react-best-practices", "weight": 2.0},
    ],
    "react": [
        {"category": "frontend.react", "skill": "vercel-react-best-practices", "weight": 1.5},
    ],
    "tailwind": [
        {"category": "frontend.engineering", "skill": "frontend-ui-engineering", "weight": 1.5},
    ],
    "solidity": [
        {"category": "security.blockchain", "skill": "smart-contract-auditor", "weight": 2.5},
    ],
    "testing": [
        {"category": "verification.qa", "skill": "engineering-quality-gate", "weight": 2.0},
    ],
}

_ACTIVE_STACK_ALIGNMENTS: Dict[str, List[Dict[str, Any]]] = {
    k: list(v) for k, v in DEFAULT_STACK_ALIGNMENTS.items()
}


def register_stack_alignment(ecosystem: str, category: str, skill_name: str, weight: float = 2.0) -> None:
    """Register or customize a stack ecosystem recommendation alignment."""
    eco = ecosystem.strip().lower()
    entry = {"category": category.strip(), "skill": skill_name.strip(), "weight": float(weight)}
    if eco not in _ACTIVE_STACK_ALIGNMENTS:
        _ACTIVE_STACK_ALIGNMENTS[eco] = []
    _ACTIVE_STACK_ALIGNMENTS[eco].append(entry)


def get_stack_alignments() -> Dict[str, List[Dict[str, Any]]]:
    """Return all active stack-to-skill ecosystem alignments."""
    return {k: list(v) for k, v in _ACTIVE_STACK_ALIGNMENTS.items()}


def reset_stack_alignments() -> None:
    """Reset stack alignments to default configuration."""
    global _ACTIVE_STACK_ALIGNMENTS
    _ACTIVE_STACK_ALIGNMENTS = {k: list(v) for k, v in DEFAULT_STACK_ALIGNMENTS.items()}


# =====================================================================
# 4. Meta Categories Registry
# =====================================================================

DEFAULT_META_CATEGORIES: FrozenSet[str] = frozenset({
    "agy.customization", "agy.guide", "agy.plugin", "agy.skills", "agy.migration",
    "antigravity.config", "antigravity.docs", "ecosystem.plugin", "tooling.migration",
})

DEFAULT_META_SKILL_NAMES: FrozenSet[str] = frozenset({
    "agy-customizations", "antigravity-guide", "automation", "generative_ui",
    "migrate-agent-settings", "migrate-workflows", "swarm", "permissioned-github",
    "plugin", "run-workflow", "swarm_monitor", "swarm_narrator", "ui-plugin-navigation",
})

_ACTIVE_META_CATEGORIES: Set[str] = set(DEFAULT_META_CATEGORIES)
_ACTIVE_META_SKILLS: Set[str] = set(DEFAULT_META_SKILL_NAMES)


def get_meta_categories() -> Set[str]:
    """Return currently recognized meta/platform tooling categories."""
    return set(_ACTIVE_META_CATEGORIES)


def register_meta_category(category: str) -> None:
    """Register an additional category as meta/platform tooling."""
    clean = category.strip().lower()
    if clean:
        _ACTIVE_META_CATEGORIES.add(clean)


def get_meta_skills() -> Set[str]:
    """Return currently recognized meta/platform tooling skill names."""
    return set(_ACTIVE_META_SKILLS)


def register_meta_skill(skill_name: str) -> None:
    """Register an additional skill name as meta/platform tooling."""
    clean = skill_name.strip().lower()
    if clean:
        _ACTIVE_META_SKILLS.add(clean)


def is_meta_skill(skill: Union[str, Any]) -> bool:
    """Check if a skill belongs to the meta/platform tooling registry."""
    if isinstance(skill, str):
        name = skill.strip().lower()
        cat = ""
    elif hasattr(skill, "name"):
        name = str(skill.name).strip().lower()
        cat = str(getattr(skill, "category", "")).strip().lower()
    else:
        return False

    if name in _ACTIVE_META_SKILLS or name.startswith(("agy-", "antigravity-")):
        return True
    if cat and cat in _ACTIVE_META_CATEGORIES:
        return True
    return False
