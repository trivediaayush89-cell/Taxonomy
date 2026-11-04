"""Ranked skill resolver with pre-compiled token sets, word-boundary tag scoring, and conflict locking."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
import time
from collections import defaultdict
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Union

from taxonomy.gate import CompoundGate
from taxonomy.indexer import SkillIndexer
from taxonomy.models import GateResult, ResolutionResult, SkillMetadata, SkillScore
from taxonomy.taste import TasteProfile, load_taste_profile

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

UI_CATEGORY_PREFIXES = ("ui.", "frontend.", "quality.animation")

AGY_META_CATEGORIES = frozenset({
    "agy.customization", "agy.guide", "agy.plugin", "agy.skills", "agy.migration",
    "antigravity.config", "antigravity.docs", "ecosystem.plugin", "tooling.migration",
})

AGY_META_SIGNALS = frozenset({
    "antigravity", "agy", "plugin", "plugins", "mcp", "skill", "skills",
    "slash", "keybinding", "keybindings", "sidecar", "sidecars",
    "customization", "customizations", "marketplace", "workflow", "workflows",
    "npx-skills", "skill-creator", "find-skills",
})

TOKEN_REGEX = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
WORD_REGEX = re.compile(r"[a-z0-9]+")


def normalize_stem(word: str) -> str:
    """Fast deterministic suffix stripper for matching plurals, gerunds, and agent nouns."""
    w = word.lower().strip(".,;:?!'\"()[]{}#*`~")
    if len(w) <= 3:
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


@dataclass(frozen=True)
class _CompiledSkillTokens:
    mtime: float
    single_tags: Tuple[Tuple[str, str], ...]  # (tag_lower, tag_stem)
    compound_tags: Tuple[Tuple[str, str, Tuple[str, ...]], ...]  # (tag_lower, tag_spaced, part_stems)
    desc_stems: FrozenSet[str]
    name_lower: str
    name_spaced: str
    name_parts: FrozenSet[str]


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

    return _CompiledSkillTokens(
        mtime=skill.mtime,
        single_tags=tuple(single_tags),
        compound_tags=tuple(compound_tags),
        desc_stems=desc_stems,
        name_lower=name_lower,
        name_spaced=name_spaced,
        name_parts=name_parts,
    )


PHASE_CATEGORY_MAP = {
    "architecture": {
        "orchestration.lead", "decision.review", "mentorship.learning",
        "general", "agy.customization", "agy.guide",
    },
    "implementation": {
        "ui.frontend", "ui.design", "ui.marketing", "ui.product", "ui.cleanup",
        "ui.component", "ui.animation", "ui.polish", "ui.reference",
        "frontend.engineering", "frontend.react", "backend.api",
        "security.blockchain", "ops.performance", "orchestration.lead",
        "agy.automation", "agy.ui", "agy.plugin", "agy.github", "agy.skills",
    },
    "verification": {
        "verification.qa", "quality.animation", "ops.performance",
        "security.blockchain", "decision.review",
    },
    "review": {
        "decision.review", "orchestration.lead", "verification.qa",
        "quality.animation", "mentorship.learning",
    },
}


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
    ):
        self.indexer = indexer
        self.gate = CompoundGate()
        if max_skills is not None:
            self.max_skills = max_skills
        else:
            active_count = len([s for s in self.indexer.all_skills if s.status != "deprecated"])
            self.max_skills = compute_dynamic_budget(active_count)

        if taste_profile is not None:
            self.taste_profile = taste_profile
        else:
            self.taste_profile = load_taste_profile(workspace_root=workspace_root)

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

    def resolve(
        self,
        prompt: str,
        force_route: bool = False,
        phase: Optional[str] = None,
        prefer: Optional[Union[str, List[str], Set[str]]] = None,
    ) -> ResolutionResult:
        """Resolve a prompt to the optimal subset of specialized skills, optionally constrained by project phase and taste preferences."""
        start_time = time.perf_counter()

        # Step 1: Gate evaluation
        gate_res = self.gate.evaluate(prompt)

        # If gate says don't route and not forced, return empty list immediately
        if not gate_res.should_route and not force_route:
            total_elapsed = (time.perf_counter() - start_time) * 1000
            return ResolutionResult(
                gate=gate_res,
                selected_skills=[],
                category_scores={},
                total_latency_ms=total_elapsed,
                taste_profile_source=None,
                skill_scores={},
            )

        # Normalize prefer overrides
        direct_prefer: Set[str] = set()
        if prefer:
            if isinstance(prefer, str):
                direct_prefer.add(prefer.strip())
            elif isinstance(prefer, (list, tuple, set)):
                direct_prefer.update(str(p).strip() for p in prefer if str(p).strip())

        # Step 2: Tokenize prompt once on word boundaries
        lower_prompt = prompt.lower()
        raw_tokens = TOKEN_REGEX.findall(lower_prompt)
        prompt_words: Set[str] = set()
        for tok in raw_tokens:
            if tok not in STOP_WORDS:
                prompt_words.add(tok)
            if "-" in tok:
                for sub in tok.split("-"):
                    if sub and sub not in STOP_WORDS:
                        prompt_words.add(sub)

        prompt_stems = {normalize_stem(w) for w in prompt_words}

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

        # Determine phase allowed categories
        phase_categories: Optional[Set[str]] = None
        if phase:
            phase_clean = phase.lower().strip()
            phase_categories = PHASE_CATEGORY_MAP.get(phase_clean)

        all_skills = self.indexer.all_skills

        for skill in all_skills:
            if skill.status == "deprecated":
                continue

            if phase_categories and skill.category not in phase_categories:
                continue

            compiled = self._get_compiled(skill)
            direct_name_match = compiled.name_lower in prompt_words or compiled.name_spaced in lower_prompt

            is_ui_skill = (
                skill.category.startswith(UI_CATEGORY_PREFIXES)
                or any(t.lower() in ("ui", "frontend", "css", "tailwind", "ux") for t in skill.tags)
            )

            if suppress_ui_categories and not direct_name_match:
                if is_ui_skill:
                    continue

            if skill.category in AGY_META_CATEGORIES and not has_agy_meta_signal and not direct_name_match:
                continue

            score = 0.0
            relevance_hits = 0

            # 1. Single-word Tag match (word-boundary safe, O(1) set lookup)
            for tag_lower, tag_stem in compiled.single_tags:
                if tag_lower in prompt_words or tag_stem in prompt_stems:
                    score += 6.0
                    relevance_hits += 1
                    category_scores[skill.category] += 3.0

            # 2. Compound Tag match
            for tag_lower, tag_spaced, part_stems in compiled.compound_tags:
                if tag_lower in prompt_words or tag_spaced in lower_prompt or (
                    part_stems and all(ps in prompt_stems for ps in part_stems)
                ):
                    score += 6.0
                    relevance_hits += 1
                    category_scores[skill.category] += 3.0

            # 3. Description stem intersection (capped so verbose descriptions don't drown out curated tags)
            matched_stems = prompt_stems.intersection(compiled.desc_stems)
            if matched_stems:
                hit_cnt = len(matched_stems)
                score += min(hit_cnt * 1.0, 3.0)
                relevance_hits += hit_cnt

            # 4. Direct skill name match or distinctive sub-token match
            if direct_name_match:
                score += 8.0
                relevance_hits += 2
            elif compiled.name_parts:
                matched_parts = prompt_words.intersection(compiled.name_parts)
                if matched_parts:
                    score += len(matched_parts) * 3.0
                    relevance_hits += 1

            # Phase affinity bonus
            if phase and phase_categories and skill.category in phase_categories:
                score += 2.0

            # Direct CLI preference or domain-aligned positive taste preference
            if skill.name in direct_prefer and not (suppress_ui_categories and is_ui_skill):
                if score < 2.0:
                    score += 2.0
                relevance_hits += 1
            elif relevance_hits == 0 and self.taste_profile and not self.taste_profile.is_empty():
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
                taste_bias = 0.0

                if not (suppress_ui_categories and is_ui_skill):
                    if self.taste_profile:
                        taste_bias = self.taste_profile.get_bias(skill, direct_prefer=direct_prefer)
                    elif skill.name in direct_prefer:
                        taste_bias = 3.0

                # Domain Gate Invariant: if domain score is 0, taste bias must be 0.0
                if suppress_ui_categories and is_ui_skill:
                    taste_bias = 0.0

                # Quality Sentry Immunity:
                if skill.name == "engineering-quality-gate" or skill.category in ("decision.review", "verification.qa"):
                    if taste_bias < 0.0:
                        taste_bias = 0.0

                final_score = base_score + taste_bias
                scores[skill.name] = final_score
                skill_score_details[skill.name] = SkillScore(
                    skill_name=skill.name,
                    base_score=round(base_score, 2),
                    taste_bias=round(taste_bias, 2),
                    final_score=round(final_score, 2),
                )

                if taste_bias != 0.0:
                    taste_applied = True
                    if skill.name in direct_prefer:
                        active_taste_source = "cli"
                    elif not active_taste_source:
                        active_taste_source = self.taste_profile.source if self.taste_profile else "user"

        # If at least one skill matched a curated tag or name (score >= 6.0),
        # prune weak incidental description-only matches (score < 4.0) so we don't pollute context.
        if scores:
            top_score = max(scores.values())
            if top_score >= 6.0:
                scores = {n: s for n, s in scores.items() if s >= 4.0}

        # Deterministic sort: explicit CLI --prefer override first, then score descending, then skill name ascending
        sorted_skill_names = sorted(
            scores.keys(),
            key=lambda n: (0 if n in direct_prefer else 1, -scores[n], n),
        )

        # Enforce conflict exclusion (conflicts_with) and dependencies (requires)
        selected_skills: List[SkillMetadata] = []
        selected_names_set: Set[str] = set()
        conflicted_out: Set[str] = set()

        # Determine effective budget (honor explicit max_skills, default to dynamic 5% formula)
        active_catalog_size = len([s for s in all_skills if s.status != "deprecated"])
        dynamic_budget = compute_dynamic_budget(active_catalog_size)
        effective_max = self.max_skills if self.max_skills is not None else dynamic_budget

        for name in sorted_skill_names:
            if len(selected_skills) >= effective_max:
                break
            if name in conflicted_out or name in selected_names_set:
                continue

            candidate = self.indexer.get_skill(name)
            if candidate is None or candidate.status == "deprecated":
                continue

            if any(name in sel.conflicts_with or sel.name in candidate.conflicts_with for sel in selected_skills):
                conflicted_out.add(name)
                continue

            selected_skills.append(candidate)
            selected_names_set.add(name)
            for c in candidate.conflicts_with:
                conflicted_out.add(c)

            for req in candidate.requires:
                if len(selected_skills) >= effective_max:
                    break
                if req in selected_names_set or req in conflicted_out:
                    continue
                req_skill = self.indexer.get_skill(req)
                if req_skill is None or req_skill.status == "deprecated":
                    continue
                if any(req in sel.conflicts_with or sel.name in req_skill.conflicts_with for sel in selected_skills):
                    continue
                selected_skills.append(req_skill)
                selected_names_set.add(req)
                for c in req_skill.conflicts_with:
                    conflicted_out.add(c)

        # Guardrail 2: Complementary Pod Pairing (The Triad / Pod Architecture)
        # If a domain deliverable is selected but the pod size is below target_pod_size (min 2-3 skills, scaled up to 5 on 100+ catalogs, clamped by effective_max),
        # recruit qualified non-conflicting complementary partners (Domain Lead + Implementation Engineering + Verification/QA).
        target_pod_size = min(effective_max, max(3, dynamic_budget))

        if len(selected_skills) >= 1 and len(selected_skills) < target_pod_size:
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
                candidates = [s for s in all_skills if s.category == role_cat and s.status != "deprecated"]
                valid_candidates = []
                for cand in candidates:
                    if cand.name in selected_names_set or cand.name in conflicted_out:
                        continue
                    if any(cand.name in sel.conflicts_with or sel.name in cand.conflicts_with for sel in selected_skills):
                        conflicted_out.add(cand.name)
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
                    if cand.category in AGY_META_CATEGORIES and not has_agy_meta_signal and not (cand.name.lower() in prompt_words):
                        continue
                    valid_candidates.append(cand)

                if valid_candidates:
                    valid_candidates.sort(
                        key=lambda c: (
                            -scores.get(c.name, 0.0),
                            -(self.taste_profile.get_bias(c, direct_prefer=direct_prefer) if self.taste_profile else 0.0),
                            -c.priority,
                            c.name,
                        )
                    )
                    partner = valid_candidates[0]
                    selected_skills.append(partner)
                    selected_names_set.add(partner.name)
                    for c in partner.conflicts_with:
                        conflicted_out.add(c)
                    for req in partner.requires:
                        if len(selected_skills) >= effective_max:
                            break
                        if req in selected_names_set or req in conflicted_out:
                            continue
                        req_skill = self.indexer.get_skill(req)
                        if req_skill and req_skill.status != "deprecated":
                            if not any(req in sel.conflicts_with or sel.name in req_skill.conflicts_with for sel in selected_skills):
                                selected_skills.append(req_skill)
                                selected_names_set.add(req)
                                for c in req_skill.conflicts_with:
                                    conflicted_out.add(c)

        # On large catalogs (100+ skills), if budget permits (effective_max up to 5), fill remaining slots with valid scored candidates
        if len(selected_skills) < effective_max:
            for name in sorted_skill_names:
                if len(selected_skills) >= effective_max:
                    break
                if name in conflicted_out or name in selected_names_set:
                    continue
                cand = self.indexer.get_skill(name)
                if cand is None or cand.status == "deprecated":
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
                selected_skills.append(cand)
                selected_names_set.add(name)
                for c in cand.conflicts_with:
                    conflicted_out.add(c)

        selected_names = [s.name for s in selected_skills]
        total_elapsed = (time.perf_counter() - start_time) * 1000

        from taxonomy.telemetry import telemetry
        telemetry.record_resolution(
            selected_names,
            total_elapsed,
            taste_applied=taste_applied,
            profile_source=active_taste_source,
        )

        return ResolutionResult(
            gate=gate_res,
            selected_skills=selected_skills,
            category_scores=category_scores,
            total_latency_ms=total_elapsed,
            taste_profile_source=active_taste_source,
            skill_scores=skill_score_details,
        )
