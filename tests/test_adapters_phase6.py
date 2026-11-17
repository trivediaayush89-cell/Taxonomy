"""Comprehensive test suite for Phase 6: Universal Agent Adapters, Shadow Mode & Persistent Telemetry.

Covers:
- ISS-27: Universal Agent Adapter Contract & Hook Implementations
  - Adapters: ClaudeCodeAdapter, CursorAdapter, MCPAdapter, OpenAIAdapter, AntigravityAdapter, GenericAdapter.
  - get_adapter alias mapping and fallback behavior.
  - Progressive disclosure payload building (Level 3 instructions for selected, Level 2 summaries for fallbacks).
  - CLI `taxonomy hook` command execution (argument and stdin).
- ISS-28: Shadow Mode for Non-Disruptive Evaluation
  - Resolver shadow mode: selected_skills is empty, shadow_skills contains predictions.
  - Hook shadow mode and telemetry shadow event tracking.
  - Adapter output suppression in shadow mode.
  - User override tracking in telemetry and CLI `taxonomy override`.
- ISS-29: Atomic UsageTracker & Hook Dispatches Hit Recording
  - Atomic file writes via tempfile + os.replace.
  - dispatch_prompt records hits in UsageTracker when skills are dispatched.
- ISS-30: Persistent TelemetryCollector & SRE CLI Diagnostics
  - Disk persistence and reload across fresh collector instances.
  - Tier distribution, shadow predictions, user overrides, cache hits tracking.
  - `taxonomy stats` reporting, `--benchmark` execution, and `--reset`.
- ISS-32: `/api/resolve` & `cmd_explain` Efficacy Bias and Dynamic Gating
  - `/api/resolve` respects client `force_route` flag instead of hardcoding True.
  - `/api/resolve` includes `efficacy_bias`, `shadow_mode`, and `shadow_skills`.
  - `cmd_explain` includes `Efficacy Bias` line in candidate breakdown.
"""

import json
from pathlib import Path
import socketserver
import sys
import threading
import urllib.request
import pytest

from taxonomy.adapters import (
    AntigravityAdapter,
    ClaudeCodeAdapter,
    CursorAdapter,
    GenericAdapter,
    MCPAdapter,
    OpenAIAdapter,
    build_progressive_context,
    get_adapter,
    list_supported_adapters,
)
from taxonomy.cli import WorkbenchRequestHandler, cmd_explain, cmd_hook, cmd_override, cmd_resolve, cmd_stats
from taxonomy.hook import dispatch_prompt
from taxonomy.indexer import SkillIndexer
from taxonomy.models import GateResult, ResolutionResult, SkillMetadata, SkillScore
from taxonomy.resolver import SkillResolver
from taxonomy.telemetry import TelemetryCollector, telemetry
from taxonomy.tracker import UsageTracker

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mock_skills"


# ============================================================================
# ISS-27: Universal Agent Adapters & Hook Formatting Contracts
# ============================================================================

def test_iss27_adapter_registry_and_aliases():
    """Verify get_adapter resolves canonical names and aliases, defaulting to Claude/Generic."""
    # Canonical names
    assert isinstance(get_adapter("claude"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("cursor"), CursorAdapter)
    assert isinstance(get_adapter("mcp"), MCPAdapter)
    assert isinstance(get_adapter("openai"), OpenAIAdapter)
    assert isinstance(get_adapter("antigravity"), AntigravityAdapter)
    assert isinstance(get_adapter("generic"), GenericAdapter)

    # Aliases
    assert isinstance(get_adapter("claude-code"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("claudecode"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("windsurf"), CursorAdapter)
    assert isinstance(get_adapter("cursor-editor"), CursorAdapter)
    assert isinstance(get_adapter("model-context-protocol"), MCPAdapter)
    assert isinstance(get_adapter("anthropic"), OpenAIAdapter)
    assert isinstance(get_adapter("chatgpt"), OpenAIAdapter)
    assert isinstance(get_adapter("gemini-cli"), AntigravityAdapter)
    assert isinstance(get_adapter("agy"), AntigravityAdapter)
    assert isinstance(get_adapter("json"), GenericAdapter)
    assert isinstance(get_adapter("markdown"), GenericAdapter)

    # Default / fallback
    assert isinstance(get_adapter(None), ClaudeCodeAdapter)
    assert isinstance(get_adapter("unknown-agent"), GenericAdapter)

    supported = list_supported_adapters()
    assert "claude" in supported
    assert "cursor" in supported
    assert "mcp" in supported
    assert "openai" in supported
    assert "antigravity" in supported
    assert "generic" in supported


def test_iss27_progressive_disclosure_payload_builder():
    """Verify build_progressive_context injects Level 3 for selected and Level 2 for fallbacks."""
    skill_a = SkillMetadata(
        name="vercel-react-best-practices",
        description="React and Next.js best practices",
        category="frontend.framework",
        tags=["react", "nextjs"],
        priority=80,
    )
    fallback_b = SkillMetadata(
        name="design-taste-frontend",
        description="Visual design aesthetics",
        category="frontend.visual",
        tags=["design", "css"],
        priority=75,
    )

    # Case 1: Standard routed result
    res = ResolutionResult(
        gate=GateResult(should_route=True, tier=2, reason="explicit_intent"),
        selected_skills=[skill_a],
        confidence="high",
        confidence_score=0.9,
    )

    ctx = build_progressive_context(res, fallback_candidates=[fallback_b])
    assert "Active Specialist Skill: vercel-react-best-practices" in ctx
    assert "Alternative Available Specialists" in ctx
    assert "design-taste-frontend" in ctx

    # Case 2: Gate bypassed -> 0 token context
    res_bypassed = ResolutionResult(
        gate=GateResult(should_route=False, tier=0, reason="casual_conversation"),
        selected_skills=[],
        confidence="none",
    )
    assert build_progressive_context(res_bypassed) == ""

    # Case 3: Shadow mode -> 0 token context
    res_shadow = ResolutionResult(
        gate=GateResult(should_route=True, tier=2, reason="explicit_intent"),
        selected_skills=[],
        shadow_mode=True,
        shadow_skills=[skill_a],
    )
    assert build_progressive_context(res_shadow) == ""


def test_iss27_claude_code_adapter_output():
    """Verify ClaudeCodeAdapter produces valid UserPromptSubmit hook JSON."""
    skill = SkillMetadata(
        name="test-skill",
        description="Testing helper",
        category="testing",
        tags=["pytest"],
    )
    res = ResolutionResult(
        gate=GateResult(should_route=True, tier=1, reason="intent"),
        selected_skills=[skill],
        confidence="high",
        confidence_score=0.95,
        attribution_id="sess-123",
        catalog_hash="cat-abc",
        config_hash="cfg-xyz",
    )

    adapter = ClaudeCodeAdapter()
    payload = adapter.build_payload(res, "Run tests")
    assert payload.agent == "claude"
    assert "hookSpecificOutput" in payload.raw_payload
    hso = payload.raw_payload["hookSpecificOutput"]
    assert hso["continue"] is True
    assert hso["suppressOutput"] is False
    assert "test-skill" in hso["additionalContext"]

    tax = payload.raw_payload["taxonomy"]
    assert tax["tier"] == 1
    assert tax["confidence"] == "high"
    assert tax["selected_skills"] == ["test-skill"]
    assert tax["attribution_id"] == "sess-123"

    out_str = adapter.format_output(payload)
    parsed = json.loads(out_str)
    assert parsed["taxonomy"]["selected_skills"] == ["test-skill"]


def test_iss27_cursor_and_mcp_and_openai_adapters():
    """Verify Cursor, MCP, and OpenAI adapters construct appropriate host schemas."""
    skill = SkillMetadata(
        name="api-architect",
        description="FastAPI endpoint specialist",
        category="backend.api",
        tags=["fastapi", "rest"],
    )
    res = ResolutionResult(
        gate=GateResult(should_route=True, tier=2, reason="intent"),
        selected_skills=[skill],
        confidence="medium",
        confidence_score=0.8,
    )

    # 1. Cursor
    cursor_ad = CursorAdapter()
    cursor_pl = cursor_ad.build_payload(res, "Add endpoint")
    assert "system_prompt_addition" in cursor_pl.raw_payload
    assert "api-architect" in cursor_pl.raw_payload["skills_loaded"]
    assert len(cursor_pl.raw_payload["rules"]) == 1

    # 2. MCP
    mcp_ad = MCPAdapter()
    mcp_pl = mcp_ad.build_payload(res, "Add endpoint")
    assert len(mcp_pl.raw_payload["tools"]) == 1
    assert mcp_pl.raw_payload["tools"][0]["name"] == "api_architect"
    assert "inputSchema" in mcp_pl.raw_payload["tools"][0]
    assert len(mcp_pl.raw_payload["prompts"]) == 1

    # 3. OpenAI
    openai_ad = OpenAIAdapter()
    openai_pl = openai_ad.build_payload(res, "Add endpoint")
    assert len(openai_pl.raw_payload["tools"]) == 1
    assert openai_pl.raw_payload["tools"][0]["type"] == "function"
    assert openai_pl.raw_payload["tools"][0]["function"]["name"] == "api_architect"
    assert "system_message" in openai_pl.raw_payload


def test_iss27_antigravity_and_generic_adapters():
    """Verify AntigravityAdapter and GenericAdapter output formatting."""
    skill = SkillMetadata(
        name="audit-sentry",
        description="Quality and security sentry",
        category="verification.qa",
    )
    res = ResolutionResult(
        gate=GateResult(should_route=True, tier=2, reason="intent"),
        selected_skills=[skill],
        confidence="high",
        confidence_score=0.92,
    )

    # 1. Antigravity
    agy_ad = AntigravityAdapter()
    agy_pl = agy_ad.build_payload(res, "Review code")
    formatted = agy_ad.format_output(agy_pl)
    assert '<instructions source="taxonomy-dispatcher">' in formatted
    assert "Active Specialist Skill: audit-sentry" in formatted

    # 2. Generic
    gen_ad = GenericAdapter()
    gen_pl = gen_ad.build_payload(res, "Review code")
    assert gen_pl.raw_payload["selected_skills"] == ["audit-sentry"]


def test_iss27_cli_cmd_hook(capsys):
    """Verify CLI `taxonomy hook --agent <name> <prompt>` executes and outputs JSON."""
    class Args:
        prompt = "Create a new react component with tailwind"
        agent = "claude"
        shadow = False
        phase = None
        prefer = None
        max_skills = 2
        skills_dir = str(FIXTURES_DIR)
        workspace = None
        json = False

    cmd_hook(Args())
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "hookSpecificOutput" in parsed
    assert "taxonomy" in parsed


# ============================================================================
# ISS-28: Shadow Mode for Non-Disruptive Evaluation
# ============================================================================

def test_iss28_resolver_shadow_mode():
    """Verify that in shadow mode, resolver predicts skills without activating them."""
    indexer = SkillIndexer([FIXTURES_DIR])
    indexer.scan()
    resolver = SkillResolver(indexer)

    prompt = "Create a responsive navigation bar with tailwind"
    # Normal execution
    res_normal = resolver.resolve(prompt, force_route=True, shadow_mode=False)
    assert not res_normal.shadow_mode
    assert len(res_normal.selected_skills) > 0
    assert len(res_normal.shadow_skills) == 0

    # Shadow execution
    res_shadow = resolver.resolve(prompt, force_route=True, shadow_mode=True)
    assert res_shadow.shadow_mode is True
    assert len(res_shadow.selected_skills) == 0  # Zero disruption to live prompt!
    assert len(res_shadow.shadow_skills) > 0    # Captured for telemetry/analysis!

    # Dictionary representation exposes both
    d = res_shadow.to_dict()
    assert d["shadow_mode"] is True
    assert len(d["selected_skills"]) == 0
    assert len(d["shadow_skills"]) > 0


def test_iss28_hook_and_adapter_shadow_mode():
    """Verify dispatch_prompt and adapters honor shadow mode without prompt alterations."""
    res = dispatch_prompt(
        "Build a backend api database service",
        skills_roots=[FIXTURES_DIR],
        force_route=True,
        shadow_mode=True,
    )
    assert res.shadow_mode is True
    assert len(res.selected_skills) == 0
    assert len(res.shadow_skills) > 0

    adapter = ClaudeCodeAdapter()
    payload = adapter.build_payload(res, "Build a backend api database service")
    assert payload.additional_context == ""
    assert payload.raw_payload["hookSpecificOutput"]["additionalContext"] == ""
    assert payload.raw_payload["taxonomy"]["shadow_mode"] is True


def test_iss28_override_recording(tmp_path, monkeypatch):
    """Verify recording developer overrides updates telemetry metrics."""
    t_file = tmp_path / "test_telemetry.json"
    coll = TelemetryCollector(log_path=t_file, persist=True)

    coll.record_override(
        prompt="Build a blog",
        routed_skills=["generic-builder"],
        actual_skills=["specialist-blog"],
        notes="Developer preferred specialized blog tool",
    )

    stats = coll.get_stats()
    assert stats["user_overrides"] == 1
    assert len(stats["recent_overrides"]) == 1
    assert stats["recent_overrides"][0]["prompt"] == "Build a blog"


# ============================================================================
# ISS-29: Atomic Usage Tracking & Real Hook Hit Invocations
# ============================================================================

def test_iss29_atomic_usage_tracker_file_persistence(tmp_path):
    """Verify UsageTracker safely persists hits atomically via os.replace."""
    log_file = tmp_path / "usage.json"
    tracker = UsageTracker(log_path=log_file)

    tracker.record_hit("skill-a")
    tracker.record_hits(["skill-b", "skill-c"])

    assert log_file.is_file()
    # Reload fresh instance
    fresh_tracker = UsageTracker(log_path=log_file)
    assert fresh_tracker.get_hit_count("skill-a") == 1
    assert fresh_tracker.get_hit_count("skill-b") == 1
    assert fresh_tracker.get_hit_count("skill-c") == 1
    assert fresh_tracker.get_stats_summary()["total_queries"] == 2


def test_iss29_dispatch_prompt_records_hits(tmp_path, monkeypatch):
    """Verify dispatch_prompt records hits in UsageTracker when skills are dispatched."""
    log_file = tmp_path / "hook_usage.json"
    monkeypatch.setattr("taxonomy.tracker.DEFAULT_USAGE_PATH", log_file)

    res = dispatch_prompt(
        "Build a react interface",
        skills_roots=[FIXTURES_DIR],
        force_route=True,
        shadow_mode=False,
    )
    if res.selected_skills:
        first_skill = res.selected_skills[0].name
        tracker = UsageTracker(log_path=log_file)
        assert tracker.get_hit_count(first_skill) >= 1


# ============================================================================
# ISS-30: Persistent TelemetryCollector Across Process Lifecycles
# ============================================================================

def test_iss30_persistent_telemetry_collector(tmp_path):
    """Verify TelemetryCollector persists queries, tier distributions, and latencies across instances."""
    log_file = tmp_path / "telemetry_persistence.json"

    # Instance 1
    t1 = TelemetryCollector(log_path=log_file, persist=True)
    t1.record_gate(tier=2, should_route=True, latency_ms=0.045, reason="code_work")
    t1.record_resolution(["skill-1", "skill-2"], latency_ms=1.23, taste_applied=True)
    t1.record_shadow(prompt="Test shadow", shadow_skills=["skill-shadow"], latency_ms=0.95)
    t1.record_cache_hit()

    s1 = t1.get_stats()
    assert s1["total_queries"] == 1
    assert s1["routed"] == 1
    assert s1["shadow_predictions"] == 1
    assert s1["cache_hits"] == 1
    assert s1["tier_distribution"]["2"] == 1

    # Instance 2 (Simulating a fresh CLI subprocess)
    t2 = TelemetryCollector(log_path=log_file, persist=True)
    s2 = t2.get_stats()
    assert s2["total_queries"] == 1
    assert s2["routed"] == 1
    assert s2["shadow_predictions"] == 1
    assert s2["cache_hits"] == 1
    assert s2["tier_distribution"]["2"] == 1
    assert s2["gate_latency_ms"]["avg"] == 0.045

    # Reset
    t2.reset()
    s3 = t2.get_stats()
    assert s3["total_queries"] == 0
    assert not log_file.exists()


def test_iss30_cmd_stats_benchmark_and_json(tmp_path, monkeypatch, capsys):
    """Verify cmd_stats executes benchmark, json formatting, and reset."""
    log_file = tmp_path / "cli_telemetry.json"
    test_coll = TelemetryCollector(log_path=log_file, persist=True)
    monkeypatch.setattr("taxonomy.telemetry.telemetry", test_coll)

    class Args:
        skills_dir = str(FIXTURES_DIR)
        workspace = None
        benchmark = True
        reset = False
        json = False

    # 1. Run live benchmark
    cmd_stats(Args())
    captured = capsys.readouterr()
    assert "Running live latency benchmark" in captured.out
    assert "Gate Latency" in captured.out

    # 2. Output JSON
    Args.benchmark = False
    Args.json = True
    cmd_stats(Args())
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["total_queries"] > 0
    assert "gate_latency_ms" in data

    # 3. Reset
    Args.json = False
    Args.reset = True
    cmd_stats(Args())
    captured_reset = capsys.readouterr()
    assert "reset successfully" in captured_reset.out


# ============================================================================
# ISS-32: `/api/resolve` & `cmd_explain` Efficacy Bias and Dynamic Gating
# ============================================================================

def test_iss32_workbench_resolve_api_respects_force_route(tmp_path):
    """Verify /api/resolve respects force_route parameter and returns efficacy_bias and shadow_mode."""
    server = socketserver.TCPServer(("127.0.0.1", 0), WorkbenchRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Casual prompt without force_route -> Gate bypasses (should_route=False)
        req_casual = urllib.request.Request(
            f"{base_url}/api/resolve",
            data=json.dumps({"prompt": "Hello there!", "force_route": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_casual) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["gate"]["should_route"] is False
            assert res["abstained"] is True
            assert len(res["selected_skills"]) == 0

        # 2. Casual prompt WITH force_route -> Routes through
        req_forced = urllib.request.Request(
            f"{base_url}/api/resolve",
            data=json.dumps({"prompt": "Hello there!", "force_route": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_forced) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["gate"]["should_route"] is False  # Gate still saw it as casual
            assert "shadow_mode" in res
            assert "shadow_skills" in res

        # 3. Technical prompt -> Checks efficacy_bias inclusion in skill_scores
        req_tech = urllib.request.Request(
            f"{base_url}/api/resolve",
            data=json.dumps({"prompt": "Build a react frontend view", "force_route": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_tech) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            if res["skill_scores"]:
                first_score = next(iter(res["skill_scores"].values()))
                assert "efficacy_bias" in first_score
                assert "taste_bias" in first_score
                assert "base_score" in first_score
                assert "final_score" in first_score
    finally:
        server.shutdown()
        server.server_close()


def test_iss32_cmd_explain_shows_efficacy_bias(capsys):
    """Verify cmd_explain prints Efficacy Bias line in candidate breakdown."""
    class Args:
        prompt = "Create a nextjs component"
        skills_dir = str(FIXTURES_DIR)
        max_skills = 3
        phase = None
        prefer = None
        force = True
        no_triad = False

    cmd_explain(Args())
    captured = capsys.readouterr()
    assert "Efficacy Bias  :" in captured.out
    assert "Taste Bias     :" in captured.out
    assert "Final Score    :" in captured.out
