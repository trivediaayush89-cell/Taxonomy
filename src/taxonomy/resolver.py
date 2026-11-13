"""Ranked skill resolver with pre-compiled token sets, word-boundary tag scoring, and conflict locking."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from collections import defaultdict
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, Union

from taxonomy.bm25 import BM25Index
from taxonomy.gate import CompoundGate
from taxonomy.indexer import SkillIndexer
from taxonomy.models import GateResult, ResolutionResult, SkillMetadata, SkillScore
from taxonomy.taste import TasteProfile, load_taste_profile
from taxonomy.efficacy import EfficacyTracker
from taxonomy.dag import CyclicDependencyError, SkillDAG

VISUAL_AUTHORITY_CATEGORIES: FrozenSet[str] = frozenset({
    "ui.marketing", "ui.product", "ui.cleanup", "ui.taste", "ui.design",
})

DEFAULT_EXCLUSIVE_CATEGORIES: FrozenSet[str] = frozenset({
    "ui.marketing", "ui.product", "ui.cleanup", "ui.taste", "ui.design",
})

STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "let's", "me", "more", "most", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "won't", "would", "you", "your", "yours", "yourself",
    "use", "when", "skip", "before", "after", "any", "every", "across",
    "run", "running", "make", "get", "set", "put", "new", "start", "starting", "proposed",
    "build", "building", "create", "creating", "work", "working", "want", "wants",
    "need", "needs", "help", "helps", "using", "used", "also", "like", "other",
})

GENERIC_NAME_PARTS = frozenset({
    "design", "review", "frontend", "engineering", "quality", "gate", "code",
    "skill", "skills", "find", "creator", "best", "practices", "pro", "max",
    "ui", "ux", "guide", "development", "director", "independent", "eng",
    "settings", "agent", "tool", "tools", "helper", "util", "utils",
})

NEGATIVE_CLAUSE_REGEX = re.compile(
    r"(?:not for|skip for|skip it for|don't use for|do not use for|never use for|"
    r"for critiquing existing|for auditing a whole)[^.;]*",
    re.IGNORECASE,
)

UI_FRONTEND_SIGNALS = frozenset({
    "ui", "ux", "frontend", "front-end", "react", "nextjs", "next-js", "vue", "svelte",
    "astro", "tailwind", "css", "html", "tsx", "jsx", "landing", "website", "webpage",
    "dashboard", "screen", "screens", "component", "components", "modal", "dropdown",
    "popover", "toast", "button", "form", "forms", "onboarding", "settings", "admin",
    "animation", "animations", "animate", "motion", "transition", "transitions", "easing",
    "spring", "layout", "responsive", "viewport", "accessibility", "wcag", "unslop",
    "slop", "vibecoded", "vibe-coded", "portfolio", "showcase", "hero", "one-pager",
    "marketing", "widget", "chart", "charts", "palette", "typography", "font", "fonts",
    "theme", "tokens", "ios", "android", "mobile", "desktop", "interface", "redesign",
    "restyle", "polish", "impeccable", "emil", "sonner", "gsap", "scrollytelling",
    "blog", "documentation", "saas",
})

BACKEND_ONLY_SIGNALS = frozenset({
    "backend", "api", "rest", "graphql", "grpc", "database", "sql", "postgres",
    "postgresql", "mysql", "sqlite", "redis", "kafka", "microservice", "microservices",
    "solidity", "smart-contract", "contract", "foundry", "evm", "defi", "rust", "golang",
    "cli", "daemon", "kernel", "socket", "tcp", "udp", "indexer", "dispatcher",
    "pytest", "fastapi", "django", "flask", "sqlalchemy", "alembic", "docker",
    "kubernetes", "terraform", "ci", "pipeline",
})

from taxonomy.registry import get_meta_categories, is_protected_sentry, get_protected_sentries, is_meta_skill

UI_CATEGORY_PREFIXES = ("ui.", "frontend.", "quality.animation")

AGY_META_CATEGORIES = get_meta_categories()

AGY_META_SIGNALS = frozenset({
    "antigravity", "agy", "plugin", "plugins", "mcp", "skill", "skills",
    "slash", "keybinding", "keybindings", "sidecar", "sidecars",
    "customization", "customizations", "marketplace", "workflow", "workflows",
    "npx-skills", "skill-creator", "find-skills",
})

PROTECTED_TECH_TERMS: FrozenSet[str] = frozenset({
    "postgres", "postgresql", "redis", "docker", "kubernetes", "k8s",
    "nextjs", "nestjs", "express", "flutter", "server", "serverless",
    "ethers", "hardhat", "foundry", "solidity", "solana", "graphql",
    "tailwind", "fastapi", "django", "flask", "prisma", "pandas", "numpy",
    "ansible", "terraform", "prometheus", "grafana", "nginx", "apache",
    "linux", "windows", "macos", "android", "ios", "rust", "golang",
    "python", "typescript", "javascript", "webpack", "vite", "turborepo",
    "pnpm", "yarn", "npm", "cargo", "css", "aws", "gcp", "azure", "ci", "qa",
    "evm", "zkp", "jwt", "api", "cli", "sdk", "grpc", "rest", "soap",
})

TECH_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "postgres": ("postgresql",),
    "postgresql": ("postgres",),
    "k8s": ("kubernetes",),
    "kubernetes": ("k8s",),
    "next.js": ("nextjs",),
    "nextjs": ("next.js",),
    "vue.js": ("vuejs",),
    "vuejs": ("vue.js",),
    "node.js": ("nodejs",),
    "nodejs": ("node.js",),
    "js": ("javascript",),
    "javascript": ("js",),
    "ts": ("typescript",),
    "typescript": ("ts",),
}

CAMEL_SPLIT_REGEX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
CODE_TOKEN_REGEX = re.compile(r"[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*")
TOKEN_REGEX = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
WORD_REGEX = re.compile(r"[a-z0-9]+")


def normalize_stem(word: str) -> str:
    """Fast deterministic stemmer protecting technical vocabulary from naive suffix stripping."""
    w = word.lower().strip(".,;:?!'\"()[]{}#*`~")
    if len(w) <= 3:
        return w
    if w in PROTECTED_TECH_TERMS:
        return w
    if w in ("juror", "jurors", "juries"):
        return "jury"
    for suffix in ("ing", "tion", "tions", "ment", "ments", "ers", "er", "ies", "es", "ed", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            stem = w[:-len(suffix)]
            if suffix == "ies":
                return stem + "y"
            return stem
    return w


def tokenize_code_aware(text: str) -> Tuple[Set[str], Set[str]]:
    """Tokenize a developer prompt or code text preserving identifiers, frameworks, and symbols.

    Returns:
        (prompt_words, prompt_stems)
    """
    raw_tokens = CODE_TOKEN_REGEX.findall(text)
    prompt_words: Set[str] = set()

    for raw in raw_tokens:
        lower = raw.lower()
        if lower not in STOP_WORDS and len(lower) >= 2:
            prompt_words.add(lower)

        # Dotted frameworks: next.js -> nextjs, next, js
        if "." in lower:
            no_dots = lower.replace(".", "")
            if no_dots not in STOP_WORDS and len(no_dots) >= 2:
                prompt_words.add(no_dots)
            for part in lower.split("."):
                if part and part not in STOP_WORDS and len(part) >= 2:
                    prompt_words.add(part)

        # Snake_case: query_param -> query, param, query_param
        if "_" in lower:
            for part in lower.split("_"):
                if part and part not in STOP_WORDS and len(part) >= 2:
                    prompt_words.add(part)

        # Hyphenated standards: erc-20 -> erc20, erc, 20
        if "-" in lower:
            no_hyphen = lower.replace("-", "")
            if no_hyphen not in STOP_WORDS and len(no_hyphen) >= 2:
                prompt_words.add(no_hyphen)
            for part in lower.split("-"):
                if part and part not in STOP_WORDS and len(part) >= 2:
                    prompt_words.add(part)

        # camelCase splitting: useEffect -> use, effect
        splits = CAMEL_SPLIT_REGEX.split(raw)
        if len(splits) > 1:
            for s in splits:
                s_lower = s.lower()
                if s_lower not in STOP_WORDS and len(s_lower) >= 2:
                    prompt_words.add(s_lower)

    prompt_stems: Set[str] = set()
    for w in prompt_words:
        stem = normalize_stem(w)
        prompt_stems.add(stem)
        # Tech synonyms
        if w in TECH_SYNONYMS:
            for syn in TECH_SYNONYMS[w]:
                prompt_stems.add(normalize_stem(syn))

    return prompt_words, prompt_stems


@dataclass(frozen=True)
class _CompiledSkillTokens:
    mtime: float
    single_tags: Tuple[Tuple[str, str], ...]  # (tag_lower, tag_stem)
    compound_tags: Tuple[Tuple[str, str, Tuple[str, ...]], ...]  # (tag_lower, tag_spaced, part_stems)
    desc_stems: FrozenSet[str]
    name_lower: str
    name_spaced: str
    name_parts: FrozenSet[str]
    is_ui_skill: bool
    is_meta: bool


def _compile_skill_tokens(skill: SkillMetadata) -> _CompiledSkillTokens:
    single_tags: List[Tuple[str, str]] = []
    compound_tags: List[Tuple[str, str, Tuple[str, ...]]] = []

    for tag in skill.tags:
        tag_lower = tag.lower().strip()
        if not tag_lower:
            continue
        if "-" in tag_lower or " " in tag_lower:
            tag_spaced = tag_lower.replace("-", " ")
            parts = tuple(normalize_stem(p) for p in re.split(r"[-\s]+", tag_lower) if p)
            compound_tags.append((tag_lower, tag_spaced, parts))
        else:
            single_tags.append((tag_lower, normalize_stem(tag_lower)))

    cleaned_desc = NEGATIVE_CLAUSE_REGEX.sub(" ", skill.description.lower())
    desc_tokens = WORD_REGEX.findall(cleaned_desc)
    desc_stems = frozenset(
        normalize_stem(w) for w in desc_tokens if len(w) >= 3 and w not in STOP_WORDS
    )

    name_lower = skill.name.lower()
    name_spaced = name_lower.replace("-", " ")
    name_parts = frozenset(
        p for p in name_lower.split("-")
        if len(p) >= 3 and p not in STOP_WORDS and p not in GENERIC_NAME_PARTS
    )
    is_ui_skill = (
        skill.category.startswith(UI_CATEGORY_PREFIXES)
        or any(t.lower() in ("ui", "frontend", "css", "tailwind", "ux") for t in skill.tags)
    )
    is_meta = is_meta_skill(skill)

    return _CompiledSkillTokens(
        mtime=skill.mtime,
        single_tags=tuple(single_tags),
        compound_tags=tuple(compound_tags),
        desc_stems=desc_stems,
        name_lower=name_lower,
        name_spaced=name_spaced,
        name_parts=name_parts,
        is_ui_skill=is_ui_skill,
        is_meta=is_meta,
    )


from taxonomy.lifecycle import (
    LIFECYCLE_PHASE_CATEGORY_MAP,
    PHASE_ALIASES,
    get_categories_for_phase,
    normalize_phase_name,
)

# Canonical phase mapping (ISS-14: enriched with design, planning, understanding, evaluation aliases)
PHASE_CATEGORY_MAP = LIFECYCLE_PHASE_CATEGORY_MAP


def compute_dynamic_budget(total_skills: int) -> int:
    """Judge Guardrail 1: Dynamic 5% Sizing Formula.
    Scales from min 3 on small/medium catalogs up to 5 on large (100+) catalogs.
    Formula: min(5, max(3, math.ceil(0.05 * total_skills)))
    """
    return min(5, max(3, math.ceil(0.05 * max(1, total_skills))))


COMPLEMENTARY_DOMAIN_ROLES: Dict[str, Tuple[str, ...]] = {
    # UI / Marketing / Design -> Engineering + Verification QA + Architecture Lead
    "ui.marketing": ("frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"),
    "ui.product": ("frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"),
    "ui.cleanup": ("frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"),
    "ui.component": ("frontend.engineering", "verification.qa", "frontend.react", "orchestration.lead"),
    "ui.animation": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    "ui.polish": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    "ui.interactive": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    "ui.reference": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    "ui.design": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    # Frontend Engineering / React -> Verification QA + Architecture Lead
    "frontend.engineering": ("verification.qa", "orchestration.lead", "frontend.react"),
    "frontend.react": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    # Backend / Systems / Security -> Architecture Lead + Verification QA + Review
    "backend.api": ("orchestration.lead", "verification.qa", "decision.review"),
    "security.blockchain": ("orchestration.lead", "verification.qa", "decision.review"),
    "ops.performance": ("orchestration.lead", "verification.qa"),
    # Orchestration / Coordination -> Verification QA + Review
    "orchestration.lead": ("verification.qa", "decision.review"),
    "decision.review": ("orchestration.lead", "verification.qa"),
    "quality.animation": ("frontend.engineering", "verification.qa", "orchestration.lead"),
    # Antigravity tooling
    "antigravity.config": ("antigravity.docs", "verification.qa", "orchestration.lead"),
    "antigravity.docs": ("antigravity.config", "verification.qa", "orchestration.lead"),
    "ecosystem.plugin": ("antigravity.config", "verification.qa", "orchestration.lead"),
    "agy.skills": ("antigravity.config", "verification.qa", "orchestration.lead"),
    "automation.cron": ("orchestration.lead", "verification.qa"),
}


class SkillResolver:
    """Evaluates prompts through the gate and resolves ranked skills from the index."""

    def __init__(
        self,
        indexer: SkillIndexer,
        max_skills: Optional[int] = None,
        taste_profile: Optional[TasteProfile] = None,
        workspace_root: Optional[Path | str] = None,
        efficacy_tracker: Optional[EfficacyTracker] = None,
        enable_efficacy_bias: bool = True,
        enable_triad: bool = True,
        exclusive_categories: Optional[Set[str]] = None,
        score_dropoff_ratio: float = 0.35,
        allow_sentry_override: bool = False,
    ):
        self.indexer = indexer
        self.gate = CompoundGate()
        self.enable_triad = enable_triad
        self.skill_dag = SkillDAG(self.indexer)
        self.exclusive_categories = set(exclusive_categories) if exclusive_categories is not None else set(DEFAULT_EXCLUSIVE_CATEGORIES)
        self.score_dropoff_ratio = score_dropoff_ratio
        self.allow_sentry_override = allow_sentry_override
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        if max_skills is not None:
            self.max_skills = max_skills
        else:
            active_count = len([s for s in self.indexer.all_skills if s.status != "deprecated"])
            self.max_skills = compute_dynamic_budget(active_count)

        if taste_profile is not None:
            self.taste_profile = taste_profile
        else:
            self.taste_profile = load_taste_profile(workspace_root=workspace_root)

        self.enable_efficacy_bias = enable_efficacy_bias
        if efficacy_tracker is not None:
            self.efficacy_tracker = efficacy_tracker
        else:
            try:
                self.efficacy_tracker = EfficacyTracker(workspace_root=self.workspace_root)
            except Exception:
                self.efficacy_tracker = None

        self.bm25_index = BM25Index()
        self.bm25_index.build(self.indexer.all_skills, catalog_hash=self.get_catalog_hash())

        self._compiled_cache: Dict[str, _CompiledSkillTokens] = {}
        # Pre-compile tokens for all indexed skills so query #1 has zero cold-compilation latency
        for skill in self.indexer.all_skills:
            self._get_compiled(skill)

    def _get_compiled(self, skill: SkillMetadata) -> _CompiledSkillTokens:
        cached = self._compiled_cache.get(skill.name)
        if cached is None or cached.mtime != skill.mtime:
            cached = _compile_skill_tokens(skill)
            self._compiled_cache[skill.name] = cached
        return cached

    def _compute_efficacy_bias(self, skill_name: str) -> float:
        """Compute empirical outcome efficacy bias [-1.5, +1.5] if tracker is active (ISS-15/16)."""
        if not (self.enable_efficacy_bias and self.efficacy_tracker):
            return 0.0
        if hasattr(self.efficacy_tracker, "compute_efficacy_bias"):
            return self.efficacy_tracker.compute_efficacy_bias(skill_name, max_bias=1.5)
        eff_stat = self.efficacy_tracker.get_skill_stats(skill_name)
        if eff_stat and (eff_stat.total_evaluations + eff_stat.tests_passed + eff_stat.tests_failed) >= 2:
            raw_bias = (eff_stat.win_rate - 50.0) / 100.0
            return round(max(-1.5, min(1.5, raw_bias)), 2)
        return 0.0

    def get_catalog_hash(self) -> str:
        """Return the deterministic 16-hex digest of the active indexed catalog."""
        if hasattr(self.indexer, "compute_catalog_hash"):
            return self.indexer.compute_catalog_hash()
        skills_summary = []
        for s in sorted(self.indexer.all_skills, key=lambda x: x.name):
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
            })
        if not skills_summary:
            return "empty_catalog000"
        raw = json.dumps(skills_summary, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def compute_config_hash(
        self,
        phase: Optional[str] = None,
        direct_prefer: Optional[Set[str]] = None,
        enable_triad: Optional[bool] = None,
        allow_sentry_override: Optional[bool] = None,
    ) -> str:
        """Return a deterministic 16-hex digest of active resolver configuration."""
        taste_h = self.taste_profile.compute_hash() if self.taste_profile else "empty_taste_0000"
        cfg_dict = {
            "taste_hash": taste_h,
            "max_skills": self.max_skills,
            "enable_triad": self.enable_triad if enable_triad is None else bool(enable_triad),
            "exclusive_categories": sorted(list(self.exclusive_categories)),
            "score_dropoff_ratio": round(self.score_dropoff_ratio, 4),
            "allow_sentry_override": (
                self.allow_sentry_override if allow_sentry_override is None else bool(allow_sentry_override)
            ),
            "enable_efficacy_bias": self.enable_efficacy_bias,
            "protected_sentries": sorted(list(get_protected_sentries())),
            "phase": phase or "",
            "direct_prefer": sorted(list(direct_prefer or [])),
        }
        raw = json.dumps(cfg_dict, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def resolve(
        self,
        prompt: str,
        force_route: bool = False,
        phase: Optional[str] = None,
        prefer: Optional[Union[str, List[str], Set[str]]] = None,
        record_attribution: bool = False,
        min_confidence_threshold: float = 3.0,
        allow_low_confidence: bool = False,
        enable_triad: Optional[bool] = None,
        allow_sentry_override: Optional[bool] = None,
    ) -> ResolutionResult:
        """Resolve a prompt to the optimal subset of specialized skills, optionally constrained by project phase and taste preferences."""
        start_time = time.perf_counter()
        effective_enable_triad = self.enable_triad if enable_triad is None else bool(enable_triad)
        effective_allow_sentry_override = (
            self.allow_sentry_override if allow_sentry_override is None else bool(allow_sentry_override)
        )

        # Normalize prefer overrides
        direct_prefer: Set[str] = set()
        if prefer:
            if isinstance(prefer, str):
                direct_prefer.add(prefer.strip())
            elif isinstance(prefer, (list, tuple, set)):
                direct_prefer.update(str(p).strip() for p in prefer if str(p).strip())

        # Step 1: Gate evaluation
        gate_res = self.gate.evaluate(prompt)

        # If gate says don't route and not forced, return empty list immediately
        if not gate_res.should_route and not force_route:
            total_elapsed = (time.perf_counter() - start_time) * 1000
            catalog_hash = self.get_catalog_hash()
            config_hash = self.compute_config_hash(
                phase=phase,
                direct_prefer=direct_prefer,
                enable_triad=effective_enable_triad,
                allow_sentry_override=effective_allow_sentry_override,
            )
            return ResolutionResult(
                gate=gate_res,
                selected_skills=[],
                category_scores={},
                total_latency_ms=total_elapsed,
                taste_profile_source=None,
                skill_scores={},
                confidence="none",
                confidence_score=0.0,
                margin=0.0,
                abstained=True,
                abstention_reason=f"gate_bypassed ({gate_res.reason})",
                catalog_hash=catalog_hash,
                config_hash=config_hash,
            )

        # Step 2: Code-aware tokenization preserving technical identifiers and frameworks
        lower_prompt = prompt.lower()
        prompt_words, prompt_stems = tokenize_code_aware(prompt)

        # Domain Negative Selection: if prompt has pure backend/systems signals and zero UI/frontend signals,
        # lock out UI/frontend categories unless the user explicitly names a UI skill.
        has_ui_signal = bool(prompt_words.intersection(UI_FRONTEND_SIGNALS))
        has_backend_signal = bool(prompt_words.intersection(BACKEND_ONLY_SIGNALS))
        suppress_ui_categories = has_backend_signal and not has_ui_signal
        has_agy_meta_signal = bool(prompt_words.intersection(AGY_META_SIGNALS))

        scores: Dict[str, float] = {}
        skill_score_details: Dict[str, SkillScore] = {}
        category_scores: Dict[str, float] = defaultdict(float)
        taste_applied = False
        active_taste_source: Optional[str] = None

        # Determine phase allowed categories (ISS-14: supporting canonical aliases like 'design', 'planning', 'qa')
        phase_categories: Optional[Set[str]] = None
        if phase:
            phase_categories = get_categories_for_phase(phase)

        all_skills = self.indexer.all_skills
        catalog_hash = self.get_catalog_hash()

        # Ensure BM25 inverted index is synchronized with catalog
        self.bm25_index.build(all_skills, catalog_hash=catalog_hash)
        bm25_scores, bm25_hits = self.bm25_index.score_query(
            prompt_words, prompt_stems, lower_prompt
        )

        taste_is_empty = (self.taste_profile is None) or self.taste_profile.is_empty()
        taste_named_skills: Set[str] = set(direct_prefer)
        if self.taste_profile and not taste_is_empty:
            taste_named_skills.update(self.taste_profile.weights.keys())
            taste_named_skills.update(self.taste_profile.avoid_skills)
            taste_named_skills.update(self.taste_profile.preferred_skills.values())

        efficacy_skills_dict = (
            getattr(self.efficacy_tracker, "_skills", None)
            if (self.enable_efficacy_bias and self.efficacy_tracker)
            else None
        )
        efficacy_named_skills: Set[str] = set(efficacy_skills_dict.keys()) if efficacy_skills_dict else set()

        candidate_names = set(bm25_hits.keys()) | taste_named_skills
        candidate_skills = [
            s for name in candidate_names
            if (s := self.indexer.get_skill(name)) is not None
        ]

        for skill in candidate_skills:
            if skill.status == "deprecated":
                continue

            if phase_categories and skill.category not in phase_categories:
                continue

            compiled = self._get_compiled(skill)
            direct_name_match = compiled.name_lower in prompt_words or compiled.name_spaced in lower_prompt

            is_ui_skill = compiled.is_ui_skill

            if suppress_ui_categories and not direct_name_match:
                if is_ui_skill:
                    continue

            if compiled.is_meta and not has_agy_meta_signal and not direct_name_match:
                continue

            score = bm25_scores.get(skill.name, 0.0)
            relevance_hits = bm25_hits.get(skill.name, 0)
            if score > 0.0:
                category_scores[skill.category] += round(score * 0.5, 2)

            # Phase affinity bonus
            if phase and phase_categories and skill.category in phase_categories:
                score += 2.0

            has_taste_entry = skill.name in taste_named_skills
            has_eff_entry = skill.name in efficacy_named_skills

            # Direct CLI preference or domain-aligned positive taste preference
            if direct_prefer and skill.name in direct_prefer and not (suppress_ui_categories and is_ui_skill):
                if score < 2.0:
                    score += 2.0
                relevance_hits += 1
            elif relevance_hits == 0 and has_taste_entry and self.taste_profile:
                is_backend_skill = skill.category.startswith(("backend.", "db.", "api."))
                domain_aligned = (
                    (is_ui_skill and has_ui_signal and not suppress_ui_categories)
                    or (is_backend_skill and has_backend_signal)
                )
                if domain_aligned and self.taste_profile.get_bias(skill, direct_prefer=direct_prefer) > 0.0:
                    score += 2.0
                    relevance_hits += 1

            if relevance_hits > 0:
                base_score = score + (skill.priority / 100.0)

                if not has_taste_entry and not has_eff_entry:
                    final_score = max(0.0, round(base_score, 2))
                    if final_score > 0.0:
                        scores[skill.name] = final_score
                    skill_score_details[skill.name] = SkillScore(
                        skill_name=skill.name,
                        base_score=final_score,
                        taste_bias=0.0,
                        efficacy_bias=0.0,
                        final_score=final_score,
                    )
                    continue

                taste_bias = 0.0

                if not (suppress_ui_categories and is_ui_skill):
                    if self.taste_profile and not taste_is_empty:
                        taste_bias = self.taste_profile.get_bias(
                            skill,
                            direct_prefer=direct_prefer,
                            allow_sentry_override=effective_allow_sentry_override,
                        )
                    elif direct_prefer and skill.name in direct_prefer:
                        taste_bias = 3.0

                # Domain Gate Invariant: if domain score is 0, taste bias must be 0.0
                if suppress_ui_categories and is_ui_skill:
                    taste_bias = 0.0

                # Quality Sentry Immunity:
                # Security/QA/Review sentries cannot be downvoted or suppressed by taste unless overridden.
                is_sentry = is_protected_sentry(skill, allow_override=effective_allow_sentry_override) or (
                    not effective_allow_sentry_override and skill.category in ("decision.review", "verification.qa")
                )
                if is_sentry:
                    if taste_bias < 0.0:
                        taste_bias = 0.0

                # Empirical Efficacy Bias (Zero Token)
                efficacy_bias = self._compute_efficacy_bias(skill.name) if has_eff_entry else 0.0

                if suppress_ui_categories and is_ui_skill:
                    efficacy_bias = 0.0

                if is_sentry:
                    if efficacy_bias < 0.0:
                        efficacy_bias = 0.0

                is_avoided = bool(
                    not taste_is_empty
                    and self.taste_profile
                    and skill.name in self.taste_profile.avoid_skills
                    and skill.name not in direct_prefer
                    and not is_sentry
                )

                raw_final = base_score + taste_bias + efficacy_bias
                final_score = 0.0 if is_avoided else max(0.0, round(raw_final, 2))

                # Hard exclusion of avoided or non-positive score skills from candidate selection
                if final_score > 0.0 and not is_avoided:
                    scores[skill.name] = final_score

                skill_score_details[skill.name] = SkillScore(
                    skill_name=skill.name,
                    base_score=round(base_score, 2),
                    taste_bias=round(taste_bias, 2),
                    efficacy_bias=round(efficacy_bias, 2),
                    final_score=round(final_score, 2),
                )

                if taste_bias != 0.0:
                    taste_applied = True
                    if skill.name in direct_prefer:
                        active_taste_source = "cli"
                    elif not active_taste_source:
                        active_taste_source = self.taste_profile.source if self.taste_profile else "user"

        if not scores:
            total_elapsed = (time.perf_counter() - start_time) * 1000
            catalog_hash = self.get_catalog_hash()
            config_hash = self.compute_config_hash(
                phase=phase,
                direct_prefer=direct_prefer,
                enable_triad=effective_enable_triad,
                allow_sentry_override=effective_allow_sentry_override,
            )
            return ResolutionResult(
                gate=gate_res,
                selected_skills=[],
                category_scores=category_scores,
                total_latency_ms=total_elapsed,
                taste_profile_source=active_taste_source,
                skill_scores=skill_score_details,
                confidence="none",
                confidence_score=0.0,
                margin=0.0,
                abstained=True,
                abstention_reason="no_matching_skills",
                catalog_hash=catalog_hash,
                config_hash=config_hash,
            )

        # Calibrated Confidence & Score Margin Evaluation
        sorted_scores_desc = sorted(scores.values(), reverse=True)
        top_score = sorted_scores_desc[0]
        runner_up_score = sorted_scores_desc[1] if len(sorted_scores_desc) > 1 else 0.0
        margin = round(top_score - runner_up_score, 2)

        # Scale minimum confidence threshold for tiny catalogs (N < 8) where max theoretical IDF is smaller
        catalog_n = max(1, len(all_skills))
        effective_threshold = min(min_confidence_threshold, max(1.5, 1.0 + math.log(catalog_n)))
        high_threshold = max(3.0, min(4.5, 2.0 + math.log(catalog_n)))

        has_direct_prefer = bool(direct_prefer and any(p in scores for p in direct_prefer))
        if has_direct_prefer or top_score >= 8.0:
            confidence = "high"
            confidence_score = 1.0 if has_direct_prefer else round(min(1.0, 0.85 + (top_score / 50.0)), 2)
        elif top_score >= high_threshold and margin >= 0.35:
            confidence = "high"
            confidence_score = round(min(0.95, 0.75 + (margin / 10.0)), 2)
        elif top_score >= effective_threshold:
            confidence = "medium"
            confidence_score = round(0.50 + min(0.24, margin / 4.0), 2)
        else:
            confidence = "low"
            confidence_score = round(max(0.05, top_score / 10.0), 2)

        abstained = False
        abstention_reason = None

        # Abstain if confidence is low and not explicitly allowed/forced
        if confidence == "low" and not allow_low_confidence and not force_route:
            abstained = True
            abstention_reason = f"low_confidence (top_score {top_score:.2f} < {effective_threshold:.1f})"
            scores = {}

        # Candidate pruning: score dropoff margin (ISS-05)
        if scores:
            prune_floor = max(effective_threshold * 0.75, top_score * self.score_dropoff_ratio)
            scores = {n: s for n, s in scores.items() if s >= prune_floor or n in direct_prefer}

        # Deterministic sort: explicit CLI --prefer override first, then score descending, then skill name ascending
        sorted_skill_names = sorted(
            scores.keys(),
            key=lambda n: (0 if n in direct_prefer else 1, -scores[n], n),
        )

        # Enforce conflict exclusion (conflicts_with), category locking (ISS-07), and DAG requirements (ISS-06)
        selected_skills: List[SkillMetadata] = []
        selected_names_set: Set[str] = set()
        conflicted_out: Set[str] = set()
        locked_categories: Set[str] = set()

        # Determine effective budget (honor explicit max_skills, default to dynamic 5% formula)
        active_catalog_size = len([s for s in all_skills if s.status != "deprecated"])
        dynamic_budget = compute_dynamic_budget(active_catalog_size)
        effective_max = self.max_skills if self.max_skills is not None else dynamic_budget
        # Tier 1: single-specialist fast path cap (ISS-13)
        if gate_res.tier == 1:
            effective_max = min(effective_max, 1)

        for name in sorted_skill_names:
            if len(selected_skills) >= effective_max:
                break
            if name in conflicted_out or name in selected_names_set:
                continue

            candidate = self.indexer.get_skill(name)
            if candidate is None or candidate.status == "deprecated":
                continue

            # Category locking check (ISS-07)
            if candidate.category in locked_categories:
                conflicted_out.add(name)
                continue
            if candidate.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in locked_categories for cat in VISUAL_AUTHORITY_CATEGORIES):
                conflicted_out.add(name)
                continue

            # Direct conflicts check
            if any(name in sel.conflicts_with or sel.name in candidate.conflicts_with for sel in selected_skills):
                conflicted_out.add(name)
                continue

            # Resolve transitive prerequisites via SkillDAG (ISS-06)
            try:
                prereqs = self.skill_dag.resolve_transitive_prerequisites(candidate)
            except CyclicDependencyError:
                conflicted_out.add(name)
                continue

            new_prereqs = [p for p in prereqs if p.name not in selected_names_set]

            # Verify budget constraint: candidate + all unselected prerequisites must fit
            if len(selected_skills) + len(new_prereqs) + 1 > effective_max:
                continue

            # Verify no prerequisites have conflicts or violate category locks
            has_prereq_conflict = False
            temp_selected = list(selected_skills)
            temp_locked = set(locked_categories)
            for p in new_prereqs:
                p_immune = is_protected_sentry(p, allow_override=effective_allow_sentry_override)
                if (
                    self.taste_profile
                    and p.name in self.taste_profile.avoid_skills
                    and p.name not in direct_prefer
                    and not p_immune
                ):
                    has_prereq_conflict = True
                    break
                if p.name in conflicted_out:
                    has_prereq_conflict = True
                    break
                if any(p.name in sel.conflicts_with or sel.name in p.conflicts_with for sel in temp_selected):
                    has_prereq_conflict = True
                    break
                if p.name in candidate.conflicts_with or candidate.name in p.conflicts_with:
                    has_prereq_conflict = True
                    break
                if p.category in temp_locked:
                    has_prereq_conflict = True
                    break
                if p.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in temp_locked for cat in VISUAL_AUTHORITY_CATEGORIES):
                    has_prereq_conflict = True
                    break
                temp_selected.append(p)
                if p.category in self.exclusive_categories or p.category in VISUAL_AUTHORITY_CATEGORIES:
                    temp_locked.add(p.category)

            if not has_prereq_conflict:
                if candidate.category in temp_locked:
                    has_prereq_conflict = True
                elif candidate.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in temp_locked for cat in VISUAL_AUTHORITY_CATEGORIES):
                    has_prereq_conflict = True

            if has_prereq_conflict:
                conflicted_out.add(name)
                continue

            # Add prerequisites first (topological prerequisite-before-dependent order)
            for p in new_prereqs:
                selected_skills.append(p)
                selected_names_set.add(p.name)
                for c in p.conflicts_with:
                    conflicted_out.add(c)
                if p.category in self.exclusive_categories or p.category in VISUAL_AUTHORITY_CATEGORIES:
                    locked_categories.add(p.category)
                if p.name not in skill_score_details:
                    p_taste = (
                        self.taste_profile.get_bias(
                            p,
                            direct_prefer=direct_prefer,
                            allow_sentry_override=effective_allow_sentry_override,
                        )
                        if self.taste_profile else 0.0
                    )
                    p_eff = self._compute_efficacy_bias(p.name)
                    p_base = 2.0
                    p_final = round(max(0.1, p_base + p_taste + p_eff), 2)
                    skill_score_details[p.name] = SkillScore(
                        skill_name=p.name,
                        base_score=p_base,
                        taste_bias=p_taste,
                        efficacy_bias=p_eff,
                        final_score=p_final,
                    )
                    scores[p.name] = p_final

            # Add candidate
            selected_skills.append(candidate)
            selected_names_set.add(name)
            for c in candidate.conflicts_with:
                conflicted_out.add(c)
            if candidate.category in self.exclusive_categories or candidate.category in VISUAL_AUTHORITY_CATEGORIES:
                locked_categories.add(candidate.category)

        # Guardrail 2: Complementary Pod Pairing (The Triad / Pod Architecture)
        # If a domain deliverable is selected but the pod size is below target_pod_size (min 2-3 skills, scaled up to 5 on 100+ catalogs, clamped by effective_max),
        # and triad pairing is enabled and the task tier is Tier 2+ (deliverable/feature/module/project),
        # recruit qualified non-conflicting complementary partners (Domain Lead + Implementation Engineering + Verification/QA).
        target_pod_size = min(effective_max, max(3, dynamic_budget))
        should_run_triad = (
            effective_enable_triad
            and (gate_res.tier >= 2 or (force_route and gate_res.tier != 1))
            and len(selected_skills) >= 1
            and len(selected_skills) < target_pod_size
        )

        if should_run_triad:
            lead_cat = selected_skills[0].category
            partner_roles = COMPLEMENTARY_DOMAIN_ROLES.get(lead_cat)
            if not partner_roles:
                if lead_cat.startswith(("ui.", "frontend.")):
                    partner_roles = ("frontend.engineering", "verification.qa", "orchestration.lead")
                elif lead_cat.startswith(("backend.", "db.", "api.", "security.", "ops.")):
                    partner_roles = ("orchestration.lead", "verification.qa", "decision.review")
                else:
                    partner_roles = ("orchestration.lead", "verification.qa")

            for role_cat in partner_roles:
                if len(selected_skills) >= target_pod_size or len(selected_skills) >= effective_max:
                    break
                if role_cat in locked_categories:
                    continue
                if role_cat in VISUAL_AUTHORITY_CATEGORIES and any(cat in locked_categories for cat in VISUAL_AUTHORITY_CATEGORIES):
                    continue

                candidates = [s for s in all_skills if s.category == role_cat and s.status != "deprecated"]
                valid_candidates = []
                for cand in candidates:
                    if cand.name in selected_names_set or cand.name in conflicted_out:
                        continue
                    if any(cand.name in sel.conflicts_with or sel.name in cand.conflicts_with for sel in selected_skills):
                        conflicted_out.add(cand.name)
                        continue
                    # Never recruit avoided skills unless explicitly preferred
                    cand_immune = is_protected_sentry(cand, allow_override=effective_allow_sentry_override)
                    if (
                        self.taste_profile
                        and cand.name in self.taste_profile.avoid_skills
                        and cand.name not in direct_prefer
                        and not cand_immune
                    ):
                        continue
                    # Guardrail 3: Strict Domain Negative Selection
                    is_ui_cand = (
                        cand.category.startswith(UI_CATEGORY_PREFIXES)
                        or any(t.lower() in ("ui", "frontend", "css", "tailwind", "ux") for t in cand.tags)
                    )
                    if suppress_ui_categories and is_ui_cand:
                        continue
                    if phase_categories and cand.category not in phase_categories:
                        continue
                    if is_meta_skill(cand) and not has_agy_meta_signal and not (cand.name.lower() in prompt_words):
                        continue
                    valid_candidates.append(cand)

                if valid_candidates:
                    valid_candidates.sort(
                        key=lambda c: (
                            -scores.get(c.name, 0.0),
                            -(
                                self.taste_profile.get_bias(
                                    c,
                                    direct_prefer=direct_prefer,
                                    allow_sentry_override=effective_allow_sentry_override,
                                )
                                if self.taste_profile else 0.0
                            ),
                            -(self.efficacy_tracker.get_skill_stats(c.name).win_rate if (self.efficacy_tracker and self.efficacy_tracker.get_skill_stats(c.name)) else 0.0),
                            -c.priority,
                            c.name,
                        )
                    )
                    for partner in valid_candidates:
                        # Resolve transitive prerequisites of partner
                        try:
                            partner_prereqs = self.skill_dag.resolve_transitive_prerequisites(partner)
                        except CyclicDependencyError:
                            conflicted_out.add(partner.name)
                            continue

                        new_partner_prereqs = [p for p in partner_prereqs if p.name not in selected_names_set]
                        if len(selected_skills) + len(new_partner_prereqs) + 1 > effective_max:
                            continue

                        has_p_conflict = False
                        temp_p_selected = list(selected_skills)
                        temp_p_locked = set(locked_categories)
                        for p in new_partner_prereqs:
                            p_immune = is_protected_sentry(p, allow_override=effective_allow_sentry_override)
                            if (
                                self.taste_profile
                                and p.name in self.taste_profile.avoid_skills
                                and p.name not in direct_prefer
                                and not p_immune
                            ):
                                has_p_conflict = True
                                break
                            if p.name in conflicted_out:
                                has_p_conflict = True
                                break
                            if any(p.name in sel.conflicts_with or sel.name in p.conflicts_with for sel in temp_p_selected):
                                has_p_conflict = True
                                break
                            if p.name in partner.conflicts_with or partner.name in p.conflicts_with:
                                has_p_conflict = True
                                break
                            if p.category in temp_p_locked:
                                has_p_conflict = True
                                break
                            if p.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in temp_p_locked for cat in VISUAL_AUTHORITY_CATEGORIES):
                                has_p_conflict = True
                                break
                            temp_p_selected.append(p)
                            if p.category in self.exclusive_categories or p.category in VISUAL_AUTHORITY_CATEGORIES:
                                temp_p_locked.add(p.category)

                        if not has_p_conflict:
                            if partner.category in temp_p_locked:
                                has_p_conflict = True
                            elif partner.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in temp_p_locked for cat in VISUAL_AUTHORITY_CATEGORIES):
                                has_p_conflict = True

                        if has_p_conflict:
                            conflicted_out.add(partner.name)
                            continue

                        # Add partner prerequisites first
                        for p in new_partner_prereqs:
                            selected_skills.append(p)
                            selected_names_set.add(p.name)
                            for c in p.conflicts_with:
                                conflicted_out.add(c)
                            if p.category in self.exclusive_categories or p.category in VISUAL_AUTHORITY_CATEGORIES:
                                locked_categories.add(p.category)
                            if p.name not in skill_score_details:
                                r_taste = (
                                    self.taste_profile.get_bias(
                                        p,
                                        direct_prefer=direct_prefer,
                                        allow_sentry_override=effective_allow_sentry_override,
                                    )
                                    if self.taste_profile else 0.0
                                )
                                r_eff = self._compute_efficacy_bias(p.name)
                                r_base = 2.0
                                r_final = round(max(0.1, r_base + r_taste + r_eff), 2)
                                skill_score_details[p.name] = SkillScore(
                                    skill_name=p.name,
                                    base_score=r_base,
                                    taste_bias=r_taste,
                                    efficacy_bias=r_eff,
                                    final_score=r_final,
                                )
                                scores[p.name] = r_final

                        # Add partner
                        selected_skills.append(partner)
                        selected_names_set.add(partner.name)
                        for c in partner.conflicts_with:
                            conflicted_out.add(c)
                        if partner.category in self.exclusive_categories or partner.category in VISUAL_AUTHORITY_CATEGORIES:
                            locked_categories.add(partner.category)
                        if partner.name not in skill_score_details:
                            p_taste_bias = (
                                self.taste_profile.get_bias(
                                    partner,
                                    direct_prefer=direct_prefer,
                                    allow_sentry_override=effective_allow_sentry_override,
                                )
                                if self.taste_profile else 0.0
                            )
                            p_eff_bias = self._compute_efficacy_bias(partner.name)
                            p_base = 2.0
                            p_final = round(max(0.1, p_base + p_taste_bias + p_eff_bias), 2)
                            skill_score_details[partner.name] = SkillScore(
                                skill_name=partner.name,
                                base_score=p_base,
                                taste_bias=p_taste_bias,
                                efficacy_bias=p_eff_bias,
                                final_score=p_final,
                            )
                            scores[partner.name] = p_final
                        break

        # On large catalogs (100+ skills), if budget permits (effective_max up to 5), fill remaining slots with valid scored candidates
        if len(selected_skills) < effective_max and effective_enable_triad:
            for name in sorted_skill_names:
                if len(selected_skills) >= effective_max:
                    break
                if name in conflicted_out or name in selected_names_set:
                    continue
                cand = self.indexer.get_skill(name)
                if cand is None or cand.status == "deprecated":
                    continue
                cand_immune = is_protected_sentry(cand, allow_override=effective_allow_sentry_override)
                if (
                    self.taste_profile
                    and cand.name in self.taste_profile.avoid_skills
                    and cand.name not in direct_prefer
                    and not cand_immune
                ):
                    continue
                if cand.category in locked_categories:
                    conflicted_out.add(name)
                    continue
                if cand.category in VISUAL_AUTHORITY_CATEGORIES and any(cat in locked_categories for cat in VISUAL_AUTHORITY_CATEGORIES):
                    conflicted_out.add(name)
                    continue
                if any(name in sel.conflicts_with or sel.name in cand.conflicts_with for sel in selected_skills):
                    conflicted_out.add(name)
                    continue
                is_ui_cand = (
                    cand.category.startswith(UI_CATEGORY_PREFIXES)
                    or any(t.lower() in ("ui", "frontend", "css", "tailwind", "ux") for t in cand.tags)
                )
                if suppress_ui_categories and is_ui_cand:
                    continue
                if is_meta_skill(cand) and not has_agy_meta_signal and not (cand.name.lower() in prompt_words):
                    continue
                selected_skills.append(cand)
                selected_names_set.add(name)
                for c in cand.conflicts_with:
                    conflicted_out.add(c)
                if cand.category in self.exclusive_categories or cand.category in VISUAL_AUTHORITY_CATEGORIES:
                    locked_categories.add(cand.category)

        # Final topological sort pass: guarantees prerequisites ALWAYS precede dependents in output
        selected_skills = self.skill_dag.topological_sort(selected_skills)
        selected_names = [s.name for s in selected_skills]
        total_elapsed = (time.perf_counter() - start_time) * 1000

        attribution_id: Optional[str] = None
        if record_attribution and selected_skills and self.efficacy_tracker:
            try:
                # Per-skill attribution roles (ISS-17): lead specialist 1.0, guardrail 0.25, partner 0.5
                skill_weights: Dict[str, float] = {}
                for idx, s in enumerate(selected_skills):
                    if idx == 0:
                        skill_weights[s.name] = 1.0
                    elif s.category == "verification.qa" or s.name in ("engineering-quality-gate", "development-director"):
                        skill_weights[s.name] = 0.25
                    else:
                        skill_weights[s.name] = 0.5

                skill_hashes = {s.name: getattr(s, "content_hash", "") for s in selected_skills}
                skill_versions = {s.name: getattr(s, "version", "1.0.0") for s in selected_skills}

                low_p = prompt.lower()
                if "tdd" in low_p or "failing test" in low_p or "red phase" in low_p:
                    sess_mode = "tdd"
                elif all(getattr(s, "category", "") in ("security.blockchain", "decision.review", "mentorship.learning", "architecture.system") for s in selected_skills):
                    sess_mode = "advisory"
                elif any(kw in low_p for kw in ("audit", "review", "explain", "inspect", "assess", "check")):
                    sess_mode = "advisory"
                else:
                    sess_mode = "standard"

                eff_sess = self.efficacy_tracker.start_session(
                    skills=selected_names,
                    prompt=prompt,
                    workspace_root=self.workspace_root,
                    skill_weights=skill_weights,
                    session_mode=sess_mode,
                    skill_hashes=skill_hashes,
                    skill_versions=skill_versions,
                )
                attribution_id = eff_sess.session_id
            except Exception:
                pass

        from taxonomy.telemetry import telemetry
        telemetry.record_resolution(
            selected_names,
            total_elapsed,
            taste_applied=taste_applied,
            profile_source=active_taste_source,
        )

        catalog_hash = self.get_catalog_hash()
        config_hash = self.compute_config_hash(
            phase=phase,
            direct_prefer=direct_prefer,
            enable_triad=effective_enable_triad,
            allow_sentry_override=effective_allow_sentry_override,
        )

        return ResolutionResult(
            gate=gate_res,
            selected_skills=selected_skills,
            category_scores=category_scores,
            total_latency_ms=total_elapsed,
            taste_profile_source=active_taste_source,
            skill_scores=skill_score_details,
            attribution_id=attribution_id,
            confidence=confidence,
            confidence_score=confidence_score,
            margin=margin,
            abstained=abstained,
            abstention_reason=abstention_reason,
            catalog_hash=catalog_hash,
            config_hash=config_hash,
        )

    def redispatch_on_observation(
        self,
        current_result: Optional[ResolutionResult] = None,
        files_touched: Optional[List[str]] = None,
        test_passed: Optional[bool] = None,
        error_output: Optional[str] = None,
        observation: Optional[str] = None,
        phase: Optional[str] = None,
        lifecycle_state: Optional[Any] = None,
    ) -> ResolutionResult:
        """Dynamic mid-session re-dispatch responding to observations, touched files, or test failures (ISS-14)."""
        from taxonomy.lifecycle import redispatch_on_observation
        return redispatch_on_observation(
            resolver=self,
            current_result=current_result,
            files_touched=files_touched,
            test_passed=test_passed,
            error_output=error_output,
            observation=observation,
            phase=phase,
            lifecycle_state=lifecycle_state,
        )
