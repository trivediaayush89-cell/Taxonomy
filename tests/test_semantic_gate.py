"""Tests for semantic intent fallback on ambiguous prompts."""

from taxonomy.gate import CompoundGate


def test_semantic_fallback_promotes_ambiguous_blockchain_exploit():
    gate = CompoundGate(enable_semantic_fallback=True)
    # Does not contain 'build', 'smart contract', or 'audit', but has domain intent tokens: 'siphon', 'liquidity', 'arbitrage'
    res = gate.evaluate("Prevent bad actors from siphoning liquidity via oracle arbitrage")
    assert res.should_route is True
    assert "semantic_fallback" in res.reason
    assert "security.blockchain" in res.reason


def test_semantic_fallback_promotes_ambiguous_ui_glitch():
    gate = CompoundGate(enable_semantic_fallback=True)
    # Does not contain 'component' or 'react', but has UI intent tokens: 'jarring', 'stutter', 'viewport'
    res = gate.evaluate("The mobile viewport feels jarring with layout stutter and flicker")
    assert res.should_route is True
    assert "semantic_fallback" in res.reason
    assert "ui.frontend" in res.reason


def test_casual_query_still_bypasses_semantic_fallback():
    gate = CompoundGate(enable_semantic_fallback=True)
    res = gate.evaluate("What is your favorite color and what time is it?")
    assert res.should_route is False
    assert res.tier in (0, 1)
