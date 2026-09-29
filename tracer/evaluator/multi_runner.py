"""Round-robin evaluator — evaluates one task from each domain before moving to the next.

Usage:
    # Every domain's valid tasks of one split, from the standard paths
    # (output/tasks/<split>_valid/<domain>_<split>_tasks_valid.json ->
    #  output/evaluations/<domain>_<split>_eval.json):
    python -m evaluator.multi_runner --domains all --split test

    # Via the combined config (all 10 domains, test split):
    python -m evaluator.multi_runner --config evaluator/config/eval_config_all.json

    # Via explicit per-domain configs (model flags apply to all domains):
    python -m evaluator.multi_runner \\
      --configs evaluator/config/eval_config_bank.json \\
               evaluator/config/eval_config_movie.json \\
      --eval-model gpt-4.1 --eval-model-provider openai

One set of judge agents serves every domain. The model settings (eval_model,
eval_model_provider, eval_temperature, api_base) come from the CLI or the combined
config (default: gpt-4.1, openai, 0.0); a per-domain config only gives the domain,
its input/output paths and the task selection (start_index, end_index, task_ids).
--start-index/--end-index/--task-ids, or the same keys in the combined config when
set (not null), override the per-domain selection.

Each domain maintains its own checkpoint file. The runner iterates round-robin:
  round 0: airline[0] → bank[0] → ... → travel[0]
  round 1: airline[1] → bank[1] → ... → travel[1]
  ...
Domains without a task file are skipped with a message; domains that have exhausted
their task list are skipped in later rounds.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

import litellm

litellm.drop_params = True

from tracer.prompts.in_domain_checker import SYSTEM_PROMPTS_BY_DOMAIN

from evaluator.agents.domain_violation_agent import DomainViolationAgent
from evaluator.agents.goal_orientation_agent import GoalOrientationAgent
from evaluator.agents.solvability_checker_agent import (
    SolvabilityCheckerAgent,
)
from evaluator.agents.template_checker_agent import TemplateCheckerAgent
from evaluator.runner import (
    _default_output_path,
    _load_config_defaults,
    evaluate_task,
)

ALL_DOMAINS = sorted(SYSTEM_PROMPTS_BY_DOMAIN)

# ---------------------------------------------------------------------------
# Per-domain state
# ---------------------------------------------------------------------------


@dataclass
class DomainState:
    domain: str
    selected: List[Dict[str, Any]]  # tasks to evaluate (pre-filtered)
    results: List[Dict[str, Any]]  # existing + accumulated results
    out_p: Path
    completed_ok: Set[Tuple[int, int]] = field(default_factory=set)
    failed_keys: Set[Tuple[int, int]] = field(default_factory=set)

    def checkpoint(self) -> None:
        with open(self.out_p, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2)


def _build_domain_state(
    cfg: Dict[str, Any],
    global_overrides: Dict[str, Any],
) -> DomainState:
    """Load one domain's task list and existing results."""
    # Global overrides win over per-domain config values for the task selection
    merged = {**cfg, **{k: v for k, v in global_overrides.items() if v is not None}}

    input_path = merged.get("input_path")
    domain = merged.get("domain")
    if not input_path or not domain:
        raise ValueError(f"A domain config needs 'domain' and 'input_path': {cfg}")

    with open(input_path, "r", encoding="utf-8") as f:
        all_tasks: List[Dict[str, Any]] = json.load(f)

    # Filter by task_ids / start_index / end_index
    task_ids = merged.get("task_ids")
    start = int(merged.get("start_index") or 0)
    end_val = merged.get("end_index")

    if task_ids:
        id_set = {int(x) for x in task_ids}
        selected = [t for t in all_tasks if t.get("task_id") in id_set]
    else:
        end = int(end_val) if end_val is not None else len(all_tasks)
        selected = all_tasks[start:end]

    output_path = merged.get("output_path") or _default_output_path(input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    if out_p.exists():
        with open(out_p, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"  [{domain}] Resuming: {len(results)} existing entries from {out_p}")

    completed_ok = {
        (r["task_id"], r["run"])
        for r in results
        if not r.get("failed") and not r.get("inconclusive")
    }
    failed_keys = {
        (r["task_id"], r["run"])
        for r in results
        if r.get("failed") or r.get("inconclusive")
    }
    print(
        f"  [{domain}] {len(selected)} tasks selected, "
        f"{len(completed_ok)} already done, {len(failed_keys)} to retry"
    )

    return DomainState(
        domain=domain,
        selected=selected,
        results=results,
        out_p=out_p,
        completed_ok=completed_ok,
        failed_keys=failed_keys,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Round-robin evaluation across multiple domains."
    )
    p.add_argument(
        "--config",
        default=None,
        help="Combined config JSON with a 'configs' list of per-domain config paths.",
    )
    p.add_argument(
        "--configs",
        nargs="+",
        default=None,
        metavar="CONFIG",
        help="One or more per-domain config JSON paths (alternative to --config).",
    )
    p.add_argument(
        "--domains",
        nargs="+",
        default=None,
        help="Without a config: these domains ('all' for every one), read from "
        "and written to the standard paths for --split.",
    )
    p.add_argument("--split", default="test", choices=["test", "train"])
    p.add_argument("--eval-model-provider", default=None)
    p.add_argument("--eval-model", default=None)
    p.add_argument("--eval-temperature", type=float, default=None)
    p.add_argument("--api-base", default=None)
    p.add_argument("--start-index", type=int, default=None)
    p.add_argument("--end-index", type=int, default=None)
    p.add_argument("--task-ids", nargs="*", default=None)
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()

    # Resolve list of per-domain config paths
    per_domain_config_paths: List[str] = []
    combined_cfg: Dict[str, Any] = {}

    if args.config is not None:
        combined_cfg = _load_config_defaults(args.config)
        per_domain_config_paths = combined_cfg.get("configs", [])
        if not per_domain_config_paths:
            print(
                "Error: combined config must have a 'configs' list of per-domain config paths."
            )
            sys.exit(1)
    elif args.configs:
        per_domain_config_paths = args.configs
    elif args.domains:
        domains = ALL_DOMAINS if args.domains == ["all"] else args.domains
        unknown = sorted(set(domains) - set(ALL_DOMAINS))
        if unknown:
            print(f"Error: unknown domains {unknown}; choose from {ALL_DOMAINS}.")
            sys.exit(1)
    else:
        print(
            "Error: provide --domains <d1 d2 ...|all>, --config <combined.json> "
            "or --configs <d1.json> <d2.json> ..."
        )
        sys.exit(1)

    # Global overrides from CLI (and from combined config for model settings)
    global_overrides: Dict[str, Any] = {
        "eval_model": args.eval_model or combined_cfg.get("eval_model"),
        "eval_model_provider": args.eval_model_provider
        or combined_cfg.get("eval_model_provider"),
        "eval_temperature": args.eval_temperature
        if args.eval_temperature is not None
        else combined_cfg.get("eval_temperature"),
        "api_base": args.api_base or combined_cfg.get("api_base"),
        "start_index": args.start_index
        if args.start_index is not None
        else combined_cfg.get("start_index"),
        "end_index": args.end_index
        if args.end_index is not None
        else combined_cfg.get("end_index"),
        "task_ids": args.task_ids or combined_cfg.get("task_ids"),
    }

    # Build shared agents (domain is passed per-task, not baked into agents)
    model = global_overrides.get("eval_model") or "gpt-4.1"
    provider = global_overrides.get("eval_model_provider") or "openai"
    temperature = global_overrides.get("eval_temperature") or 0.0
    api_base = global_overrides.get("api_base")

    agent_kwargs: Dict[str, Any] = {
        "model": model,
        "provider": provider,
        "temperature": temperature,
    }
    if api_base:
        agent_kwargs["api_base"] = api_base

    goal_agent = GoalOrientationAgent(**agent_kwargs)
    template_agent = TemplateCheckerAgent(**agent_kwargs)
    solv_agent = SolvabilityCheckerAgent(**agent_kwargs)
    domain_agent = DomainViolationAgent(**agent_kwargs)

    # Load per-domain state
    print("\nLoading domain configs...")
    domain_states: List[DomainState] = []
    if per_domain_config_paths:
        per_domain_configs = [_load_config_defaults(p) for p in per_domain_config_paths]
    else:
        per_domain_configs = [
            {
                "domain": d,
                "input_path": f"output/tasks/{args.split}_valid/{d}_{args.split}_tasks_valid.json",
                "output_path": f"output/evaluations/{d}_{args.split}_eval.json",
            }
            for d in domains
        ]
    for per_cfg in per_domain_configs:
        if not Path(per_cfg.get("input_path", "")).exists():
            print(
                f"  [{per_cfg.get('domain')}] no task file at {per_cfg.get('input_path')}; skipped"
            )
            continue
        domain_states.append(_build_domain_state(per_cfg, global_overrides))

    if not domain_states:
        print("Error: no domain configs loaded.")
        sys.exit(1)

    max_rounds = max(len(ds.selected) for ds in domain_states)
    total_done = sum(len(ds.completed_ok) for ds in domain_states)
    print(
        f"\nStarting round-robin: {len(domain_states)} domains, "
        f"up to {max_rounds} rounds, {total_done} already completed.\n"
    )

    for round_idx in range(max_rounds):
        for ds in domain_states:
            if round_idx >= len(ds.selected):
                continue

            task = ds.selected[round_idx]
            task_id = task.get("task_id", -1)
            run = task.get("run", 0)
            key = (task_id, run)

            if key in ds.completed_ok:
                print(
                    f"  [{ds.domain}] task_id={task_id} run={run} — already done, skipping."
                )
                continue
            attempt_history = []
            if key in ds.failed_keys:
                previous = next(
                    r for r in ds.results if (r.get("task_id"), r.get("run")) == key
                )
                attempt_history = previous.get("attempt_history", []) + [
                    {k: v for k, v in previous.items() if k != "attempt_history"}
                ]
                ds.results = [
                    r
                    for r in ds.results
                    if not (r.get("task_id") == task_id and r.get("run") == run)
                ]
                ds.failed_keys.discard(key)

            print(f"\n{'=' * 60}")
            print(f"[Round {round_idx}] {ds.domain}  task_id={task_id}  run={run}")
            print(f"{'=' * 60}")

            try:
                eval_record = evaluate_task(
                    task=task,
                    domain=ds.domain,
                    goal_agent=goal_agent,
                    template_agent=template_agent,
                    solvability_agent=solv_agent,
                    domain_agent=domain_agent,
                )
                ds.results.append(eval_record.model_dump())
                ds.completed_ok.add(key)
                print(
                    f"  ✓ [{ds.domain}] task_id={task_id} run={run} "
                    f"passed={eval_record.overall_passed} "
                    f"violations={eval_record.overall_violations}"
                )
            except Exception as e:
                print(f"  ✗ [{ds.domain}] task_id={task_id} run={run}: {e}")
                ds.results.append(
                    {"task_id": task_id, "run": run, "error": str(e), "failed": True}
                )

            ds.results[-1]["attempt_history"] = attempt_history
            ds.checkpoint()

    # Final summary
    print(f"\n{'=' * 60}")
    print("DONE")
    print(f"{'=' * 60}")
    for ds in domain_states:
        successful = len(
            [r for r in ds.results if not r.get("failed") and not r.get("inconclusive")]
        )
        print(
            f"  {ds.domain}: {successful}/{len(ds.results)} tasks evaluated → {ds.out_p}"
        )


if __name__ == "__main__":
    main()
