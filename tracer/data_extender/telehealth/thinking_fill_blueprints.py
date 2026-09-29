from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    from dotenv import load_dotenv  # type: ignore[reportMissingImports]
except ImportError:  # pragma: no cover

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


if __package__ in {None, ""}:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from litellm import completion  # type: ignore[reportMissingImports]

from data_extender.telehealth.common import (
    normalize_seed_payload,
    read_json,
    repo_root,
    write_json,
)
from data_extender.telehealth.telehealth_seed_prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


def _sanitize_temperature(model: str, temperature: float) -> float:
    if model.startswith("gpt-5"):
        return 1.0
    return temperature


def _preview_model_output(text: str, max_chars: int = 320) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return "[empty]"
    return compact[:max_chars] + ("..." if len(compact) > max_chars else "")


def _stringify_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _completion_options(
    provider: str,
    model_id: str,
    temperature: float,
    base_api: Optional[str],
    api_key: Optional[str],
    enable_thinking: bool,
) -> Dict[str, Any]:
    provider = provider.lower()
    normalized_model = model_id
    options: Dict[str, Any] = {
        "model": normalized_model,
        "temperature": _sanitize_temperature(model_id, temperature),
    }

    if provider == "openai":
        if api_key:
            options["api_key"] = api_key
        return options

    if provider in {"vllm", "openai-compatible", "openai_compatible", "vllm_hosted"}:
        if not base_api:
            raise ValueError(
                "For provider 'vllm', 'vllm_hosted', or 'openai-compatible', you must supply --base-api."
            )
        if normalized_model.startswith("vllm_hosted/"):
            normalized_model = normalized_model.split("/", 1)[1]
        if not normalized_model.startswith("openai/"):
            options["model"] = f"openai/{normalized_model}"
        options["api_base"] = base_api
        if provider == "vllm_hosted":
            options["api_key"] = (
                api_key
                or os.getenv("VLLM_API_KEY")
                or os.getenv("OPENAI_COMPATIBLE_API_KEY")
                or "EMPTY"
            )
        else:
            options["api_key"] = (
                api_key
                or os.getenv("OPENAI_COMPATIBLE_API_KEY")
                or os.getenv("VLLM_API_KEY")
                or "EMPTY"
            )
        if enable_thinking:
            options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        return options

    if provider == "deepseek":
        options["api_base"] = base_api or "https://api.deepseek.com/v1"
        options["api_key"] = api_key or os.getenv("DEEPSEEK_API_KEY") or "EMPTY"
        return options

    raise ValueError(f"Unsupported provider: {provider}")


def _blueprint_fill_schema(batch_size: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "blueprints": {
                "type": "array",
                "minItems": batch_size,
                "maxItems": batch_size,
                "items": {
                    "type": "object",
                    "properties": {
                        "blueprint_id": {"type": "string"},
                        "appointments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "appointment_id": {"type": "string"},
                                    "chief_complaint": {"type": "string"},
                                    "notes": {"type": "string"},
                                },
                                "required": [
                                    "appointment_id",
                                    "chief_complaint",
                                    "notes",
                                ],
                            },
                        },
                        "medical_records": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "record_id": {"type": "string"},
                                    "subjective": {"type": "string"},
                                    "assessment": {"type": "string"},
                                    "plan": {"type": "string"},
                                },
                                "required": [
                                    "record_id",
                                    "subjective",
                                    "assessment",
                                    "plan",
                                ],
                            },
                        },
                        "regimen_plans": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "patient_id": {"type": "string"},
                                    "current_regimen_notes": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "optimized_regimens": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "focus": {"type": "string"},
                                                "synergy_notes": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                            "required": [
                                                "name",
                                                "focus",
                                                "synergy_notes",
                                            ],
                                        },
                                    },
                                },
                                "required": [
                                    "patient_id",
                                    "current_regimen_notes",
                                    "optimized_regimens",
                                ],
                            },
                        },
                    },
                    "required": [
                        "blueprint_id",
                        "appointments",
                        "medical_records",
                        "regimen_plans",
                    ],
                },
            }
        },
        "required": ["blueprints"],
    }


def _call_model_json(
    provider: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    base_api: Optional[str],
    api_key: Optional[str],
    temperature: float,
    enable_thinking: bool,
    transcript_entries: Optional[List[Dict[str, Any]]] = None,
    batch_index: Optional[int] = None,
) -> Dict[str, Any]:
    options = _completion_options(
        provider=provider,
        model_id=model_id,
        temperature=temperature,
        base_api=base_api,
        api_key=api_key,
        enable_thinking=enable_thinking,
    )
    response = completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "telehealth_blueprint_fill", "schema": schema},
        },
        **options,
    )
    message = response.choices[0].message
    content = _stringify_message_content(message.content)
    reasoning = _stringify_message_content(
        getattr(message, "reasoning_content", "") or ""
    )
    if not content:
        raise ValueError("Model returned empty content.")
    if transcript_entries is not None:
        transcript_entries.append(
            {
                "batch_index": batch_index,
                "request": {
                    "provider": provider,
                    "model": model_id,
                    "temperature": options.get("temperature"),
                    "api_base": options.get("api_base"),
                    "enable_thinking": enable_thinking,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                "response": {
                    "content": content,
                    "reasoning_content": reasoning or None,
                },
            }
        )
    print(
        f"[telehealth-fill] Model output preview: {_preview_model_output(content)}",
        flush=True,
    )
    return json.loads(content)


def _merge_blueprint_fill(
    case: Mapping[str, Any], fill_payload: Mapping[str, Any]
) -> Dict[str, Any]:
    merged = json.loads(json.dumps(case))
    appointment_updates = {
        row["appointment_id"]: row
        for row in fill_payload.get("appointments", [])
        if isinstance(row, Mapping)
    }
    for appointment in merged.get("appointments", []):
        update = appointment_updates.get(appointment["appointment_id"])
        if update:
            appointment["chief_complaint"] = str(update["chief_complaint"]).strip()
            appointment["notes"] = str(update["notes"]).strip()

    record_updates = {
        row["record_id"]: row
        for row in fill_payload.get("medical_records", [])
        if isinstance(row, Mapping)
    }
    for record in merged.get("medical_records", []):
        update = record_updates.get(record["record_id"])
        if update:
            record["subjective"] = str(update["subjective"]).strip()
            record["assessment"] = str(update["assessment"]).strip()
            record["plan"] = str(update["plan"]).strip()

    regimen_updates = {
        row["patient_id"]: row
        for row in fill_payload.get("regimen_plans", [])
        if isinstance(row, Mapping)
    }
    for plan in merged.get("regimen_plans", []):
        update = regimen_updates.get(plan["patient_id"])
        if not update:
            continue
        plan.setdefault("current_regimen", {})["notes"] = list(
            update.get("current_regimen_notes", [])
        )
        focus_updates = {
            row["name"]: row
            for row in update.get("optimized_regimens", [])
            if isinstance(row, Mapping) and "name" in row
        }
        for option in plan.get("optimized_regimens", []):
            updated = focus_updates.get(option["name"])
            if updated:
                option["focus"] = str(updated["focus"]).strip()
                option["synergy_notes"] = list(updated.get("synergy_notes", []))

    merged.pop("fill_request", None)
    return merged


def _user_prompt_for_blueprints(batch: Sequence[Mapping[str, Any]]) -> str:
    payload = []
    for case in batch:
        payload.append(
            {
                "metadata": case.get("metadata", {}),
                "appointments": case.get("appointments", []),
                "medical_records": case.get("medical_records", []),
                "telemetry_uploads": case.get("telemetry_uploads", []),
                "regimen_plans": case.get("regimen_plans", []),
                "fill_request": case.get("fill_request", {}),
            }
        )
    return USER_PROMPT_TEMPLATE.format(batch_json=json.dumps(payload, indent=2))


def fill_blueprint_cases(
    blueprint_cases: Sequence[Mapping[str, Any]],
    provider: str,
    model_id: str,
    output_path: Path,
    transcript_path: Optional[Path],
    base_api: Optional[str],
    api_key: Optional[str],
    temperature: float,
    batch_size: int,
    enable_thinking: bool,
) -> Path:
    transcript_entries: List[Dict[str, Any]] = []
    completed_cases: List[Dict[str, Any]] = []
    total_batches = (len(blueprint_cases) + max(1, batch_size) - 1) // max(
        1, batch_size
    )
    print(
        f"[telehealth-fill] Starting blueprint fill: blueprints={len(blueprint_cases)}, batch_size={batch_size}, "
        f"provider={provider}, model={model_id}, thinking={enable_thinking}",
        flush=True,
    )
    for batch_index in range(total_batches):
        start = batch_index * max(1, batch_size)
        end = min(len(blueprint_cases), start + max(1, batch_size))
        batch = blueprint_cases[start:end]
        print(
            f"[telehealth-fill] Filling batch {batch_index + 1}/{total_batches} (blueprints {start + 1}-{end})",
            flush=True,
        )
        result = _call_model_json(
            provider=provider,
            model_id=model_id,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_user_prompt_for_blueprints(batch),
            schema=_blueprint_fill_schema(len(batch)),
            base_api=base_api,
            api_key=api_key,
            temperature=temperature,
            enable_thinking=enable_thinking,
            transcript_entries=transcript_entries,
            batch_index=batch_index + 1,
        )
        by_blueprint_id = {
            row["blueprint_id"]: row
            for row in result.get("blueprints", [])
            if isinstance(row, Mapping) and "blueprint_id" in row
        }
        for case in batch:
            blueprint_id = str(case.get("metadata", {}).get("blueprint_id", ""))
            if blueprint_id not in by_blueprint_id:
                raise ValueError(
                    f"Model response missing blueprint fill for {blueprint_id}"
                )
            completed_cases.append(
                _merge_blueprint_fill(case, by_blueprint_id[blueprint_id])
            )
        print(
            f"[telehealth-fill] Completed batch {batch_index + 1}/{total_batches}",
            flush=True,
        )

    write_json(output_path, {"cases": completed_cases})
    if transcript_path is not None:
        write_json(
            transcript_path,
            {
                "provider": provider,
                "model": model_id,
                "temperature": _sanitize_temperature(model_id, temperature),
                "base_api": base_api,
                "enable_thinking": enable_thinking,
                "blueprint_count": len(blueprint_cases),
                "batch_size": batch_size,
                "calls": transcript_entries,
            },
        )
        print(
            f"[telehealth-fill] Wrote LLM transcript to {transcript_path}", flush=True
        )
    print(f"[telehealth-fill] Wrote filled scenario cases to {output_path}", flush=True)
    return output_path


def fill_blueprints_from_file(
    blueprint_path: Path,
    provider: str,
    model_id: str,
    output_path: Path,
    transcript_path: Optional[Path],
    base_api: Optional[str],
    api_key: Optional[str],
    temperature: float,
    batch_size: int,
    enable_thinking: bool,
) -> Path:
    payload = read_json(blueprint_path)
    cases = normalize_seed_payload(payload)
    return fill_blueprint_cases(
        blueprint_cases=cases,
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
        prog="thinking_fill_blueprints",
        description="Fill deterministic telehealth blueprints with a thinking model while preserving code-owned structure.",
    )
    parser.add_argument("blueprint_path", type=str)
    parser.add_argument("--model", type=str, default="gpt-4.1")
    parser.add_argument("--provider", type=str, default="openai")
    parser.add_argument("--base-api", dest="base_api", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_scenarios.json"),
    )
    parser.add_argument(
        "--transcript-out",
        type=str,
        default=str(Path("data_extender") / "generated_telehealth_llm_transcript.json"),
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

    fill_blueprints_from_file(
        blueprint_path=resolved_blueprint,
        provider=args.provider,
        model_id=args.model,
        output_path=resolved_output,
        transcript_path=resolved_transcript,
        base_api=args.base_api,
        api_key=args.api_key,
        temperature=args.temperature,
        batch_size=max(1, args.batch_size),
        enable_thinking=args.enable_thinking,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
