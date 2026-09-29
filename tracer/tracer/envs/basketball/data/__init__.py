import json
import os
from typing import Any

FOLDER_PATH = os.path.dirname(__file__)
SPLITS = ("test", "train")

# No shared catalog: clubs carry roster/games back-references into the split's
# players and games, so each split ships its own clubs.json (the shipped 240 club
# identities, rosters/games rebuilt for that split).
CATALOG = []
# Owned files are partitioned per split, in test/ and train/.
OWNED = ["players", "games", "clubs"]


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(split: str = "train") -> dict[str, Any]:
    """Load the basketball database for one split ("test" or "train")."""
    if split not in SPLITS:
        raise ValueError(f"Unknown data split: {split} (expected one of {SPLITS})")
    owned_dir = os.path.join(FOLDER_PATH, split)

    data: dict[str, Any] = {}
    for name in CATALOG:
        data[name] = _read(os.path.join(FOLDER_PATH, f"{name}.json"))
    for name in OWNED:
        data[name] = _read(os.path.join(owned_dir, f"{name}.json"))
    return data


def available_splits() -> list[str]:
    return list(SPLITS)
