"""Security containment, path traversal protection, provenance, and threat scanning for skill taxonomy."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import urllib.parse
import yaml

# Hard security limits to prevent DoS, resource exhaustion, and memory bombs
MAX_SKILL_FILE_BYTES = 1024 * 1024       # 1 MB max for SKILL.md
MAX_FRONTMATTER_BYTES = 16 * 1024        # 16 KB max for YAML frontmatter
MAX_TASTE_FILE_BYTES = 256 * 1024        # 256 KB max for taste JSON/YAML profiles
MAX_REQUEST_BYTES = 256 * 1024           # 256 KB max for HTTP API payloads
MAX_YAML_ALIASES = 10                    # Maximum anchor alias expansions allowed in YAML

# Canonical loopback hosts for local workbench network lockdown
ALLOWED_LOOPBACK_HOSTS = frozenset({
    "127.0.0.1",
    "localhost",
    "::1",
    "[::1]",
})

# Protected Quality Sentries that cannot be silently suppressed or demoted
PROTECTED_QUALITY_SENTRIES = frozenset({
    "engineering-quality-gate",
    "independent-jury",
})


class SecurityValidationError(PermissionError):
    """Raised when a path escapes the designated skills root or attempts traversal."""
    pass


@dataclass
class SecurityFinding:
    """Security audit finding representing a potential threat or misconfiguration."""
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    category: str  # "prompt_injection", "command_injection", "exfiltration", "path_traversal", "untrusted_override", "resource_exhaustion", "malformed"
    message: str
    location: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "location": self.location,
        }


# Threat signature patterns
PROMPT_INJECTION_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts|rules)\b"),
        "CRITICAL",
        "Prompt injection: directive attempts to ignore previous instructions",
    ),
    (
        re.compile(r"(?i)\bdisregard\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts|rules)\b"),
        "CRITICAL",
        "Prompt injection: directive attempts to disregard prior instructions",
    ),
    (
        re.compile(r"(?i)\bsystem\s+prompt\s+override\b"),
        "CRITICAL",
        "Prompt injection: explicit system prompt override attempt",
    ),
    (
        re.compile(r"(?i)\byou\s+are\s+now\s+in\s+[\"']?(developer\s+mode|dan\s+mode)[\"']?"),
        "CRITICAL",
        "Prompt injection: jailbreak / developer mode attempt",
    ),
    (
        re.compile(r"(?i)\bbypass\s+(all\s+)?(safety|guardrails|filters|restrictions)\b"),
        "HIGH",
        "Prompt injection: directive requests safety or guardrail bypass",
    ),
    (
        re.compile(r"(?i)<\/?system>|\[SYSTEM(\s+INSTRUCTION)?\]"),
        "HIGH",
        "Prompt injection: artificial system delimiter marker",
    ),
]

DANGEROUS_EXECUTION_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?i)\brm\s+-rf\s+[/~]|\brmdir\s+/[sq]\s+[a-z]:\\|\bRemove-Item\s+-Recurse\s+-Force\s+[a-z]:\\"),
        "CRITICAL",
        "Destructive filesystem wipe command pattern detected",
    ),
    (
        re.compile(r"(?i)\b(curl|wget)\b[^\n|;&]*\|\s*(sh|bash|zsh|powershell|pwsh)\b"),
        "CRITICAL",
        "Arbitrary remote script execution pipeline (curl/wget | sh)",
    ),
    (
        re.compile(r"(?i)\bInvoke-Expression\s*\(\s*New-Object\s+Net\.WebClient"),
        "CRITICAL",
        "PowerShell WebClient arbitrary remote script execution",
    ),
    (
        re.compile(r"(?i)\bpowershell(\.exe)?\s+(-(enc|encodedcommand))\b"),
        "HIGH",
        "Obfuscated / encoded PowerShell execution directive",
    ),
]

EXFILTRATION_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?i)\b(curl|fetch|wget|requests\.(post|get))\b[^\n]*\b(api_key|token|secret|password|credential|id_rsa)\b"),
        "HIGH",
        "Credential or secret exfiltration pattern via network request",
    ),
    (
        re.compile(r"(?i)\b(webhook\.site|postb\.in|requestbin\.net|requestcatcher\.com|pipedream\.net|ngrok\.io)\b"),
        "MEDIUM",
        "Outbound webhook / data capture service domain referenced",
    ),
]

ILLEGAL_NAME_CHARS_REGEX = re.compile(r"[<>\r\n\t\0;\|\&\$\`\\]")


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

    target_str = str(target_path).strip()
    clean_str = target_str.replace("\\", "/")
    has_drive = len(clean_str) >= 2 and clean_str[1] == ":" and clean_str[0].isalpha()

    root_resolved = Path(skills_root).resolve(strict=False)
    
    if has_drive and os.name != "nt":
        raise SecurityValidationError(
            f"Security Alert: Path traversal attempt blocked! '{target_path}' escapes sandbox '{skills_root}'"
        )

    # If target is relative, join it with root; if absolute, resolve directly
    target = Path(target_path)
    if has_drive or target.is_absolute() or clean_str.startswith("/"):
        target_resolved = target.resolve(strict=False)
    else:
        target_resolved = (root_resolved / target).resolve(strict=False)

    # Containment check: target must be inside or equal to root_resolved
    try:
        # relative_to raises ValueError if target_resolved is not under root_resolved
        target_resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityValidationError(
            f"Security Alert: Path traversal attempt blocked! '{target_path}' escapes sandbox '{skills_root}'"
        )

    return target_resolved


YAML_ANCHOR_REGEX = re.compile(r"(?:^|[\s,\[\{:])&([A-Za-z0-9_-]+)", re.MULTILINE)
YAML_ALIAS_REGEX = re.compile(r"(?:^|[\s,\[\{:])\*([A-Za-z0-9_-]+)(?=$|[\s,\]\}\r\n])", re.MULTILINE)


def check_yaml_bomb(raw_content: str, max_aliases: int = MAX_YAML_ALIASES) -> bool:
    """Detect potential YAML entity expansion bomb (billion laughs in YAML).
    
    Returns True if YAML anchors and excessive alias references (*ident) are found.
    Avoids false positives on Markdown bold (**text**), bullets (* item), or glob patterns (apps/*).
    """
    if not raw_content:
        return False
    if not YAML_ANCHOR_REGEX.search(raw_content):
        return False
    alias_count = len(YAML_ALIAS_REGEX.findall(raw_content))
    return alias_count > max_aliases


def validate_loopback_host(host_header: Optional[str]) -> bool:
    """Validate that the HTTP Host header corresponds strictly to local loopback interface."""
    if not host_header:
        return False
    clean_host = host_header.strip().lower()
    if clean_host in ALLOWED_LOOPBACK_HOSTS:
        return True

    # Bracketed IPv6 literal with port: [::1]:8765
    if clean_host.startswith("["):
        idx = clean_host.find("]")
        if idx != -1:
            host_part = clean_host[:idx + 1]
            rest = clean_host[idx + 1:]
            if rest.startswith(":"):
                port_part = rest[1:]
                if not (port_part.isdigit() and 1 <= int(port_part) <= 65535):
                    return False
                return host_part in ALLOWED_LOOPBACK_HOSTS

    # IPv4 or hostname with port: 127.0.0.1:8765 or localhost:8765
    if ":" in clean_host and clean_host.count(":") == 1:
        host_part, port_part = clean_host.split(":", 1)
        if not (port_part.isdigit() and 1 <= int(port_part) <= 65535):
            return False
        return host_part in ALLOWED_LOOPBACK_HOSTS

    return False


def validate_loopback_origin(origin_header: Optional[str]) -> bool:
    """Validate that the HTTP Origin header originates strictly from local loopback."""
    if not origin_header:
        # If no origin header is provided (CLI or direct curl), origin is not untrusted cross-origin
        return True
    try:
        parsed = urllib.parse.urlparse(origin_header.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        hostname = (parsed.hostname or "").lower()
        if parsed.port is not None and not (1 <= parsed.port <= 65535):
            return False
        return hostname in ALLOWED_LOOPBACK_HOSTS
    except Exception:
        return False


def scan_skill_security(metadata: Any, full_content: Optional[str] = None) -> List[SecurityFinding]:
    """Scan skill metadata and instructions for prompt injection, command injection, and security flaws."""
    findings: List[SecurityFinding] = []
    name = getattr(metadata, "name", "")
    description = getattr(metadata, "description", "")
    tags = getattr(metadata, "tags", []) or []
    permissions = getattr(metadata, "permissions", []) or []

    # 1. Check skill name for illegal characters or path traversal
    if ".." in name or "/" in name or "\\" in name:
        findings.append(SecurityFinding(
            severity="CRITICAL",
            category="path_traversal",
            message=f"Skill name '{name}' contains illegal path traversal characters",
            location=f"name: {name}"
        ))
    if ILLEGAL_NAME_CHARS_REGEX.search(name):
        findings.append(SecurityFinding(
            severity="CRITICAL",
            category="command_injection",
            message=f"Skill name '{name}' contains dangerous shell or control characters",
            location=f"name: {name}"
        ))

    # 2. Check metadata text (description + tags) against threat patterns
    text_to_scan = f"{description}\n" + " ".join(tags)
    for pattern, severity, msg in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text_to_scan):
            findings.append(SecurityFinding(
                severity=severity,
                category="prompt_injection",
                message=f"{msg} in metadata",
                location=f"skill: {name}"
            ))

    for pattern, severity, msg in DANGEROUS_EXECUTION_PATTERNS:
        if pattern.search(text_to_scan):
            findings.append(SecurityFinding(
                severity=severity,
                category="command_injection",
                message=f"{msg} in metadata",
                location=f"skill: {name}"
            ))

    for pattern, severity, msg in EXFILTRATION_PATTERNS:
        if pattern.search(text_to_scan):
            findings.append(SecurityFinding(
                severity=severity,
                category="exfiltration",
                message=f"{msg} in metadata",
                location=f"skill: {name}"
            ))

    # 3. Check full instructions if provided
    instructions = full_content
    if instructions is None and hasattr(metadata, "get_full_instructions"):
        try:
            instructions = metadata.get_full_instructions()
        except Exception:
            instructions = None

    if instructions:
        # Enforce instruction length check
        if len(instructions.encode("utf-8")) > MAX_SKILL_FILE_BYTES:
            findings.append(SecurityFinding(
                severity="HIGH",
                category="resource_exhaustion",
                message=f"Skill instructions size ({len(instructions.encode('utf-8'))} bytes) exceeds maximum limit of {MAX_SKILL_FILE_BYTES} bytes",
                location=f"skill: {name}"
            ))

        for pattern, severity, msg in PROMPT_INJECTION_PATTERNS:
            if pattern.search(instructions):
                findings.append(SecurityFinding(
                    severity=severity,
                    category="prompt_injection",
                    message=f"{msg} in instructions",
                    location=f"skill: {name}"
                ))

        for pattern, severity, msg in DANGEROUS_EXECUTION_PATTERNS:
            if pattern.search(instructions):
                findings.append(SecurityFinding(
                    severity=severity,
                    category="command_injection",
                    message=f"{msg} in instructions",
                    location=f"skill: {name}"
                ))

        for pattern, severity, msg in EXFILTRATION_PATTERNS:
            if pattern.search(instructions):
                findings.append(SecurityFinding(
                    severity=severity,
                    category="exfiltration",
                    message=f"{msg} in instructions",
                    location=f"skill: {name}"
                ))

    # 4. Permissions check
    dangerous_perms = {"root", "unrestricted_shell", "all_filesystem_write"}
    for p in permissions:
        if str(p).lower() in dangerous_perms:
            findings.append(SecurityFinding(
                severity="HIGH",
                category="untrusted_override",
                message=f"Dangerous permission '{p}' requested",
                location=f"skill: {name}"
            ))

    return findings


def validate_workspace_taste_safety(
    taste_path: Path | str,
    known_skills: Optional[Set[str]] = None
) -> Tuple[bool, List[SecurityFinding]]:
    """Validate that a workspace .taxonomy/taste.json or .yaml profile is safe and untampered.
    
    Checks:
    1. File size does not exceed MAX_TASTE_FILE_BYTES.
    2. YAML bomb / excessive entity expansion protection.
    3. Skill names do not contain command injection or path traversal characters.
    4. Protected Quality Sentries are not avoided or suppressed without user consent.
    5. Unknown skills are flagged with informational warnings if known_skills is provided.
    
    Returns:
        (is_safe: bool, findings: List[SecurityFinding])
    """
    findings: List[SecurityFinding] = []
    p = Path(taste_path).expanduser().resolve(strict=False)

    if not p.is_file():
        return True, findings

    try:
        stat = p.stat()
        if stat.st_size > MAX_TASTE_FILE_BYTES:
            findings.append(SecurityFinding(
                severity="CRITICAL",
                category="resource_exhaustion",
                message=f"Workspace taste file size ({stat.st_size} bytes) exceeds maximum allowable limit of {MAX_TASTE_FILE_BYTES} bytes",
                location=str(p)
            ))
            return False, findings

        raw = p.read_text(encoding="utf-8")
        if check_yaml_bomb(raw):
            findings.append(SecurityFinding(
                severity="CRITICAL",
                category="resource_exhaustion",
                message=f"Potential YAML entity expansion bomb detected in workspace taste file (exceeds {MAX_YAML_ALIASES} aliases)",
                location=str(p)
            ))
            return False, findings

        try:
            data = json.loads(raw)
        except Exception:
            data = yaml.safe_load(raw)

        if not isinstance(data, dict):
            findings.append(SecurityFinding(
                severity="HIGH",
                category="malformed",
                message="Workspace taste profile root must be a JSON/YAML mapping",
                location=str(p)
            ))
            return False, findings

        preferred = data.get("preferred_skills") or {}
        avoid = data.get("avoid_skills") or []
        weights = data.get("weights") or {}

        # Validate skill name strings
        skills_to_check: List[Tuple[str, str]] = []
        if isinstance(preferred, dict):
            for cat, sk in preferred.items():
                skills_to_check.append((str(sk), f"preferred_skills[{cat}]"))
        if isinstance(avoid, list):
            for sk in avoid:
                skills_to_check.append((str(sk), "avoid_skills"))
        if isinstance(weights, dict):
            for sk, w in weights.items():
                skills_to_check.append((str(sk), f"weights[{sk}]"))

        for sk_name, loc in skills_to_check:
            if ".." in sk_name or "/" in sk_name or "\\" in sk_name or ILLEGAL_NAME_CHARS_REGEX.search(sk_name):
                findings.append(SecurityFinding(
                    severity="CRITICAL",
                    category="command_injection",
                    message=f"Illegal or malicious characters detected in skill reference '{sk_name}'",
                    location=f"{p.name}:{loc}"
                ))

        # Check for demotion/avoidance of Quality Sentries
        try:
            from taxonomy.registry import get_protected_sentries
            active_sentries = set(PROTECTED_QUALITY_SENTRIES) | set(get_protected_sentries())
        except Exception:
            active_sentries = set(PROTECTED_QUALITY_SENTRIES)

        if isinstance(avoid, list):
            for sentry in active_sentries:
                if sentry in avoid:
                    findings.append(SecurityFinding(
                        severity="HIGH",
                        category="untrusted_override",
                        message=f"Workspace taste file attempts to avoid protected Quality Sentry '{sentry}'",
                        location=f"{p.name}:avoid_skills"
                    ))

        if isinstance(weights, dict):
            for sentry in active_sentries:
                if sentry in weights:
                    try:
                        w_val = float(weights[sentry])
                        if w_val < 0.0:
                            findings.append(SecurityFinding(
                                severity="HIGH",
                                category="untrusted_override",
                                message=f"Workspace taste file attempts to apply negative bias ({w_val}) to protected Quality Sentry '{sentry}'",
                                location=f"{p.name}:weights"
                            ))
                    except (ValueError, TypeError):
                        pass

        # Check against known skills catalog
        if known_skills:
            for sk_name, loc in skills_to_check:
                clean_name = sk_name.strip()
                if clean_name and clean_name not in known_skills and not any(f.message.startswith("Illegal") for f in findings):
                    findings.append(SecurityFinding(
                        severity="LOW",
                        category="untrusted_override",
                        message=f"Workspace taste file references unknown skill '{clean_name}' not found in registered skill catalog",
                        location=f"{p.name}:{loc}"
                    ))

    except Exception as e:
        findings.append(SecurityFinding(
            severity="HIGH",
            category="malformed",
            message=f"Failed to parse workspace taste file: {e}",
            location=str(p)
        ))

    is_safe = not any(f.severity in ("CRITICAL", "HIGH") for f in findings)
    return is_safe, findings
