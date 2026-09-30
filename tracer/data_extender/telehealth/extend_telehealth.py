from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Optional

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dotenv import load_dotenv  # type: ignore[reportMissingImports]
except ImportError:  # pragma: no cover

    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False


from data_extender.telehealth.common import repo_root
from data_extender.telehealth.master_data_extender import generate_master_data_cases
from data_extender.telehealth.pack_telehealth_seed import pack_seed_cases
from data_extender.telehealth.scenario_blueprints import generate_scenario_blueprints
from data_extender.telehealth.thinking_fill_blueprints import fill_blueprint_cases


def _load_config_defaults(config_path: str) -> dict[str, object]:
    with open(config_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError("Config JSON must contain an object at the top level.")
    return loaded


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Cannot interpret boolean value: {value}")


def _parse_mix(value: object) -> Optional[dict[str, float]]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): float(weight) for key, weight in value.items()}
    text = str(value).strip()
    if not text:
        return None
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise argparse.ArgumentTypeError("scenario_mix must parse to a JSON object.")
    return {str(key): float(weight) for key, weight in loaded.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="extend_telehealth",
        description="Deterministically extend telehealth master data, generate deterministic scenario blueprints, then use a thinking model only for bounded scenario text filling.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to JSON config file. Config keys override script defaults; CLI overrides config.",
    )
    parser.add_argument(
        "input_data_dir",
        nargs="?",
        type=str,
        help="Path to the source telehealth data directory, laid out like "
        "tracer/envs/telehealth/data/.",
    )
    parser.add_argument(
        "--split",
        choices=["test", "train"],
        default="test",
        help="Which split's patients to extend. The output directory has the "
        "same layout as the input, so it can be copied over it.",
    )
    parser.add_argument(
        "--target-new-patients",
        type=int,
        default=12,
        help="How many new patient records to create deterministically.",
    )
    parser.add_argument(
        "--target-family-groups",
        type=int,
        default=3,
        help="How many deterministic family groups to include within the new patient total.",
    )
    parser.add_argument(
        "--target-new-providers",
        type=int,
        default=8,
        help="How many new providers to create deterministically.",
    )
    parser.add_argument(
        "--target-new-devices",
        type=int,
        default=10,
        help="How many telemetry inventory devices to create deterministically.",
    )
    parser.add_argument(
        "--target-scenarios",
        type=int,
        default=12,
        help="How many deterministic scenario blueprints to generate.",
    )
    parser.add_argument(
        "--scenario-mix",
        type=_parse_mix,
        default=None,
        help="Optional JSON object for scenario category weights; 0 disables a category.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1",
        help="Thinking-model ID for bounded narrative filling.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        help="LLM provider: openai | vllm | openai-compatible | vllm_hosted | deepseek",
    )
    parser.add_argument(
        "--base-api",
        dest="base_api",
        type=str,
        default=None,
        help="Base URL for OpenAI-compatible providers such as vLLM.",
    )
    parser.add_argument(
        "--api-key", type=str, default=None, help="Optional explicit API key."
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.4,
        help="Model temperature for the bounded narrative filling step.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="How many deterministic blueprints to fill per LLM call.",
    )
    parser.add_argument(
        "--enable-thinking",
        type=_parse_bool,
        default=True,
        help="Whether to request provider-side thinking mode.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="RNG seed for Faker when generating master names/addresses.",
    )
    parser.add_argument(
        "--master-cases-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_master_cases.json"),
        help="Path to write deterministic master-data additive cases.",
    )
    parser.add_argument(
        "--master-metadata-out",
        type=str,
        default=str(
            Path("data_extender") / "generated_telehealth_master_metadata.json"
        ),
        help="Path to write deterministic master-data metadata.",
    )
    parser.add_argument(
        "--master-output-dir",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_master"),
        help="Intermediate directory holding the packed deterministic master dataset.",
    )
    parser.add_argument(
        "--blueprint-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_blueprints.json"),
        help="Path to write deterministic scenario blueprints.",
    )
    parser.add_argument(
        "--scenario-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_scenarios.json"),
        help="Path to write model-filled scenario cases.",
    )
    parser.add_argument(
        "--transcript-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_llm_transcript.json"),
        help="Path to write the JSON transcript of all LLM messages and responses.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth"),
        help="Output directory for the final merged telehealth dataset.",
    )
    args_pre, _ = parser.parse_known_args()
    if args_pre.config is not None:
        cfg = _load_config_defaults(args_pre.config)
        for action in parser._actions:
            if action.dest != "config" and action.dest in cfg:
                action.default = cfg[action.dest]
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input_data_dir:
        raise SystemExit("input_data_dir is required (via CLI or --config).")
    if (
        args.target_new_patients < 0
        or args.target_family_groups < 0
        or args.target_new_providers < 0
        or args.target_new_devices < 0
    ):
        raise SystemExit("Target counts must be >= 0.")
    if args.target_scenarios <= 0:
        raise SystemExit("target_scenarios must be > 0.")

    root = repo_root(Path.cwd())
    load_dotenv(root / ".env", override=False)

    input_data_dir = Path(args.input_data_dir)
    resolved_input = (
        input_data_dir if input_data_dir.is_absolute() else (root / input_data_dir)
    )
    resolved_master_cases_out = (
        Path(args.master_cases_out)
        if Path(args.master_cases_out).is_absolute()
        else (root / args.master_cases_out)
    )
    resolved_master_metadata_out = (
        Path(args.master_metadata_out)
        if Path(args.master_metadata_out).is_absolute()
        else (root / args.master_metadata_out)
    )
    resolved_master_output_dir = (
        Path(args.master_output_dir)
        if Path(args.master_output_dir).is_absolute()
        else (root / args.master_output_dir)
    )
    resolved_blueprint_out = (
        Path(args.blueprint_out)
        if Path(args.blueprint_out).is_absolute()
        else (root / args.blueprint_out)
    )
    resolved_scenario_out = (
        Path(args.scenario_out)
        if Path(args.scenario_out).is_absolute()
        else (root / args.scenario_out)
    )
    resolved_transcript_out = (
        Path(args.transcript_out)
        if Path(args.transcript_out).is_absolute()
        else (root / args.transcript_out)
    )
    resolved_out = Path(args.out) if Path(args.out).is_absolute() else (root / args.out)

    print("[telehealth] Starting deterministic-first extension pipeline", flush=True)
    print(f"[telehealth] Input data: {resolved_input} (split {args.split})", flush=True)
    print(
        "[telehealth] Deterministic targets: "
        f"patients={args.target_new_patients}, family_groups={args.target_family_groups}, "
        f"providers={args.target_new_providers}, devices={args.target_new_devices}, "
        f"scenarios={args.target_scenarios}",
        flush=True,
    )
    print(
        f"[telehealth] Thinking-model config: provider={args.provider}, model={args.model}, "
        f"batch_size={max(1, args.batch_size)}, thinking={bool(args.enable_thinking)}",
        flush=True,
    )
    if args.base_api:
        print(f"[telehealth] Base API: {args.base_api}", flush=True)
    print(f"[telehealth] Master cases out: {resolved_master_cases_out}", flush=True)
    print(
        f"[telehealth] Master metadata out: {resolved_master_metadata_out}", flush=True
    )
    print(f"[telehealth] Master snapshot dir: {resolved_master_output_dir}", flush=True)
    print(f"[telehealth] Blueprint out: {resolved_blueprint_out}", flush=True)
    print(f"[telehealth] Scenario out: {resolved_scenario_out}", flush=True)
    print(f"[telehealth] Transcript out: {resolved_transcript_out}", flush=True)
    print(f"[telehealth] Final output dir: {resolved_out}", flush=True)
    print(f"[telehealth] Master data Faker seed: {args.seed}", flush=True)

    master_cases, master_metadata = generate_master_data_cases(
        input_data_dir=resolved_input,
        target_new_patients=args.target_new_patients,
        target_family_groups=args.target_family_groups,
        target_new_providers=args.target_new_providers,
        target_new_devices=args.target_new_devices,
        cases_output_path=resolved_master_cases_out,
        metadata_output_path=resolved_master_metadata_out,
        seed=args.seed,
        split=args.split,
    )
    print(
        f"[telehealth] Deterministic master cases generated: {len(master_cases)}",
        flush=True,
    )

    pack_seed_cases(
        input_data_dir=resolved_input,
        seed_path=resolved_master_cases_out,
        output_dir=resolved_master_output_dir,
        input_split=args.split,
    )
    print("[telehealth] Deterministic master snapshot packed", flush=True)

    blueprints = generate_scenario_blueprints(
        input_data_dir=resolved_master_output_dir,
        master_metadata=master_metadata,
        target_scenarios=args.target_scenarios,
        scenario_mix=args.scenario_mix,
        output_path=resolved_blueprint_out,
    )
    print(
        f"[telehealth] Deterministic blueprints generated: {len(blueprints)}",
        flush=True,
    )

    fill_blueprint_cases(
        blueprint_cases=blueprints,
        provider=args.provider,
        model_id=args.model,
        output_path=resolved_scenario_out,
        transcript_path=resolved_transcript_out,
        batch_size=max(1, args.batch_size),
        base_api=args.base_api,
        api_key=args.api_key,
        temperature=args.temperature,
        enable_thinking=bool(args.enable_thinking),
    )
    print("[telehealth] Thinking-model blueprint fill complete", flush=True)

    pack_seed_cases(
        input_data_dir=resolved_master_output_dir,
        seed_path=resolved_scenario_out,
        output_dir=resolved_out,
        output_split=args.split,
    )
    print("[telehealth] Deterministic-first extension pipeline complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
