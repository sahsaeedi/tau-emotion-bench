"""Extract passed tasks in original input-file format.

Joins eval results with the original input files so the output has the
full task data (instructions, ground-truth actions, traces, etc.) rather
than evaluation metadata.

Usage:
    # Single pair of files:
    python -m evaluator.get_passed_tasks \\
        --eval-path  output/evaluations/airline_test_eval.json \\
        --input-path output/tasks/test_valid/airline_test_tasks_valid.json \\
        --output-path output/evaluations/airline_test_passed_tasks.json

    # All eval files at once, auto-matched to input files, each written separately:
    python -m evaluator.get_passed_tasks \\
        --eval-dir   output/evaluations \\
        --input-dir  output/tasks/test_valid \\
        --per-file

    # Combined into one file:
    python -m evaluator.get_passed_tasks \\
        --eval-dir   output/evaluations \\
        --input-dir  output/tasks/test_valid \\
        --output-path output/evaluations/all_passed_tasks.json

Re-run protection: a registry file tracks already-extracted (task_id, run, source)
keys so re-running never duplicates tasks in the output.
Delete output/evaluations/.passed_tasks_registry.json to start fresh.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REGISTRY_FILENAME = ".passed_tasks_registry.json"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry(path: Path) -> Set[str]:
    return set(json.load(open(path))) if path.exists() else set()


def _save_registry(path: Path, registry: Set[str]) -> None:
    json.dump(sorted(registry), open(path, "w"), indent=2)


def _key(task: Dict[str, Any], source: str) -> str:
    return f"{source}::{task.get('task_id')}::{task.get('run', 0)}"


# ---------------------------------------------------------------------------
# Matching eval → input file
# ---------------------------------------------------------------------------


def _find_input_file(eval_path: Path, input_dir: Path) -> Optional[Path]:
    """Derive the input filename from the eval filename and search input_dir."""
    stem = eval_path.stem  # e.g. "airline_test_eval"
    if stem.endswith("_eval"):
        base = stem[: -len("_eval")]  # "airline_test"
    else:
        base = stem

    # Try common suffixes in order
    candidates = [
        base + "_tasks_valid.json",
        base + "_tasks.json",
        base + "_generated_tasks.json",
        base + ".json",
        base + "_traces.json",
    ]
    for name in candidates:
        p = input_dir / name
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_passed_tasks(
    eval_path: Path,
    input_path: Path,
    output_path: Path,
    registry: Set[str],
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Returns (newly_added_tasks, skipped_already_in_registry).
    Updates registry in-place; caller is responsible for saving it.
    """
    eval_records = json.load(open(eval_path))
    input_records = json.load(open(input_path))

    # Build lookup: (task_id, run) → full input record
    input_map: Dict[Tuple, Dict[str, Any]] = {
        (r.get("task_id"), r.get("run", 0)): r for r in input_records
    }

    source = eval_path.name
    newly_added: List[Dict[str, Any]] = []
    skipped = 0

    for r in eval_records:
        if limit is not None and len(newly_added) >= limit:
            break
        if r.get("failed") or r.get("inconclusive") or not r.get("overall_passed"):
            continue
        k = _key(r, source)
        if k in registry:
            skipped += 1
            continue
        full_task = input_map.get((r.get("task_id"), r.get("run", 0)))
        if full_task is None:
            continue  # eval entry has no matching input record
        newly_added.append(full_task)
        registry.add(k)

    # Append to existing output
    existing: List[Dict[str, Any]] = (
        json.load(open(output_path)) if output_path.exists() else []
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(existing + newly_added, open(output_path, "w"), indent=2)

    return newly_added, skipped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Extract passed tasks in original input-file format."
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--eval-path", help="Single eval JSON file.")
    mode.add_argument("--eval-dir", help="Directory of *_eval.json files.")

    p.add_argument(
        "--input-path", help="Matching input file (required with --eval-path)."
    )
    p.add_argument(
        "--input-dir",
        help="Directory to search for input files (used with --eval-dir).",
    )
    p.add_argument(
        "--output-path",
        default=None,
        help="Output file. With --per-file, ignored (auto-derived).",
    )
    p.add_argument(
        "--per-file",
        action="store_true",
        help="Write each domain's passed tasks to its own *_passed_tasks.json.",
    )
    p.add_argument("--registry-path", default=None)
    p.add_argument(
        "--limit", type=int, default=None, help="Max new tasks to extract per file."
    )
    return p.parse_args()


def main():
    args = parse_args()

    # --- Resolve eval + input path pairs ---
    pairs: List[Tuple[Path, Path, Path]] = []  # (eval_path, input_path, output_path)

    if args.eval_path:
        if not args.input_path:
            print("Error: --input-path is required with --eval-path.")
            sys.exit(1)
        if not args.output_path:
            print("Error: --output-path is required with --eval-path.")
            sys.exit(1)
        pairs.append(
            (Path(args.eval_path), Path(args.input_path), Path(args.output_path))
        )

    else:  # --eval-dir
        eval_dir = Path(args.eval_dir)
        input_dir = Path(args.input_dir) if args.input_dir else eval_dir
        eval_files = sorted(eval_dir.glob("*_eval.json"))
        if not eval_files:
            print(f"No *_eval.json files found in {eval_dir}")
            sys.exit(1)

        for ef in eval_files:
            ip = _find_input_file(ef, input_dir)
            if ip is None:
                print(f"  [skip] no matching input file found for {ef.name}")
                continue
            if args.per_file:
                stem = (
                    ef.stem[: -len("_eval")] if ef.stem.endswith("_eval") else ef.stem
                )
                op = ef.parent / (stem + "_passed_tasks.json")
            else:
                if not args.output_path:
                    print("Error: --output-path required unless --per-file is set.")
                    sys.exit(1)
                op = Path(args.output_path)
            pairs.append((ef, ip, op))

    if not pairs:
        print("Nothing to process.")
        sys.exit(0)

    # Registry lives next to the first output file
    base_dir = pairs[0][2].parent
    registry_path = (
        Path(args.registry_path) if args.registry_path else base_dir / REGISTRY_FILENAME
    )
    registry = _load_registry(registry_path)

    # --- Process each pair ---
    total_new = 0
    for eval_path, input_path, output_path in pairs:
        newly_added, skipped = extract_passed_tasks(
            eval_path=eval_path,
            input_path=input_path,
            output_path=output_path,
            registry=registry,
            limit=args.limit,
        )
        print(
            f"{eval_path.name}  →  {output_path.name}  "
            f"({len(newly_added)} new, {skipped} already extracted)"
        )
        total_new += len(newly_added)

    _save_registry(registry_path, registry)

    print(f"\nTotal new tasks written : {total_new}")
    print(f"Registry                : {registry_path}  ({len(registry)} total tracked)")


if __name__ == "__main__":
    main()
