"""Command-line interface for taxonomy inspection, diagnostics, and testing."""

import argparse
import http.server
import json
from pathlib import Path
import socketserver
from typing import Optional
import urllib.parse
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


def print_taste_hints(result, resolver, prefer: Optional[str] = None) -> None:
    """Print unobtrusive taste configuration suggestions when competing alternatives exist."""
    if not result.selected_skills:
        return
    active_profile = resolver.taste_profile
    has_explicit_pref = bool(
        active_profile
        and (
            active_profile.preferred_skills.get("frontend.visual")
            or active_profile.preferred_skills.get("ui.visual")
            or active_profile.preferred_skills.get("ui")
        )
    )
    if has_explicit_pref:
        return

    visual_selected = [
        s for s in result.selected_skills
        if s.name in ("design-taste-frontend", "impeccable", "unslop", "frontend-design")
    ]
    if visual_selected:
        selected_name = visual_selected[0].name
        if prefer and prefer.strip() == selected_name:
            print(f"\n[Taste Hint] Ad-hoc CLI override active: '{selected_name}'.")
            print(f"To persist '{selected_name}' as your default visual authority, run:")
            print(f"  taxonomy taste set frontend.visual {selected_name}")
        else:
            alternatives = [a for a in ("impeccable", "design-taste-frontend", "unslop") if a != selected_name]
            alt_suggestion = alternatives[0] if alternatives else "impeccable"
            print(f"\n[Taste Hint] Resolved visual authority: '{selected_name}'.")
            print(f"To prefer '{alt_suggestion}' for UI tasks instead, run:")
            print(f"  taxonomy taste set frontend.visual {alt_suggestion}")


def cmd_resolve(args):
    """Resolve optimal skill pod for a prompt."""
    indexer = get_default_indexer(args.skills_dir)
    resolver = SkillResolver(indexer, max_skills=args.max_skills)

    phase = getattr(args, "phase", None)
    prefer = getattr(args, "prefer", None)
    result = resolver.resolve(args.prompt, force_route=args.force, phase=phase, prefer=prefer)

    print("\n=== RESOLVER SELECTION ===")
    print(f"Prompt: \"{args.prompt}\"")
    print(f"Total Latency: {result.total_latency_ms:.3f} ms")
    if result.taste_profile_source:
        print(f"Taste Applied: Yes (source: {result.taste_profile_source})")

    if not result.selected_skills:
        print("Selected Skills: (None - prompt bypassed or below threshold)")
    else:
        from taxonomy.tracker import UsageTracker
        tracker = UsageTracker()
        print(f"Selected Skills ({len(result.selected_skills)} / max {resolver.max_skills}):")
        for s in result.selected_skills:
            tracker.record_hit(s.name)
            score_info = ""
            if s.name in result.skill_scores:
                sc = result.skill_scores[s.name]
                score_info = f" (score: {sc.final_score:.1f}, bias: {sc.taste_bias:+.1f})"
            print(f"  * {s.name} [{s.category}] (priority: {s.priority}){score_info}")
            print(f"    Tags: {', '.join(s.tags) if s.tags else '(none)'}")

    print_taste_hints(result, resolver, prefer=prefer)
    print()


def cmd_explain(args):
    """Explain why a prompt is gated or which skills it triggers."""
    indexer = get_default_indexer(args.skills_dir)
    resolver = SkillResolver(indexer, max_skills=args.max_skills)

    phase = getattr(args, "phase", None)
    prefer = getattr(args, "prefer", None)
    result = resolver.resolve(args.prompt, force_route=args.force, phase=phase, prefer=prefer)

    print("\n=== TAXONOMY GATE EVALUATION ===")
    print(f"Prompt: \"{args.prompt}\"")
    print(f"Should Route: {result.gate.should_route}")
    print(f"Assigned Tier: Tier {result.gate.tier}")
    print(f"Gate Reason:  {result.gate.reason}")
    if phase:
        print(f"Active Phase: {phase}")
    print(f"Gate Latency: {result.gate.latency_ms:.3f} ms")

    # Display active taste profile information
    active_profile = resolver.taste_profile
    if active_profile and not active_profile.is_empty():
        src = active_profile.source or "user"
        path_str = str(active_profile.path) if active_profile.path else "in-memory"
        print(f"Active Taste Profile: {path_str} ({src.capitalize()} Level)")

    # Display auto-detected project fingerprint
    try:
        from taxonomy.fingerprint import detect_project_fingerprint
        fp = detect_project_fingerprint()
        if fp.detected_ecosystems:
            manifest_str = f" ({', '.join(fp.manifest_files)})" if fp.manifest_files else ""
            print(f"Detected Stack:       {fp.summary_label()}{manifest_str}")
    except Exception:
        pass

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
            score_info = ""
            if s.name in result.skill_scores:
                sc = result.skill_scores[s.name]
                score_info = f" (score: {sc.final_score:.1f}, bias: {sc.taste_bias:+.1f})"
            print(f"  * {s.name} [{s.category}] (priority: {s.priority}){score_info}")
            print(f"    Tags: {', '.join(s.tags) if s.tags else '(none)'}")

    if result.skill_scores:
        print("\n=== CANDIDATE SCORING & TASTE BIAS ===")
        selected_set = {s.name for s in result.selected_skills}
        direct_pref_set = {prefer.strip()} if isinstance(prefer, str) and prefer.strip() else set()
        for name, sc in sorted(result.skill_scores.items(), key=lambda x: x[1].final_score, reverse=True):
            cand_meta = indexer.get_skill(name)
            if name in selected_set:
                status = "[SELECTED]"
            else:
                conflict_winner = None
                for sel in result.selected_skills:
                    if name in sel.conflicts_with or (cand_meta and sel.name in cand_meta.conflicts_with):
                        conflict_winner = sel.name
                        break
                if conflict_winner:
                    status = f"[EXCLUDED by Conflict A with '{conflict_winner}']"
                else:
                    status = "[EXCLUDED]"

            bias_reason = ""
            if cand_meta and active_profile:
                reason = active_profile.get_bias_reason(cand_meta, direct_prefer=direct_pref_set)
                if reason:
                    bias_reason = f" ({reason})"
            elif name in direct_pref_set:
                bias_reason = " (cli: --prefer)"

            print(f"Candidate: '{name}' {status}")
            print(f"  Base Score     : {sc.base_score:.2f}")
            print(f"  Taste Bias     : {sc.taste_bias:+.2f}{bias_reason}")
            print(f"  Final Score    : {sc.final_score:.2f}")

    if result.category_scores:
        print("\n=== CATEGORY SCORES ===")
        for cat, score in sorted(result.category_scores.items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat:20} -> {score:.1f}")

    print_taste_hints(result, resolver, prefer=prefer)
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


class WorkbenchRequestHandler(http.server.SimpleHTTPRequestHandler):
    """API-enabled HTTP handler for the Taxonomy Web Workbench."""

    def __init__(self, *args, directory=None, skills_dir=None, **kwargs):
        self.skills_dir = skills_dir
        default_dir = Path(__file__).parent / "web"
        target_dir = str(directory) if directory is not None else str(default_dir)
        super().__init__(*args, directory=target_dir, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/taste":
            self._handle_get_taste()
        elif parsed.path == "/api/presets":
            self._handle_get_presets()
        elif parsed.path == "/api/taste/export":
            self._handle_export_taste(parsed.query)
        elif parsed.path == "/api/fingerprint":
            self._handle_get_fingerprint()
        elif parsed.path == "/api/skills":
            self._handle_get_skills()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/taste":
            self._handle_save_taste()
        elif parsed.path == "/api/presets/apply":
            self._handle_apply_preset()
        elif parsed.path == "/api/taste/import":
            self._handle_import_taste()
        elif parsed.path == "/api/fingerprint/apply":
            self._handle_apply_fingerprint()
        elif parsed.path == "/api/resolve":
            self._handle_resolve()
        else:
            self.send_error(404, "Endpoint not found")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        raw = self.rfile.read(content_len).decode("utf-8")
        return json.loads(raw)

    def _handle_get_taste(self):
        try:
            from taxonomy.taste import (
                find_workspace_taste_path,
                get_user_taste_path,
                load_taste_file,
                load_taste_profile,
            )
            from taxonomy.fingerprint import detect_project_fingerprint

            active = load_taste_profile()
            ws_path = find_workspace_taste_path()
            ws_profile = load_taste_file(ws_path) if ws_path else None
            u_path = get_user_taste_path()
            u_profile = load_taste_file(u_path)
            fp = detect_project_fingerprint()

            self._send_json({
                "active": active.to_dict(),
                "workspace": ws_profile.to_dict() if ws_profile else None,
                "workspace_path": str(ws_path) if ws_path else None,
                "user": u_profile.to_dict() if u_profile else None,
                "user_path": str(u_path),
                "fingerprint": fp.to_dict(),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_save_taste(self):
        try:
            from taxonomy.taste import (
                IMMUNE_QUALITY_SENTRIES,
                TasteProfile,
                get_user_taste_path,
                get_workspace_taste_path,
                save_taste_profile,
                validate_taste_schema,
            )

            data = self._read_json()
            scope = data.get("scope", "workspace")

            profile_data = {
                "version": int(data.get("version", 1)),
                "preferred_skills": data.get("preferred_skills", {}),
                "avoid_skills": data.get("avoid_skills", []),
                "weights": data.get("weights", {}),
            }

            is_valid, errors = validate_taste_schema(profile_data)
            if not is_valid:
                self._send_json({"error": "Validation failed", "details": errors}, status=400)
                return

            sanitized_avoid = [
                sk for sk in profile_data["avoid_skills"]
                if sk not in IMMUNE_QUALITY_SENTRIES
            ]
            sanitized_weights = {
                k: (0.0 if k in IMMUNE_QUALITY_SENTRIES and float(v) < 0.0 else float(v))
                for k, v in profile_data["weights"].items()
            }

            profile = TasteProfile(
                version=profile_data["version"],
                preferred_skills=profile_data["preferred_skills"],
                avoid_skills=sanitized_avoid,
                weights=sanitized_weights,
            )

            if scope == "user":
                target = get_user_taste_path()
            else:
                target = get_workspace_taste_path()

            saved_path = save_taste_profile(profile, target)
            self._send_json({
                "status": "ok",
                "scope": scope,
                "saved_path": str(saved_path),
                "profile": profile.to_dict(),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_get_fingerprint(self):
        try:
            from taxonomy.fingerprint import detect_project_fingerprint
            fp = detect_project_fingerprint()
            self._send_json(fp.to_dict())
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_apply_fingerprint(self):
        try:
            from taxonomy.fingerprint import detect_project_fingerprint
            from taxonomy.taste import (
                TasteProfile,
                get_workspace_taste_path,
                load_taste_file,
                save_taste_profile,
            )

            fp = detect_project_fingerprint()
            ws_path = get_workspace_taste_path()
            existing = load_taste_file(ws_path) or TasteProfile()

            applied_count = 0
            for cat, sk in fp.suggested_preferences.items():
                if cat not in existing.preferred_skills:
                    existing.preferred_skills[cat] = sk
                    applied_count += 1
            for sk, wt in fp.suggested_weights.items():
                if sk not in existing.weights and sk not in existing.avoid_skills:
                    existing.weights[sk] = wt
                    applied_count += 1

            saved_path = save_taste_profile(existing, ws_path)
            self._send_json({
                "status": "ok",
                "applied_count": applied_count,
                "saved_path": str(saved_path),
                "profile": existing.to_dict(),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_get_presets(self):
        try:
            from taxonomy.presets import list_presets
            presets = list_presets()
            self._send_json({"presets": presets, "total": len(presets)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_apply_preset(self):
        try:
            from taxonomy.taste import (
                get_user_taste_path,
                get_workspace_taste_path,
                import_taste_profile,
            )
            data = self._read_json()
            preset_name = data.get("name")
            scope = data.get("scope", "workspace")
            if not preset_name:
                self._send_json({"error": "Missing required field 'name'"}, status=400)
                return

            target = get_user_taste_path() if scope == "user" else get_workspace_taste_path()
            profile, saved_path = import_taste_profile(preset_name, target_path=target, force=True)
            self._send_json({
                "status": "ok",
                "preset": preset_name,
                "scope": scope,
                "saved_path": str(saved_path),
                "profile": profile.to_dict(),
            })
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_export_taste(self, query_str: str):
        try:
            from taxonomy.taste import (
                TasteProfile,
                export_taste_profile,
                find_workspace_taste_path,
                get_user_taste_path,
                load_taste_file,
                load_taste_profile,
            )
            qs = urllib.parse.parse_qs(query_str or "")
            scope = qs.get("scope", ["active"])[0]
            fmt = qs.get("format", ["json"])[0]

            if scope == "workspace":
                ws_path = find_workspace_taste_path()
                profile = load_taste_file(ws_path) if ws_path else None
                if not profile:
                    profile = TasteProfile(source="workspace")
            elif scope == "user":
                u_path = get_user_taste_path()
                profile = load_taste_file(u_path)
                if not profile:
                    profile = TasteProfile(source="user")
            else:
                profile = load_taste_profile()

            as_yaml = fmt.lower() in ("yaml", "yml")
            content = export_taste_profile(profile, as_yaml=as_yaml)
            self._send_json({
                "scope": scope,
                "format": "yaml" if as_yaml else "json",
                "content": content,
                "profile": profile.to_dict(),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_import_taste(self):
        try:
            from taxonomy.taste import (
                get_user_taste_path,
                get_workspace_taste_path,
                import_taste_profile,
            )
            data = self._read_json()
            source = data.get("content") or data.get("source") or data.get("preset")
            scope = data.get("scope", "workspace")
            force = data.get("force", True)

            if not source:
                self._send_json({"error": "Missing required field 'content' or 'source'"}, status=400)
                return

            target = get_user_taste_path() if scope == "user" else get_workspace_taste_path()
            profile, saved_path = import_taste_profile(source, target_path=target, force=force)
            self._send_json({
                "status": "ok",
                "scope": scope,
                "saved_path": str(saved_path),
                "profile": profile.to_dict(),
            })
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_get_skills(self):
        try:
            indexer = get_default_indexer(self.skills_dir)
            skills = {s.name: s.to_dict() for s in indexer.all_skills}
            self._send_json({"skills": skills, "total": len(skills)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_resolve(self):
        try:
            data = self._read_json()
            prompt = data.get("prompt", "")
            phase = data.get("phase", None)
            prefer = data.get("prefer", None)
            max_skills = data.get("max_skills", None)

            indexer = get_default_indexer(self.skills_dir)
            resolver = SkillResolver(indexer, max_skills=max_skills)
            res = resolver.resolve(prompt, force_route=True, phase=phase, prefer=prefer)

            self._send_json({
                "prompt": prompt,
                "gate": {
                    "should_route": res.gate.should_route,
                    "tier": res.gate.tier,
                    "reason": res.gate.reason,
                    "latency_ms": res.gate.latency_ms,
                },
                "total_latency_ms": res.total_latency_ms,
                "taste_profile_source": res.taste_profile_source,
                "selected_skills": [s.name for s in res.selected_skills],
                "skill_scores": {
                    k: {
                        "base_score": v.base_score,
                        "taste_bias": v.taste_bias,
                        "final_score": v.final_score,
                    }
                    for k, v in res.skill_scores.items()
                },
                "category_scores": res.category_scores,
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)


def cmd_ui(args):
    """Launch the interactive Skill Taxonomy & Gated Dispatcher web workbench."""
    import webbrowser

    web_dir = Path(__file__).parent / "web"
    index_html = web_dir / "index.html"
    if not index_html.exists():
        print(f"[ERROR] UI assets not found at: {web_dir}")
        return

    port = args.port
    skills_dir = getattr(args, "skills_dir", None)
    handler = lambda *h_args, **h_kwargs: WorkbenchRequestHandler(
        *h_args, directory=str(web_dir), skills_dir=skills_dir, **h_kwargs
    )

    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://127.0.0.1:{port}"
            print("\n=======================================================")
            print("  Skill Taxonomy & Gated Dispatcher Web Workbench")
            print(f"  Serving interactive UI at: {url}")
            print("  API Endpoints active: /api/taste, /api/fingerprint, /api/skills, /api/resolve")
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


def cmd_taste_list(args):
    """Display the active hierarchical taste profile."""
    from taxonomy.taste import (
        find_workspace_taste_path,
        get_user_taste_path,
        load_taste_file,
        load_taste_profile,
    )

    user_path = get_user_taste_path()
    ws_path = find_workspace_taste_path()
    ws_profile = load_taste_file(ws_path, source_label="workspace") if ws_path else None
    user_profile = load_taste_file(user_path, source_label="user")
    effective = load_taste_profile()

    print("\n=== ACTIVE TASTE PROFILES ===")
    print(f"Workspace Profile: {ws_path if ws_path else '(none found)'}")
    if ws_profile and not ws_profile.is_empty():
        print("  Workspace Preferences:")
        if ws_profile.preferred_skills:
            for cat, sk in sorted(ws_profile.preferred_skills.items()):
                print(f"    preferred: {cat} -> {sk}")
        if ws_profile.avoid_skills:
            print(f"    avoid: {', '.join(ws_profile.avoid_skills)}")
        if ws_profile.weights:
            for sk, wt in sorted(ws_profile.weights.items()):
                print(f"    weight: {sk} -> {wt:+.1f}")

    print(f"\nUser Local Profile: {user_path if user_path.exists() else '(empty/not created)'}")
    if user_profile and not user_profile.is_empty():
        print("  User Preferences:")
        if user_profile.preferred_skills:
            for cat, sk in sorted(user_profile.preferred_skills.items()):
                print(f"    preferred: {cat} -> {sk}")
        if user_profile.avoid_skills:
            print(f"    avoid: {', '.join(user_profile.avoid_skills)}")
        if user_profile.weights:
            for sk, wt in sorted(user_profile.weights.items()):
                print(f"    weight: {sk} -> {wt:+.1f}")

    print(f"\nEffective Hierarchical Taste (Source: {effective.source or 'default unweighted'}):")
    if effective.is_empty():
        print("  (Zero active overrides; standard pure BM25 triad routing active)")
    else:
        if effective.preferred_skills:
            print("  Preferred Category Skills:")
            for cat, sk in sorted(effective.preferred_skills.items()):
                print(f"    * {cat:20} -> {sk} (+3.0 bias)")
        if effective.avoid_skills:
            print("  Avoided Skills:")
            for sk in sorted(effective.avoid_skills):
                print(f"    * {sk:20} (-3.0 bias)")
        if effective.weights:
            print("  Custom Skill Weights:")
            for sk, wt in sorted(effective.weights.items()):
                print(f"    * {sk:20} -> {wt:+.1f} bias")
    print()


def cmd_taste_set(args):
    """Set a preferred skill or custom weight."""
    from taxonomy.taste import (
        IMMUNE_QUALITY_SENTRIES,
        TasteProfile,
        get_user_taste_path,
        get_workspace_taste_path,
        load_taste_file,
        save_taste_profile,
    )

    target_path = get_workspace_taste_path() if getattr(args, "workspace", False) else get_user_taste_path()
    profile = load_taste_file(target_path) or TasteProfile()

    key = args.key.strip()
    val = args.val.strip()

    try:
        weight = float(val)
        weight = max(-3.0, min(3.0, round(weight, 2)))
        if key in IMMUNE_QUALITY_SENTRIES and weight < 0.0:
            print(
                f"\n[Judicial Guardrail Notice] '{key}' is a protected Quality Sentry "
                f"and is immune to negative taste bias (clamped to 0.0)."
            )
            weight = 0.0
        profile.weights[key] = weight
        if weight > -3.0 and key in profile.avoid_skills:
            profile.avoid_skills.remove(key)
        save_taste_profile(profile, target_path)
        print(f"\n[Taste Updated] Set weight for '{key}' to {weight:+.1f} in {target_path}")
    except ValueError:
        profile.preferred_skills[key] = val
        if val in profile.avoid_skills:
            profile.avoid_skills.remove(val)
        if val in profile.weights and profile.weights[val] < 0.0:
            del profile.weights[val]
        save_taste_profile(profile, target_path)
        print(f"\n[Taste Updated] Preferred '{val}' for '{key}' in {target_path}")
    print()


def cmd_taste_avoid(args):
    """Add a skill to the avoidance list."""
    from taxonomy.taste import (
        IMMUNE_QUALITY_SENTRIES,
        TasteProfile,
        get_user_taste_path,
        get_workspace_taste_path,
        load_taste_file,
        save_taste_profile,
    )

    target_path = get_workspace_taste_path() if getattr(args, "workspace", False) else get_user_taste_path()
    profile = load_taste_file(target_path) or TasteProfile()

    skill = args.skill.strip()
    if skill in IMMUNE_QUALITY_SENTRIES:
        print(
            f"\n[Judicial Guardrail Notice] '{skill}' is a protected Quality Sentry "
            f"and is immune to negative taste bias or avoidance.\n"
        )
        return

    if skill in profile.weights:
        del profile.weights[skill]
    for cat, pref in list(profile.preferred_skills.items()):
        if pref == skill:
            del profile.preferred_skills[cat]

    if skill not in profile.avoid_skills:
        profile.avoid_skills.append(skill)
        profile.avoid_skills.sort()
        save_taste_profile(profile, target_path)
        print(f"\n[Taste Updated] Added '{skill}' to avoidance list (-3.0 bias) in {target_path}")
    else:
        save_taste_profile(profile, target_path)
        print(f"\n[Taste Notice] '{skill}' is already in avoidance list in {target_path}")
    print()


def cmd_taste_reset(args):
    """Reset taste preferences."""
    from taxonomy.taste import (
        TasteProfile,
        get_user_taste_path,
        get_workspace_taste_path,
        save_taste_profile,
    )

    paths_to_reset = []
    if getattr(args, "all", False):
        paths_to_reset.append(get_workspace_taste_path())
        paths_to_reset.append(get_user_taste_path())
    elif getattr(args, "workspace", False):
        paths_to_reset.append(get_workspace_taste_path())
    else:
        paths_to_reset.append(get_user_taste_path())

    for p in paths_to_reset:
        if p.exists():
            save_taste_profile(TasteProfile(), p)
            print(f"\n[Taste Reset] Cleared taste preferences in {p}")
        else:
            print(f"\n[Taste Notice] No file existed at {p} to reset")
    print()


def cmd_taste_presets(args):
    """List curated community taste presets."""
    from taxonomy.presets import list_presets
    presets = list_presets()

    print("\n=== CURATED COMMUNITY TASTE PRESETS ===")
    print("Pre-configured, domain-specialized taste profiles ready to apply.\n")
    for p in presets:
        print(f"  * {p['name']} - {p.get('title', '')}")
        print(f"    Description: {p.get('description', '')}")
        if p.get("preferred_skills"):
            prefs = [f"{k} -> {v}" for k, v in p["preferred_skills"].items()]
            print(f"    Preferred:   {', '.join(prefs)}")
        if p.get("avoid_skills"):
            print(f"    Avoid:       {', '.join(p['avoid_skills'])}")
        if p.get("weights"):
            wts = [f"{k} ({v:+.1f})" for k, v in p["weights"].items()]
            print(f"    Weights:     {', '.join(wts)}")
        print()
    print("Tip: Run 'taxonomy taste import <preset-name> [--workspace|--user]' to apply one.\n")


def cmd_taste_export(args):
    """Export taste profile to JSON or YAML."""
    from taxonomy.taste import (
        export_taste_profile,
        find_workspace_taste_path,
        get_user_taste_path,
        load_taste_file,
        load_taste_profile,
        TasteProfile,
    )

    if getattr(args, "workspace", False):
        ws_path = find_workspace_taste_path()
        profile = load_taste_file(ws_path) if ws_path else None
        if not profile:
            profile = TasteProfile(source="workspace")
    elif getattr(args, "user", False):
        u_path = get_user_taste_path()
        profile = load_taste_file(u_path)
        if not profile:
            profile = TasteProfile(source="user")
    else:
        profile = load_taste_profile()

    as_yaml = getattr(args, "yaml", False)
    target_file = getattr(args, "file", None)
    if target_file and not as_yaml and target_file.lower().endswith((".yaml", ".yml")):
        as_yaml = True

    content = export_taste_profile(profile, target_path=target_file, as_yaml=as_yaml)
    if target_file:
        print(f"\n[Exported] Saved taste profile to {target_file} ({'YAML' if as_yaml else 'JSON'})\n")
    else:
        print(content)


def cmd_taste_import(args):
    """Import a taste profile from a community preset or file."""
    from taxonomy.taste import (
        get_user_taste_path,
        get_workspace_taste_path,
        import_taste_profile,
    )

    target_path = get_user_taste_path() if getattr(args, "user", False) else get_workspace_taste_path()
    source = args.source.strip()
    force = getattr(args, "force", False)

    try:
        profile, saved_path = import_taste_profile(source, target_path=target_path, force=force)
        scope_str = "user ~/.gemini/taxonomy/taste.json" if getattr(args, "user", False) else "workspace .taxonomy/taste.json"
        print(f"\n[Taste Imported] Successfully applied '{source}' to {scope_str} ({saved_path})")
        if profile.preferred_skills:
            print("  Preferred skills:")
            for k, v in profile.preferred_skills.items():
                print(f"    * {k} -> {v}")
        if profile.avoid_skills:
            print(f"  Avoid skills: {', '.join(profile.avoid_skills)}")
        if profile.weights:
            print("  Weights:")
            for k, v in profile.weights.items():
                print(f"    * {k} -> {v:+.1f}")
        print()
    except FileExistsError as e:
        print(f"\n[Error] {e}")
        print("Use '--force' to overwrite the existing profile.\n")
    except Exception as e:
        print(f"\n[Error] Failed to import taste profile: {e}\n")


def cmd_fingerprint(args):
    """Detect and display project ecosystems, frameworks, and recommended skill alignments."""
    import json
    from taxonomy.fingerprint import detect_project_fingerprint, find_project_root
    from taxonomy.taste import TasteProfile, get_workspace_taste_path, load_taste_file, save_taste_profile

    root = find_project_root(args.path)
    fp = detect_project_fingerprint(root)

    if getattr(args, "json", False):
        print(json.dumps(fp.to_dict(), indent=2))
        return

    print("\n=== PROJECT STACK FINGERPRINT ===")
    print(f"Workspace Root:   {fp.root}")
    print(f"Primary Language: {fp.primary_language.capitalize() if fp.primary_language else '(unspecified)'}")
    print(f"Detected Stack:   {fp.summary_label()}")
    print(f"Manifest Files:   {', '.join(fp.manifest_files) if fp.manifest_files else '(none detected)'}")
    if fp.is_pure_contract:
        domain_type = "Smart Contract / Web3 Protocol"
    elif fp.is_pure_backend:
        domain_type = "Backend / Systems Service"
    elif "nextjs" in fp.detected_ecosystems or "react" in fp.detected_ecosystems:
        domain_type = "Full-Stack Web Application"
    else:
        domain_type = "General Software Project"
    print(f"Domain Type:      {domain_type}")
    print(f"Scan Latency:     {fp.scan_latency_ms:.3f} ms")

    if fp.recommended_skills:
        print("\n--- Recommended Skill Pod Alignments ---")
        for sk in fp.recommended_skills:
            wt = fp.suggested_weights.get(sk, 1.5)
            pref_cat = [c for c, s in fp.suggested_preferences.items() if s == sk]
            cat_str = f" [{pref_cat[0]}]" if pref_cat else ""
            print(f"  * {sk}{cat_str} (suggested bias: {wt:+.1f})")

    if getattr(args, "apply", False):
        ws_path = get_workspace_taste_path(root)
        existing = load_taste_file(ws_path) or TasteProfile()
        applied_cnt = 0
        for cat, sk in fp.suggested_preferences.items():
            if cat not in existing.preferred_skills:
                existing.preferred_skills[cat] = sk
                applied_cnt += 1
        for sk, wt in fp.suggested_weights.items():
            if sk not in existing.weights and sk not in existing.avoid_skills:
                existing.weights[sk] = wt
                applied_cnt += 1
        save_taste_profile(existing, ws_path)
        print(f"\n[Applied] Saved {applied_cnt} auto-detected stack preferences to {ws_path}")
    elif fp.recommended_skills:
        print("\nTip: Run 'taxonomy fingerprint --apply' to persist these recommendations into .taxonomy/taste.json.")
    print()


def main():
    parser = argparse.ArgumentParser(prog="taxonomy", description="Skill Taxonomy & Gated Dispatcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fingerprint
    p_fp = subparsers.add_parser("fingerprint", help="Inspect and auto-detect project tech stack and skill alignments")
    p_fp.add_argument("path", type=str, nargs="?", default=None, help="Project root directory to inspect")
    p_fp.add_argument("--apply", action="store_true", help="Persist detected recommendations into .taxonomy/taste.json")
    p_fp.add_argument("--json", action="store_true", help="Output fingerprint data as JSON")
    p_fp.set_defaults(func=cmd_fingerprint)

    # resolve
    p_resolve = subparsers.add_parser("resolve", help="Resolve optimal skill pod for a prompt")
    p_resolve.add_argument("prompt", type=str, help="User prompt to evaluate")
    p_resolve.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_resolve.add_argument("--max-skills", type=int, default=None, help="Max skills to return")
    p_resolve.add_argument("--phase", type=str, default=None, help="Optional lifecycle phase filter")
    p_resolve.add_argument("--prefer", type=str, default=None, help="Explicit skill preference override")
    p_resolve.add_argument("--force", action="store_true", help="Force resolution even if gate bypassed")
    p_resolve.set_defaults(func=cmd_resolve)

    # explain
    p_explain = subparsers.add_parser("explain", help="Explain gate triage and skill resolution for a prompt")
    p_explain.add_argument("prompt", type=str, help="User prompt to evaluate")
    p_explain.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_explain.add_argument("--max-skills", type=int, default=3, help="Max skills to return")
    p_explain.add_argument("--phase", type=str, default=None, help="Optional lifecycle phase filter")
    p_explain.add_argument("--prefer", type=str, default=None, help="Explicit skill preference override")
    p_explain.add_argument("--force", action="store_true", help="Force resolution even if gate bypassed")
    p_explain.set_defaults(func=cmd_explain)

    # taste
    p_taste = subparsers.add_parser("taste", help="Manage User Taste Profiles & personal skill preferences")
    taste_sub = p_taste.add_subparsers(dest="taste_command", required=True)

    # taste list
    p_t_list = taste_sub.add_parser("list", help="List active taste preferences and hierarchy")
    p_t_list.set_defaults(func=cmd_taste_list)

    # taste set
    p_t_set = taste_sub.add_parser("set", help="Set preferred skill or custom weight")
    p_t_set.add_argument("key", type=str, help="Category (e.g. 'frontend.visual') or skill name (e.g. 'impeccable')")
    p_t_set.add_argument("val", type=str, help="Preferred skill name or numerical weight (-3.0 to +3.0)")
    p_t_set.add_argument("--workspace", action="store_true", help="Save preference to workspace .taxonomy/taste.json")
    p_t_set.set_defaults(func=cmd_taste_set)

    # taste avoid
    p_t_avoid = taste_sub.add_parser("avoid", help="Add a skill to the avoidance list")
    p_t_avoid.add_argument("skill", type=str, help="Skill name to avoid (-3.0 bias)")
    p_t_avoid.add_argument("--workspace", action="store_true", help="Save to workspace .taxonomy/taste.json")
    p_t_avoid.set_defaults(func=cmd_taste_avoid)

    # taste reset
    p_t_reset = taste_sub.add_parser("reset", help="Reset taste preferences to default")
    p_t_reset.add_argument("--workspace", action="store_true", help="Reset workspace taste profile only")
    p_t_reset.add_argument("--all", action="store_true", help="Reset both workspace and user profiles")
    p_t_reset.set_defaults(func=cmd_taste_reset)

    # taste presets
    p_t_presets = taste_sub.add_parser("presets", help="List curated community taste presets")
    p_t_presets.set_defaults(func=cmd_taste_presets)

    # taste export
    p_t_export = taste_sub.add_parser("export", help="Export active or scoped taste profile to JSON or YAML")
    p_t_export.add_argument("file", type=str, nargs="?", default=None, help="Output file path (prints to stdout if omitted)")
    p_t_export.add_argument("--workspace", action="store_true", help="Export workspace profile only")
    p_t_export.add_argument("--user", action="store_true", help="Export user profile only")
    p_t_export.add_argument("--yaml", action="store_true", help="Export in YAML format instead of JSON")
    p_t_export.set_defaults(func=cmd_taste_export)

    # taste import
    p_t_import = taste_sub.add_parser("import", help="Import taste profile from a community preset or file")
    p_t_import.add_argument("source", type=str, help="Preset name (e.g. 'minimalist-backend') or file path (.json/.yaml)")
    p_t_import.add_argument("--workspace", action="store_true", help="Import into workspace .taxonomy/taste.json (default)")
    p_t_import.add_argument("--user", action="store_true", help="Import into global user ~/.gemini/taxonomy/taste.json")
    p_t_import.add_argument("--force", action="store_true", help="Overwrite existing target profile without error")
    p_t_import.set_defaults(func=cmd_taste_import)

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
    p_ui.add_argument("--skills-dir", type=str, default=None, help="Path to skills directory")
    p_ui.set_defaults(func=cmd_ui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
