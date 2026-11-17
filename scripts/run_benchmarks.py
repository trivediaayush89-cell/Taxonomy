"""Standalone benchmark runner script for skill-taxonomy-dispatcher."""

import argparse
import json
from pathlib import Path
import sys

# Ensure src is in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from taxonomy.benchmark import BenchmarkRunner


def main():
    parser = argparse.ArgumentParser(description="Skill Taxonomy Dispatcher Accuracy & Benchmark Suite")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(ROOT / "benchmarks" / "labeled_routing_dataset.json"),
        help="Path to labeled benchmark dataset JSON",
    )
    parser.add_argument(
        "--catalog",
        type=str,
        default=str(ROOT / "benchmarks" / "catalog"),
        help="Path to benchmark skill catalog directory",
    )
    parser.add_argument(
        "--max-skills",
        type=int,
        default=3,
        help="Maximum skills to dispatch per prompt (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON metrics instead of text summary",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to write JSON metrics result",
    )
    args = parser.parse_args()

    runner = BenchmarkRunner(
        dataset_path=Path(args.dataset),
        catalog_path=Path(args.catalog),
        max_skills=args.max_skills,
    )
    result = runner.run()

    if args.json:
        payload = json.dumps(result.to_dict(), indent=2)
        print(payload)
    else:
        result.print_summary()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"Benchmark metrics saved to: {out_path}")


if __name__ == "__main__":
    main()
