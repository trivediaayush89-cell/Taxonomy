"""Compound Lexical & Intent-Cluster Gate (ISS-11).

Provides zero-token, deterministic domain intent clustering for ambiguous engineering prompts,
with an optional pluggable SemanticProvider interface for external embedding/similarity models.
"""

from typing import Dict, FrozenSet, List, Optional, Protocol, Set, runtime_checkable

from taxonomy.models import GateResult
from taxonomy.resolver import STOP_WORDS, WORD_REGEX, normalize_stem

# Recognized 2-letter technical tokens preserved during intent clustering
FALLBACK_2LETTER_TOKENS: FrozenSet[str] = frozenset({
    "ui", "ux", "db", "ci", "cd", "qa", "go", "ai", "js", "ts", "ip", "os", "io", "pr",
})

# Raw category intent profiles (lexical domain clustering)
CATEGORY_INTENT_PROFILES: Dict[str, FrozenSet[str]] = {
    "security.blockchain": frozenset({
        "siphon", "drain", "liquidity", "slippage", "exploit", "rugpull",
        "arbitrage", "collateral", "insolvent", "unbacked", "flashloan",
        "reentrancy", "frontrun", "mev", "mempool", "sybil", "oracle",
        "bytecode", "assembly", "selfdestruct", "delegatecall", "overflow",
    }),
    "ui.frontend": frozenset({
        "clunky", "jarring", "transition", "stutter", "misaligned", "viewport",
        "flicker", "overflow", "padding", "margin", "unresponsive", "squished",
        "overlap", "wrap", "truncat", "scrollable", "sticky", "typography",
        "contrast", "kerning", "palette", "elevation", "backdrop",
    }),
    "frontend.engineering": frozenset({
        "hydration", "hydrate", "rerender", "memoize", "repaint", "reflow",
        "suspense", "waterfall", "virtualize", "bundle", "treeshake",
        "debounce", "throttle", "dom", "vdom", "props", "propsdrilling",
    }),
    "backend.api": frozenset({
        "endpoint", "controller", "payload", "serializ", "deserializ", "middleware",
        "cors", "webhook", "grpc", "protobuf", "rest", "graphql", "rpc",
        "ratelimit", "idempotency", "circuitbreaker", "backpressure", "ingress",
    }),
    "db.primary": frozenset({
        "migration", "deadlock", "slowquery", "sharding", "replica", "replication",
        "transaction", "isolation", "indexes", "vacuum", "wal", "connectionpool",
        "pooling", "lockup", "cascade", "foreignkey", "unindexed",
    }),
    "ops.performance": frozenset({
        "bottleneck", "choke", "stall", "sluggish", "slowdown", "spike",
        "saturation", "exhaustion", "thrashing", "deadlock", "starvation",
        "timeout", "hung", "unresponsive", "overload", "profiling", "flamegraph",
    }),
    "devops.ci": frozenset({
        "containerize", "dockerfile", "pipeline", "artifact", "runner", "workflow",
        "manifest", "helm", "k8s", "kubernetes", "rollout", "canary", "ingress",
    }),
    "decision.review": frozenset({
        "dispute", "disagree", "weigh", "tradeoff", "verdict", "consensus",
        "adjudicate", "debate", "objection", "deliberat", "scrutiny", "critique",
        "unbiased", "dissent", "assessment",
    }),
    "verification.qa": frozenset({
        "regress", "flake", "flaky", "untested", "broken", "failing",
        "assert", "mock", "stub", "fixture", "coverage", "unverified",
        "snapshot", "fuzz", "fuzzer", "mutation", "smoke",
    }),
}

# Pre-normalized intent profiles containing both raw terms and their normalized stems
# so inflected/stemmed forms (e.g. "migration" -> "migr", "padding" -> "padd") always match.
STEMMED_CATEGORY_INTENT_PROFILES: Dict[str, FrozenSet[str]] = {
    cat: frozenset(
        set(terms) | {normalize_stem(t) for t in terms if len(t) >= 3}
    )
    for cat, terms in CATEGORY_INTENT_PROFILES.items()
}


@runtime_checkable
class SemanticProvider(Protocol):
    """Pluggable interface for optional external neural embeddings or semantic models."""

    def compute_similarity(self, prompt: str, target_categories: List[str]) -> Dict[str, float]:
        """Return similarity scores in [0.0, 1.0] for each target category."""
        ...


class IntentClusterFallbackGate:
    """Zero-token lexical intent clustering engine for ambiguous engineering prompts.
    
    Catches subtle technical intent through domain-specific lexical clusters without
    external LLM token consumption, while supporting an optional SemanticProvider.
    """

    def __init__(
        self,
        min_intent_hits: int = 1,
        semantic_provider: Optional[SemanticProvider] = None,
        provider_similarity_threshold: float = 0.65,
    ):
        self.min_intent_hits = min_intent_hits
        self.semantic_provider = semantic_provider
        self.provider_similarity_threshold = provider_similarity_threshold

    def evaluate_fallback(self, prompt: str, base_result: GateResult) -> GateResult:
        """Promote an unmatched prompt to routed if it exhibits strong domain intent tokens or semantic similarity."""
        # If gate already routed, zero work needed
        if base_result.should_route:
            return base_result

        # 1. Optional pluggable neural/embedding semantic provider evaluation
        if self.semantic_provider is not None:
            try:
                categories = list(CATEGORY_INTENT_PROFILES.keys())
                sim_scores = self.semantic_provider.compute_similarity(prompt, categories)
                if sim_scores:
                    best_cat, best_score = max(sim_scores.items(), key=lambda item: item[1])
                    if best_score >= self.provider_similarity_threshold:
                        return GateResult(
                            should_route=True,
                            tier=2,
                            reason=f"semantic_provider_fallback ({best_cat}, score: {best_score:.2f}) [semantic_fallback: {best_cat}]",
                            latency_ms=base_result.latency_ms,
                        )
            except Exception:
                # Pluggable provider fails open to deterministic lexical clustering
                pass

        # 2. Fast zero-token lexical intent-cluster matching (matching both raw tokens and normalized stems)
        tokens = WORD_REGEX.findall(prompt.lower())
        prompt_features: Set[str] = set()
        for w in tokens:
            if w in STOP_WORDS:
                continue
            if len(w) >= 3:
                prompt_features.add(w)
                prompt_features.add(normalize_stem(w))
            elif w in FALLBACK_2LETTER_TOKENS:
                prompt_features.add(w)

        best_category: Optional[str] = None
        max_hits = 0

        for category, intent_terms in STEMMED_CATEGORY_INTENT_PROFILES.items():
            hits = len(prompt_features.intersection(intent_terms))
            if hits > max_hits:
                max_hits = hits
                best_category = category

        if max_hits >= self.min_intent_hits and best_category:
            return GateResult(
                should_route=True,
                tier=2,
                reason=f"intent_cluster_fallback (semantic_fallback: {best_category}, hits: {max_hits})",
                latency_ms=base_result.latency_ms,
            )

        return base_result


# Backward compatibility alias (ISS-11: accurately reframed from "semantic" to intent-cluster)
SemanticFallbackGate = IntentClusterFallbackGate
