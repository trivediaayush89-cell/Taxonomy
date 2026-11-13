"""Fast frontmatter auto-indexer with mtime-based cache invalidation and root precedence."""

import hashlib
import json
import os
import stat
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from taxonomy.dag import CategoryDAG
from taxonomy.models import SkillMetadata
from taxonomy.schema import parse_skill_markdown

DEFAULT_SKILL_ROOTS = [
    Path("~/.gemini/config/skills").expanduser(),
    Path("~/.agents/skills").expanduser(),
    Path("~/.gemini/antigravity/builtin/skills").expanduser(),
]

DEFAULT_SKILLS_CONFIG_PATH = Path("~/.gemini/config/skills.json").expanduser()


def load_skills_config(config_path: Optional[Path | str] = None) -> Tuple[List[Path], Set[str]]:
    """Read ~/.gemini/config/skills.json to discover configured skill roots and excluded skill names."""
    path = Path(config_path).expanduser() if config_path is not None else DEFAULT_SKILLS_CONFIG_PATH
    configured_roots: List[Path] = []
    excluded_skills: Set[str] = set()

    if not path.is_file():
        return configured_roots, excluded_skills

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_path = entry.get("path")
            if isinstance(raw_path, str) and raw_path.strip():
                configured_roots.append(Path(raw_path).expanduser())
            excludes = entry.get("exclude", [])
            if isinstance(excludes, list):
                for item in excludes:
                    if isinstance(item, str) and item.strip():
                        excluded_skills.add(item.strip())
    except (OSError, json.JSONDecodeError):
        pass

    return configured_roots, excluded_skills


class SkillIndexer:
    """Discovers, parses, and indexes SKILL.md files directly from skill directories.

    Features:
    - File modification time (mtime) caching to avoid unnecessary disk I/O.
    - Root precedence: earlier roots in skills_roots override duplicate names in later roots.
    - Honors ~/.gemini/config/skills.json entries and exclusion lists.
    - Path-to-name tracking so folder names differing from YAML 'name' are never falsely evicted.
    - Canonical symlink containment via safe_resolve_skill_path.
    """

    def __init__(
        self,
        skills_roots: Optional[List[Path | str]] = None,
        skills_config_path: Optional[Path | str] = None,
        excluded_skills: Optional[Iterable[str]] = None,
    ):
        self.excluded_skills: Set[str] = set(excluded_skills or [])

        if skills_roots is None:
            cfg_roots, cfg_excludes = load_skills_config(skills_config_path)
            self.excluded_skills.update(cfg_excludes)
            # Priority order: ~/.gemini/config/skills -> skills.json roots / ~/.agents/skills -> builtin
            candidate_roots = [DEFAULT_SKILL_ROOTS[0], *cfg_roots, *DEFAULT_SKILL_ROOTS[1:]]
        else:
            if skills_config_path is not None:
                _, cfg_excludes = load_skills_config(skills_config_path)
                self.excluded_skills.update(cfg_excludes)
            candidate_roots = [Path(r).expanduser() for r in skills_roots]

        self.skills_roots: List[Path] = []
        seen_resolved: Set[Path] = set()
        for p in candidate_roots:
            if p.exists():
                resolved = p.resolve()
                if resolved not in seen_resolved:
                    self.skills_roots.append(resolved)
                    seen_resolved.add(resolved)

        self._skills_by_name: Dict[str, SkillMetadata] = {}
        self._skills_by_category: Dict[str, List[SkillMetadata]] = defaultdict(list)
        self._tag_to_skills: Dict[str, Set[str]] = defaultdict(set)
        self._cached_mtimes: Dict[str, float] = {}
        self._path_to_skill_name: Dict[str, str] = {}
        self._catalog_hash: Optional[str] = None

    def scan(self, force: bool = False) -> Dict[str, SkillMetadata]:
        """Scan skills roots and refresh the index where files have changed."""
        seen_skill_names: Set[str] = set()
        seen_paths: Set[str] = set()
        changed = False
        # Tuple of (root, skill_md, current_mtime)
        files_to_parse: List[Tuple[Path, Path, float]] = []

        for root in self.skills_roots:
            if not root.is_dir():
                continue

            # Antigravity discovers skills at: <root>/<skill-name>/SKILL.md
            for entry in sorted(os.scandir(root), key=lambda e: e.name):
                if not entry.is_dir():
                    continue
                if entry.name in self.excluded_skills:
                    continue

                skill_path_str = os.path.join(entry.path, "SKILL.md")
                try:
                    st = os.stat(skill_path_str)
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    current_mtime = st.st_mtime
                except OSError:
                    continue

                seen_paths.add(skill_path_str)
                last_mtime = self._cached_mtimes.get(skill_path_str)
                cached_name = self._path_to_skill_name.get(skill_path_str)

                if force or last_mtime is None or current_mtime > last_mtime or cached_name is None:
                    files_to_parse.append((root, Path(skill_path_str), current_mtime))
                else:
                    # Unchanged file: respect root precedence
                    if cached_name not in seen_skill_names and cached_name in self._skills_by_name:
                        seen_skill_names.add(cached_name)

        if files_to_parse:
            changed = True
            if len(files_to_parse) > 8:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as executor:
                    futures = [executor.submit(parse_skill_markdown, p, root) for root, p, _ in files_to_parse]
                    for (root, p, mtime), f in zip(files_to_parse, futures):
                        metadata = f.result()
                        if metadata and metadata.name not in self.excluded_skills:
                            path_key = str(p)
                            self._cached_mtimes[path_key] = mtime
                            self._path_to_skill_name[path_key] = metadata.name
                            # Root precedence: earlier root wins if not yet seen in this scan
                            if metadata.name not in seen_skill_names:
                                self._skills_by_name[metadata.name] = metadata
                                seen_skill_names.add(metadata.name)
            else:
                for root, p, mtime in files_to_parse:
                    metadata = parse_skill_markdown(p, root)
                    if metadata and metadata.name not in self.excluded_skills:
                        path_key = str(p)
                        self._cached_mtimes[path_key] = mtime
                        self._path_to_skill_name[path_key] = metadata.name
                        if metadata.name not in seen_skill_names:
                            self._skills_by_name[metadata.name] = metadata
                            seen_skill_names.add(metadata.name)

        # Clean up deleted file path caches
        stale_paths = [p for p in self._cached_mtimes if p not in seen_paths]
        for p in stale_paths:
            self._cached_mtimes.pop(p, None)
            self._path_to_skill_name.pop(p, None)

        # Evict deleted skills
        to_delete = [name for name in self._skills_by_name if name not in seen_skill_names]
        if to_delete:
            changed = True
            for name in to_delete:
                del self._skills_by_name[name]

        if changed or not self._skills_by_category:
            self._rebuild_indices()

        return self._skills_by_name

    def _rebuild_indices(self) -> None:
        """Rebuild category and tag lookup tables from in-memory skills."""
        self._catalog_hash = None
        self._skills_by_category = defaultdict(list)
        self._tag_to_skills = defaultdict(set)

        for skill in self._skills_by_name.values():
            if skill.status == "deprecated":
                continue

            self._skills_by_category[skill.category].append(skill)
            for tag in skill.tags:
                self._tag_to_skills[tag].add(skill.name)

        # Sort each category by priority descending, then name ascending for deterministic tie-breaking
        for cat in self._skills_by_category:
            self._skills_by_category[cat].sort(key=lambda s: (-s.priority, s.name))

    def compute_catalog_hash(self) -> str:
        """Deterministic 16-hex digest of the active indexed skill catalog."""
        if self._catalog_hash is not None:
            return self._catalog_hash

        if not self._skills_by_name:
            self._catalog_hash = "empty_catalog000"
            return self._catalog_hash

        skills_summary = []
        for name in sorted(self._skills_by_name.keys()):
            s = self._skills_by_name[name]
            if s.status == "deprecated":
                continue
            skills_summary.append({
                "name": s.name,
                "category": s.category,
                "tags": sorted(s.tags),
                "priority": s.priority,
                "requires": sorted(s.requires),
                "conflicts_with": sorted(s.conflicts_with),
                "mtime": round(s.mtime, 2),
                "version": getattr(s, "version", "1.0.0"),
                "content_hash": getattr(s, "content_hash", ""),
            })

        if not skills_summary:
            self._catalog_hash = "empty_catalog000"
            return self._catalog_hash

        raw = json.dumps(skills_summary, sort_keys=True)
        self._catalog_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return self._catalog_hash

    def validate_dependency_dag(self) -> List[str]:
        """Validate that skill 'requires' dependencies form a strict DAG without circular loops."""
        dag = CategoryDAG()
        for skill in self._skills_by_name.values():
            for req in skill.requires:
                dag.add_alias(skill.name, req)
        return dag.validate_acyclic()

    def get_skill(self, name: str) -> Optional[SkillMetadata]:
        return self._skills_by_name.get(name)

    def get_by_category(self, category: str) -> List[SkillMetadata]:
        return self._skills_by_category.get(category, [])

    def get_categories(self) -> List[str]:
        return sorted(list(self._skills_by_category.keys()))

    def get_skills_for_tag(self, tag: str) -> List[SkillMetadata]:
        names = self._tag_to_skills.get(tag.lower(), set())
        return [self._skills_by_name[n] for n in names if n in self._skills_by_name]

    @property
    def all_skills(self) -> List[SkillMetadata]:
        return list(self._skills_by_name.values())
