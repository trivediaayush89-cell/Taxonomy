"""Fast, deterministic project fingerprinting and zero-config stack detection."""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("taxonomy.fingerprint")

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", "target", "dist", "build", ".next",
    ".taxonomy", ".court", ".agents",
})

# In-memory cache: root_str -> (mtime, ProjectFingerprint)
_FINGERPRINT_CACHE: Dict[str, Tuple[float, "ProjectFingerprint"]] = {}


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
            "scan_latency_ms": round(self.scan_latency_ms, 3),
        }

    def summary_label(self) -> str:
        """Concise one-line summary of the detected project stack."""
        if not self.detected_ecosystems:
            return "Generic / Unspecified Stack"
        parts = [e.capitalize() for e in self.detected_ecosystems[:4]]
        if self.primary_language and self.primary_language.capitalize() not in parts:
            parts.insert(0, self.primary_language.capitalize())
        return " + ".join(parts)


def find_project_root(start_dir: Optional[Path | str] = None) -> Path:
    """Locate project root by ascending until .git or major manifest is found."""
    try:
        curr = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        if curr.is_file():
            curr = curr.parent
    except Exception:
        return Path.cwd().resolve()

    root_markers = (
        ".git", "package.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "foundry.toml", "hardhat.config.js", "hardhat.config.ts",
    )
    for m in root_markers:
        if (curr / m).exists():
            return curr

    for parent in curr.parents:
        if any((parent / m).exists() for m in root_markers):
            return parent

    return curr


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
            try:
                if Path(root_dir).stat().st_mtime == cached_input[0]:
                    return cached_input[1]
            except OSError:
                pass

    root = find_project_root(root_dir)
    cache_key = str(root)

    try:
        stat = root.stat()
        mtime = stat.st_mtime
    except OSError:
        mtime = 0.0

    cached = _FINGERPRINT_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        if root_dir is not None:
            _FINGERPRINT_CACHE[str(root_dir)] = cached
        return cached[1]

    ecosystems: Set[str] = set()
    manifests: List[str] = []
    primary_lang: Optional[str] = None
    suggested_preferences: Dict[str, str] = {}
    suggested_weights: Dict[str, float] = {}

    has_frontend = False
    has_backend = False
    has_contracts = False

    # Check root entries
    try:
        root_entries = {e.name.lower(): e for e in root.iterdir() if e.name not in IGNORED_DIRS}
    except OSError:
        root_entries = {}

    # 1. Smart Contracts / EVM / Web3
    if "foundry.toml" in root_entries:
        manifests.append("foundry.toml")
        ecosystems.update(["solidity", "foundry", "smart-contract"])
        primary_lang = primary_lang or "solidity"
        has_contracts = True

    if any(k in root_entries for k in ("hardhat.config.js", "hardhat.config.ts")):
        manifests.append([k for k in ("hardhat.config.js", "hardhat.config.ts") if k in root_entries][0])
        ecosystems.update(["solidity", "hardhat", "smart-contract"])
        primary_lang = primary_lang or "solidity"
        has_contracts = True

    if "contracts" in root_entries and root_entries["contracts"].is_dir():
        try:
            for sub in root_entries["contracts"].iterdir():
                if sub.suffix.lower() == ".sol":
                    ecosystems.add("solidity")
                    primary_lang = primary_lang or "solidity"
                    has_contracts = True
                    break
        except OSError:
            pass

    # 2. Rust
    if "cargo.toml" in root_entries:
        manifests.append("Cargo.toml")
        ecosystems.add("rust")
        primary_lang = primary_lang or "rust"
        has_backend = True

    # 3. Go
    if "go.mod" in root_entries:
        manifests.append("go.mod")
        ecosystems.add("golang")
        primary_lang = primary_lang or "go"
        has_backend = True

    # 4. JavaScript / TypeScript / Frontend Web
    if "package.json" in root_entries:
        manifests.append("package.json")
        ecosystems.add("nodejs")
        pkg_file = root_entries["package.json"]
        try:
            raw_text = pkg_file.read_text(encoding="utf-8", errors="ignore")[:max_inspect_bytes]
            pkg_data = json.loads(raw_text)
            if isinstance(pkg_data, dict):
                deps = {}
                for d_key in ("dependencies", "devDependencies", "peerDependencies"):
                    sub = pkg_data.get(d_key)
                    if isinstance(sub, dict):
                        deps.update({k.lower(): v for k, v in sub.items()})

                # Check framework dependencies
                if "next" in deps:
                    ecosystems.update(["nextjs", "react"])
                    has_frontend = True
                elif "react" in deps:
                    ecosystems.add("react")
                    has_frontend = True

                if "vue" in deps or "nuxt" in deps:
                    ecosystems.add("vue")
                    has_frontend = True

                if "svelte" in deps or "@sveltejs/kit" in deps:
                    ecosystems.add("svelte")
                    has_frontend = True

                if "tailwindcss" in deps or any("tailwind" in k for k in deps):
                    ecosystems.add("tailwind")
                    has_frontend = True

                if "typescript" in deps:
                    ecosystems.add("typescript")
                    primary_lang = primary_lang or "typescript"

                if any(b in deps for b in ("express", "fastify", "nest", "@nestjs/core")):
                    ecosystems.add("node-backend")
                    has_backend = True
        except Exception:
            pass

    if any(k.startswith("next.config.") for k in root_entries):
        cfg_name = [k for k in root_entries if k.startswith("next.config.")][0]
        manifests.append(cfg_name)
        ecosystems.update(["nextjs", "react"])
        has_frontend = True

    if any(k.startswith("tailwind.config.") for k in root_entries):
        cfg_name = [k for k in root_entries if k.startswith("tailwind.config.")][0]
        manifests.append(cfg_name)
        ecosystems.add("tailwind")
        has_frontend = True

    if any(k in root_entries for k in ("tsconfig.json", "jsconfig.json")):
        if "tsconfig.json" in root_entries:
            manifests.append("tsconfig.json")
            ecosystems.add("typescript")
            primary_lang = primary_lang or "typescript"
        else:
            manifests.append("jsconfig.json")
            ecosystems.add("javascript")
            primary_lang = primary_lang or "javascript"
    elif "package.json" in root_entries:
        primary_lang = primary_lang or "javascript"

    # 5. Python
    if any(k in root_entries for k in ("pyproject.toml", "requirements.txt", "setup.py", "pipfile", "poetry.lock")):
        ecosystems.add("python")
        primary_lang = primary_lang or "python"
        has_backend = True

        py_manifest = None
        for cand in ("pyproject.toml", "requirements.txt", "setup.py"):
            if cand in root_entries:
                py_manifest = cand
                manifests.append(cand)
                break

        if py_manifest and py_manifest in root_entries:
            try:
                py_text = root_entries[py_manifest].read_text(encoding="utf-8", errors="ignore")[:max_inspect_bytes].lower()
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

    if "alembic.ini" in root_entries or "alembic" in root_entries:
        ecosystems.add("alembic")
        has_backend = True

    # 6. Containers / Docker
    if any(k in root_entries for k in ("dockerfile", "docker-compose.yml", "docker-compose.yaml")):
        ecosystems.add("docker")

    # Determine domain categorization
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
    if "pytest" in ecosystems or "nodejs" in ecosystems or "rust" in ecosystems:
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
        manifest_files=manifests,
        recommended_skills=recommended_skills,
        suggested_preferences=suggested_preferences,
        suggested_weights=suggested_weights,
        is_pure_backend=is_pure_backend,
        is_pure_contract=is_pure_contract,
        scan_latency_ms=elapsed_ms,
    )

    _FINGERPRINT_CACHE[cache_key] = (mtime, fingerprint)
    return fingerprint
