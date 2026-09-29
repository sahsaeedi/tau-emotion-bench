"""Collect the valid generated tasks of one split into one file per domain.

    python scripts/taskgen/filter_valid_tasks.py --split train
    python scripts/taskgen/filter_valid_tasks.py --split train --overwrite       # refresh a snapshot
    python scripts/taskgen/filter_valid_tasks.py --split train --batch batch2    # only tasks not in earlier batches

Reads   output/tasks/<split>/<domain>_<split>_tasks*.json   (every model's file)
Writes  output/tasks/<split>_valid/<domain>_<split>_tasks_valid.json
        or, with --batch NAME, output/tasks/<split>_valid_NAME/ holding only valid tasks whose
        (task_id, run) is not already in another output/tasks/<split>_valid* folder

A task is valid when it did not crash, has ground-truth actions and a non-empty
preference_instruction, every action replays without an error, and the checker marked it
solvable and not out of domain. Each kept task gains `source_file` and `generator_model`.

Safe to run while generation is still going: the generators rewrite their file after
every trace, so a read that lands mid-save is retried.
"""

import argparse
import glob
import json
import os
import sys
import time

DOMAINS = [
    "airline",
    "bank",
    "basketball",
    "movie",
    "restaurant",
    "retail",
    "school",
    "telecom",
    "telehealth",
    "travel",
]
MODEL_BY_TAG = {
    "qwen3-235b": "qwen3-235b-a22b-instruct-2507",
    "qwen3.8-27b": "Qwen/Qwen3.8-27B",
}


def is_valid(task):
    return (
        not task.get("failed")
        and bool(task.get("ground_truth_actions"))
        and isinstance(task.get("preference_instruction"), str)
        and bool(task["preference_instruction"].strip())
        and not any(
            step.get("error") for step in task.get("task_checker_action_replay") or []
        )
        and task.get("solvable") is True
        and task.get("in_domain") is not False
    )


def load_json(path, retries=10):
    for _ in range(retries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            time.sleep(3)
    raise RuntimeError(
        f"could not parse {path} after {retries} tries (still being written?)"
    )


def generator_model(filename):
    for tag, model in MODEL_BY_TAG.items():
        if f"_{tag}_" in filename:
            return model
    return MODEL_BY_TAG["qwen3-235b"]  # untagged file = the original 235B test run


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--split", required=True, choices=["train", "test", "dev"])
    p.add_argument(
        "--overwrite", action="store_true", help="replace existing <split>_valid files"
    )
    p.add_argument(
        "--batch",
        help="write only tasks not in earlier <split>_valid* folders, to <split>_valid_BATCH",
    )
    args = p.parse_args()

    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    out_dir = f"output/tasks/{args.split}_valid" + (
        f"_{args.batch}" if args.batch else ""
    )
    earlier = (
        sorted(
            e
            for e in glob.glob(f"output/tasks/{args.split}_valid*")
            if os.path.isdir(e) and e != out_dir
        )
        if args.batch
        else []
    )
    if earlier:
        print("excluding tasks already in: " + ", ".join(earlier))
    os.makedirs(out_dir, exist_ok=True)

    total_gen = total_valid = total_old = 0
    for d in DOMAINS:
        out = f"{out_dir}/{d}_{args.split}_tasks_valid.json"
        if os.path.exists(out) and not args.overwrite:
            sys.exit(f"{out} exists; pass --overwrite to replace it")
        batched = set()
        for e in earlier:
            prev = f"{e}/{d}_{args.split}_tasks_valid.json"
            if os.path.exists(prev):
                batched.update((t["task_id"], t["run"]) for t in load_json(prev))
        sources = sorted(
            glob.glob(f"output/tasks/{args.split}/{d}_{args.split}_tasks*.json")
        )
        keep, seen, generated, old = [], set(), 0, 0
        for src in sources:
            name = os.path.basename(src)
            model = generator_model(name)
            for task in load_json(src):
                if task.get("failed"):
                    continue
                generated += 1
                if not is_valid(task):
                    continue
                key = (task["task_id"], task["run"])
                if key in seen:
                    sys.exit(
                        f"duplicate task_id/run {key} for {d} (overlapping trace ranges?)"
                    )
                seen.add(key)
                if key in batched:
                    old += 1
                    continue
                keep.append(dict(task, source_file=name, generator_model=model))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(keep, f, indent=2)
        total_gen += generated
        total_valid += len(keep) + old
        total_old += old
        print(
            f"{d:11} files={len(sources)} generated={generated:5} valid={len(keep) + old:5} "
            f"in earlier batches={old:5} written={len(keep):5} -> {out}"
        )
    pct = 100 * total_valid / total_gen if total_gen else 0
    print(
        f"TOTAL generated={total_gen} valid={total_valid} ({pct:.0f}%) in earlier batches={total_old} "
        f"written={total_valid - total_old}  snapshot {time.strftime('%Y-%m-%d %H:%M')}"
    )


if __name__ == "__main__":
    main()
