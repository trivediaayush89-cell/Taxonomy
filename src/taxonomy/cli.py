"""Command-line interface for taxonomy inspection, diagnostics, and testing."""

import argparse
from pathlib import Path
from typing import Optional
import yaml

from taxonomy.dag import CyclicDependencyError
from taxonomy.indexer import DEFAULT_SKILL_ROOTS, SkillIndexer
from taxonomy.resolver import SkillResolver
from taxonomy.schema import FRONTMATTER_REGEX

DEFAULT_SKILLS_PATH = Path("~/.gemini/config/skills").expanduser()


def get_default_indexer(path_arg: Optional[str] = None) -> SkillIndexer:
    roots = [Path(path_arg).expanduser()] if path_arg else None
    indexer = SkillIndexer(roots)
    indexer.scan()
    return indexer


def cmd_explain(args):
    """Explain why a prompt is gated or which skills it triggers."""
    indexer = get_default_indexer(args.skills_dir)
    resolver = SkillResolver(indexer, max_skills=args.max_skills)

    phase = getattr(args, "phase", None)
    result = resolver.resolve(args.prompt, force_route=args.force, phase=phase)

    print("\n=== TAXONOMY GATE EVALUATION ===")
    print(f"Prompt: \"{args.prompt}\"")
    print(f"Should Route: {result.gate.should_route}")
    print(f"Assigned Tier: Tier {result.gate.tier}")
    print(f"Gate Reason:  {result.gate.reason}")
    if phase:
        print(f"Active Phase: {phase}")
    print(f"Gate Latency: {result.gate.latency_ms:.3f} ms")

    print("\n=== RESOLVER SELECTION ===")
    print(f"Total Latency: {result.total_latency_ms:.3f} ms")
    if not result.selected_skills:
        print("Selected Skills: (None - prompt bypassed or below threshold)")
    else:
        from taxonomy.tracker import UsageTracker
        tracker = UsageTracker()
        print(f"Selected Skills ({len(result.selected_skills)} / max {resolver.max_skills}):")
        for s in result.selected_skills:
            tracker.record_hit(s.name)
            print(f"  * {s.name} [{s.category}] (priority: {s.priority})")
            print(f"    Tags: {', '.join(s.tags) if s.tags else '(none)'}")

    if result.category_scores:
        print("\n=== CATEGORY SCORES ===")
        for cat, score in sorted(result.category_scores.items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat:20} -> {score:.1f}")
    print()


def cmd_list(args):
    """List indexed skills grouped by category."""
    indexer = get_default_indexer(args.skills_dir)
    categories = indexer.get_categories()

    print(f"\nIndexed {len(indexer.all_skills)} skills across {len(categories)} categories:")
    for cat in categories:
        skills = indexer.get_by_category(cat)
        print(f"\nCategory: {cat} ({len(skills)} skills)")
        for s in skills:
            print(f"  - {s.name} (priority: {s.priority}, status: {s.status})")
            print(f"    {s.description}")


def cmd_doctor(args):
    """Deep diagnostic inspection of skills directory with optional auto-healing."""
    if args.skills_dir:
        p = Path(args.skills_dir).expanduser()
        if not p.is_dir():
            print(f"[ERROR] Directory does not exist: {p}")
            return
        roots = [p]
        excluded = set()
    else:
        base_indexer = SkillIndexer()
        roots = base_indexer.skills_roots
        excluded = base_indexer.excluded_skills

    print("\n=== TAXONOMY DOCTOR ===")
    print(f"Inspecting directories: {', '.join(str(r) for r in roots)}\n")

    issues_found = 0
    issues_fixed = 0

    for path in roots:
        if not path.is_dir():
            continue
        for entry in sorted(path.iterdir()):
            if not entry.is_dir() or entry.name in excluded:
                continue

            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                print(f"[WARN] Orphan directory without SKILL.md: {entry.name}")
                issues_found += 1
                continue

            text = skill_md.read_text(encoding="utf-8")
            match = FRONTMATTER_REGEX.match(text)

            if not match:
                print(f"[FAIL] {entry.name}: Missing YAML frontmatter block")
                issues_found += 1
                if args.fix:
                    new_fm = (
                        f"---\n"
                        f"name: {entry.name}\n"
                        f"description: Skill {entry.name} in {path.name}\n"
                        f"category: general\n"
                        f"tags: []\n"
                        f"status: active\n"
                        f"priority: 50\n"
                        f"---\n\n"
                    )
                    skill_md.write_text(new_fm + text, encoding="utf-8")
                    print(f"  [FIXED] Injected standard frontmatter block into {skill_md.name}")
                    issues_fixed += 1
                continue

            raw_yaml = match.group(1)
            try:
                data = yaml.safe_load(raw_yaml) or {}
                if not isinstance(data, dict):
                    raise ValueError("Frontmatter must be a YAML mapping")
            except Exception as e:
                print(f"[FAIL] {entry.name}: Corrupted YAML in frontmatter ({e})")
                issues_found += 1
                continue

            item_issues = []
            if not data.get("category"):
                item_issues.append("missing 'category'")
            if not data.get("tags"):
                item_issues.append("missing 'tags'")
            if not data.get("status"):
                item_issues.append("missing 'status'")
            if data.get("priority") is None:
                item_issues.append("missing 'priority'")

            if item_issues:
                issues_found += len(item_issues)
                print(f"[WARN] {entry.name}: {', '.join(item_issues)}")

                if args.fix:
                    changed = False
                    if not data.get("category"):
                        data["category"] = "general"
                        changed = True
                    if not data.get("tags"):
                        data["tags"] = []
                        changed = True
                    if not data.get("status"):
                        data["status"] = "active"
                        changed = True
                    if data.get("priority") is None:
                        data["priority"] = 50
                        changed = True

                    if changed:
                        new_yaml = yaml.dump(data, sort_keys=False, default_flow_style=False).strip()
                        rest_of_file = text[match.end():]
                        new_content = f"---\n{new_yaml}\n---\n" + rest_of_file
                        skill_md.write_text(new_content, encoding="utf-8")
                        print("  [FIXED] Updated frontmatter with sensible defaults")
                        issues_fixed += 1

    # Also verify dependency DAG across indexed skills
    indexer = SkillIndexer(roots, excluded_skills=excluded)
    indexer.scan()
    try:
        indexer.validate_dependency_dag()
    except CyclicDependencyError as e:
        print(f"[FAIL] Dependency cycle detected: {e}")
        issues_found += 1

    print("\n--- Diagnostic Summary ---")
    print(f"Issues detected: {issues_found}")
    if args.fix:
        print(f"Issues auto-healed: {issues_fixed}")
    elif issues_found > 0:
        print("Tip: Run 'taxonomy doctor --fix' to automatically heal missing fields.")


def cmd_check(args):
    """Check integrity of the skills directory and report drift or warnings."""
    indexer = get_default_indexer(args.skills_dir)
    skills = indexer.all_skills

    roots_str = ", ".join(str(r) for r in indexer.skills_roots) if indexer.skills_roots else "(none found)"
    print(f"Scanning skills at: {roots_str}")
    print(f"Found {len(skills)} valid skills.\n")

    warnings = 0
    for s in skills:
        if s.description == "Unclassified skill (no frontmatter)":
            print(f"  [WARN] Skill '{s.name}' lacks YAML frontmatter in SKILL.md")
            warnings += 1
        elif not s.tags:
            print(f"  [INFO] Skill '{s.name}' has no tags defined")

    try:
        indexer.validate_dependency_dag()
    except CyclicDependencyError as e:
        print(f"  [FAIL] {e}")
        warnings += 1

    if warnings == 0:
        print("All skills have valid frontmatter, metadata, and acyclic dependencies!")
    else:
        print(f"\nTotal warnings: {warnings}")


def cmd_stats(args):
    """Display SRE telemetry and latency benchmarks."""
    from taxonomy.telemetry import telemetry
    indexer = get_default_indexer(args.skills_dir)
    resolver = SkillResolver(indexer)

    # If no prior queries in session, run a quick baseline benchmark across sample prompts
    stats = telemetry.get_stats()
    if stats["total_queries"] == 0:
        print("Running quick baseline benchmark across sample queries...")
        sample_prompts = [
            "Hi there", "Thanks!", "Add a login page with JWT",
            "Explain binary search", "Optimize postgres queries",
            "Fix typo on line 4", "Audit smart contract",
            "Scaffold full stack app", "How do I build a habit"
        ]
        for p in sample_prompts:
            resolver.resolve(p)
        stats = telemetry.get_stats()

    print("\n=== SRE TELEMETRY & LATENCY METRICS ===")
    print(f"Total Evaluated Queries: {stats['total_queries']}")
    print(f"Routed:   {stats['routed']} ({stats['route_ratio']*100:.1f}%)")
    print(f"Bypassed: {stats['bypassed']} ({(1 - stats['route_ratio'])*100:.1f}%)")

    g = stats["gate_latency_ms"]
    print("\n--- Gate Latency (Sub-millisecond SLA) ---")
    print(f"  Average: {g['avg']:.4f} ms")
    print(f"  p50:     {g['p50']:.4f} ms")
    print(f"  p95:     {g['p95']:.4f} ms")
    print(f"  p99:     {g['p99']:.4f} ms")
    print(f"  Max:     {g['max']:.4f} ms")

    r = stats["resolve_latency_ms"]
    print("\n--- End-to-End Resolver Latency ---")
    print(f"  Average: {r['avg']:.4f} ms")
    print(f"  p50:     {r['p50']:.4f} ms")
    print(f"  p95:     {r['p95']:.4f} ms")
    print(f"  p99:     {r['p99']:.4f} ms")
    print(f"  Max:     {r['max']:.4f} ms")
    print()


def cmd_inspect(args):
    """Progressive disclosure inspection of a specific skill (Level 1, 2, or 3)."""
    indexer = get_default_indexer(args.skills_dir)
    skill = indexer.get_skill(args.skill_name)
    if not skill:
        print(f"[ERROR] Skill '{args.skill_name}' not found in indexed catalog.")
        return

    level = args.level
    print(f"\n=== PROGRESSIVE DISCLOSURE (Level {level}) ===")
    if level == 1:
        # Pointer Level: 0 token cost
        pointer = skill.to_pointer()
        print(f"Name:     {pointer['name']}")
        print(f"Category: {pointer['category']}")
        print(f"Path:     {pointer['path']}")
    elif level == 2:
        # Summary Level: ~50 tokens
        summary = skill.to_summary()
        print(f"Skill:       {summary['name']} [{summary['category']}]")
        print(f"Priority:    {summary['priority']} (status: {summary['status']})")
        print(f"Tags:        {', '.join(summary['tags']) if summary['tags'] else '(none)'}")
        print(f"Description: {summary['description']}")
        if skill.conflicts_with:
            print(f"Conflicts:   {', '.join(skill.conflicts_with)}")
        if skill.requires:
            print(f"Requires:    {', '.join(skill.requires)}")
    elif level == 3:
        # Full Level: On-demand markdown body sliced cleanly by line count
        print(f"--- Full Instructions for {skill.name} ---")
        full_text = skill.get_full_instructions()
        if not full_text:
            print("(No body content)")
        else:
            lines = full_text.splitlines()
            shown = "\n".join(lines[:args.max_lines])
            print(shown)
            if len(lines) > args.max_lines:
                print(f"\n... ({len(lines) - args.max_lines} more lines omitted, use --max-lines to view more)")
    print()


def cmd_overlap(args):
    """Detect overlapping/redundant skills and case collisions."""
    from taxonomy.overlap import OverlapDetector
    indexer = get_default_indexer(args.skills_dir)
    detector = OverlapDetector(indexer, threshold=args.threshold)

    print("\n=== SKILL OVERLAP & REDUNDANCY SCANNER ===")
    collisions = detector.find_case_collisions()
    if collisions:
        print("\n[ALERT] Case Collisions Detected (will crash on case-insensitive filesystems):")
        for a, b in collisions:
            print(f"  * '{a}' vs '{b}'")
    else:
        print("Zero case-collision hazards detected.")

    overlaps = detector.find_overlaps()
    if not overlaps:
        print(f"\nNo skills exceeded the {args.threshold*100:.0f}% overlap threshold! Your catalog is well-partitioned.")
    else:
        print(f"\nFound {len(overlaps)} skill pairs with potential overlap (threshold >= {args.threshold*100:.0f}%):")
        for o in overlaps:
            print(f"\n* {o.skill_a} <-> {o.skill_b} (Similarity: {o.similarity_score*100:.0f}%)")
            print(f"  Shared Tags: {', '.join(o.shared_tags) if o.shared_tags else '(none)'}")
            if o.shared_keywords:
                print(f"  Shared Keywords: {', '.join(o.shared_keywords)}")
            print(f"  Recommendation: {o.recommendation}")
    print()


def cmd_unused(args):
    """Identify skills that have never been invoked or have zero hits."""
    from taxonomy.tracker import UsageTracker
    indexer = get_default_indexer(args.skills_dir)
    tracker = UsageTracker()

    all_names = [s.name for s in indexer.all_skills]
    stale = tracker.get_stale_skills(all_names)

    print("\n=== SKILL USAGE & STALE TOOL AUDIT ===")
    total_q = tracker.get_stats_summary().get("total_queries", 0)
    print(f"Total Logged Queries: {total_q}")
    print(f"Total Indexed Skills: {len(all_names)}")
    print(f"Unpicked / Stale Skills: {len(stale)} ({len(stale)/max(1, len(all_names))*100:.1f}%)")

    if stale:
        print("\nThe following skills have zero logged invocations:")
        for name in stale:
            s = indexer.get_skill(name)
            cat = s.category if s else "unknown"
            print(f"  * {name} [{cat}]")
        print("\nTip: Consider improving their tags/descriptions or deleting them if obsolete.")
    else:
        print("\nAll indexed skills have been actively invoked at least once!")
    print()


def cmd_ui(args):
    """Launch the interactive Skill Taxonomy & Gated Dispatcher web workbench."""
    import http.server
    import socketserver
    import webbrowser

    web_dir = Path(__file__).parent / "web"
    index_html = web_dir / "index.html"
    if not index_html.exists():
        print(f"[ERROR] UI assets not found at: {web_dir}")
        return

    port = args.port
    handler = lambda *h_args, **h_kwargs: http.server.SimpleHTTPRequestHandler(
        *h_args, directory=str(web_dir), **h_kwargs
    )

    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://127.0.0.1:{port}"
            print("\n=======================================================")
            print("  Skill Taxonomy & Gated Dispatcher Web Workbench")
            print(f"  Serving interactive UI at: {url}")
            print("  Press Ctrl+C to stop the local UI server")
            print("=======================================================\n")
            if not args.no_open:
                webbrowser.open(url)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down UI server.")
    except OSError as e:
        print(f"[ERROR] Could not start server on port {port}: {e}")


def main():
    parser = argparse.ArgumentParser(prog="taxonomy", description="Skill Taxonomy & Gated Dispatcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # explain
    p_explain = subparsers.add_parser("explain", help="Explain gate triage and skill resolution for a prompt")
    p_explain.add_argument("prompt", type=str, help="User prompt to evaluate")
    p_explain.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_explain.add_argument("--max-skills", type=int, default=3, help="Max skills to return")
    p_explain.add_argument("--phase", type=str, default=None, help="Optional lifecycle phase filter")
    p_explain.add_argument("--force", action="store_true", help="Force resolution even if gate bypassed")
    p_explain.set_defaults(func=cmd_explain)

    # list
    p_list = subparsers.add_parser("list", help="List all skills by category")
    p_list.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_list.set_defaults(func=cmd_list)

    # check
    p_check = subparsers.add_parser("check", help="Verify frontmatter integrity across skills")
    p_check.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_check.set_defaults(func=cmd_check)

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Deep diagnostic inspection and self-healing")
    p_doctor.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_doctor.add_argument("--fix", action="store_true", help="Automatically repair missing frontmatter fields")
    p_doctor.set_defaults(func=cmd_doctor)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show SRE latency benchmarks and routing metrics")
    p_stats.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_stats.set_defaults(func=cmd_stats)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Progressive disclosure inspection (Level 1, 2, or 3)")
    p_inspect.add_argument("skill_name", type=str, help="Name of the skill to inspect")
    p_inspect.add_argument("--level", type=int, choices=[1, 2, 3], default=2, help="Disclosure level: 1 (Pointer), 2 (Summary), 3 (Full body)")
    p_inspect.add_argument("--max-lines", type=int, default=30, help="Max lines for level 3 output")
    p_inspect.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_inspect.set_defaults(func=cmd_inspect)

    # overlap
    p_overlap = subparsers.add_parser("overlap", help="Find redundant or overlapping skills")
    p_overlap.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_overlap.add_argument("--threshold", type=float, default=0.45, help="Overlap similarity threshold (default: 0.45)")
    p_overlap.set_defaults(func=cmd_overlap)

    # unused
    p_unused = subparsers.add_parser("unused", help="Audit unpicked or stale skills")
    p_unused.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_unused.set_defaults(func=cmd_unused)

    # ui
    p_ui = subparsers.add_parser("ui", help="Launch interactive web workbench dashboard")
    p_ui.add_argument("--port", type=int, default=8765, help="Port to serve UI on (default: 8765)")
    p_ui.add_argument("--no-open", action="store_true", help="Do not automatically open browser")
    p_ui.set_defaults(func=cmd_ui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
