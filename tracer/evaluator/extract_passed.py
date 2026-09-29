"""Extract tasks that passed all evaluation criteria.

Tracks already-selected tasks in a registry file so re-running never
returns the same task twice.

Usage:
    # Extract from a single eval file:
    python -m evaluator.extract_passed \
        --eval-path output/evaluations/airline_test_eval.json \
        --output-path output/evaluations/airline_test_passed.json

    # Extract from all eval files in the evaluations directory:
    python -m evaluator.extract_passed \
        --eval-dir output/evaluations \
        --output-path output/evaluations/all_passed.json

    # Limit how many new tasks to extract this run:
    python -m evaluator.extract_passed --eval-dir output/evaluations \
        --output-path output/evaluations/all_passed.json --limit 100

Registry file: output/evaluations/.selected_registry.json
  Stores the set of (task_id, run, domain, source_file) keys already extracted.
  Delete this file to start fresh.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REGISTRY_FILENAME = ".selected_registry.json"


def _load_registry(registry_path: Path) -> Set[str]:
    if registry_path.exists():
        return set(json.load(open(registry_path)))
    return set()


def _save_registry(registry_path: Path, registry: Set[str]) -> None:
    json.dump(sorted(registry), open(registry_path, "w"), indent=2)


def _registry_key(task: Dict[str, Any], source_file: str) -> str:
    return f"{source_file}::{task.get('task_id')}::{task.get('run', 0)}"


def extract_passed(
    eval_paths: List[Path],
    output_path: Path,
    registry_path: Path,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    registry = _load_registry(registry_path)

    newly_selected: List[Dict[str, Any]] = []

    for eval_path in eval_paths:
        records = json.load(open(eval_path))
        source = eval_path.name

        for r in records:
            if limit is not None and len(newly_selected) >= limit:
                break
            if r.get("failed") or r.get("inconclusive"):
                continue
            if not r.get("overall_passed"):
                continue
            key = _registry_key(r, source)
            if key in registry:
                continue
            newly_selected.append({**r, "_source_file": source})
            registry.add(key)

        if limit is not None and len(newly_selected) >= limit:
            break

    # Append to existing output file if it already has content
    existing: List[Dict[str, Any]] = []
    if output_path.exists():
        existing = json.load(open(output_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(existing + newly_selected, open(output_path, "w"), indent=2)
    _save_registry(registry_path, registry)

    return newly_selected


def _passed_output_path(eval_path: Path) -> Path:
    """Derive the per-file passed output path: *_eval.json → *_passed.json."""
    name = eval_path.name
    if name.endswith("_eval.json"):
        name = name[: -len("_eval.json")] + "_passed.json"
    else:
        name = name.replace(".json", "_passed.json")
    return eval_path.parent / name


def main():
    p = argparse.ArgumentParser(
        description="Extract passed tasks, never repeating selections."
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--eval-path", help="Single *_eval.json file.")
    group.add_argument(
        "--eval-dir", help="Directory — processes all *_eval.json files found."
    )
    p.add_argument(
        "--output-path",
        default=None,
        help="Where to write (appends on re-runs). Ignored when --per-file is set.",
    )
    p.add_argument(
        "--per-file",
        action="store_true",
        help="Write each eval file's passed tasks to its own *_passed.json "
        "instead of a single combined output file.",
    )
    p.add_argument(
        "--registry-path",
        default=None,
        help="Path to registry JSON (default: <output-dir>/.selected_registry.json).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of new tasks to extract per file (--per-file) or in total.",
    )
    args = p.parse_args()

    if args.eval_path:
        eval_paths = [Path(args.eval_path)]
    else:
        eval_paths = sorted(Path(args.eval_dir).glob("*_eval.json"))
        if not eval_paths:
            print(f"No *_eval.json files found in {args.eval_dir}")
            sys.exit(1)

    # Shared registry across all files so keys stay globally unique
    base_dir = eval_paths[0].parent
    registry_path = (
        Path(args.registry_path) if args.registry_path else base_dir / REGISTRY_FILENAME
    )

    if args.per_file:
        # --- Per-file mode: one *_passed.json per eval file ---
        total_new = 0
        for eval_path in eval_paths:
            output_path = _passed_output_path(eval_path)
            selected = extract_passed(
                eval_paths=[eval_path],
                output_path=output_path,
                registry_path=registry_path,
                limit=args.limit,
            )
            print(f"{eval_path.name}  →  {output_path.name}  ({len(selected)} new)")
            total_new += len(selected)
        print(f"\nTotal newly extracted : {total_new}")
        print(
            f"Registry              : {registry_path}  "
            f"({len(_load_registry(registry_path))} total tracked)"
        )

    else:
        # --- Combined mode: all into one output file ---
        if not args.output_path:
            print("Error: --output-path is required unless --per-file is set.")
            sys.exit(1)
        output_path = Path(args.output_path)
        selected = extract_passed(
            eval_paths=eval_paths,
            output_path=output_path,
            registry_path=registry_path,
            limit=args.limit,
        )
        print(f"Newly extracted : {len(selected)} tasks")
        print(f"Output          : {output_path}")
        print(
            f"Registry        : {registry_path}  ({len(_load_registry(registry_path))} total tracked)"
        )
        if selected:
            passed_ids = [
                (r.get("task_id"), r.get("run"), r.get("_source_file"))
                for r in selected
            ]
            print(
                "Selected        :",
                passed_ids[:10],
                "..." if len(passed_ids) > 10 else "",
            )


if __name__ == "__main__":
    main()
