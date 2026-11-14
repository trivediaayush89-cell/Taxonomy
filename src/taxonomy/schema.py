"""Frontmatter parsing and schema validation for SKILL.md files."""

import hashlib
import re
from pathlib import Path
from typing import Optional
import yaml

from taxonomy.models import SkillMetadata
from taxonomy.security import (
    MAX_FRONTMATTER_BYTES,
    MAX_SKILL_FILE_BYTES,
    SecurityValidationError,
    check_yaml_bomb,
    safe_resolve_skill_path,
)

FRONTMATTER_REGEX = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)


def infer_trust_level(resolved_file: Path, skills_root: Optional[Path] = None) -> str:
    """Infer provenance trust level based on file system hierarchy."""
    parts = [p.lower() for p in resolved_file.parts]
    root_parts = [p.lower() for p in skills_root.parts] if skills_root else []

    if "builtin" in parts or "builtin" in root_parts:
        return "builtin"
    if ".taxonomy" in parts or ".agents" in parts:
        return "workspace"
    if ".gemini" in parts or "skills" in parts:
        return "user"
    return "community"


def parse_skill_markdown(
    file_path: Path,
    skills_root: Optional[Path] = None,
) -> Optional[SkillMetadata]:
    """Parse a SKILL.md file, extracting frontmatter metadata.

    If skills_root is provided, enforces canonical path containment via safe_resolve_skill_path
    to block symlink escapes outside the root directory.
    Enforces maximum file size (MAX_SKILL_FILE_BYTES) and frontmatter size (MAX_FRONTMATTER_BYTES),
    protects against YAML bomb expansions, and gracefully returns None on corruption or violation.
    """
    try:
        if skills_root is not None:
            resolved_file = safe_resolve_skill_path(skills_root, file_path)
        else:
            resolved_file = file_path.resolve(strict=False)

        if not resolved_file.is_file():
            return None

        stat = resolved_file.stat()
        # Cap max skill file size to prevent memory exhaustion DoS
        if stat.st_size > MAX_SKILL_FILE_BYTES:
            return None

        text = resolved_file.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        match = FRONTMATTER_REGEX.match(text)
        if not match:
            # Fallback: Check if file has minimal structure without frontmatter
            name = file_path.parent.name
            trust_lvl = infer_trust_level(resolved_file, skills_root)
            return SkillMetadata(
                name=name,
                description="Unclassified skill (no frontmatter)",
                category="general",
                path=resolved_file.parent,
                mtime=stat.st_mtime,
                version="1.0.0",
                content_hash=content_hash,
                trust_level=trust_lvl,
            )

        raw_yaml = match.group(1)
        # Cap frontmatter size to prevent oversized extraction
        if len(raw_yaml.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
            return None

        # Guard against YAML entity expansion bombs (billion laughs in YAML)
        if check_yaml_bomb(raw_yaml):
            return None

        data = yaml.safe_load(raw_yaml)
        if not isinstance(data, dict):
            return None

        name = str(data.get("name") or file_path.parent.name).strip()
        description = str(data.get("description") or "").strip()
        category = str(data.get("category") or "general").strip()
        version = str(data.get("version") or "1.0.0").strip()

        # Provenance and Trust
        trust_level_declared = str(data.get("trust_level") or "").lower().strip()
        if trust_level_declared in ("builtin", "user", "workspace", "community"):
            trust_level = trust_level_declared
        else:
            trust_level = infer_trust_level(resolved_file, skills_root)

        provenance = str(data.get("provenance") or "").strip() or None

        # Supported agents
        sup_agents = data.get("supported_agents") or []
        if isinstance(sup_agents, str):
            sup_agents = [a.strip() for a in sup_agents.split(",") if a.strip()]
        elif not isinstance(sup_agents, list):
            sup_agents = []
        supported_agents = [str(a).lower().strip() for a in sup_agents if str(a).strip()]

        # Permissions
        perms = data.get("permissions") or []
        if isinstance(perms, str):
            perms = [p.strip() for p in perms.split(",") if p.strip()]
        elif not isinstance(perms, list):
            perms = []
        permissions = [str(p).lower().strip() for p in perms if str(p).strip()]

        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        elif not isinstance(tags, list):
            tags = []
        tags = [str(t).lower().strip() for t in tags if str(t).strip()]

        status = str(data.get("status") or "active").lower().strip()
        if status not in ("active", "experimental", "deprecated"):
            status = "active"

        try:
            priority = int(data.get("priority", 50))
            priority = max(0, min(100, priority))
        except (ValueError, TypeError):
            priority = 50

        conflicts = data.get("conflicts_with") or []
        if isinstance(conflicts, str):
            conflicts = [c.strip() for c in conflicts.split(",") if c.strip()]
        elif not isinstance(conflicts, list):
            conflicts = []
        conflicts = [str(c).lower().strip() for c in conflicts if str(c).strip()]

        requires = data.get("requires") or []
        if isinstance(requires, str):
            requires = [r.strip() for r in requires.split(",") if r.strip()]
        elif not isinstance(requires, list):
            requires = []
        requires = [str(r).lower().strip() for r in requires if str(r).strip()]

        return SkillMetadata(
            name=name,
            description=description,
            category=category,
            tags=tags,
            status=status,
            priority=priority,
            conflicts_with=conflicts,
            requires=requires,
            path=resolved_file.parent,
            mtime=stat.st_mtime,
            version=version,
            content_hash=content_hash,
            trust_level=trust_level,
            provenance=provenance,
            supported_agents=supported_agents,
            permissions=permissions,
        )
    except SecurityValidationError:
        # Block escaping symlinks or traversal paths
        return None
    except Exception:
        # Fail-open: Never let a corrupted file crash the caller
        return None
