import json
import os
from typing import Any

FOLDER_PATH = os.path.dirname(__file__)

# Catalog files are SHARED across splits and never generated.
CATALOG = ["services", "devices"]
# Owned files are partitioned per split; absent split dir => flat layout (= train).
OWNED = ["customers", "billing", "support_tickets"]
OPTIONAL = {}


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(split: str = "train") -> dict[str, Any]:
    """Load the telecom database for one split.

    `split` defaults to "train" and the flat layout IS the train split, so every
    existing caller (`load_data()` with no args) keeps working unchanged.
    """
    split_dir = os.path.join(FOLDER_PATH, split)
    owned_dir = split_dir if os.path.isdir(split_dir) else FOLDER_PATH

    data: dict[str, Any] = {}
    for name in CATALOG:
        data[name] = _read(os.path.join(FOLDER_PATH, f"{name}.json"))
    for name in OWNED:
        path = os.path.join(owned_dir, f"{name}.json")
        if not os.path.exists(path) and name in OPTIONAL:
            data[name] = OPTIONAL[name]
            continue
        data[name] = _read(path)
    return data


def available_splits() -> list[str]:
    found = [
        d
        for d in ("train", "test", "dev")
        if os.path.isdir(os.path.join(FOLDER_PATH, d))
    ]
    return ["train"] + [d for d in found if d != "train"]
