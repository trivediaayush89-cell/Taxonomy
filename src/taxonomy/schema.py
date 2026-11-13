"""Frontmatter parsing and schema validation for SKILL.md files."""

import hashlib
import re
from pathlib import Path
from typing import Optional
import yaml

from taxonomy.models import SkillMetadata
from taxonomy.security import SecurityValidationError, safe_resolve_skill_path

FRONTMATTER_REGEX = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)


def parse_skill_markdown(
    file_path: Path,
    skills_root: Optional[Path] = None,
) -> Optional[SkillMetadata]:
    """Parse a SKILL.md file, extracting frontmatter metadata.

    If skills_root is provided, enforces canonical path containment via safe_resolve_skill_path
    to block symlink escapes outside the root directory.
    Gracefully returns None if frontmatter is invalid or path escapes root, avoiding crashes.
    """
    try:
        if skills_root is not None:
            resolved_file = safe_resolve_skill_path(skills_root, file_path)
        else:
            resolved_file = file_path.resolve(strict=False)

        if not resolved_file.is_file():
            return None

        stat = resolved_file.stat()
        text = resolved_file.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        match = FRONTMATTER_REGEX.match(text)
        if not match:
            # Fallback: Check if file has minimal structure without frontmatter
            name = file_path.parent.name
            return SkillMetadata(
                name=name,
                description="Unclassified skill (no frontmatter)",
                category="general",
                path=resolved_file.parent,
                mtime=stat.st_mtime,
                version="1.0.0",
                content_hash=content_hash,
            )

        raw_yaml = match.group(1)
        data = yaml.safe_load(raw_yaml)
        if not isinstance(data, dict):
            return None

        name = str(data.get("name") or file_path.parent.name).strip()
        description = str(data.get("description") or "").strip()
        category = str(data.get("category") or "general").strip()
        version = str(data.get("version") or "1.0.0").strip()

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
        )
    except SecurityValidationError:
        # Block escaping symlinks or traversal paths
        return None
    except Exception:
        # Fail-open: Never let a corrupted file crash the caller
        return None
