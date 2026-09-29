"""Export TRACER-generated tasks into the benchmark's task files.

    python export_tasks.py <generated_tasks.json> --domain bank --split test
    python export_tasks.py <generated_tasks.json> --domain bank --split train --dry-run

Reads a generated-task JSON list (the generator's output after emotion_analysis has
added `novel_emotion_prediction` to each task) and writes

    ../data/tau_emotion/domains/<domain>/tasks.json        (--split test)
    ../data/tau_emotion/domains/<domain>/tasks_train.json  (--split train)

in the tau_emotion Task schema. An existing file is only replaced with --overwrite.

Per generated task:
- `preference_instruction` (else the first `preference_instructions` entry, else
  `instruction`) plus "Use <user_id> for authentication."
                                     -> user_scenario.instructions
- novel_emotion_prediction.selected_instruction.text
                                     -> user_scenario.emotion_instruction
- selected_instruction.spec labels  -> user_scenario.emotion_metadata
- ground_truth_actions (else actions) -> evaluation_criteria.actions
- outputs                           -> evaluation_criteria.communicate_info

Skipped, and counted in the summary: failed generator rows, rows without a user_id,
and rows without a selected emotion instruction (every benchmark task carries one).

Train tasks reference records in the train database, so a train split also needs
the domain's db_train.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

TRACER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TRACER_ROOT.parent
DATA_ROOT = REPO_ROOT / "data" / "tau_emotion" / "domains"
OUTPUT_FILE = {"test": "tasks.json", "train": "tasks_train.json"}
EMOTION_LABELS = (
    ("emotion_family", "emotion_family"),
    ("emotion_leaf", "emotion_leaf"),
    ("dimension_politeness", "politeness"),
    ("dimension_urgency", "urgency"),
    ("dimension_trust_in_agent", "trust_in_agent"),
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def pick_instruction(task: Dict[str, Any]) -> str:
    if _text(task.get("preference_instruction")):
        return _text(task["preference_instruction"])
    for item in task.get("preference_instructions") or []:
        if _text(item):
            return _text(item)
    return _text(task.get("instruction"))


def pick_actions(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("ground_truth_actions", "actions"):
        if isinstance(task.get(key), list):
            return task[key]
    return []


def selected_emotion(task: Dict[str, Any]) -> Dict[str, Any]:
    """The emotion instruction chosen by emotion_analysis, if present."""
    prediction = task.get("novel_emotion_prediction")
    if isinstance(prediction, dict) and isinstance(
        prediction.get("selected_instruction"), dict
    ):
        return prediction["selected_instruction"]
    return {}


def skip_reason(task: Any) -> Optional[str]:
    if not isinstance(task, dict) or task.get("failed") is True:
        return "failed"
    if not _text(task.get("user_id")):
        return "no user_id"
    if not _text(selected_emotion(task).get("text")):
        return (
            "no selected emotion instruction (run emotion_analysis/run_all.py on this file; "
            "older predictions lack selected_instruction)"
        )
    return None


def convert_task(
    task: Dict[str, Any], idx: int, domain: str, split: str
) -> Dict[str, Any]:
    emotion = selected_emotion(task)
    instructions = pick_instruction(task)
    auth = f"Use {_text(task['user_id'])} for authentication."
    instructions = f"{instructions}\n\n{auth}" if instructions else auth

    spec = emotion.get("spec") if isinstance(emotion.get("spec"), dict) else {}
    labels = {field: _text(spec.get(key)) or None for field, key in EMOTION_LABELS}

    actions = [
        {"action_id": f"{idx}_{j}", "name": a["name"], "arguments": a.get("kwargs", {})}
        for j, a in enumerate(pick_actions(task))
    ]
    outputs = task.get("outputs") if isinstance(task.get("outputs"), list) else []
    return {
        "id": f"{domain}_{split}_{idx:04d}",
        "split": split,
        "user_scenario": {
            "instructions": instructions,
            "emotion_instruction": _text(emotion["text"]),
            "emotion_metadata": labels if any(labels.values()) else None,
        },
        "evaluation_criteria": {
            "actions": actions,
            "communicate_info": list(outputs),
            "reward_basis": ["DB", "COMMUNICATE"],
        },
    }


def validate(tasks: List[Dict[str, Any]], domain: str) -> List[str]:
    """Schema and tool-name checks against the benchmark package, when installed."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from tau_emotion.data_model.tasks import Task
        from tau_emotion.registry import registry
    except ImportError as e:
        print(
            f"  [warn] tau_emotion not importable ({e}); skipping schema and tool checks"
        )
        return []

    errors: List[str] = []
    tool_names = set(registry.get_env_constructor(domain)().tools.get_tools())
    for task in tasks:
        try:
            Task.model_validate(task)
        except Exception as e:  # pydantic.ValidationError
            errors.append(f"  {task['id']}: not a valid Task: {e}")
        for action in task["evaluation_criteria"]["actions"]:
            if action["name"] not in tool_names:
                errors.append(f"  {task['id']}: unknown tool {action['name']!r}")
    return errors


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("input_json", type=Path, help="Generated-task JSON list")
    p.add_argument("--domain", required=True)
    p.add_argument("--split", required=True, choices=sorted(OUTPUT_FILE))
    p.add_argument(
        "--output", type=Path, help="Default: the domain's task file for --split"
    )
    p.add_argument(
        "--overwrite", action="store_true", help="Replace an existing output file"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Convert and check, but do not write"
    )
    args = p.parse_args()

    raw = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("Input JSON must be a list of generated tasks.")

    kept: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = {}
    for task in raw:
        reason = skip_reason(task)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
        else:
            kept.append(task)
    tasks = [convert_task(t, i, args.domain, args.split) for i, t in enumerate(kept)]

    print(f"{args.domain}/{args.split}: {len(tasks)} tasks from {len(raw)} rows")
    for reason, n in sorted(skipped.items()):
        print(f"  skipped {n}: {reason}")
    if not tasks:
        raise SystemExit("Nothing to export.")

    errors = validate(tasks, args.domain)
    if errors:
        print(f"ABORTING: {len(errors)} validation error(s)")
        print("\n".join(errors[:20]))
        raise SystemExit(2)

    out = args.output or DATA_ROOT / args.domain / OUTPUT_FILE[args.split]
    if args.dry_run:
        print(f"DRY RUN: would write {out}")
        return
    if out.exists() and not args.overwrite:
        raise SystemExit(f"{out} exists; pass --overwrite to replace it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()
