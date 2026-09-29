# Copyright Sierra

import json
import os
from typing import Any

FOLDER_PATH = os.path.dirname(__file__)
SPLITS = ("test", "train")

# Catalog files are SHARED across splits and never generated: freezing them keeps the
# hardcoded "2024-05" date arithmetic in the tools valid, keeps list_all_airports.py
# honest, and leaves the existing tasks (which name concrete flight numbers) working.
CATALOG = ["flights"]

# Owned files are partitioned per split, in test/ and train/.
OWNED = ["users", "reservations"]


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(split: str = "train") -> dict[str, Any]:
    """Load the airline database for one split ("test" or "train")."""
    if split not in SPLITS:
        raise ValueError(f"Unknown data split: {split} (expected one of {SPLITS})")
    owned_dir = os.path.join(FOLDER_PATH, split)

    data = {name: _read(os.path.join(FOLDER_PATH, f"{name}.json")) for name in CATALOG}
    data.update(
        {name: _read(os.path.join(owned_dir, f"{name}.json")) for name in OWNED}
    )
    return data


def available_splits() -> list[str]:
    return list(SPLITS)
