"""Shared task-file loading for the 10 domains whose tasks TRACER generated.

Those domains ship the benchmark's test tasks as `tasks.json`. Training tasks
live in their own file, `tasks_train.json` (see docs/train_tasks.md).

Splits:
    "base" (default), None  -> the shipped benchmark tasks
    "test"                  -> the same tasks, filtered to split == "test"
    "train"                 -> the combined training tasks

The train tasks reference records that only exist in TRACER's train data, so
a domain run on them must also load `db_train.json` (see `db_path`).
"""

from pathlib import Path
from typing import Optional

from tau_emotion.data_model.tasks import Task
from tau_emotion.utils import load_file

TRAIN_SPLIT = "train"
BASE_SPLITS = (None, "base")
VALID_SPLITS = ("base", "train", "test", None)


def _missing_train_file(domain: str, path: Path) -> ValueError:
    return ValueError(
        f"{domain}: no train tasks at {path}. The file ships with the "
        f"repository; restore it with `git checkout -- {path}`."
    )


def load_tasks(
    domain: str,
    task_split_name: Optional[str],
    *,
    test_path: Path,
    train_path: Path,
) -> list[Task]:
    """Load one domain's tasks for a split.

    Args:
        domain: Domain name, for error messages.
        task_split_name: "base"/None, "test" or "train".
        test_path: The shipped benchmark task file.
        train_path: The training task file.

    Raises:
        ValueError: On an unknown split, or when the train files are missing.
    """
    if task_split_name not in VALID_SPLITS:
        raise ValueError(
            f"Invalid task split name: {task_split_name}. "
            f"Valid splits are: base, train, test, None."
        )

    if task_split_name == TRAIN_SPLIT:
        if not train_path.exists():
            raise _missing_train_file(domain, train_path)
        raw = load_file(train_path)
    else:
        raw = load_file(test_path)
        if task_split_name not in BASE_SPLITS:
            raw = [t for t in raw if t.get("split") == task_split_name]

    return [Task.model_validate(t) for t in raw]


def task_splits(test_path: Path, train_path: Path) -> dict[str, list[str]]:
    """Split-name -> task-id mapping, derived from the task files.

    'base' is the shipped benchmark set; 'train' is empty until the training
    tasks are built.
    """
    splits: dict[str, list[str]] = {"train": [], "test": [], "base": []}
    for t in load_file(test_path):
        if t.get("split") == "test":
            splits["test"].append(t["id"])
        splits["base"].append(t["id"])
    if train_path.exists():
        splits["train"] = [t["id"] for t in load_file(train_path)]
    return splits


def db_path(domain: str, db_split: str, *, test_path: Path, train_path: Path) -> Path:
    """The database file a data split runs against.

    Args:
        domain: Domain name, for error messages.
        db_split: "test" for the shipped db.json, "train" for db_train.json.
        test_path, train_path: The two database files.

    Raises:
        ValueError: On an unknown split, or when db_train.json is missing.
    """
    if db_split == "test":
        return test_path
    if db_split != TRAIN_SPLIT:
        raise ValueError(
            f"Invalid db split: {db_split}. Valid splits are: test, train."
        )
    if not train_path.exists():
        raise ValueError(
            f"{domain}: no train database at {train_path}. The file ships "
            f"with the repository; restore it with `git checkout -- {train_path}`."
        )
    return train_path
