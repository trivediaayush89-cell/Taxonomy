"""Deterministic Compound Gate for rapid (<1ms) prompt triage (ISS-11, ISS-12, ISS-13)."""

import re
import time
from typing import Optional, Set

from taxonomy.models import GateResult

# Maximum prompt length evaluated to guarantee sub-millisecond execution and ReDoS immunity
MAX_PROMPT_CHARS = 2048

# Conversational / trivial prompts to bypass immediately (Tier 0)
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

# Metaphoric or casual phrases that contain engineering words but should NOT trigger heavy routing (Tier 0)
CASUAL_METAPHOR_PATTERNS = [
    re.compile(r"\b(?:build|scaffold|implement) (?:a|an) (?:\w+ )*(?:habit|analogy|metaphor|relationship|bridge|sandwich|poem|song|story|joke|pun|prank|meme)\b", re.I),
    re.compile(r"\b(?:what is|favorite) feature\b", re.I),
]

# Explanation / learning patterns (Tier 0 - educational, bypass multi-tool routing)
EXPLANATION_PATTERNS = [
    re.compile(r"^(?:can you )?explain (?:how|what|why)\b", re.I),
    re.compile(r"^what is the difference between\b", re.I),
    re.compile(r"^what does this (?:regex|code|snippet|function) do\b", re.I),
]

# Micro-fix patterns (Tier 1 - single-line typo, rename, console.log, quick-fix)
MICRO_FIX_PATTERNS = [
    re.compile(r"^fix (?:the )?typo\b", re.I),
    re.compile(r"^rename (?:the )?variable\b", re.I),
    re.compile(r"^add a console\.log\b", re.I),
    re.compile(r"^change the background color in [^\n]+ to #[0-9a-fA-F]+\b", re.I),
    re.compile(r"^quick(?: |-)?fix\b", re.I),
    re.compile(r"^one(?: |-)?line(?: |-)?fix\b", re.I),
    re.compile(r"^update (?:the )?import\b", re.I),
    re.compile(r"^bump (?:the )?version\b", re.I),
]

# Recognized 2-letter technical tokens (ISS-12)
TECH_2LETTER_TOKENS = frozenset({
    "ui", "ux", "db", "ci", "cd", "qa", "go", "ai", "js", "ts", "ip", "os", "io", "pr", "k8s"
})

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
    # CLI, Systems, Parsers, Compilers & Pipelines (ISS-12)
    re.compile(r"\b(?:cli|parser|lexer|compiler|interpreter|sdk|daemon|middleware|pipeline|worker|queue|subprocess|threading|multiprocessing)\b", re.I),
    # Languages, Runtimes & Cloud (ISS-12)
    re.compile(r"\b(?:python|rust|golang|typescript|javascript|nodejs|node\.js|fastapi|flask|django|express|actix|tokio|spring|docker|kubernetes|k8s|terraform|ansible)\b", re.I),
    # VCS & CI/CD (ISS-12)
    re.compile(r"\b(?:git|pull-request|commit|branch|rebase|ci/cd|github actions|workflow)\b", re.I),
]

# Structural engineering action verbs (ISS-12)
ACTION_VERBS = frozenset({
    "scaffold", "refactor", "architect", "audit", "optimize", "profile", "schedule", "automate",
    "build", "implement", "create", "develop", "design", "migrate", "debug", "fix", "deploy",
    "test", "secure", "benchmark", "configure", "integrate", "setup", "wire", "patch",
    "parse", "containerize", "instrument", "provision", "triage",
})


class CompoundGate:
    """Sub-millisecond prompt complexity gating engine with optional intent cluster fallback."""

    def __init__(self, enable_semantic_fallback: bool = True, route_tier_1: bool = False):
        self.enable_semantic_fallback = enable_semantic_fallback
        self.route_tier_1 = route_tier_1
        if enable_semantic_fallback:
            from taxonomy.semantic_gate import IntentClusterFallbackGate
            self._semantic_fallback = IntentClusterFallbackGate()
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

        # 3. Suppress casual metaphors containing engineering words ("build a habit", "implement a joke") (Tier 0)
        for pat in CASUAL_METAPHOR_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=0, reason="casual_metaphor_suppressed", latency_ms=elapsed)

        # 4. Conceptual explanations (Tier 0)
        for pat in EXPLANATION_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                return GateResult(should_route=False, tier=0, reason="educational_explanation", latency_ms=elapsed)

        # 5. Micro-fixes / targeted single-specialist query (Tier 1, ISS-13)
        for pat in MICRO_FIX_PATTERNS:
            if pat.search(capped):
                elapsed = (time.perf_counter() - start_time) * 1000
                if self.route_tier_1:
                    return GateResult(
                        should_route=True,
                        tier=1,
                        reason="micro_fix_targeted (tier 1)",
                        latency_ms=elapsed
                    )
                else:
                    return GateResult(
                        should_route=False,
                        tier=1,
                        reason="micro_fix_bypass (tier 1)",
                        latency_ms=elapsed
                    )

        # 6. Domain Engineering Pattern match (Tier 2 or 3)
        matched_domain = False
        for pat in DOMAIN_PATTERNS:
            if pat.search(capped):
                matched_domain = True
                break

        # Check action verbs and technical context tokens (ISS-12: preserving 2-letter tokens like 'ui', 'db', 'qa', 'go')
        raw_tokens = re.findall(r"\b[a-z0-9_.-]{2,30}\b", lower)
        words = {t for t in raw_tokens if len(t) >= 3 or t in TECH_2LETTER_TOKENS}
        has_heavy_action = bool(words.intersection(ACTION_VERBS))

        has_tech_context = (
            matched_domain
            or bool(words.intersection(TECH_2LETTER_TOKENS))
            or any(w in lower for w in (
                "parser", "cli", "sdk", "middleware", "daemon", "worker",
                "script", "endpoint", "pipeline", "function", "module", "class",
            ))
        )

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

        if matched_domain or (has_heavy_action and has_tech_context):
            tier = 3 if is_tier_3 else 2
            elapsed = (time.perf_counter() - start_time) * 1000
            return GateResult(
                should_route=True,
                tier=tier,
                reason=f"domain_match (tier {tier})",
                latency_ms=elapsed
            )

        if has_heavy_action:
            # Action verb present without explicit domain match
            elapsed = (time.perf_counter() - start_time) * 1000
            return GateResult(
                should_route=True,
                tier=2,
                reason="action_verb_match (tier 2)",
                latency_ms=elapsed
            )

        # Default fallback: check optional intent cluster fallback before bypassing (Tier 0)
        elapsed = (time.perf_counter() - start_time) * 1000
        fallback_res = GateResult(
            should_route=False,
            tier=0,
            reason="default_unmatched",
            latency_ms=elapsed
        )

        if self._semantic_fallback:
            promoted = self._semantic_fallback.evaluate_fallback(capped, fallback_res)
            promoted.latency_ms = (time.perf_counter() - start_time) * 1000
            return promoted

        return fallback_res
