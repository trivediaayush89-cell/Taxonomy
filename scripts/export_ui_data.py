"""Export your installed skills into src/taxonomy/web_data.json for the workbench UI.

Portable: output paths are resolved relative to this repository, and skill paths are
written with your home directory replaced by "~" so no usernames end up in the file.
By default, proprietary instructions bodies are NOT exported to keep distributed metadata clean.

Usage:
    python scripts/export_ui_data.py                          # scan standard skill roots
    python scripts/export_ui_data.py --skills-dir ./my-skills # scan specific folder(s)
    python scripts/export_ui_data.py --include-body           # optionally include body previews
    python scripts/export_ui_data.py --out custom_data.json
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from taxonomy.indexer import SkillIndexer  # noqa: E402


def portable_path(path) -> str:
    """Render a path with the user's home directory collapsed to '~' and forward slashes."""
    if not path:
        return ""
    p = Path(path).expanduser().resolve(strict=False)
    try:
        return "~/" + p.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export skill metadata for the workbench UI.")
    parser.add_argument("--skills-dir", type=Path, action="append", default=None,
                        help="Skill root folder to scan (repeatable). Defaults to standard roots.")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "src" / "taxonomy" / "web_data.json",
                        help="Output JSON path (default: src/taxonomy/web_data.json)")
    parser.add_argument("--include-body", action="store_true", default=False,
                        help="Include first 2000 chars of skill instructions body (default: False)")
    args = parser.parse_args()

    indexer = SkillIndexer(args.skills_dir)
    skills = indexer.scan()

    skills_data = {}
    for name, s in sorted(skills.items()):
        item = {
            "name": s.name,
            "category": s.category,
            "tags": s.tags,
            "priority": s.priority,
            "conflicts_with": s.conflicts_with,
            "requires": s.requires,
            "status": s.status,
            "description": s.description,
            "path": portable_path(s.path),
        }
        if args.include_body:
            try:
                body = s.get_full_instructions()
            except Exception:
                body = ""
            item["body"] = body[:2000]
        skills_data[name] = item

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(skills_data, indent=2), encoding="utf-8")
    print(f"Exported {len(skills_data)} skills to {args.out} (include_body={args.include_body})")
    if not skills_data:
        print("[WARN] No skills found. Pass --skills-dir <folder> to point at your skills.")


if __name__ == "__main__":
    main()
