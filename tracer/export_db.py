"""Export a domain's TRACER database into the benchmark's database file.

    python export_db.py --domain telecom --split test --dry-run
    python export_db.py --domain telecom --split test --overwrite

Merges `tracer/envs/<domain>/data/` (the catalog files, shared by every split,
plus the split's own files in `<split>/`) into one file:

    ../data/tau_emotion/domains/<domain>/db.json        (--split test)
    ../data/tau_emotion/domains/<domain>/db_train.json  (--split train)

Run it after changing the TRACER data, e.g. with the data extenders, so the
benchmark's tools see the same records the generated tasks refer to. An existing
file is only replaced with --overwrite.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict

TRACER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TRACER_ROOT.parent
DATA_ROOT = REPO_ROOT / "data" / "tau_emotion" / "domains"
OUTPUT_FILE = {"test": "db.json", "train": "db_train.json"}


def load_tracer_db(domain: str, split: str) -> Dict[str, Any]:
    """The domain's database for `split`, as TRACER's tools see it."""
    return importlib.import_module(f"tracer.envs.{domain}.data").load_data(split)


def dump_db(db: Dict[str, Any]) -> str:
    """Serialize a database the way the shipped db.json files are written."""
    return json.dumps(db, indent=2)


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--domain", required=True)
    p.add_argument("--split", required=True, choices=sorted(OUTPUT_FILE))
    p.add_argument(
        "--output", type=Path, help="Default: the domain's database file for --split"
    )
    p.add_argument(
        "--overwrite", action="store_true", help="Replace an existing output file"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Report the changes, but do not write"
    )
    args = p.parse_args()

    db = load_tracer_db(args.domain, args.split)
    out = args.output or DATA_ROOT / args.domain / OUTPUT_FILE[args.split]
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

    print(f"{args.domain}/{args.split} -> {out}")
    for name in sorted(set(db) | set(old)):
        before, after = len(old.get(name, ())), len(db.get(name, ()))
        change = "" if name in old and old[name] == db.get(name) else "  (changed)"
        print(f"  {name:24s} {before:6d} -> {after:6d}{change}")
    if db == old:
        print("No changes.")
        return

    if args.dry_run:
        print(f"DRY RUN: would write {out}")
        return
    if out.exists() and not args.overwrite:
        raise SystemExit(f"{out} exists; pass --overwrite to replace it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_db(db), encoding="utf-8")
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()
