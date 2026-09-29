from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_extender.telehealth.common import (
    TelehealthSeedPacker,
    load_base_telehealth_data,
    normalize_seed_payload,
    read_json,
    repo_root,
)


def pack_seed_cases(
    input_data_dir: Path,
    seed_path: Path,
    output_dir: Path,
    input_split: Optional[str] = None,
    output_split: Optional[str] = None,
) -> Path:
    base_data = load_base_telehealth_data(input_data_dir, split=input_split)
    payload = read_json(seed_path)
    cases = normalize_seed_payload(payload)

    packer = TelehealthSeedPacker(base_data)
    packer.apply_seed_cases(cases)
    packer.validate()
    packer.write_snapshot(output_dir, split=output_split)

    print(f"Wrote extended telehealth dataset to: {output_dir}")
    print("Added:")
    for key, value in packer.stats.items():
        print(f"  - {key}: {value}")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pack_telehealth_seed",
        description="Pack additive telehealth payload cases into a validated telehealth dataset snapshot.",
    )
    parser.add_argument(
        "input_data_dir", type=str, help="Path to the source telehealth data directory."
    )
    parser.add_argument(
        "seed_path", type=str, help="Path to the generated telehealth seed payload."
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth"),
        help="Output directory for the merged telehealth dataset.",
    )
    parser.add_argument(
        "--split",
        choices=["test", "train"],
        default=None,
        help="Read and write the split layout of tracer/envs/telehealth/data/ "
        "(catalog files at the top, the split's own files in <split>/). "
        "Omit for flat directories.",
    )
    args = parser.parse_args()

    root = repo_root(Path.cwd())
    input_data_dir = Path(args.input_data_dir)
    resolved_input = (
        input_data_dir if input_data_dir.is_absolute() else (root / input_data_dir)
    )
    seed_path = Path(args.seed_path)
    resolved_seed = seed_path if seed_path.is_absolute() else (root / seed_path)
    output_dir = Path(args.out)
    resolved_output = output_dir if output_dir.is_absolute() else (root / output_dir)

    if not resolved_input.exists():
        raise SystemExit(f"Input data directory does not exist: {resolved_input}")
    if not resolved_seed.exists():
        raise SystemExit(f"Seed file does not exist: {resolved_seed}")

    pack_seed_cases(
        input_data_dir=resolved_input,
        seed_path=resolved_seed,
        output_dir=resolved_output,
        input_split=args.split,
        output_split=args.split,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
