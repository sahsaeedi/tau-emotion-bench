"""
Emotion persona combinatorial batch generator (OpenAI Batch API).

Defaults are loaded from emotions/config.json (override with --config before subcommand).

  python emotions/build_emotion_persona_instructions_batch.py submit

  python emotions/build_emotion_persona_instructions_batch.py status

  python emotions/build_emotion_persona_instructions_batch.py wait-download

Requires OPENAI_API_KEY. Batch pricing applies; completion is typically async (up to 24h).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterator

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
from openai import OpenAI

from emotions.emotion_batch_prompts import (
    EMOTION_PERSONA_BATCH_SYSTEM_PROMPT,
    EMOTION_PERSONA_BATCH_USER_TEMPLATE,
)

load_dotenv()

DEFAULT_CONFIG_REL = Path("emotions/config.json")


def _default_config_values() -> dict[str, Any]:
    return {
        "schema_path": "emotions/emotion_persona_schema.json",
        "state_path": "emotions/output/emotion_persona_batch_state.json",
        "work_dir": "emotions/output",
        "batch_input_name": "emotion_persona_batch_input.jsonl",
        "specs_snapshot_name": "emotion_persona_batch_specs.json",
        "merged_output_path": "emotions/output/emotion_persona_instructions.json",
        "model": "gpt-4o-mini",
        "instructions_per_spec": 2,
        "temperature": 0.2,
        "poll_seconds": 30,
        "max_specs": None,
    }


def load_emotion_batch_config(path: Path) -> dict[str, Any]:
    merged = _default_config_values()
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged


def config_path_to_repo_path(raw: str | Path) -> Path:
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (_REPO_ROOT / p).resolve()


def _sanitize_temperature(model: str, temperature: float) -> float:
    if model.startswith("gpt-5"):
        return 1.0
    return temperature


def _spec_custom_id(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_schema(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def expand_specs(schema: dict[str, Any]) -> list[dict[str, Any]]:
    curated = schema.get("customer_service_curated_hierarchy") or {}
    dims = schema.get("generation_dimensions") or {}
    if not curated or not dims:
        raise ValueError(
            "Schema must contain customer_service_curated_hierarchy and generation_dimensions"
        )

    dim_keys = list(dims.keys())
    dim_value_lists = [dims[k] for k in dim_keys]

    out: list[dict[str, Any]] = []
    for family, leaves in curated.items():
        for leaf in leaves:
            for combo in product(*dim_value_lists):
                spec = {
                    "emotion_family": family,
                    "emotion_leaf": leaf,
                    **{dim_keys[i]: combo[i] for i in range(len(dim_keys))},
                }
                out.append(spec)
    return out


def iter_batch_request_lines(
    specs: list[dict[str, Any]],
    model: str,
    num_variants: int,
    temperature: float,
) -> Iterator[dict[str, Any]]:
    temperature = _sanitize_temperature(model, temperature)
    for spec in specs:
        cid = _spec_custom_id(spec)
        spec_json = json.dumps(spec, indent=2, ensure_ascii=False)
        user_content = EMOTION_PERSONA_BATCH_USER_TEMPLATE.format(
            spec_json=spec_json,
            num_variants=num_variants,
        )
        body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EMOTION_PERSONA_BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        yield {
            "custom_id": cid,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }


def write_jsonl(
    path: Path, lines: Iterator[dict[str, Any]] | list[dict[str, Any]]
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    return n


def _write_specs_snapshot(path: Path, specs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = [{"custom_id": _spec_custom_id(s), "spec": s} for s in specs]
    with path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _load_specs_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        rows = json.load(f)
    return {row["custom_id"]: row["spec"] for row in rows}


def _load_state(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_submit(args: argparse.Namespace) -> None:
    schema_path = Path(args.schema).resolve()
    work_dir = Path(args.work_dir).resolve()
    state_path = Path(args.state_path).resolve()
    schema = load_schema(schema_path)
    specs = expand_specs(schema)
    if args.max_specs is not None:
        specs = specs[: max(0, args.max_specs)]

    jsonl_path = work_dir / args.batch_input_name
    specs_path = work_dir / args.specs_snapshot_name

    n = write_jsonl(
        jsonl_path,
        iter_batch_request_lines(
            specs,
            model=args.model,
            num_variants=args.instructions_per_spec,
            temperature=args.temperature,
        ),
    )
    _write_specs_snapshot(specs_path, specs)

    client = OpenAI()
    with jsonl_path.open("rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")

    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    output_json_path = Path(args.output).resolve()

    state = {
        "batch_id": batch.id,
        "input_file_id": batch_file.id,
        "jsonl_path": str(jsonl_path),
        "specs_path": str(specs_path),
        "schema_path": str(schema_path),
        "model": args.model,
        "instructions_per_spec": args.instructions_per_spec,
        "temperature": args.temperature,
        "spec_count": n,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_json_path": str(output_json_path),
        "batch_status": batch.status,
        "config_path": str(args.config_path),
    }
    _write_state(state_path, state)

    print(f"Submitted batch {batch.id} with {n} requests.", flush=True)
    print(f"State written to {state_path}", flush=True)
    print(f"Input JSONL: {jsonl_path}", flush=True)
    print(f"Specs snapshot: {specs_path}", flush=True)
    print(
        "When complete, run: wait-download (same --state-path if non-default)",
        flush=True,
    )


def _resolve_batch_id(args: argparse.Namespace, state_path: Path) -> str:
    if args.batch_id:
        return args.batch_id
    if not state_path.exists():
        raise SystemExit(f"No --batch-id and state file missing: {state_path}")
    state = _load_state(state_path)
    bid = state.get("batch_id")
    if not bid:
        raise SystemExit("State file has no batch_id")
    return bid


def cmd_status(args: argparse.Namespace) -> None:
    state_path = Path(args.state_path).resolve()
    batch_id = _resolve_batch_id(args, state_path)
    client = OpenAI()
    batch = client.batches.retrieve(batch_id)
    print(f"batch_id: {batch.id}", flush=True)
    print(f"status: {batch.status}", flush=True)
    if batch.request_counts:
        print(f"request_counts: {batch.request_counts}", flush=True)
    if batch.output_file_id:
        print(f"output_file_id: {batch.output_file_id}", flush=True)
    if batch.error_file_id:
        print(f"error_file_id: {batch.error_file_id}", flush=True)
    if getattr(batch, "errors", None):
        print(f"errors: {batch.errors}", flush=True)


def _parse_output_line(obj: dict[str, Any]) -> tuple[str, list[str] | None, str | None]:
    cid = obj.get("custom_id", "")
    if obj.get("error"):
        err = obj["error"]
        if isinstance(err, dict):
            msg = err.get("message") or json.dumps(err)
        else:
            msg = str(err)
        return cid, None, msg
    resp = obj.get("response")
    if not resp:
        return cid, None, "missing response"
    body = resp.get("body")
    if resp.get("status_code") != 200:
        return cid, None, f"HTTP {resp.get('status_code')}: {body}"
    if not isinstance(body, dict):
        return cid, None, "unexpected response body type"
    choices = body.get("choices") or []
    if not choices:
        return cid, None, "no choices in body"
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        return cid, None, "empty message content"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        return cid, None, f"invalid JSON in content: {e}"
    instr = parsed.get("instructions")
    if not isinstance(instr, list):
        return cid, None, "instructions not a list"
    texts = [str(x).strip() for x in instr if str(x).strip()]
    return cid, texts, None


def cmd_wait_download(args: argparse.Namespace) -> None:
    state_path = Path(args.state_path).resolve()
    state: dict[str, Any] = {}
    if state_path.exists():
        state = _load_state(state_path)

    if args.batch_id:
        batch_id = args.batch_id
        if state.get("batch_id") and state["batch_id"] != batch_id:
            print(
                "Note: --batch-id does not match state file; ignoring state for spec paths and metadata.",
                flush=True,
            )
            state = {}
    else:
        if not state.get("batch_id"):
            raise SystemExit(
                f"No --batch-id and no batch_id in state file: {state_path}"
            )
        batch_id = state["batch_id"]

    specs_path = (
        Path(state["specs_path"]).resolve() if state.get("specs_path") else None
    )
    schema_path = (
        Path(args.schema).resolve()
        if getattr(args, "schema", None)
        else (
            Path(state["schema_path"]).resolve() if state.get("schema_path") else None
        )
    )

    spec_by_id: dict[str, dict[str, Any]] = {}
    if specs_path and specs_path.exists():
        spec_by_id = _load_specs_snapshot(specs_path)
    elif schema_path and schema_path.exists():
        for s in expand_specs(load_schema(schema_path)):
            spec_by_id[_spec_custom_id(s)] = s
    else:
        print(
            "Warning: no specs snapshot or schema; merged items may have empty spec. "
            "Pass --schema if you only have --batch-id.",
            file=sys.stderr,
            flush=True,
        )

    default_merged = config_path_to_repo_path(
        str(load_emotion_batch_config(args.config_path).get("merged_output_path", ""))
        or "emotions/output/emotion_persona_instructions.json"
    )
    out_path = Path(
        args.output or state.get("output_json_path") or default_merged
    ).resolve()

    client = OpenAI()
    poll = max(5, int(args.poll_seconds))
    terminal = {"completed", "failed", "expired", "cancelled"}

    while True:
        batch = client.batches.retrieve(batch_id)
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] status={batch.status}",
            flush=True,
        )
        if batch.status in terminal:
            break
        time.sleep(poll)

    if batch.status != "completed":
        print(f"Batch ended with status={batch.status}", file=sys.stderr, flush=True)
        if batch.error_file_id:
            print(
                f"error_file_id={batch.error_file_id} (download via OpenAI files API)",
                file=sys.stderr,
                flush=True,
            )
        if getattr(batch, "errors", None):
            print(f"errors={batch.errors}", file=sys.stderr, flush=True)
        state_update = {
            **state,
            "batch_status": batch.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if state_path.exists():
            _write_state(state_path, state_update)
        raise SystemExit(1)

    if not batch.output_file_id:
        raise SystemExit("Batch completed but output_file_id is missing")

    content = client.files.content(batch.output_file_id)
    if hasattr(content, "read"):
        raw = content.read()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    else:
        text = getattr(content, "text", str(content))

    items: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            parse_errors.append(f"jsonl line: {e}")
            continue
        cid, instructions, err = _parse_output_line(obj)
        if err:
            parse_errors.append(f"{cid}: {err}")
            continue
        spec = spec_by_id.get(cid, {})
        inst_objs = [
            {"id": f"{cid}_i{idx + 1}", "text": t}
            for idx, t in enumerate(instructions or [])
        ]
        items.append(
            {
                "id": cid,
                "spec": spec,
                "instructions": inst_objs,
            }
        )

    merged = {
        "version": "1.0",
        "source_schema": str(schema_path) if schema_path else None,
        "batch_id": batch_id,
        "model": state.get("model"),
        "instructions_per_spec": state.get("instructions_per_spec"),
        "interpretation": (
            "User-side persona instructions for each combinatorial persona spec; "
            "append one instruction block to a base customer-service task prompt."
        ),
        "items": items,
        "parse_errors": parse_errors,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write("\n")

    state_update = {
        **state,
        "batch_status": "completed",
        "output_file_id": batch.output_file_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "output_json_path": str(out_path),
        "merged_item_count": len(items),
        "parse_error_count": len(parse_errors),
    }
    if state_path.exists():
        _write_state(state_path, state_update)

    print(f"Wrote {len(items)} items to {out_path}", flush=True)
    if parse_errors:
        print(
            f"Warning: {len(parse_errors)} parse errors (see parse_errors in JSON)",
            file=sys.stderr,
            flush=True,
        )


def build_parser(cfg: dict[str, Any], config_path: Path) -> argparse.ArgumentParser:
    schema_p = config_path_to_repo_path(cfg["schema_path"])
    state_p = config_path_to_repo_path(cfg["state_path"])
    work_p = config_path_to_repo_path(cfg["work_dir"])
    merged_p = config_path_to_repo_path(cfg["merged_output_path"])
    model = cfg["model"]
    instructions_per_spec = int(cfg["instructions_per_spec"])
    temperature = float(cfg["temperature"])
    poll_seconds = int(cfg["poll_seconds"])
    max_specs = cfg.get("max_specs")
    batch_input_name = str(cfg["batch_input_name"])
    specs_snapshot_name = str(cfg["specs_snapshot_name"])

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--config",
        type=Path,
        default=config_path,
        help="Path to config JSON (merged with built-in defaults)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("submit", help="Build JSONL, upload, create batch, write state")
    ps.add_argument("--schema", type=Path, default=schema_p)
    ps.add_argument("--state-path", type=Path, default=state_p)
    ps.add_argument("--work-dir", type=Path, default=work_p)
    ps.add_argument("--model", default=model)
    ps.add_argument("--instructions-per-spec", type=int, default=instructions_per_spec)
    ps.add_argument("--temperature", type=float, default=temperature)
    ps.add_argument(
        "--max-specs", type=int, default=max_specs, help="Cap specs for testing"
    )
    ps.add_argument(
        "--batch-input-name",
        default=batch_input_name,
        help="JSONL filename under work-dir",
    )
    ps.add_argument(
        "--specs-snapshot-name",
        default=specs_snapshot_name,
        help="Specs JSON filename under work-dir",
    )
    ps.add_argument(
        "--output",
        type=Path,
        default=merged_p,
        help="Target path for merged JSON (stored in state for wait-download)",
    )
    ps.set_defaults(func=cmd_submit)

    pst = sub.add_parser("status", help="Print batch status from state or --batch-id")
    pst.add_argument("--state-path", type=Path, default=state_p)
    pst.add_argument("--batch-id", default=None)
    pst.set_defaults(func=cmd_status)

    pwd = sub.add_parser(
        "wait-download", help="Poll until terminal, then download output and merge JSON"
    )
    pwd.add_argument("--state-path", type=Path, default=state_p)
    pwd.add_argument("--batch-id", default=None)
    pwd.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Rebuild spec map from schema when state/specs snapshot is missing (e.g. only --batch-id)",
    )
    pwd.add_argument(
        "--output", type=Path, default=None, help="Override merged JSON path"
    )
    pwd.add_argument("--poll-seconds", type=int, default=poll_seconds)
    pwd.set_defaults(func=cmd_wait_download)

    return p


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    pre_ns, rest = pre.parse_known_args()
    config_path = (
        pre_ns.config
        if pre_ns.config is not None
        else (_REPO_ROOT / DEFAULT_CONFIG_REL).resolve()
    )
    cfg = load_emotion_batch_config(config_path)

    parser = build_parser(cfg, config_path)
    args = parser.parse_args(rest)
    args.config_path = config_path

    if args.command == "submit" and not (args.model or "").strip():
        parser.error("model is empty; set model in config.json or pass --model")

    args.func(args)


if __name__ == "__main__":
    main()
