"""User taste profiles, hierarchical preference loading, and deterministic scoring bias."""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Set, Tuple
import yaml

from taxonomy.models import SkillMetadata
from taxonomy.schema import FRONTMATTER_REGEX

logger = logging.getLogger("taxonomy.taste")

DEFAULT_USER_TASTE_PATH = Path("~/.gemini/taxonomy/taste.json").expanduser()
FALLBACK_USER_PROFILE_PATH = Path("~/.gemini/developer-profile.local.md").expanduser()
WORKSPACE_TASTE_REL_PATH = Path(".taxonomy/taste.json")

TASTE_FENCE_REGEX = re.compile(
    r"```(?:json:taste|taste)\s*\r?\n(.*?)\r?\n```",
    re.DOTALL | re.IGNORECASE,
)

ALLOWED_SCHEMA_KEYS = frozenset({"version", "preferred_skills", "avoid_skills", "weights"})

# In-memory mtime cache: path_str -> (mtime, Optional[TasteProfile])
_TASTE_CACHE: Dict[str, Tuple[float, Optional["TasteProfile"]]] = {}


def clear_taste_cache() -> None:
    """Clear in-memory cache for deterministic testing."""
    _TASTE_CACHE.clear()


def validate_taste_schema(data: object) -> Tuple[bool, List[str]]:
    """Validate a parsed dictionary against schemas/taste.schema.json rules."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return False, ["Root value must be a JSON object"]

    if "version" not in data:
        errors.append("Missing required property 'version'")
    elif not isinstance(data["version"], int) or isinstance(data["version"], bool) or data["version"] < 1:
        errors.append("'version' must be an integer >= 1")

    unknown_keys = set(data.keys()) - ALLOWED_SCHEMA_KEYS
    if unknown_keys:
        errors.append(f"Additional properties not allowed: {sorted(unknown_keys)}")

    if "preferred_skills" in data:
        pref = data["preferred_skills"]
        if not isinstance(pref, dict):
            errors.append("'preferred_skills' must be an object")
        else:
            for k, v in pref.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    errors.append(f"'preferred_skills' entries must map string to string (got {k!r}: {v!r})")

    if "avoid_skills" in data:
        avoid = data["avoid_skills"]
        if not isinstance(avoid, list) or not all(isinstance(x, str) for x in avoid):
            errors.append("'avoid_skills' must be an array of strings")

    if "weights" in data:
        weights = data["weights"]
        if not isinstance(weights, dict):
            errors.append("'weights' must be an object")
        else:
            for k, v in weights.items():
                if not isinstance(k, str) or isinstance(v, bool) or not isinstance(v, (int, float)):
                    errors.append(f"'weights[{k!r}]' must be a number")
                elif float(v) < -3.0 or float(v) > 3.0:
                    errors.append(f"'weights[{k!r}]' ({v}) out of [-3.0, 3.0] bounds")

    return len(errors) == 0, errors


@dataclass
class TasteProfile:
    """Declarative user or workspace taste profile."""

    version: int = 1
    preferred_skills: Dict[str, str] = field(default_factory=dict)
    avoid_skills: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)
    source: Optional[str] = None  # "workspace", "user", "workspace+user", "cli", or None
    path: Optional[Path] = None
    mtime: float = 0.0

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "preferred_skills": dict(self.preferred_skills),
            "avoid_skills": list(self.avoid_skills),
            "weights": {k: round(float(v), 2) for k, v in self.weights.items()},
            "source": self.source,
            "path": str(self.path) if self.path else None,
        }

    def is_empty(self) -> bool:
        return not self.preferred_skills and not self.avoid_skills and not self.weights

    def get_bias(self, skill: SkillMetadata, direct_prefer: Optional[Set[str]] = None) -> float:
        """Compute the deterministic taste bias for a candidate skill in [-3.0, +3.0].

        Invariants enforced:
        - Direct CLI preference override yields +3.0.
        - Custom weights are clamped to [-3.0, +3.0].
        - Avoided skills receive -3.0.
        - Preferred category skills receive +3.0.
        - Quality Sentry Immunity: 'engineering-quality-gate' and skills in 'decision.review'
          or 'verification.qa' can NEVER receive negative bias.
        """
        # 1. CLI ad-hoc override
        if direct_prefer and skill.name in direct_prefer:
            return 3.0

        raw_bias = 0.0

        # 2. Custom weight
        if skill.name in self.weights:
            try:
                raw_bias = float(self.weights[skill.name])
            except (ValueError, TypeError):
                raw_bias = 0.0
        # 3. Explicit avoid list
        elif skill.name in self.avoid_skills:
            raw_bias = -3.0
        # 4. Explicit category preference
        elif self._is_preferred_for_category(skill):
            raw_bias = 3.0

        # Quality Sentry Immunity (Guardrail Judicial Invariant):
        # Security/QA/Review sentries cannot be downvoted or suppressed by taste.
        if skill.name == "engineering-quality-gate" or skill.category in ("decision.review", "verification.qa"):
            if raw_bias < 0.0:
                raw_bias = 0.0

        # Clamp strictly between -3.0 and +3.0
        return max(-3.0, min(3.0, round(raw_bias, 2)))

    def get_bias_reason(self, skill: SkillMetadata, direct_prefer: Optional[Set[str]] = None) -> Optional[str]:
        """Return a human-readable explanation for why a taste bias was applied to a skill."""
        if direct_prefer and skill.name in direct_prefer:
            return "cli: --prefer"
        if skill.name in self.weights:
            return f"weight: {self.weights[skill.name]:+.2f}"
        if skill.name in self.avoid_skills:
            if skill.name == "engineering-quality-gate" or skill.category in ("decision.review", "verification.qa"):
                return "immune: quality sentry"
            return "avoid_skills"
        for cat_key, pref_skill in self.preferred_skills.items():
            if pref_skill == skill.name and self._is_preferred_for_category(skill):
                return f"preferred: {cat_key}"
        return None

    def _is_preferred_for_category(self, skill: SkillMetadata) -> bool:
        """Check whether the candidate skill satisfies any category preference rule."""
        if not self.preferred_skills:
            return False

        for cat_key, pref_skill in self.preferred_skills.items():
            if pref_skill != skill.name:
                continue

            cat_lower = cat_key.lower().strip()
            skill_cat = skill.category.lower().strip()

            # Exact category match
            if cat_lower == skill_cat:
                return True

            # Visual authority aliases (e.g. 'frontend.visual', 'ui.visual', 'ui')
            if cat_lower in ("frontend.visual", "ui.visual", "visual", "ui", "frontend"):
                if skill_cat.startswith(("ui.", "frontend.")) or skill.name in (
                    "design-taste-frontend", "impeccable", "unslop", "frontend-design"
                ):
                    return True

            # Backend framework / API aliases
            if cat_lower in ("backend.framework", "backend", "backend.api"):
                if skill_cat.startswith(("backend.", "db.", "api.")):
                    return True

            # Sub-category or prefix match
            if skill_cat.startswith(cat_lower) or cat_lower in skill.tags:
                return True

            # Wildcard / general category
            if cat_lower in ("*", "general", "all"):
                return True

        return False


def _dict_to_taste_profile(
    data: dict,
    source_label: Optional[str],
    path: Path,
    mtime: float,
) -> TasteProfile:
    version = int(data.get("version", 1))

    pref_raw = data.get("preferred_skills") or {}
    preferred: Dict[str, str] = {}
    if isinstance(pref_raw, dict):
        for k, v in pref_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                preferred[k.strip()] = v.strip()

    avoid_raw = data.get("avoid_skills") or []
    avoid: List[str] = []
    if isinstance(avoid_raw, list):
        for item in avoid_raw:
            if isinstance(item, str) and item.strip():
                avoid.append(item.strip())

    weights_raw = data.get("weights") or {}
    weights: Dict[str, float] = {}
    if isinstance(weights_raw, dict):
        for k, v in weights_raw.items():
            try:
                w = float(v)
                weights[str(k).strip()] = max(-3.0, min(3.0, round(w, 2)))
            except (ValueError, TypeError):
                continue

    return TasteProfile(
        version=version,
        preferred_skills=preferred,
        avoid_skills=avoid,
        weights=weights,
        source=source_label,
        path=path,
        mtime=mtime,
    )


def load_taste_file(path: Path | str, source_label: Optional[str] = None) -> Optional[TasteProfile]:
    """Load a taste profile JSON file with mtime caching and fail-open resilience."""
    try:
        p = Path(path).expanduser()
        cache_key = str(p)
        try:
            stat = p.stat()
            mtime = stat.st_mtime
        except (FileNotFoundError, OSError):
            return None

        if cache_key in _TASTE_CACHE and _TASTE_CACHE[cache_key][0] == mtime:
            return _TASTE_CACHE[cache_key][1]

        text = p.read_text(encoding="utf-8")
        if not text.strip():
            _TASTE_CACHE[cache_key] = (mtime, None)
            return None

        data = json.loads(text)
        if not isinstance(data, dict):
            logger.warning("Taste profile at %s is not a JSON object; failing open", p)
            _TASTE_CACHE[cache_key] = (mtime, None)
            return None

        profile = _dict_to_taste_profile(data, source_label, p, mtime)
        _TASTE_CACHE[cache_key] = (mtime, profile)
        return profile
    except Exception as e:
        logger.warning("Failed to load taste profile from %s: %s (failing open)", path, e)
        return None


def load_markdown_taste_file(path: Path | str, source_label: Optional[str] = "user") -> Optional[TasteProfile]:
    """Fallback loader that extracts taste preferences from developer-profile.local.md if present."""
    try:
        p = Path(path).expanduser()
        cache_key = f"md:{p}"
        try:
            stat = p.stat()
            mtime = stat.st_mtime
        except (FileNotFoundError, OSError):
            return None

        if cache_key in _TASTE_CACHE and _TASTE_CACHE[cache_key][0] == mtime:
            return _TASTE_CACHE[cache_key][1]

        text = p.read_text(encoding="utf-8")
        if not text.strip():
            _TASTE_CACHE[cache_key] = (mtime, None)
            return None

        taste_dict: Optional[dict] = None

        # 1. Check for ```json:taste or ```taste fenced block
        fence_match = TASTE_FENCE_REGEX.search(text)
        if fence_match:
            raw_block = fence_match.group(1).strip()
            parsed = yaml.safe_load(raw_block)
            if isinstance(parsed, dict):
                taste_dict = parsed

        # 2. Check YAML frontmatter for a 'taste' section
        if taste_dict is None:
            fm_match = FRONTMATTER_REGEX.match(text)
            if fm_match:
                fm_data = yaml.safe_load(fm_match.group(1))
                if isinstance(fm_data, dict):
                    if isinstance(fm_data.get("taste"), dict):
                        taste_dict = fm_data["taste"]
                    elif any(k in fm_data for k in ("preferred_skills", "avoid_skills", "weights")):
                        taste_dict = fm_data

        if not taste_dict:
            _TASTE_CACHE[cache_key] = (mtime, None)
            return None

        profile = _dict_to_taste_profile(taste_dict, source_label, p, mtime)
        _TASTE_CACHE[cache_key] = (mtime, profile)
        return profile
    except Exception as e:
        logger.warning("Failed to parse markdown taste profile from %s: %s (failing open)", path, e)
        return None


def find_workspace_taste_path(start_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Ascend directories from start_dir looking for .taxonomy/taste.json, stopping at git root."""
    try:
        curr = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
    except Exception:
        return None

    for parent in [curr] + list(curr.parents):
        candidate = parent / WORKSPACE_TASTE_REL_PATH
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists():
            # Stop searching above git root
            break
    return None


def get_user_taste_path() -> Path:
    """Return the default canonical path for user taste configuration."""
    return DEFAULT_USER_TASTE_PATH


def get_workspace_taste_path(start_dir: Optional[Path | str] = None) -> Path:
    """Return the target path for workspace taste configuration."""
    existing = find_workspace_taste_path(start_dir)
    if existing:
        return existing
    curr = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists():
            return parent / WORKSPACE_TASTE_REL_PATH
    return curr / WORKSPACE_TASTE_REL_PATH


def merge_taste_profiles(
    user_profile: Optional[TasteProfile],
    workspace_profile: Optional[TasteProfile],
) -> TasteProfile:
    """Merge user and workspace taste profiles according to 2-tier hierarchy rules.

    Precedence: Workspace Profile strictly overrides User Profile across all fields.
    """
    if user_profile is None and workspace_profile is None:
        return TasteProfile()
    if user_profile is None:
        return workspace_profile  # type: ignore[return-value]
    if workspace_profile is None:
        return user_profile

    merged_preferred = dict(user_profile.preferred_skills)
    merged_weights = dict(user_profile.weights)
    merged_avoid = set(user_profile.avoid_skills)

    # 1. Workspace avoid_skills overrides user weights and user preferred_skills
    for sk in workspace_profile.avoid_skills:
        merged_avoid.add(sk)
        if sk in merged_weights and sk not in workspace_profile.weights:
            del merged_weights[sk]
        for cat, pref in list(merged_preferred.items()):
            if pref == sk and cat not in workspace_profile.preferred_skills:
                del merged_preferred[cat]

    # 2. Workspace preferred_skills overrides user preferred_skills, user avoid_skills, and negative user weights
    merged_preferred.update(workspace_profile.preferred_skills)
    for pref in workspace_profile.preferred_skills.values():
        if pref in merged_avoid and pref not in workspace_profile.avoid_skills:
            merged_avoid.remove(pref)
        if pref in merged_weights and merged_weights[pref] < 3.0 and pref not in workspace_profile.weights:
            del merged_weights[pref]

    # 3. Workspace weights overrides user weights and user avoid_skills (when weight > -3.0)
    merged_weights.update(workspace_profile.weights)
    for skill, weight in workspace_profile.weights.items():
        if weight > -3.0 and skill in merged_avoid and skill not in workspace_profile.avoid_skills:
            merged_avoid.remove(skill)

    has_ws = not workspace_profile.is_empty()
    has_user = not user_profile.is_empty()

    if has_ws and has_user:
        source = "workspace+user"
    elif has_ws:
        source = "workspace"
    elif has_user:
        source = "user"
    else:
        source = None

    return TasteProfile(
        version=workspace_profile.version or user_profile.version or 1,
        preferred_skills=merged_preferred,
        avoid_skills=sorted(list(merged_avoid)),
        weights=merged_weights,
        source=source,
        path=workspace_profile.path or user_profile.path,
        mtime=max(workspace_profile.mtime, user_profile.mtime),
    )


def load_taste_profile(
    workspace_root: Optional[Path | str] = None,
    user_path: Optional[Path | str] = None,
) -> TasteProfile:
    """Hierarchically resolve and load active taste profile across workspace and user levels."""
    u_path = Path(user_path).expanduser() if user_path else get_user_taste_path()
    user_profile = load_taste_file(u_path, source_label="user")
    if user_profile is None and user_path is None:
        user_profile = load_markdown_taste_file(FALLBACK_USER_PROFILE_PATH, source_label="user")

    ws_path = find_workspace_taste_path(workspace_root)
    ws_profile = load_taste_file(ws_path, source_label="workspace") if ws_path else None

    return merge_taste_profiles(user_profile, ws_profile)


def save_taste_profile(profile: TasteProfile, target_path: Path | str) -> Path:
    """Save a taste profile to disk with atomic write semantics (temp file + os.replace)."""
    p = Path(target_path).expanduser().resolve(strict=False)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": profile.version or 1,
        "preferred_skills": profile.preferred_skills,
        "avoid_skills": sorted(profile.avoid_skills),
        "weights": {k: round(float(v), 2) for k, v in profile.weights.items()},
    }

    # Write atomically to a temp file on the same filesystem/directory, then rename
    tmp_path = p.with_suffix(f".tmp.{os.getpid()}.{time.time_ns()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, p)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    try:
        mtime = p.stat().st_mtime
        profile.path = p
        profile.mtime = mtime
        _TASTE_CACHE[str(p)] = (mtime, profile)
        _TASTE_CACHE[str( Path(target_path).expanduser() )] = (mtime, profile)
    except OSError:
        pass

    return p
