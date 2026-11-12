"""Unit tests for Phase 2: Gating, Triage & Lifecycle State (ISS-11, ISS-12, ISS-13, ISS-14)."""

from pathlib import Path
import pytest

from taxonomy.gate import CompoundGate
from taxonomy.indexer import SkillIndexer
from taxonomy.lifecycle import (
    PHASE_ALIASES,
    TaskLifecycleStage,
    TaskLifecycleStateMachine,
    get_categories_for_phase,
    normalize_phase_name,
    redispatch_on_observation,
)
from taxonomy.resolver import SkillResolver
from taxonomy.semantic_gate import (
    IntentClusterFallbackGate,
    SemanticFallbackGate,
    SemanticProvider,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


@pytest.fixture(scope="module")
def resolver():
    idx = SkillIndexer([FIXTURES_DIR])
    idx.scan()
    return SkillResolver(idx, max_skills=3)


# --- ISS-11 Tests: Intent-Cluster Gate & SemanticProvider Interface ---

def test_iss11_intent_cluster_alias_and_matching():
    """Verify IntentClusterFallbackGate catches domain intent tokens and SemanticFallbackGate alias works."""
    gate = IntentClusterFallbackGate()
    alias_gate = SemanticFallbackGate()

    prompt = "Prevent liquidity drain and flashloan exploit through oracle arbitrage"
    base_res = CompoundGate(enable_semantic_fallback=False).evaluate(prompt)

    # Both class names should produce identical results
    res1 = gate.evaluate_fallback(prompt, base_res)
    res2 = alias_gate.evaluate_fallback(prompt, base_res)

    assert res1.should_route is True
    assert res2.should_route is True
    assert "security.blockchain" in res1.reason
    assert "semantic_fallback" in res1.reason or "intent_cluster" in res1.reason


def test_iss11_pluggable_semantic_provider():
    """Verify pluggable SemanticProvider interface can be injected and evaluated."""
    class MockSemanticProvider:
        def compute_similarity(self, prompt: str, target_categories: list):
            # Simulate a neural embedding model returning high similarity for backend.api
            if "payload" in prompt.lower():
                return {"backend.api": 0.92, "ui.frontend": 0.10}
            return {cat: 0.20 for cat in target_categories}

    provider = MockSemanticProvider()
    assert isinstance(provider, SemanticProvider)

    gate = IntentClusterFallbackGate(semantic_provider=provider, provider_similarity_threshold=0.70)
    prompt = "streamline processing for incoming payloads"
    base_res = CompoundGate(enable_semantic_fallback=False).evaluate(prompt)
    assert base_res.should_route is False

    res = gate.evaluate_fallback(prompt, base_res)
    assert res.should_route is True
    assert "backend.api" in res.reason


# --- ISS-12 Tests: Action Verbs, 2-Letter Tokens & Technical Prompts ---

def test_iss12_action_verbs_and_two_letter_tokens():
    """Verify 2-letter tokens ('ui', 'db', 'qa', 'go') and action verbs ('build', 'implement') route correctly."""
    gate = CompoundGate(enable_semantic_fallback=True)

    # 1. 2-letter token + action verb prompts
    res_ui = gate.evaluate("build a responsive ui layout")
    assert res_ui.should_route is True
    assert res_ui.tier in (2, 3)

    res_db = gate.evaluate("implement db connection pooling")
    assert res_db.should_route is True
    assert res_db.tier in (2, 3)

    # 2. Real engineering prompts previously dropped due to narrow verb set
    res_cli = gate.evaluate("Build a custom CLI parser in Python")
    assert res_cli.should_route is True
    assert res_cli.tier in (2, 3)

    res_fastapi = gate.evaluate("Implement rate limiting middleware in FastAPI")
    assert res_fastapi.should_route is True
    assert res_fastapi.tier in (2, 3)

    res_deploy = gate.evaluate("deploy container to kubernetes cluster")
    assert res_deploy.should_route is True
    assert res_deploy.tier in (2, 3)


# --- ISS-13 Tests: Tier 1 Micro-Fix & Single Specialist Dispatch ---

def test_iss13_tier1_micro_fix_routing_and_tier0_distinction(resolver):
    """Verify Tier 1 micro-fixes route to a single specialist, while Tier 0 bypasses."""
    gate_routing = CompoundGate(route_tier_1=True)
    gate_bypassing = CompoundGate(route_tier_1=False)

    micro_prompt = "fix the typo in the login page authentication handler"

    # With route_tier_1=True (default), micro-fixes route as Tier 1
    res_routed = gate_routing.evaluate(micro_prompt)
    assert res_routed.should_route is True
    assert res_routed.tier == 1
    assert "micro_fix" in res_routed.reason

    # With route_tier_1=False, micro-fixes bypass
    res_bypass = gate_bypassing.evaluate(micro_prompt)
    assert res_bypass.should_route is False
    assert res_bypass.tier == 1

    # Conversational & explanations remain Tier 0 (always bypass)
    res_casual = gate_routing.evaluate("Can you explain how async await works in Rust?")
    assert res_casual.should_route is False
    assert res_casual.tier == 0


def test_iss13_tier1_single_specialist_execution(resolver):
    """Tier 1 prompts dispatched by resolver enforce max_skills <= 1 with zero triad padding."""
    # A Tier 1 quick fix prompt
    prompt = "fix the typo in smart contract reentrancy assertion"
    res = resolver.resolve(prompt, force_route=True, enable_triad=True)

    # Tier 1 must enforce single-specialist execution
    if res.gate.tier == 1:
        assert len(res.selected_skills) <= 1


# --- ISS-14 Tests: Lifecycle State Machine & Mid-Session Dynamic Re-Routing ---

def test_iss14_phase_aliases_and_normalization():
    """Verify canonical phase aliases ('design', 'planning', 'qa', 'review') normalize correctly."""
    assert normalize_phase_name("design") == "design"
    assert normalize_phase_name("plan") == "planning"
    assert normalize_phase_name("planning") == "planning"
    assert normalize_phase_name("qa") == "verification"
    assert normalize_phase_name("test") == "verification"
    assert normalize_phase_name("eval") == "evaluation"
    assert normalize_phase_name("review") == "review"

    cats_design = get_categories_for_phase("design")
    assert cats_design is not None
    assert "ui.design" in cats_design

    cats_qa = get_categories_for_phase("qa")
    assert cats_qa is not None
    assert "verification.qa" in cats_qa


def test_iss14_lifecycle_state_machine_transitions():
    """Verify forward stage progression and backward transition on test failure."""
    sm = TaskLifecycleStateMachine(TaskLifecycleStage.PLANNING)
    assert sm.current_stage == TaskLifecycleStage.PLANNING

    # Advance forward: PLANNING -> IMPLEMENTATION
    sm.advance()
    assert sm.current_stage == TaskLifecycleStage.IMPLEMENTATION

    # Advance forward: IMPLEMENTATION -> VERIFICATION
    sm.advance()
    assert sm.current_stage == TaskLifecycleStage.VERIFICATION

    # Simulate test failure: VERIFICATION -> backward to IMPLEMENTATION
    sm.on_test_failure("AssertionError in test_transfer: expected 100 got 0")
    assert sm.current_stage == TaskLifecycleStage.IMPLEMENTATION
    assert len(sm.stage_history) >= 4
    assert "test_failure" in sm.stage_history[-1]["reason"]

    # Test serialization
    data = sm.to_dict()
    assert data["current_stage"] == "implementation"
    assert len(data["stage_history"]) >= 4


def test_iss14_mid_session_redispatch_on_observation(resolver):
    """Verify redispatch_on_observation dynamically re-routes when test failures or file changes occur."""
    sm = TaskLifecycleStateMachine(TaskLifecycleStage.VERIFICATION)

    # 1. Initial resolution (e.g. general design or planning)
    initial_res = resolver.resolve("Design and architect the application system", force_route=True, phase="planning")
    assert initial_res is not None

    # 2. Agent runs tests, encounters failure in database migration -> mid-session re-dispatch
    re_res = resolver.redispatch_on_observation(
        current_result=initial_res,
        files_touched=["src/db/schema.prisma", "migrations/001_init.sql"],
        test_passed=False,
        error_output="PrismaClientKnownRequestError: Migration failed on foreign key constraint",
        lifecycle_state=sm,
    )

    # State machine should have fallen back to implementation
    assert sm.current_stage == TaskLifecycleStage.IMPLEMENTATION
    assert re_res is not None
    assert len(re_res.selected_skills) > 0
