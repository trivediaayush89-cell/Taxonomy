"""Optional lightweight semantic intent fallback for ambiguous prompts."""

from typing import Dict, FrozenSet, Optional, Tuple

from taxonomy.models import GateResult
from taxonomy.resolver import STOP_WORDS, WORD_REGEX, normalize_stem

# Pre-compiled category semantic intent profiles
CATEGORY_INTENT_PROFILES: Dict[str, FrozenSet[str]] = {
    "security.blockchain": frozenset({
        "siphon", "drain", "liquidity", "slippage", "exploit", "rugpull",
        "arbitrage", "collateral", "insolvent", "unbacked", "flashloan",
        "reentrancy", "frontrun", "mev", "mempool", "sybil", "oracle",
    }),
    "ui.frontend": frozenset({
        "clunky", "jarring", "transition", "stutter", "misaligned", "viewport",
        "flicker", "overflow", "padding", "margin", "unresponsive", "squished",
        "overlap", "wrap", "truncat", "scrollable", "sticky",
    }),
    "ops.performance": frozenset({
        "bottleneck", "choke", "stall", "sluggish", "slowdown", "spike",
        "saturation", "exhaustion", "thrashing", "deadlock", "starvation",
        "timeout", "hung", "unresponsive", "overload",
    }),
    "decision.review": frozenset({
        "dispute", "disagree", "weigh", "tradeoff", "verdict", "consensus",
        "adjudicate", "debate", "objection", "deliberat", "scrutiny",
    }),
    "verification.qa": frozenset({
        "regress", "flake", "flaky", "untested", "broken", "failing",
        "assert", "mock", "stub", "fixture", "coverage", "unverified",
    }),
}


class SemanticFallbackGate:
    """Catches subtle or ambiguously phrased engineering requests without external LLM overhead."""

    def __init__(self, min_intent_hits: int = 1):
        self.min_intent_hits = min_intent_hits

    def evaluate_fallback(self, prompt: str, base_result: GateResult) -> GateResult:
        """Promote an unmatched prompt to routed if it exhibits strong domain intent tokens."""
        # If gate already routed, zero work needed
        if base_result.should_route:
            return base_result

        tokens = WORD_REGEX.findall(prompt.lower())
        prompt_stems = {normalize_stem(w) for w in tokens if len(w) >= 3 and w not in STOP_WORDS}

        best_category: Optional[str] = None
        max_hits = 0

        for category, intent_stems in CATEGORY_INTENT_PROFILES.items():
            hits = len(prompt_stems.intersection(intent_stems))
            if hits > max_hits:
                max_hits = hits
                best_category = category

        if max_hits >= self.min_intent_hits and best_category:
            return GateResult(
                should_route=True,
                tier=2,
                reason=f"semantic_fallback ({best_category}, hits: {max_hits})",
                latency_ms=base_result.latency_ms,
            )

        return base_result
