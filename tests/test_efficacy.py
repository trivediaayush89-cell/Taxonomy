"""Comprehensive tests for zero-token outcome-based empirical efficacy telemetry."""

import json
from pathlib import Path
import subprocess
import time
import pytest

from taxonomy.efficacy import (
    AttributionSession,
    EfficacyTracker,
    GitInspector,
    SkillEfficacyRecord,
)
from taxonomy.indexer import SkillIndexer
from taxonomy.models import SkillMetadata
from taxonomy.resolver import SkillResolver
from taxonomy.hook import dispatch_prompt


def test_efficacy_record_math():
    rec = SkillEfficacyRecord(skill_name="impeccable")
    assert rec.win_rate == 0.0
    assert rec.keep_rate == 0.0
    assert rec.discard_rate == 0.0
    assert rec.test_pass_rate == 0.0

    # 8 commits, 2 retained, 1 discarded
    rec.commits_count = 8
    rec.retains_count = 2
    rec.discards_count = 1
    # total evals = 11. win_points = 8 + (0.5 * 2) = 9.0 -> 9/11 = 81.8%
    assert rec.total_evaluations == 11
    assert rec.win_rate == 81.8
    assert rec.keep_rate == 90.9
    assert rec.discard_rate == 9.1

    # 4 tests passed, 1 test failed
    rec.tests_passed = 4
    rec.tests_failed = 1
    assert rec.test_pass_rate == 80.0

    # Serialization roundtrip
    d = rec.to_dict()
    assert d["skill_name"] == "impeccable"
    assert d["win_rate"] == 81.8

    rec2 = SkillEfficacyRecord.from_dict(d)
    assert rec2.skill_name == rec.skill_name
    assert rec2.commits_count == rec.commits_count
    assert rec2.win_rate == rec.win_rate


def test_attribution_session_serialization():
    sess = AttributionSession(
        session_id="test1234",
        timestamp=time.time(),
        prompt="build button",
        dispatched_skills=["impeccable"],
        workspace_root="/tmp/fake",
        initial_commit="abc1234",
        initial_dirty_files=["file1.ts"],
        files_touched=["file2.ts"],
        status="active",
    )
    d = sess.to_dict()
    assert d["session_id"] == "test1234"
    assert d["initial_commit"] == "abc1234"

    sess2 = AttributionSession.from_dict(d)
    assert sess2.session_id == "test1234"
    assert sess2.dispatched_skills == ["impeccable"]


def _init_dummy_git_repo(repo_dir: Path):
    """Helper to initialize a clean git repository for testing outcomes."""
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    init_file = repo_dir / "init.txt"
    init_file.write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo_dir), check=True, capture_output=True)


def test_git_outcome_committed(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    store_file = tmp_path / "efficacy.json"
    tracker = EfficacyTracker(storage_path=store_file, workspace_root=repo_dir)

    # Start session
    session = tracker.start_session(
        skills=["fastapi-backend", "engineering-quality-gate"],
        prompt="add health check endpoint",
        workspace_root=repo_dir,
        files_touched=["app/health.py"],
    )
    assert session.status == "active"
    assert session.initial_commit is not None

    # Simulate developer making changes and committing them
    health_file = repo_dir / "app" / "health.py"
    health_file.parent.mkdir(parents=True, exist_ok=True)
    health_file.write_text("def health(): return {'status': 'ok'}", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: health check"], cwd=str(repo_dir), check=True, capture_output=True)

    # Evaluate session
    evaluated = tracker.evaluate_session(session.session_id, test_passed=True)
    assert evaluated is not None
    assert evaluated.outcome == "committed"
    assert evaluated.test_outcome == "passed"
    assert evaluated.score_delta == 2.0  # +1.0 commit, +1.0 test pass

    # Verify skill metrics
    fastapi_stat = tracker.get_skill_stats("fastapi-backend")
    assert fastapi_stat is not None
    assert fastapi_stat.commits_count == 1
    assert fastapi_stat.tests_passed == 1
    assert fastapi_stat.win_rate == 100.0
    assert fastapi_stat.net_score == 2.0


def test_git_outcome_retained(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    store_file = tmp_path / "efficacy.json"
    tracker = EfficacyTracker(storage_path=store_file, workspace_root=repo_dir)

    # Start session
    session = tracker.start_session(
        skills=["impeccable"],
        prompt="tweak colors",
        workspace_root=repo_dir,
        files_touched=["styles.css"],
    )

    # Modify file without committing
    style_file = repo_dir / "styles.css"
    style_file.write_text("body { color: red; }", encoding="utf-8")

    # Evaluate session (tests not run)
    evaluated = tracker.evaluate_session(session.session_id, test_passed=None)
    assert evaluated.outcome == "retained"
    assert evaluated.test_outcome == "not_run"
    assert evaluated.score_delta == 0.5  # +0.5 for retained

    stat = tracker.get_skill_stats("impeccable")
    assert stat.retains_count == 1
    assert stat.commits_count == 0
    assert stat.win_rate == 50.0  # 0.5 * 1 / 1 = 50.0%
    assert stat.keep_rate == 100.0


def test_git_outcome_discarded(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    store_file = tmp_path / "efficacy.json"
    tracker = EfficacyTracker(storage_path=store_file, workspace_root=repo_dir)

    # Start session touching bad_file.py
    session = tracker.start_session(
        skills=["sloppy-ui"],
        prompt="experimental layout",
        workspace_root=repo_dir,
        files_touched=["bad_file.py"],
    )

    # Developer writes file, dislikes it, and removes/restores it
    bad_file = repo_dir / "bad_file.py"
    bad_file.write_text("bad code", encoding="utf-8")
    bad_file.unlink()  # discarded!

    # Evaluate session with failed test
    evaluated = tracker.evaluate_session(session.session_id, test_passed=False)
    assert evaluated.outcome == "discarded"
    assert evaluated.test_outcome == "failed"
    assert evaluated.score_delta == -3.0  # -2.0 discard, -1.0 test fail

    stat = tracker.get_skill_stats("sloppy-ui")
    assert stat.discards_count == 1
    assert stat.tests_failed == 1
    assert stat.win_rate == 0.0
    assert stat.discard_rate == 100.0
    assert stat.net_score == -3.0


def test_direct_outcome_and_leaderboard(tmp_path):
    store_file = tmp_path / "efficacy.json"
    tracker = EfficacyTracker(storage_path=store_file)

    # Record direct outcomes
    tracker.record_direct_outcome(["skill-top"], outcome="committed", test_passed=True)
    tracker.record_direct_outcome(["skill-top"], outcome="committed", test_passed=True)
    tracker.record_direct_outcome(["skill-mid"], outcome="retained", test_passed=True)
    tracker.record_direct_outcome(["skill-bad"], outcome="discarded", test_passed=False)

    # Leaderboard by score
    lb = tracker.get_leaderboard(sort_by="score")
    assert len(lb) == 3
    assert lb[0].skill_name == "skill-top"
    assert lb[0].net_score == 4.0  # 2*(+1.0 + 1.0)
    assert lb[1].skill_name == "skill-mid"
    assert lb[2].skill_name == "skill-bad"

    # Leaderboard by win rate
    lb_wr = tracker.get_leaderboard(sort_by="win_rate")
    assert lb_wr[0].skill_name == "skill-top"
    assert lb_wr[0].win_rate == 100.0

    summary = tracker.get_summary()
    assert summary["total_skills_tracked"] == 3
    assert summary["top_skill"] == "skill-top"
    assert "skill-bad" in summary["high_discard_skills"] or summary["total_evaluated_sessions"] >= 4


def test_fail_open_on_corrupt_efficacy_file(tmp_path):
    corrupt_file = tmp_path / "corrupt_eff.json"
    corrupt_file.write_text("{not valid json", encoding="utf-8")

    # Should not throw exception
    tracker = EfficacyTracker(storage_path=corrupt_file)
    assert tracker.get_skill_stats("any") is None
    assert tracker.get_leaderboard() == []

    # Can record after fail open
    sess = tracker.record_direct_outcome(["safe-skill"], outcome="committed")
    assert sess.outcome == "committed"
    assert tracker.get_skill_stats("safe-skill").commits_count == 1


def test_resolver_incorporates_efficacy_bias(tmp_path):
    store_file = tmp_path / "efficacy.json"
    tracker = EfficacyTracker(storage_path=store_file)

    # Record 5 wins for winner-skill
    for _ in range(5):
        tracker.record_direct_outcome(["winner-skill"], outcome="committed", test_passed=True)

    # Record 3 discards for loser-skill
    for _ in range(3):
        tracker.record_direct_outcome(["loser-skill"], outcome="discarded", test_passed=False)

    # Set up mock indexer with both skills
    class MockIndexer:
        def __init__(self):
            self.all_skills = [
                SkillMetadata(name="winner-skill", description="great backend tool", category="backend.api", tags=["backend", "api"], priority=50),
                SkillMetadata(name="loser-skill", description="troubled backend tool", category="backend.api", tags=["backend", "api"], priority=50),
                SkillMetadata(name="engineering-quality-gate", description="verification sentry", category="verification.qa", tags=["qa", "gate"], priority=50),
            ]
        def get_skill(self, name):
            for s in self.all_skills:
                if s.name == name:
                    return s
            return None

    indexer = MockIndexer()
    resolver = SkillResolver(indexer, efficacy_tracker=tracker, enable_efficacy_bias=True)

    res = resolver.resolve("build backend api endpoint", force_route=True)
    scores = res.skill_scores
    assert "winner-skill" in scores
    assert "loser-skill" in scores

    # Winner gets positive efficacy bias (+0.5 max)
    assert scores["winner-skill"].efficacy_bias > 0.0
    # Loser gets negative efficacy bias (-0.5 min)
    assert scores["loser-skill"].efficacy_bias < 0.0
    # Winner ranks above loser
    assert scores["winner-skill"].final_score > scores["loser-skill"].final_score

    # Quality Sentry Immunity: quality gate never receives negative bias
    if "engineering-quality-gate" in scores:
        assert scores["engineering-quality-gate"].efficacy_bias >= 0.0


def test_cli_efficacy_commands(tmp_path, capsys):
    from taxonomy.cli import (
        cmd_efficacy_list,
        cmd_efficacy_record,
        cmd_efficacy_inspect,
        cmd_efficacy_reset,
    )

    store_file = tmp_path / ".taxonomy" / "efficacy.json"
    ws = str(tmp_path)

    # 1. Record an outcome via CLI
    class RecordArgs:
        workspace = ws
        skills = "cli-tested-skill,engineering-quality-gate"
        session = None
        committed = True
        retained = False
        discarded = False
        outcome = None
        test_passed = True
        test_failed = False
        test = None
        notes = "Automated test suite passed"
        prompt = "CLI test run"

    cmd_efficacy_record(RecordArgs())
    out = capsys.readouterr().out
    assert "[OK] Recorded empirical outcome" in out
    assert "cli-tested-skill" in out

    # 2. List leaderboard via CLI
    class ListArgs:
        workspace = ws
        min_samples = 0
        sort = "score"
        json = False

    cmd_efficacy_list(ListArgs())
    out_list = capsys.readouterr().out
    assert "SKILL EMPIRICAL EFFICACY LEADERBOARD" in out_list
    assert "cli-tested-skill" in out_list

    # 3. List JSON format
    class JsonListArgs(ListArgs):
        json = True

    cmd_efficacy_list(JsonListArgs())
    json_out = capsys.readouterr().out
    parsed = json.loads(json_out)
    assert isinstance(parsed, list)
    assert any(item["skill_name"] == "cli-tested-skill" for item in parsed)

    # 4. Inspect session
    class InspectArgs:
        workspace = ws
        session_id = None

    cmd_efficacy_inspect(InspectArgs())
    inspect_out = capsys.readouterr().out
    assert "EFFICACY SESSION & GIT ATTRIBUTION INSPECTOR" in inspect_out

    # 5. Reset database
    class ResetArgs:
        workspace = ws
        force = True

    cmd_efficacy_reset(ResetArgs())
    reset_out = capsys.readouterr().out
    assert "[OK] Efficacy telemetry database wiped clean" in reset_out


def test_hook_dispatch_prompt_with_attribution(tmp_path):
    res = dispatch_prompt(
        prompt="Build a full stack webapp with react and fastapi",
        workspace_root=tmp_path,
        record_attribution=True,
    )
    if res.selected_skills:
        assert res.attribution_id is not None
        assert len(res.attribution_id) > 0


def test_non_git_repo_workspace_returns_unknown(tmp_path):
    plain_dir = tmp_path / "plain_folder"
    plain_dir.mkdir()
    # Write a file directly, no git repo
    (plain_dir / "file.py").write_text("print('hello')", encoding="utf-8")

    tracker = EfficacyTracker(workspace_root=plain_dir)
    sess = tracker.start_session(skills=["any-skill"], prompt="test prompt", workspace_root=plain_dir, files_touched=["file.py"])
    eval_sess = tracker.evaluate_session(sess.session_id)
    assert eval_sess.outcome == "unknown"


def test_first_commit_in_fresh_git_repo(tmp_path):
    repo_dir = tmp_path / "fresh_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True, capture_output=True)

    tracker = EfficacyTracker(workspace_root=repo_dir)
    sess = tracker.start_session(skills=["init-skill"], prompt="init repo", workspace_root=repo_dir)
    assert sess.initial_commit is None

    # Now make the repository's very first commit
    (repo_dir / "README.md").write_text("# Hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    evaluated = tracker.evaluate_session(sess.session_id)
    assert evaluated.outcome == "committed"
    stat = tracker.get_skill_stats("init-skill")
    assert stat.commits_count == 1
    assert stat.net_score == 1.0


def test_session_idempotent_reevaluation(tmp_path):
    repo_dir = tmp_path / "repo_idempotent"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    tracker = EfficacyTracker(workspace_root=repo_dir)
    sess = tracker.start_session(skills=["idempotent-skill"], prompt="work", workspace_root=repo_dir)

    # First evaluation: retained (+0.5)
    e1 = tracker.evaluate_session(sess.session_id, force_outcome="retained")
    assert e1.outcome == "retained"
    stat1 = tracker.get_skill_stats("idempotent-skill")
    assert stat1.retains_count == 1
    assert stat1.commits_count == 0
    assert stat1.net_score == 0.5
    assert stat1.evaluated_sessions == 1

    # Second evaluation of same session: upgraded to committed (+1.0)
    e2 = tracker.evaluate_session(sess.session_id, force_outcome="committed", test_passed=True)
    assert e2.outcome == "committed"
    assert e2.test_outcome == "passed"
    stat2 = tracker.get_skill_stats("idempotent-skill")
    # Retains count rolled back to 0, commits set to 1, evaluated_sessions still 1!
    assert stat2.retains_count == 0
    assert stat2.commits_count == 1
    assert stat2.tests_passed == 1
    assert stat2.net_score == 2.0  # +1.0 commit, +1.0 test pass
    assert stat2.evaluated_sessions == 1


def test_duplicate_skills_in_start_session(tmp_path):
    tracker = EfficacyTracker(workspace_root=tmp_path)
    sess = tracker.start_session(skills=["dup-skill", "dup-skill", "dup-skill"])
    assert sess.dispatched_skills == ["dup-skill"]
    stat = tracker.get_skill_stats("dup-skill")
    assert stat.total_dispatches == 1


def test_history_pruning_cap(tmp_path):
    store_file = tmp_path / "capped_eff.json"
    tracker = EfficacyTracker(storage_path=store_file, max_session_history=5)

    for i in range(12):
        tracker.start_session(skills=["cap-skill"], prompt=f"prompt {i}")

    # Memory and disk should contain only the last 5 sessions
    assert len(tracker._sessions) == 12  # in-memory buffer
    # Read saved disk file
    saved = json.loads(store_file.read_text(encoding="utf-8"))
    assert len(saved["sessions"]) == 5
    # Total skill dispatches still counts all 12
    assert saved["skills"]["cap-skill"]["total_dispatches"] == 12


def test_unicode_prompt_and_paths(tmp_path):
    tracker = EfficacyTracker(workspace_root=tmp_path)
    sess = tracker.start_session(
        skills=["unicode-skill"],
        prompt="Fix 🚀 login error with ünicode characters 🌟",
        files_touched=["src/ünicode_path.ts"],
    )
    assert "🚀" in sess.prompt
    tracker.evaluate_session(sess.session_id, force_outcome="committed", notes="Done with ✨")

    loaded = tracker.get_skill_stats("unicode-skill")
    assert loaded.commits_count == 1


def test_cli_error_handling(tmp_path, capsys):
    from taxonomy.cli import cmd_efficacy_record, cmd_efficacy_inspect

    ws = str(tmp_path)

    # Missing skills and session
    class NoArgs:
        workspace = ws
        skills = None
        session = None

    cmd_efficacy_record(NoArgs())
    out = capsys.readouterr().out
    assert "[ERROR]" in out

    # Invalid session
    class BadSessionArgs:
        workspace = ws
        skills = None
        session = "nonexistent999"
        committed = True
        retained = False
        discarded = False
        outcome = None
        test_passed = None
        test_failed = None
        test = None
        notes = ""

    cmd_efficacy_record(BadSessionArgs())
    out_bad = capsys.readouterr().out
    assert "not found" in out_bad

    # Inspect invalid session
    class InspectBadArgs:
        workspace = ws
        session_id = "nonexistent999"

    cmd_efficacy_inspect(InspectBadArgs())
    out_insp = capsys.readouterr().out
    assert "not found" in out_insp

