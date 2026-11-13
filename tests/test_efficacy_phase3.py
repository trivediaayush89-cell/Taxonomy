"""Dedicated tests for Phase 3 Efficacy & Attribution improvements (ISS-15 through ISS-19)."""

import json
from pathlib import Path
import time
import pytest

from taxonomy.efficacy import (
    AttributionSession,
    EfficacyTracker,
    GitInspector,
    SkillEfficacyRecord,
    DEFAULT_MAX_SESSION_HISTORY,
)
from taxonomy.models import SkillMetadata
from taxonomy.resolver import SkillResolver


def test_iss15_sigmoid_bounded_bias_and_session_cap(tmp_path):
    """ISS-15: Sigmoid normalization bounded within [-1.5, +1.5] and 200 session cap."""
    rec = SkillEfficacyRecord(skill_name="test-skill")
    assert rec.compute_bias(max_bias=1.5) == 0.0

    # Default max session history is 200 per deck specification
    assert DEFAULT_MAX_SESSION_HISTORY == 200

    non_git = tmp_path / "non_git"
    non_git.mkdir()
    tracker = EfficacyTracker(storage_path=tmp_path / "eff.json", workspace_root=non_git)
    assert tracker.max_session_history == 200

    # Pruning cap preserves at most max_session_history entries on disk
    tracker.max_session_history = 5
    for i in range(12):
        tracker.start_session(skills=["cap-skill"], prompt=f"prompt {i}")

    saved_data = json.loads((tmp_path / "eff.json").read_text(encoding="utf-8"))
    assert len(saved_data["sessions"]) == 5
    assert saved_data["skills"]["cap-skill"]["total_dispatches"] == 12


def test_iss16_bayesian_prior_shrinkage_and_time_decay():
    """ISS-16: Bayesian Beta prior shrinkage dampens lucky runs, proven skills earn full bias, time decays stale stats."""
    # Case A: 2 lucky commits (n=2, win_rate = 100%)
    lucky_rec = SkillEfficacyRecord(
        skill_name="lucky-skill",
        commits_count=2,
        evaluated_sessions=2,
        net_score=2.0,
        last_dispatched=time.time(),
    )
    # Bayesian win rate is shrunk from 100% to (2+2)/(2+4) = 66.7%
    bayes_p = lucky_rec.compute_bayesian_win_rate(alpha=2.0, beta=2.0)
    assert round(bayes_p, 3) == 0.667

    # Bias should be a gentle nudge (~0.3 to 0.45), NOT full 1.5
    lucky_bias = lucky_rec.compute_bias(max_bias=1.5)
    assert 0.15 <= lucky_bias <= 0.60, f"Expected gentle nudge for 2 lucky wins, got {lucky_bias}"

    # Case B: 15 proven commits (n=15, win_rate = 100%)
    proven_rec = SkillEfficacyRecord(
        skill_name="proven-skill",
        commits_count=15,
        evaluated_sessions=15,
        net_score=15.0,
        last_dispatched=time.time(),
    )
    proven_p = proven_rec.compute_bayesian_win_rate(alpha=2.0, beta=2.0)
    assert proven_p > 0.85
    proven_bias = proven_rec.compute_bias(max_bias=1.5)
    assert proven_bias >= 1.10, f"Expected strong bias >= 1.10 for 15 proven wins, got {proven_bias}"
    assert proven_bias <= 1.50

    # Case C: Negative penalty scaling for repeated discards
    bad_rec = SkillEfficacyRecord(
        skill_name="bad-skill",
        discards_count=6,
        evaluated_sessions=6,
        net_score=-12.0,
        last_dispatched=time.time(),
    )
    bad_bias = bad_rec.compute_bias(max_bias=1.5)
    assert bad_bias <= -0.90, f"Expected strong negative penalty for repeated discards, got {bad_bias}"
    assert bad_bias >= -1.50

    # Case D: Time-decay (half-life of 30 days)
    now = time.time()
    decay_rec = SkillEfficacyRecord(
        skill_name="stale-skill",
        commits_count=15,
        evaluated_sessions=15,
        net_score=15.0,
        last_dispatched=now,
    )
    bias_fresh = decay_rec.compute_bias(max_bias=1.5, current_time=now)
    # Simulate 30 days passing
    bias_30d = decay_rec.compute_bias(max_bias=1.5, half_life_days=30.0, current_time=now + (30 * 86400))
    # Bias after 1 half-life should be ~50% of fresh bias
    assert pytest.approx(bias_fresh * 0.5, abs=0.05) == bias_30d


def test_iss17_per_skill_attribution_and_domain_extension_weighting(tmp_path):
    """ISS-17: Primary specialist gets full weight, partners/guardrails weighted, domain extensions filter credit."""
    store_file = tmp_path / "eff.json"
    tracker = EfficacyTracker(storage_path=store_file)

    # Start session with lead, partner, and guardrail
    sess = tracker.start_session(
        skills=["fastapi-backend", "impeccable", "engineering-quality-gate"],
        prompt="Add user registration endpoint and validation",
        files_touched=["app/api/users.py", "app/models.py"],
    )

    # Check auto-assigned role weights
    assert sess.skill_weights["fastapi-backend"] == 1.0  # Lead
    assert sess.skill_weights["impeccable"] == 0.5        # Partner
    assert sess.skill_weights["engineering-quality-gate"] == 0.25  # Guardrail

    # Evaluate session with committed outcome (+1.0) and passing test (+1.0) -> base delta = +2.0
    # Because files_touched only contains .py (backend), impeccable (frontend) weight should be dampened!
    eval_sess = tracker.evaluate_session(sess.session_id, test_passed=True, force_outcome="committed")

    fastapi_stat = tracker.get_skill_stats("fastapi-backend")
    gate_stat = tracker.get_skill_stats("engineering-quality-gate")
    impeccable_stat = tracker.get_skill_stats("impeccable")

    # fastapi-backend gets full delta: 2.0 * 1.0 = +2.0
    assert fastapi_stat.net_score == 2.0

    # engineering-quality-gate gets guardrail delta: 2.0 * 0.25 = +0.5
    assert gate_stat.net_score == 0.5

    # impeccable was dampened due to orthogonal backend files touched: 2.0 * (0.5 * 0.25) = +0.25
    assert impeccable_stat.net_score < 0.5


def test_iss18_advisory_outcomes_and_tdd_red_phase(tmp_path):
    """ISS-18: Advisory skills receive 'consulted' outcome (+0.75) without Git diffs, TDD red phase has 0 penalty."""
    store_file = tmp_path / "eff.json"
    tracker = EfficacyTracker(storage_path=store_file)

    # 1. Advisory / Architecture Review session
    adv_sess = tracker.start_session(
        skills=["smart-contract-auditor", "independent-jury"],
        prompt="Audit staking contract for reentrancy vulnerabilities",
    )
    assert adv_sess.session_mode == "advisory"

    # Evaluate with no Git commits or dirty files (report produced in chat)
    eval_adv = tracker.evaluate_session(adv_sess.session_id)
    assert eval_adv.outcome == "consulted"
    assert eval_adv.score_delta == 0.75

    auditor_stat = tracker.get_skill_stats("smart-contract-auditor")
    assert auditor_stat.consulted_count == 1
    assert auditor_stat.commits_count == 0
    assert auditor_stat.win_rate == 75.0
    assert auditor_stat.net_score == 0.75

    # 2. TDD Red Phase session
    tdd_sess = tracker.start_session(
        skills=["pytest-runner"],
        prompt="TDD red phase: write failing test for auth token expiration",
        session_mode="tdd",
    )
    # Test failed intentionally in TDD red phase!
    eval_tdd = tracker.evaluate_session(tdd_sess.session_id, test_passed=False, force_outcome="retained")
    assert eval_tdd.test_outcome == "tdd_red"
    # Retained (+0.5) + tdd_red (0.0) = +0.5 (NO -1.0 test failure penalty!)
    assert eval_tdd.score_delta == 0.5

    tdd_stat = tracker.get_skill_stats("pytest-runner")
    assert tdd_stat.tests_failed == 0
    assert tdd_stat.retains_count == 1
    assert tdd_stat.net_score == 0.5


def test_iss19_version_and_content_hash_tracking(tmp_path):
    """ISS-19: Track version and content hash; archive previous stats and decay metrics on skill modification."""
    store_file = tmp_path / "eff.json"
    tracker = EfficacyTracker(storage_path=store_file)

    # Version 1.0 of skill gets 4 commits
    for _ in range(4):
        s = tracker.start_session(
            skills=["my-skill"],
            prompt="v1 session",
            skill_hashes={"my-skill": "hash_v1_aaa"},
            skill_versions={"my-skill": "1.0.0"},
        )
        tracker.evaluate_session(s.session_id, force_outcome="committed", test_passed=True)

    stat = tracker.get_skill_stats("my-skill")
    assert stat.commits_count == 4
    assert stat.content_hash == "hash_v1_aaa"
    assert stat.version == "1.0.0"
    assert stat.net_score == 8.0  # 4 * (+1.0 + 1.0)

    # Now developer modifies SKILL.md -> content hash changes to hash_v2_bbb
    s_v2 = tracker.start_session(
        skills=["my-skill"],
        prompt="v2 session after refactoring",
        skill_hashes={"my-skill": "hash_v2_bbb"},
        skill_versions={"my-skill": "1.1.0"},
    )
    tracker.evaluate_session(s_v2.session_id, force_outcome="committed")

    stat_v2 = tracker.get_skill_stats("my-skill")
    # Verify version 1.0 was archived
    assert "1.0.0@hash_v1_" in stat_v2.version_history
    archived = stat_v2.version_history["1.0.0@hash_v1_"]
    assert archived["commits_count"] == 4
    assert archived["net_score"] == 8.0

    # Historical stats decayed by 50% on update: 4 commits * 0.5 = 2, + 1 new commit = 3
    assert stat_v2.commits_count == 3
    assert stat_v2.content_hash == "hash_v2_bbb"
    assert stat_v2.version == "1.1.0"


def test_iss18_implementation_pod_with_director_not_misclassified_as_advisory(tmp_path):
    """Regression: implementation pod with 'development-director' or 'independent-jury' as partner stays 'standard'."""
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    tracker = EfficacyTracker(storage_path=tmp_path / "eff.json", workspace_root=non_git)

    sess = tracker.start_session(
        skills=["fastapi-backend", "development-director", "independent-jury"],
        prompt="add health check endpoint and checkout validation",
    )
    assert sess.session_mode == "standard"


def test_iss17_idempotent_reevaluation_with_domain_dampening_never_compounds(tmp_path):
    """Regression: calling evaluate_session multiple times rolls back exact applied weights and never compounds 0.25x."""
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    tracker = EfficacyTracker(storage_path=tmp_path / "eff.json", workspace_root=non_git)

    sess = tracker.start_session(
        skills=["fastapi-backend", "impeccable"],
        prompt="update backend and ui",
    )
    # 1st evaluation without files_touched: impeccable gets base partner weight 0.5 -> +0.5 * 0.5 = +0.25
    tracker.evaluate_session(sess.session_id, force_outcome="retained")
    assert tracker.get_skill_stats("impeccable").net_score == pytest.approx(0.25, abs=0.01)

    # 2nd evaluation with backend-only files_touched: rolls back +0.25, applies dampened weight (0.5 * 0.25 = 0.12) * 1.0 = +0.12
    tracker.evaluate_session(sess.session_id, files_touched=["app/api.py"], force_outcome="committed")
    score_after_2nd = tracker.get_skill_stats("impeccable").net_score
    assert score_after_2nd == pytest.approx(0.12, abs=0.01)

    # 3rd evaluation with same backend-only files_touched: must NOT compound 0.12 * 0.25 -> stays 0.12!
    tracker.evaluate_session(sess.session_id, files_touched=["app/api.py"], force_outcome="committed")
    score_after_3rd = tracker.get_skill_stats("impeccable").net_score
    assert score_after_3rd == pytest.approx(0.12, abs=0.01)


def test_iss17_primary_lead_preserves_full_weight_when_prerequisite_precedes_in_dag(tmp_path):
    """Regression: when topological_sort places a prerequisite before the lead skill, lead still gets 1.0 weight."""
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    tracker = EfficacyTracker(storage_path=tmp_path / "eff.json", workspace_root=non_git)

    class MockPrerequisiteIndexer:
        def __init__(self):
            self.all_skills = [
                SkillMetadata(
                    name="base-prereq",
                    description="foundational helper",
                    category="general",
                    tags=["helper"],
                    priority=40,
                    version="1.0.0",
                    content_hash="h_prereq",
                ),
                SkillMetadata(
                    name="lead-fastapi",
                    description="fastapi rest api endpoint builder",
                    category="backend.api",
                    tags=["fastapi", "api", "endpoint", "backend"],
                    priority=90,
                    requires=["base-prereq"],
                    version="1.2.0",
                    content_hash="h_lead",
                ),
            ]
        def get_skill(self, name):
            for s in self.all_skills:
                if s.name == name:
                    return s
            return None

    resolver = SkillResolver(
        MockPrerequisiteIndexer(),
        max_skills=3,
        workspace_root=non_git,
        efficacy_tracker=tracker,
        enable_triad=False,
    )
    res = resolver.resolve("build fastapi rest api endpoint", force_route=True, record_attribution=True)
    # Topological sort places base-prereq first in selected_skills
    assert [s.name for s in res.selected_skills] == ["base-prereq", "lead-fastapi"]
    sess = tracker.get_latest_session()
    assert sess is not None
    # Lead specialist must retain 1.0 weight, prerequisite gets 0.5
    assert sess.skill_weights["lead-fastapi"] == 1.0
    assert sess.skill_weights["base-prereq"] == 0.5
    assert sess.session_mode == "standard"


def test_iss15_external_mtime_refresh(tmp_path):
    """Regression: EfficacyTracker automatically reloads when storage file is updated by another instance."""
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    store_file = tmp_path / "shared_eff.json"

    tracker_reader = EfficacyTracker(storage_path=store_file, workspace_root=non_git)
    assert tracker_reader.get_skill_stats("shared-skill") is None

    # Another process/instance records an outcome to the same file
    tracker_writer = EfficacyTracker(storage_path=store_file, workspace_root=non_git)
    tracker_writer.record_direct_outcome(["shared-skill"], outcome="committed", test_passed=True)

    # Ensure mtime advances even on fast filesystems
    st = store_file.stat()
    import os
    os.utime(store_file, (st.st_atime, st.st_mtime + 1.0))

    # Reader instance automatically picks up the new record via refresh_if_modified()
    stat = tracker_reader.get_skill_stats("shared-skill")
    assert stat is not None
    assert stat.commits_count == 1

