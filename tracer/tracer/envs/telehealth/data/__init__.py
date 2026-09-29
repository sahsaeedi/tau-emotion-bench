import json
import os
from typing import Any

FOLDER_PATH = os.path.dirname(__file__)
SPLITS = ("test", "train")

# Catalog files are SHARED across splits and never generated.
CATALOG = ["providers", "medication_suppliers", "drug_interactions"]
# Owned files are partitioned per split, in test/ and train/.
OWNED = [
    "patients",
    "appointments",
    "medical_records",
    "telemetry_inventory",
    "telemetry_uploads",
    "regimen_plans",
]
OPTIONAL = {"telemetry_inventory": [], "telemetry_uploads": [], "regimen_plans": {}}


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(split: str = "train") -> dict[str, Any]:
    """Load the telehealth database for one split ("test" or "train")."""
    if split not in SPLITS:
        raise ValueError(f"Unknown data split: {split} (expected one of {SPLITS})")
    owned_dir = os.path.join(FOLDER_PATH, split)

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
    return list(SPLITS)
