"""Helper script to produce an explicit Development Director Skill Roster in Markdown."""

import argparse
import sys
from pathlib import Path

# Add src to pythonpath if run directly
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from taxonomy.hook import dispatch_prompt, init_dispatcher


def main():
    parser = argparse.ArgumentParser(description="Generate Skill Roster for development-director")
    parser.add_argument("prompt", type=str, help="Developer request prompt")
    parser.add_argument("--skills-dir", type=str, default=None, help="Path to skills")
    parser.add_argument("--max-skills", type=int, default=3, help="Max active skills")
    args = parser.parse_args()

    skills_roots = [Path(args.skills_dir)] if args.skills_dir else None
    res = dispatch_prompt(args.prompt, skills_roots=skills_roots, max_skills=args.max_skills)

    print("\n### Skill Roster & Complexity Triage")
    print(f"- **Evaluated Complexity**: **Tier {res.gate.tier}** ({res.gate.reason})")
    print(f"- **Gated Routing**: {'ACTIVE' if res.gate.should_route else 'BYPASS (Casual / Micro-task)'}")
    print(f"- **Triage Latency**: {res.total_latency_ms:.3f} ms\n")

    if not res.selected_skills:
        print("No specialist skills required for this request (bypassed or direct inline response).")
        return

    print("| Status | Skill Name | Category | Priority | Rationale / Match |")
    print("| :--- | :--- | :--- | :--- | :--- |")
    for s in res.selected_skills:
        print(f"| **ACTIVE** | `{s.name}` | `{s.category}` | {s.priority} | Primary domain match |")

    # Negative selection (deactivated)
    if res.category_scores:
        top_cats = set(res.category_scores.keys())
        print(f"\n> [!NOTE]\n> **Negative Selection (Conflict Lock)**: Deactivated all non-matching skill domains. Active domains: `{', '.join(top_cats)}`.\n")


if __name__ == "__main__":
    main()
