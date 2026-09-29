from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dotenv import load_dotenv  # type: ignore[reportMissingImports]
except ImportError:  # pragma: no cover

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


from data_extender.telehealth.common import repo_root
from data_extender.telehealth.thinking_fill_blueprints import (
    fill_blueprint_cases,
    fill_blueprints_from_file,
)


def generate_seed_cases(
    blueprint_cases: Sequence[Mapping[str, Any]],
    provider: str,
    model_id: str,
    output_path: Path,
    transcript_path: Optional[Path],
    batch_size: int,
    base_api: Optional[str],
    api_key: Optional[str],
    temperature: float,
    enable_thinking: bool,
) -> Path:
    return fill_blueprint_cases(
        blueprint_cases=blueprint_cases,
        provider=provider,
        model_id=model_id,
        output_path=output_path,
        transcript_path=transcript_path,
        base_api=base_api,
        api_key=api_key,
        temperature=temperature,
        batch_size=batch_size,
        enable_thinking=enable_thinking,
    )


def generate_seed_cases_from_file(
    blueprint_path: Path,
    provider: str,
    model_id: str,
    output_path: Path,
    transcript_path: Optional[Path],
    batch_size: int,
    base_api: Optional[str],
    api_key: Optional[str],
    temperature: float,
    enable_thinking: bool,
) -> Path:
    return fill_blueprints_from_file(
        blueprint_path=blueprint_path,
        provider=provider,
        model_id=model_id,
        output_path=output_path,
        transcript_path=transcript_path,
        base_api=base_api,
        api_key=api_key,
        temperature=temperature,
        batch_size=batch_size,
        enable_thinking=enable_thinking,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="generate_telehealth_seed",
        description="Fill deterministic telehealth blueprints with a thinking model while preserving code-owned IDs and structure.",
    )
    parser.add_argument(
        "blueprint_path",
        type=str,
        help="Path to the deterministic blueprint JSON file.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1",
        help="Model ID. Can be an OpenAI model or any LiteLLM-supported model string.",
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
        "--temperature", type=float, default=0.4, help="Model temperature."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="How many deterministic blueprints to fill per LLM call.",
    )
    parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="Request reasoning/thinking mode on supported providers.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_scenarios.json"),
        help="Output path for the filled scenario payloads.",
    )
    parser.add_argument(
        "--transcript-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_llm_transcript.json"),
        help="Output path for the JSON transcript of LLM messages and responses.",
    )
    args = parser.parse_args()

    root = repo_root(Path.cwd())
    load_dotenv(root / ".env", override=False)
    blueprint_path = Path(args.blueprint_path)
    resolved_blueprint = (
        blueprint_path if blueprint_path.is_absolute() else (root / blueprint_path)
    )
    output_path = Path(args.out)
    resolved_output = output_path if output_path.is_absolute() else (root / output_path)
    transcript_path = Path(args.transcript_out)
    resolved_transcript = (
        transcript_path if transcript_path.is_absolute() else (root / transcript_path)
    )

    if not resolved_blueprint.exists():
        raise SystemExit(f"Blueprint file does not exist: {resolved_blueprint}")

    generate_seed_cases_from_file(
        blueprint_path=resolved_blueprint,
        provider=args.provider,
        model_id=args.model,
        output_path=resolved_output,
        transcript_path=resolved_transcript,
        batch_size=max(1, args.batch_size),
        base_api=args.base_api,
        api_key=args.api_key,
        temperature=args.temperature,
        enable_thinking=args.enable_thinking,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
