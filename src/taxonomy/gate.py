"""Deterministic Compound Gate for rapid (<1ms) prompt triage."""

import re
import time
from typing import Set

from taxonomy.models import GateResult

# Maximum prompt length evaluated to guarantee sub-millisecond execution and ReDoS immunity
MAX_PROMPT_CHARS = 2048

# Conversational / trivial prompts to bypass immediately
CASUAL_EXACT_MATCHES = frozenset({
    "hi", "hello", "hey", "good morning", "good evening", "good afternoon",
    "thanks", "thank you", "thx", "ok", "okay", "yes", "no", "proceed",
    "nevermind", "got it", "cool", "bye", "see ya"
})

CASUAL_PREFIXES = (
    "hey ", "hello ", "hi ", "thanks", "thank you", "what time is it",
    "what is the capital", "can you recommend a good book", "nevermind",
    "yes, please", "yes please", "sure, go ahead"
)

# Metaphoric or casual phrases that contain engineering words but should NOT trigger heavy routing
CASUAL_METAPHOR_PATTERNS = [
    re.compile(r"\b(?:build|scaffold|implement) (?:a|an) (?:\w+ )*(?:habit|analogy|metaphor|relationship|bridge|sandwich|poem|song|story|joke|pun|prank|meme)\b", re.I),
    re.compile(r"\b(?:what is|favorite) feature\b", re.I),
]

# Explanation / learning patterns (Tier 0/1 - educational, bypass heavy multi-tool dispatch)
EXPLANATION_PATTERNS = [
    re.compile(r"^(?:can you )?explain (?:how|what|why)\b", re.I),
    re.compile(r"^what is the difference between\b", re.I),
    re.compile(r"^what does this (?:regex|code|snippet|function) do\b", re.I),
]

# Micro-fix patterns (Tier 1 - single-line typo, rename, console.log)
MICRO_FIX_PATTERNS = [
    re.compile(r"^fix the typo\b", re.I),
    re.compile(r"^rename the variable\b", re.I),
    re.compile(r"^add a console\.log\b", re.I),
    re.compile(r"^change the background color in [^\n]+ to #[0-9a-fA-F]+\b", re.I),
]

# Explicit Engineering & Domain Triggers (Tier 2/3)
DOMAIN_PATTERNS = [
    # Auth & API & Backend
    re.compile(r"\b(?:jwt|authentication|auth|refresh token|oauth|login page|password hashing|endpoint|backend|rest api|graphql|grpc)\b", re.I),
    # Database & Storage
    re.compile(r"\b(?:postgresql|postgres|mysql|sqlite|prisma|supabase|sql queries|database query|database schema|redis)\b", re.I),
    # Smart Contract & Security
    re.compile(r"\b(?:smart contract|smart-contract|erc-20|solidity|reentrancy|defi|audit|flash loan|evm|foundry)\b", re.I),
    # QA, Testing, Quality Gate
    re.compile(r"\b(?:pytest|integration tests?|e2e tests?|quality gate|lint and typecheck|ci pipeline|test suite|verification)\b", re.I),
    # Performance & Concurrency & React/Next.js Optimization
    re.compile(r"\b(?:memory leak|p99|latency|load testing|profiling|thread pool|concurrency|websocket cluster)\b", re.I),
    re.compile(r"\b(?:react|nextjs|next\.js|ssr|rsc|suspense|waterfall|bundle size|rerender|hydration)\b", re.I),
    # UI / Design Engineering / Marketing / Product / Cleanup / Animation
    re.compile(r"\b(?:navbar|hamburger menu|tailwind|wcag|accessible|accessibility|dark-mode|design system|design tokens|micro-interactions)\b", re.I),
    re.compile(r"\b(?:whiteboard canvas|fluid animations|visual styling|widget|interactive html|generative ui|card-widget)\b", re.I),
    re.compile(r"\b(?:landing page|landing-page|marketing|portfolio|showcase|one-pager|hero section|scrollytelling)\b", re.I),
    re.compile(r"\b(?:dashboard|saas|admin settings|web-app|web app|onboarding|product-ui|documentation|blog)\b", re.I),
    re.compile(r"\b(?:unslop|vibecoded|vibe-coded|ai-slop|generic-ui|restyle|redesign|isolated-component|single-component|prototype)\b", re.I),
    re.compile(r"\b(?:animations?|animate|motion|transitions?|easing|spring|cubic-bezier|framer-motion)\b", re.I),
    # Architecture & Orchestration & GitHub OSS
    re.compile(r"\b(?:microservice|microservices|scaffold|refactor|monolith|monolithic|architecture|architectural|full-stack)\b", re.I),
    re.compile(r"\b(?:courtroom|jury|adversarial|verdict|cross-examination)\b", re.I),
    re.compile(r"\b(?:github|pull request|pull-request|triage|issue)\b", re.I),
    # Platform, Automation, Plugins & Customization
    re.compile(r"\b(?:cron|scheduled task|recurring task|automation|automate|cron job)\b", re.I),
    re.compile(r"\b(?:install plugin|marketplace plugin|mcp server|customization|skill-creator|find-skills)\b", re.I),
]

# Structural action verbs indicating significant engineering when paired with domain context
ACTION_VERBS = frozenset({
    "scaffold", "refactor", "architect", "audit", "optimize", "profile", "schedule", "automate"
})


class CompoundGate:
    """Sub-millisecond prompt complexity gating engine with optional semantic intent fallback."""

    def __init__(self, enable_semantic_fallback: bool = True):
        self.enable_semantic_fallback = enable_semantic_fallback
        if enable_semantic_fallback:
            from taxonomy.semantic_gate import SemanticFallbackGate
            self._semantic_fallback = SemanticFallbackGate()
        else:
            self._semantic_fallback = None

    def evaluate(self, prompt: str) -> GateResult:
        result = self._evaluate_internal(prompt)
        from taxonomy.telemetry import telemetry
        telemetry.record_gate(result.tier, result.should_route, result.latency_ms, result.reason)
        return result

    def _evaluate_internal(self, prompt: str) -> GateResult:
        start_time = time.perf_counter()
        clean = prompt.strip()
        
        # Hard prompt cap to guarantee predictable performance
        capped = clean[:MAX_PROMPT_CHARS] if len(clean) > MAX_PROMPT_CHARS else clean
        lower = capped.lower()

        # 1. Exact casual match check (Tier 0)
        if lower in CASUAL_EXACT_MATCHES:
            elapsed = (time.perf_counter() - start_time) * 1000
            return GateResult(should_route=False, tier=0, reason="casual_exact_match", latency_ms=elapsed)

        # 2. Casual prefix check (Tier 0)
        for prefix in CASUAL_PREFIXES:
            if lower.startswith(prefix):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=0, reason="casual_prefix", latency_ms=elapsed)

        # 3. Suppress casual metaphors containing engineering words ("build a habit", "implement a joke")
        for pat in CASUAL_METAPHOR_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=1, reason="casual_metaphor_suppressed", latency_ms=elapsed)

        # 4. Conceptual explanations (Tier 0/1)
        for pat in EXPLANATION_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=0, reason="educational_explanation", latency_ms=elapsed)

        # 5. Micro-fixes (<30 LOC / 1-line typo / local rename) (Tier 1)
        for pat in MICRO_FIX_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=1, reason="micro_fix_bypass", latency_ms=elapsed)

        # 6. Domain Engineering Pattern match (Tier 2 or 3)
        matched_domain = False
        for pat in DOMAIN_PATTERNS:
            if pat.search(capped):
                matched_domain = True
                break

        # Check action verbs
        words = set(re.findall(r"\b[a-z]{3,20}\b", lower))
        has_heavy_action = bool(words.intersection(ACTION_VERBS))

        # Check for multi-phase / full-stack markers (Tier 3)
        is_tier_3 = (
            "full-stack" in lower or
            "microservice" in lower or
            "monolith" in lower or
            "courtroom" in lower or
            "adversarial" in lower or
            "design system" in lower or
            "load testing" in lower or
            (has_heavy_action and matched_domain and len(words) > 15)
        )

        if matched_domain or has_heavy_action:
            tier = 3 if is_tier_3 else 2
            elapsed = (time.perf_counter() - start_time) * 1000
            return GateResult(
                should_route=True,
                tier=tier,
                reason=f"domain_match (tier {tier})",
                latency_ms=elapsed
            )

        # Default fallback: check optional semantic intent fallback before bypassing
        elapsed = (time.perf_counter() - start_time) * 1000
        fallback_res = GateResult(
            should_route=False,
            tier=1,
            reason="default_unmatched",
            latency_ms=elapsed
        )

        if self._semantic_fallback:
            promoted = self._semantic_fallback.evaluate_fallback(capped, fallback_res)
            promoted.latency_ms = (time.perf_counter() - start_time) * 1000
            return promoted

        return fallback_res
