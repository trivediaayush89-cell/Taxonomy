"""Security containment and path traversal protection for skill file resolution."""

import os
from pathlib import Path


class SecurityValidationError(PermissionError):
    """Raised when a path escapes the designated skills root or attempts traversal."""
    pass


def safe_resolve_skill_path(skills_root: str | Path, target_path: str | Path) -> Path:
    """Canonicalizes and validates that target_path is strictly contained within skills_root.
    
    Protects against:
    - Path traversal attacks (e.g., '../../etc/passwd' or '..\\..\\Windows\\System32')
    - Symlink redirection outside the allowed sandbox
    - Null-byte injection
    - UNC path escaping on Windows
    """
    if "\0" in str(target_path):
        raise SecurityValidationError("Null byte detected in path")

    root_resolved = Path(skills_root).resolve(strict=False)
    
    # If target is relative, join it with root; if absolute, resolve directly
    target = Path(target_path)
    if not target.is_absolute():
        target = root_resolved / target

    target_resolved = target.resolve(strict=False)

    # Containment check: target must be inside or equal to root_resolved
    try:
        # relative_to raises ValueError if target_resolved is not under root_resolved
        target_resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityValidationError(
            f"Security Alert: Path traversal attempt blocked! '{target_path}' escapes sandbox '{skills_root}'"
        )

    return target_resolved
