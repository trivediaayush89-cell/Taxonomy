"""Fast, deterministic project fingerprinting and zero-config stack detection."""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("taxonomy.fingerprint")

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", "target", "dist", "build", ".next",
    ".taxonomy", ".court", ".agents", "vendor", "out",
})

WORKSPACE_CONTAINERS = frozenset({
    "apps", "packages", "services", "crates", "libs", "modules",
})

DIRECT_WORKSPACES = frozenset({
    "frontend", "backend", "client", "server", "web", "api", "contracts",
})

WORKSPACE_MARKERS = frozenset({
    "pnpm-workspace.yaml", "pnpm-workspace.yml", "lerna.json", "turbo.json",
    "nx.json", "rush.json",
})

KNOWN_MANIFEST_NAMES = frozenset({
    "package.json", "pyproject.toml", "cargo.toml", "go.mod", "foundry.toml",
    "hardhat.config.js", "hardhat.config.ts", "next.config.js", "next.config.mjs",
    "next.config.ts", "tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs",
    "tsconfig.json", "jsconfig.json", "requirements.txt", "setup.py", "alembic.ini",
    "pipfile", "poetry.lock", "pnpm-workspace.yaml", "pnpm-workspace.yml",
    "lerna.json", "turbo.json", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
})


def _is_manifest_file(name_lower: str) -> bool:
    """Check if filename is a recognized project manifest or configuration."""
    if name_lower in KNOWN_MANIFEST_NAMES:
        return True
    if name_lower.startswith(("next.config.", "tailwind.config.", "hardhat.config.")):
        return True
    if name_lower.endswith(".sol"):
        return True
    return False


# In-memory cache: root_str -> (cache_token, ProjectFingerprint)
_FINGERPRINT_CACHE: Dict[str, Tuple[Any, "ProjectFingerprint"]] = {}


def clear_fingerprint_cache() -> None:
    """Clear fingerprint cache for deterministic testing."""
    _FINGERPRINT_CACHE.clear()


@dataclass
class ProjectFingerprint:
    """Detected tech stack, manifests, and recommended baseline preferences."""

    root: Path
    detected_ecosystems: List[str] = field(default_factory=list)
    primary_language: Optional[str] = None
    manifest_files: List[str] = field(default_factory=list)
    recommended_skills: List[str] = field(default_factory=list)
    suggested_preferences: Dict[str, str] = field(default_factory=dict)
    suggested_weights: Dict[str, float] = field(default_factory=dict)
    is_pure_backend: bool = False
    is_pure_contract: bool = False
    is_fullstack: bool = False
    scan_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "detected_ecosystems": self.detected_ecosystems,
            "primary_language": self.primary_language,
            "manifest_files": self.manifest_files,
            "recommended_skills": self.recommended_skills,
            "suggested_preferences": self.suggested_preferences,
            "suggested_weights": {k: round(v, 2) for k, v in self.suggested_weights.items()},
            "is_pure_backend": self.is_pure_backend,
            "is_pure_contract": self.is_pure_contract,
            "is_fullstack": self.is_fullstack,
            "scan_latency_ms": round(self.scan_latency_ms, 3),
        }

    def summary_label(self) -> str:
        """Concise one-line summary of the detected project stack."""
        if not self.detected_ecosystems:
            return "Generic / Unspecified Stack"
        parts = [e.capitalize() for e in self.detected_ecosystems if e != "full-stack"][:4]
        if self.primary_language and self.primary_language.capitalize() not in parts:
            parts.insert(0, self.primary_language.capitalize())
        prefix = "Full-Stack: " if self.is_fullstack else ""
        return prefix + " + ".join(parts)


def _compute_cache_token(root: Path) -> Tuple[Tuple[str, ...], Tuple[Tuple[str, float], ...]]:
    """Compute deterministic cache invalidation token from workspace structure and manifest file mtimes."""
    workspace_dirs: List[str] = []
    manifest_tokens: List[Tuple[str, float]] = []

    try:
        with os.scandir(root) as it:
            for entry in it:
                name_lower = entry.name.lower()
                if name_lower in IGNORED_DIRS:
                    continue
                try:
                    if entry.is_file() and _is_manifest_file(name_lower):
                        manifest_tokens.append((entry.name, entry.stat().st_mtime))
                    elif entry.is_dir():
                        if name_lower in WORKSPACE_CONTAINERS:
                            workspace_dirs.append(entry.name)
                            try:
                                with os.scandir(entry.path) as sub_it:
                                    for sub in sub_it:
                                        if sub.is_dir() and sub.name.lower() not in IGNORED_DIRS:
                                            workspace_dirs.append(f"{entry.name}/{sub.name}")
                                            try:
                                                with os.scandir(sub.path) as pkg_it:
                                                    for m in pkg_it:
                                                        m_lower = m.name.lower()
                                                        if m.is_file() and _is_manifest_file(m_lower):
                                                            manifest_tokens.append((
                                                                f"{entry.name}/{sub.name}/{m.name}",
                                                                m.stat().st_mtime,
                                                            ))
                                            except OSError:
                                                pass
                            except OSError:
                                pass
                        elif name_lower in DIRECT_WORKSPACES:
                            workspace_dirs.append(entry.name)
                            try:
                                with os.scandir(entry.path) as dir_it:
                                    for m in dir_it:
                                        m_lower = m.name.lower()
                                        if m.is_file() and _is_manifest_file(m_lower):
                                            manifest_tokens.append((
                                                f"{entry.name}/{m.name}",
                                                m.stat().st_mtime,
                                            ))
                                        elif m.is_dir() and m_lower not in IGNORED_DIRS:
                                            workspace_dirs.append(f"{entry.name}/{m.name}")
                                            try:
                                                with os.scandir(m.path) as deep_it:
                                                    for dm in deep_it:
                                                        dm_lower = dm.name.lower()
                                                        if dm.is_file() and _is_manifest_file(dm_lower):
                                                            manifest_tokens.append((
                                                                f"{entry.name}/{m.name}/{dm.name}",
                                                                dm.stat().st_mtime,
                                                            ))
                                            except OSError:
                                                pass
                            except OSError:
                                pass
                except OSError:
                    pass
    except OSError:
        pass

    return (tuple(sorted(workspace_dirs)), tuple(sorted(manifest_tokens)))


def _is_cache_token_valid(
    root: Path,
    cached_token: Tuple[Tuple[str, ...], Tuple[Tuple[str, float], ...]],
) -> bool:
    """Fast O(1) check if cached token is still valid by comparing workspace structure and manifest mtimes."""
    try:
        if not root.is_dir():
            return False
        return _compute_cache_token(root) == cached_token
    except OSError:
        return False


def find_project_root(start_dir: Optional[Path | str] = None) -> Path:
    """Locate project root by ascending until .git or major monorepo/manifest root is found."""
    try:
        curr = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        if curr.is_file():
            curr = curr.parent
    except Exception:
        return Path.cwd().resolve()

    # 1. Search ancestry for VCS (.git) root - highest priority in git repos
    ancestry = [curr] + list(curr.parents)
    for p in ancestry:
        git_marker = p / ".git"
        if git_marker.exists():
            return p

    # 2. Search ancestry for explicit monorepo workspace configurations
    for p in ancestry:
        if any((p / wm).exists() for wm in WORKSPACE_MARKERS):
            return p
        pkg_json = p / "package.json"
        if pkg_json.is_file():
            try:
                raw = pkg_json.read_text(encoding="utf-8", errors="ignore")[:4096]
                if '"workspaces"' in raw:
                    return p
            except OSError:
                pass
        cargo_toml = p / "Cargo.toml"
        if cargo_toml.is_file():
            try:
                raw = cargo_toml.read_text(encoding="utf-8", errors="ignore")[:4096]
                if "[workspace]" in raw:
                    return p
            except OSError:
                pass

    # 3. Check if an ancestor contains workspace container directories enclosing curr
    for p in curr.parents:
        if any((p / c).is_dir() for c in WORKSPACE_CONTAINERS):
            if any((p / m).exists() for m in (
                "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "foundry.toml"
            )):
                return p

    # 4. Standard single-project root markers
    root_markers = (
        "package.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "foundry.toml", "hardhat.config.js", "hardhat.config.ts",
    )
    for m in root_markers:
        if (curr / m).exists():
            return curr

    for parent in curr.parents:
        if any((parent / m).exists() for m in root_markers):
            return parent

    return curr


def _inspect_directory_manifests(
    dir_path: Path,
    rel_prefix: str,
    max_inspect_bytes: int,
    ecosystems: Set[str],
    manifests: List[str],
) -> Tuple[Optional[str], bool, bool, bool]:
    """Inspects manifest files in a single directory.

    Returns:
        (detected_primary_lang, has_frontend, has_backend, has_contracts)
    """
    detected_lang: Optional[str] = None
    has_fe = False
    has_be = False
    has_ct = False

    try:
        entries = {e.name.lower(): e for e in dir_path.iterdir() if e.name not in IGNORED_DIRS}
    except OSError:
        return None, False, False, False

    # 1. Smart Contracts / EVM / Web3
    if "foundry.toml" in entries:
        manifests.append(f"{rel_prefix}foundry.toml")
        ecosystems.update(["solidity", "foundry", "smart-contract"])
        detected_lang = detected_lang or "solidity"
        has_ct = True

    if any(k in entries for k in ("hardhat.config.js", "hardhat.config.ts")):
        cfg = [k for k in ("hardhat.config.js", "hardhat.config.ts") if k in entries][0]
        manifests.append(f"{rel_prefix}{cfg}")
        ecosystems.update(["solidity", "hardhat", "smart-contract"])
        detected_lang = detected_lang or "solidity"
        has_ct = True

    for sol_subdir in ("contracts", "src"):
        if sol_subdir in entries and entries[sol_subdir].is_dir():
            try:
                for sub in entries[sol_subdir].iterdir():
                    if sub.suffix.lower() == ".sol":
                        ecosystems.add("solidity")
                        detected_lang = detected_lang or "solidity"
                        has_ct = True
                        break
            except OSError:
                pass
            if has_ct:
                break

    # Direct contracts check in dir itself
    if not has_ct:
        try:
            for sub in dir_path.iterdir():
                if sub.suffix.lower() == ".sol":
                    ecosystems.add("solidity")
                    detected_lang = detected_lang or "solidity"
                    has_ct = True
                    break
        except OSError:
            pass

    # 2. Rust
    if "cargo.toml" in entries:
        manifests.append(f"{rel_prefix}Cargo.toml")
        ecosystems.add("rust")
        detected_lang = detected_lang or "rust"
        has_be = True

    # 3. Go
    if "go.mod" in entries:
        manifests.append(f"{rel_prefix}go.mod")
        ecosystems.add("golang")
        detected_lang = detected_lang or "go"
        has_be = True

    # 4. JavaScript / TypeScript / Frontend Web
    if "package.json" in entries:
        manifests.append(f"{rel_prefix}package.json")
        ecosystems.add("nodejs")
        pkg_file = entries["package.json"]
        try:
            raw_text = pkg_file.read_text(encoding="utf-8", errors="ignore")[:max_inspect_bytes]
            pkg_data = json.loads(raw_text)
            if isinstance(pkg_data, dict):
                deps: Dict[str, Any] = {}
                for d_key in ("dependencies", "devDependencies", "peerDependencies"):
                    sub = pkg_data.get(d_key)
                    if isinstance(sub, dict):
                        deps.update({k.lower(): v for k, v in sub.items()})

                # Framework dependencies
                if "next" in deps:
                    ecosystems.update(["nextjs", "react"])
                    has_fe = True
                elif "react" in deps:
                    ecosystems.add("react")
                    has_fe = True

                if "vue" in deps or "nuxt" in deps:
                    ecosystems.add("vue")
                    has_fe = True

                if "svelte" in deps or "@sveltejs/kit" in deps:
                    ecosystems.add("svelte")
                    has_fe = True

                if "tailwindcss" in deps or any("tailwind" in k for k in deps):
                    ecosystems.add("tailwind")
                    has_fe = True

                if "typescript" in deps:
                    ecosystems.add("typescript")
                    detected_lang = detected_lang or "typescript"

                if any(b in deps for b in ("express", "fastify", "nest", "@nestjs/core")):
                    ecosystems.add("node-backend")
                    has_be = True
        except Exception:
            pass

    if any(k.startswith("next.config.") for k in entries):
        cfg_name = [k for k in entries if k.startswith("next.config.")][0]
        manifests.append(f"{rel_prefix}{cfg_name}")
        ecosystems.update(["nextjs", "react"])
        has_fe = True

    if any(k.startswith("tailwind.config.") for k in entries):
        cfg_name = [k for k in entries if k.startswith("tailwind.config.")][0]
        manifests.append(f"{rel_prefix}{cfg_name}")
        ecosystems.add("tailwind")
        has_fe = True

    if any(k in entries for k in ("tsconfig.json", "jsconfig.json")):
        if "tsconfig.json" in entries:
            manifests.append(f"{rel_prefix}tsconfig.json")
            ecosystems.add("typescript")
            detected_lang = detected_lang or "typescript"
        else:
            manifests.append(f"{rel_prefix}jsconfig.json")
            ecosystems.add("javascript")
            detected_lang = detected_lang or "javascript"
    elif "package.json" in entries:
        detected_lang = detected_lang or "javascript"

    # 5. Python
    if any(k in entries for k in ("pyproject.toml", "requirements.txt", "setup.py", "pipfile", "poetry.lock")):
        ecosystems.add("python")
        detected_lang = detected_lang or "python"
        has_be = True

        py_manifest = None
        for cand in ("pyproject.toml", "requirements.txt", "setup.py"):
            if cand in entries:
                py_manifest = cand
                manifests.append(f"{rel_prefix}{cand}")
                break

        if py_manifest and py_manifest in entries:
            try:
                py_text = entries[py_manifest].read_text(encoding="utf-8", errors="ignore")[:max_inspect_bytes].lower()
                if "fastapi" in py_text:
                    ecosystems.add("fastapi")
                if "django" in py_text:
                    ecosystems.add("django")
                if "flask" in py_text:
                    ecosystems.add("flask")
                if "pytest" in py_text:
                    ecosystems.add("pytest")
                if "sqlalchemy" in py_text or "alembic" in py_text:
                    ecosystems.add("sqlalchemy")
            except Exception:
                pass

    if "alembic.ini" in entries:
        ecosystems.add("alembic")
        manifests.append(f"{rel_prefix}alembic.ini")
        has_be = True

    # 6. Containers / Docker
    if any(k in entries for k in ("dockerfile", "docker-compose.yml", "docker-compose.yaml")):
        ecosystems.add("docker")

    return detected_lang, has_fe, has_be, has_ct


def detect_project_fingerprint(
    root_dir: Optional[Path | str] = None,
    max_inspect_bytes: int = 65536,
) -> ProjectFingerprint:
    """Detect project ecosystems, frameworks, and recommended skill alignments in < 0.5ms."""
    start_time = time.perf_counter()

    # Fast cache probe by input path before ascending directories
    if root_dir is not None:
        input_key = str(root_dir)
        cached_input = _FINGERPRINT_CACHE.get(input_key)
        if cached_input is not None:
            cached_token, cached_fp = cached_input
            if _is_cache_token_valid(cached_fp.root, cached_token):
                return cached_fp

    root = find_project_root(root_dir)
    cache_key = str(root)

    cached = _FINGERPRINT_CACHE.get(cache_key)
    if cached is not None:
        cached_token, cached_fp = cached
        if _is_cache_token_valid(cached_fp.root, cached_token):
            if root_dir is not None:
                _FINGERPRINT_CACHE[str(root_dir)] = cached
            return cached_fp

    token = _compute_cache_token(root)

    ecosystems: Set[str] = set()
    manifests: List[str] = []
    primary_lang: Optional[str] = None
    suggested_preferences: Dict[str, str] = {}
    suggested_weights: Dict[str, float] = {}

    # Inspect root directory
    root_lang, has_frontend, has_backend, has_contracts = _inspect_directory_manifests(
        root, "", max_inspect_bytes, ecosystems, manifests
    )
    primary_lang = primary_lang or root_lang

    # Inspect nested workspaces (ISS-20: apps/*, packages/*, services/*, crates/*, contracts/*, frontend, backend)
    try:
        root_entries = {e.name.lower(): e for e in root.iterdir() if e.name not in IGNORED_DIRS}
    except OSError:
        root_entries = {}

    # Container directories (apps/*, packages/*, services/*, crates/*, libs/*, modules/*)
    for c_name in WORKSPACE_CONTAINERS:
        if c_name in root_entries and root_entries[c_name].is_dir():
            c_dir = root_entries[c_name]
            try:
                for sub in c_dir.iterdir():
                    if sub.is_dir() and sub.name.lower() not in IGNORED_DIRS:
                        s_lang, s_fe, s_be, s_ct = _inspect_directory_manifests(
                            sub, f"{c_name}/{sub.name}/", max_inspect_bytes, ecosystems, manifests
                        )
                        primary_lang = primary_lang or s_lang
                        has_frontend = has_frontend or s_fe
                        has_backend = has_backend or s_be
                        has_contracts = has_contracts or s_ct
            except OSError:
                pass

    # Direct workspace directories (frontend, backend, client, server, web, api, contracts)
    for d_name in DIRECT_WORKSPACES:
        if d_name in root_entries and root_entries[d_name].is_dir():
            d_dir = root_entries[d_name]
            s_lang, s_fe, s_be, s_ct = _inspect_directory_manifests(
                d_dir, f"{d_name}/", max_inspect_bytes, ecosystems, manifests
            )
            primary_lang = primary_lang or s_lang
            has_frontend = has_frontend or s_fe
            has_backend = has_backend or s_be
            has_contracts = has_contracts or s_ct

    # Determine domain categorization & full-stack detection
    is_fullstack = has_frontend and (has_backend or has_contracts)
    if is_fullstack:
        ecosystems.add("full-stack")

    is_pure_contract = has_contracts and not has_frontend and not (has_backend and "fastapi" in ecosystems)
    is_pure_backend = (has_backend or has_contracts) and not has_frontend

    # Build recommended skill alignments via extensible registry
    from taxonomy.registry import get_stack_alignments
    alignments = get_stack_alignments()
    recommended_skills: List[str] = []

    # Next.js / React recommendation
    if "nextjs" in ecosystems or ("react" in ecosystems and "typescript" in ecosystems):
        for entry in alignments.get("nextjs" if "nextjs" in ecosystems else "react", []):
            suggested_preferences[entry["category"]] = entry["skill"]
            suggested_weights[entry["skill"]] = entry.get("weight", 2.0)
            if entry["skill"] not in recommended_skills:
                recommended_skills.append(entry["skill"])

    # Tailwind / UI recommendation
    if "tailwind" in ecosystems:
        for entry in alignments.get("tailwind", []):
            suggested_preferences[entry["category"]] = entry["skill"]
            suggested_weights[entry["skill"]] = entry.get("weight", 1.5)
            if entry["skill"] not in recommended_skills:
                recommended_skills.append(entry["skill"])

    # Smart contract auditor recommendation
    if has_contracts:
        for entry in alignments.get("solidity", []):
            suggested_preferences[entry["category"]] = entry["skill"]
            suggested_weights[entry["skill"]] = entry.get("weight", 2.5)
            if entry["skill"] not in recommended_skills:
                recommended_skills.append(entry["skill"])

    # QA / Testing recommendation
    if "pytest" in ecosystems or "nodejs" in ecosystems or "rust" in ecosystems or has_backend:
        for entry in alignments.get("testing", []):
            suggested_preferences[entry["category"]] = entry["skill"]
            suggested_weights[entry["skill"]] = entry.get("weight", 2.0)
            if entry["skill"] not in recommended_skills:
                recommended_skills.append(entry["skill"])

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    fingerprint = ProjectFingerprint(
        root=root,
        detected_ecosystems=sorted(list(ecosystems)),
        primary_language=primary_lang,
        manifest_files=sorted(list(dict.fromkeys(manifests))),
        recommended_skills=recommended_skills,
        suggested_preferences=suggested_preferences,
        suggested_weights=suggested_weights,
        is_pure_backend=is_pure_backend,
        is_pure_contract=is_pure_contract,
        is_fullstack=is_fullstack,
        scan_latency_ms=elapsed_ms,
    )

    _FINGERPRINT_CACHE[cache_key] = (token, fingerprint)
    if root_dir is not None:
        _FINGERPRINT_CACHE[str(root_dir)] = (token, fingerprint)

    return fingerprint
