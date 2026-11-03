"""Tests for persistent usage tracking and stale skill detection."""

from taxonomy.tracker import UsageTracker


def test_usage_tracker_records_hits_and_identifies_stale(tmp_path):
    log_file = tmp_path / "usage.json"
    tracker = UsageTracker(log_path=log_file)

    # Initially all skills are stale/unpicked
    all_skills = ["skill-a", "skill-b", "skill-c"]
    stale = tracker.get_stale_skills(all_skills)
    assert stale == ["skill-a", "skill-b", "skill-c"]

    # Record hits on skill-a and skill-c
    tracker.record_hit("skill-a")
    tracker.record_hit("skill-a")
    tracker.record_hit("skill-c")

    assert tracker.get_hit_count("skill-a") == 2
    assert tracker.get_hit_count("skill-b") == 0
    assert tracker.get_hit_count("skill-c") == 1

    # Reload from disk to verify persistence
    tracker2 = UsageTracker(log_path=log_file)
    stale2 = tracker2.get_stale_skills(all_skills)
    assert stale2 == ["skill-b"]  # Only skill-b has 0 hits
