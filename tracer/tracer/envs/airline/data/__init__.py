# Copyright Sierra

import json
import os
from typing import Any

FOLDER_PATH = os.path.dirname(__file__)

# Catalog files are SHARED across splits and never generated: freezing them keeps the
# hardcoded "2024-05" date arithmetic in the tools valid, keeps list_all_airports.py
# honest, and leaves the existing tasks (which name concrete flight numbers) working.
CATALOG = ["flights"]

# Owned files are partitioned per split. A split dir holds its own copy; if the dir is
# absent we fall back to the flat layout, so `load_data()` behaves exactly as before.
OWNED = ["users", "reservations"]


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(split: str = "train") -> dict[str, Any]:
    """Load the airline database for one split.

    `split` defaults to "train", and the flat layout IS the train split, so every
    existing caller (`load_data()` with no args) keeps working unchanged.
    """
    split_dir = os.path.join(FOLDER_PATH, split)
    owned_dir = split_dir if os.path.isdir(split_dir) else FOLDER_PATH

    data = {name: _read(os.path.join(FOLDER_PATH, f"{name}.json")) for name in CATALOG}
    data.update(
        {name: _read(os.path.join(owned_dir, f"{name}.json")) for name in OWNED}
    )
    return data


def available_splits() -> list[str]:
    found = [
        d
        for d in ("train", "test", "dev")
        if os.path.isdir(os.path.join(FOLDER_PATH, d))
    ]
    return ["train"] + [d for d in found if d != "train"]
