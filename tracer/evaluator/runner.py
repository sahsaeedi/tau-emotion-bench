"""Evaluator runner — entry point for the evaluator subproject.

Usage:
    python -m evaluator.runner --config evaluator/config/eval_config_airline.json
    python -m evaluator.runner --domain airline \\
        --input-path output/tasks/test_valid/airline_test_tasks_valid.json \\
        --eval-model gpt-4.1 --eval-model-provider openai

The runner loads a task file produced by the generator (usually the valid tasks
collected by scripts/taskgen/filter_valid_tasks.py), runs four evaluation agents
over each task, and writes TaskEvaluation records to
output/evaluations/<domain>_<split>_eval.json (or --output-path).

Checkpoint/resume: if the output file already exists, completed tasks are
skipped and failed tasks are retried — mirroring the behaviour of
tracer/generator.py.

--workers N evaluates N tasks at a time. To re-run only some criteria (e.g. after a policy
change), write to a new file and copy the rest from the old one:
    python -m evaluator.runner --input-path <tasks.json> --domain retail \\
        --previous-eval <old_eval.json> --output-path <new_eval.json> \\
        --rerun-criteria no_domain_violation
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
from evaluator.types import (
    CriterionResult,
    InstructionEvaluation,
    TaskEvaluation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_output_path(input_path: str) -> str:
    """output/evaluations/<name>_eval.json, e.g. bank_test_tasks_valid.json ->
    output/evaluations/bank_test_eval.json."""
    name = Path(input_path).stem
    for suffix in ("_tasks_valid", "_generated_tasks", "_tasks"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    out_dir = Path("output") / "evaluations"
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir / f"{name}_eval.json")


def _load_config_defaults(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_criterion_result(
    name: str,
    passed: Optional[bool],
    reason: str,
    raw_llm_output: Optional[Dict[str, Any]] = None,
    layer: Optional[str] = None,
) -> CriterionResult:
    if passed is None:
        raise ValueError(
            f"LLM call for criterion '{name}' returned no verdict — mark inconclusive"
        )
    is_passed = passed
    return CriterionResult(
        name=name,
        passed=is_passed,
        violation=not is_passed,
        reason=reason,
        raw_llm_output=raw_llm_output,
        layer=layer,
    )


def _evaluate_instruction(
    instruction: str,
    instruction_index: int,
    is_preference_pass: bool,
    domain: str,
    goal_agent: GoalOrientationAgent,
    template_agent: TemplateCheckerAgent,
) -> InstructionEvaluation:
    go_result = goal_agent.check(instruction=instruction, domain=domain)
    tc_result = template_agent.check(
        instruction=instruction,
        domain=domain,
        is_preference_pass=is_preference_pass,
    )

    # goal_orientation: violation iff task_type == "procedural"
    go_passed = (
        go_result.get("task_type") == "goal"
        if go_result.get("task_type") is not None
        else None
    )
    goal_cr = _build_criterion_result(
        name="goal_oriented",
        passed=go_passed,
        reason=go_result.get("reason", ""),
        raw_llm_output={k: v for k, v in go_result.items() if k != "trajectory"},
        layer="llm",
    )

    # template: violation iff follows_template == False (only definitive on pref pass)
    follows = tc_result.get("follows_template")
    if not is_preference_pass:
        # For raw instructions the preference may legitimately be absent;
        # only flag a template violation when follows_template is explicitly False AND
        # has_tool_calling_task is False (no tool task at all).
        has_tool = tc_result.get("has_tool_calling_task")
        tc_passed = has_tool if has_tool is not None else None
    else:
        tc_passed = follows
    template_cr = _build_criterion_result(
        name="template",
        passed=tc_passed,
        reason=tc_result.get("reason", ""),
        raw_llm_output={k: v for k, v in tc_result.items() if k != "trajectory"},
        layer="llm",
    )

    return InstructionEvaluation(
        instruction=instruction,
        instruction_index=instruction_index,
        is_preference_pass=is_preference_pass,
        goal_orientation=goal_cr,
        template=template_cr,
    )


CRITERIA = [
    "goal_oriented",
    "template",
    "solvable_by_ground_truth",
    "no_domain_violation",
]


def _previous_criterion(record: Dict[str, Any], name: str) -> Dict[str, Any]:
    pref = record.get("preference_instruction_eval") or {}
    return {
        "goal_oriented": pref.get("goal_orientation"),
        "template": pref.get("template"),
        "solvable_by_ground_truth": record.get("solvability"),
        "no_domain_violation": record.get("domain_violation"),
    }[name]


def _is_complete(record: Optional[Dict[str, Any]]) -> bool:
    """True for a record that holds an evaluated result for every criterion."""
    if not record or record.get("failed") or record.get("inconclusive"):
        return False
    return all(
        (_previous_criterion(record, n) or {}).get("status") == "evaluated"
        for n in CRITERIA
    )


def evaluate_task(
    task: Dict[str, Any],
    domain: str,
    goal_agent: GoalOrientationAgent,
    template_agent: TemplateCheckerAgent,
    solvability_agent: SolvabilityCheckerAgent,
    domain_agent: DomainViolationAgent,
    previous: Optional[Dict[str, Any]] = None,
    only: Optional[Set[str]] = None,
) -> TaskEvaluation:
    """Evaluate all criteria independently; retain errors without discarding other results.

    With `only` (criterion names), just those criteria are run and the others are copied from
    `previous`, an earlier complete TaskEvaluation record of the same task.
    """
    preference_instruction = task.get("preference_instruction")
    if (
        not isinstance(preference_instruction, str)
        or not preference_instruction.strip()
    ):
        raise ValueError("A non-empty preference_instruction is required")
    if only is not None and not _is_complete(previous):
        raise ValueError(
            "re-running only some criteria needs a complete previous evaluation"
        )

    def check(name, call, verdict):
        if only is not None and name not in only:
            return CriterionResult(**_previous_criterion(previous, name))
        try:
            raw = call()
            passed = verdict(raw)
            if not isinstance(passed, bool):
                result = CriterionResult(
                    name=name,
                    passed=False,
                    violation=False,
                    status="inconclusive",
                    reason=raw.get("reason") or "No definitive verdict",
                    raw_llm_output=raw,
                    layer="llm",
                )
            else:
                result = _build_criterion_result(
                    name,
                    passed,
                    raw.get("reason", ""),
                    raw,
                    "llm",
                )
        except Exception as exc:
            result = CriterionResult(
                name=name,
                passed=False,
                violation=False,
                status="error",
                reason=f"{type(exc).__name__}: {exc}",
                error=str(exc),
                layer="llm",
            )
        print(
            f"  {name}: {result.status} passed={result.passed} reason={result.reason}"
        )
        return result

    go = check(
        "goal_oriented",
        lambda: goal_agent.check(instruction=preference_instruction, domain=domain),
        lambda r: r.get("is_goal_oriented"),
    )
    template = check(
        "template",
        lambda: template_agent.check(
            instruction=preference_instruction, domain=domain, is_preference_pass=True
        ),
        lambda r: r.get("follows_template"),
    )
    solv = check(
        "solvable_by_ground_truth",
        lambda: solvability_agent.check(task=task, force_llm=True),
        lambda r: r.get("solvable"),
    )
    dom = check(
        "no_domain_violation",
        lambda: domain_agent.check(task=task, domain=domain, force_llm=True),
        lambda r: not r["is_domain_violation"]
        if isinstance(r.get("is_domain_violation"), bool)
        else None,
    )
    criteria = [go, template, solv, dom]
    errors = [c.name for c in criteria if c.status != "evaluated"]
    return TaskEvaluation(
        task_id=task.get("task_id", -1),
        run=task.get("run", 0),
        user_id=task.get("user_id", ""),
        domain=domain,
        preference_instruction_eval=InstructionEvaluation(
            instruction=preference_instruction,
            instruction_index=-1,
            is_preference_pass=True,
            goal_orientation=go,
            template=template,
        ),
        solvability=solv,
        domain_violation=dom,
        overall_passed=all(c.passed and c.status == "evaluated" for c in criteria),
        overall_violations=[c.name for c in criteria if c.violation],
        inconclusive=bool(errors),
        criterion_errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Evaluate generated tasks against four quality criteria."
    )
    p.add_argument("--config", default=None, help="Path to JSON config file.")
    p.add_argument(
        "--input-path",
        default=None,
        help="Task file from the generator, e.g. "
        "output/tasks/test_valid/<domain>_test_tasks_valid.json.",
    )
    p.add_argument(
        "--output-path",
        default=None,
        help="Where to write evaluation JSON. Default: output/evaluations/<name>_eval.json.",
    )
    p.add_argument(
        "--domain",
        default=None,
        choices=sorted(SYSTEM_PROMPTS_BY_DOMAIN),
        help="The tasks' domain; its policy is what the tasks are judged against.",
    )
    p.add_argument("--eval-model-provider", default="openai")
    p.add_argument("--eval-model", default="gpt-4.1")
    p.add_argument("--eval-temperature", type=float, default=0.0)
    p.add_argument(
        "--api-base",
        default=None,
        help="Optional LLM API base URL (e.g. vLLM endpoint).",
    )
    p.add_argument("--start-index", type=int, default=0)
    p.add_argument("--end-index", type=int, default=None)
    p.add_argument(
        "--task-ids",
        nargs="*",
        default=None,
        help="Specific task_id values to evaluate.",
    )
    p.add_argument(
        "--workers", type=int, default=1, help="Tasks evaluated concurrently."
    )
    p.add_argument(
        "--rerun-criteria",
        nargs="*",
        default=None,
        choices=CRITERIA,
        help="Re-run only these criteria and copy the others from --previous-eval "
        "(tasks without a complete previous record get a full evaluation).",
    )
    p.add_argument(
        "--previous-eval",
        default=None,
        help="Earlier *_eval.json used with --rerun-criteria.",
    )

    # Two-pass: load --config first, then let CLI override
    args_pre, _ = p.parse_known_args()
    if args_pre.config is not None:
        cfg = _load_config_defaults(args_pre.config)
        for action in p._actions:
            if action.dest != "config" and action.dest in cfg:
                action.default = cfg[action.dest]
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()

    if args.input_path is None:
        print("Error: --input-path is required (or set 'input_path' in your config).")
        sys.exit(1)
    if args.domain is None:
        print("Error: --domain is required (or set 'domain' in your config).")
        sys.exit(1)

    with open(args.input_path, "r", encoding="utf-8") as f:
        tasks: List[Dict[str, Any]] = json.load(f)

    if not isinstance(tasks, list):
        print("Error: input file must be a JSON array of task objects.")
        sys.exit(1)

    output_path = args.output_path or _default_output_path(args.input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Build agents
    agent_kwargs: Dict[str, Any] = {
        "model": args.eval_model,
        "provider": args.eval_model_provider,
        "temperature": args.eval_temperature,
    }
    if args.api_base is not None:
        agent_kwargs["api_base"] = args.api_base

    goal_agent = GoalOrientationAgent(**agent_kwargs)
    template_agent = TemplateCheckerAgent(**agent_kwargs)
    solvability_agent = SolvabilityCheckerAgent(**agent_kwargs)
    domain_agent = DomainViolationAgent(**agent_kwargs)

    # Determine which task indices to process
    if args.task_ids is not None and len(args.task_ids) > 0:
        task_id_set = {int(x) for x in args.task_ids}
        selected = [t for t in tasks if t.get("task_id") in task_id_set]
    else:
        end = args.end_index if args.end_index is not None else len(tasks)
        selected = tasks[args.start_index : end]

    only: Optional[Set[str]] = None
    previous_by_key: Dict[Any, Dict[str, Any]] = {}
    if args.rerun_criteria:
        if (
            not args.previous_eval
            or Path(args.previous_eval).resolve() == out_p.resolve()
        ):
            print(
                "Error: --rerun-criteria needs --previous-eval, a file other than the output."
            )
            sys.exit(1)
        only = set(args.rerun_criteria)
        with open(args.previous_eval, "r", encoding="utf-8") as f:
            previous_by_key = {(r["task_id"], r["run"]): r for r in json.load(f)}
        print(
            f"Re-running {sorted(only)}; other criteria copied from {args.previous_eval}"
        )

    # Load existing results for resume
    results: List[Dict[str, Any]] = []
    if out_p.exists():
        with open(out_p, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"Resuming: loaded {len(results)} existing entries from {out_p}")

    completed_ok = {
        (r["task_id"], r["run"])
        for r in results
        if not r.get("failed", False) and not r.get("inconclusive", False)
    }
    retry_keys = {
        (r["task_id"], r["run"])
        for r in results
        if r.get("failed", False) or r.get("inconclusive", False)
    }
    print(
        f"  Skipping {len(completed_ok)} completed, retrying {len(retry_keys)} failed/inconclusive"
    )

    def evaluate_one(task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task.get("task_id", -1)
        run = task.get("run", 0)
        previous = previous_by_key.get((task_id, run))
        use_previous = only is not None and _is_complete(previous)
        print(f"\n{'=' * 60}")
        print(f"Evaluating task_id={task_id} run={run}  domain={args.domain}")
        print(f"{'=' * 60}")
        try:
            eval_record = evaluate_task(
                task=task,
                domain=args.domain,
                goal_agent=goal_agent,
                template_agent=template_agent,
                solvability_agent=solvability_agent,
                domain_agent=domain_agent,
                previous=previous if use_previous else None,
                only=only if use_previous else None,
            )
            print(
                f"  ✓ task_id={task_id} run={run} "
                f"passed={eval_record.overall_passed} "
                f"violations={eval_record.overall_violations}"
            )
            record = eval_record.model_dump()
            if use_previous:
                record["rerun_criteria"] = sorted(only)
            return record

        except ValueError as e:
            print(f"  ~ Inconclusive task_id={task_id} run={run}: {e}")
            return {
                "task_id": task_id,
                "run": run,
                "error": str(e),
                "inconclusive": True,
                "overall_passed": False,
                "domain": args.domain,
                "user_id": task.get("user_id", ""),
            }
        except Exception as e:
            print(f"  ✗ Failed task_id={task_id} run={run}: {e}")
            return {
                "task_id": task_id,
                "run": run,
                "error": str(e),
                "failed": True,
                "overall_passed": False,
                "domain": args.domain,
                "user_id": task.get("user_id", ""),
            }

    todo = []
    attempt_histories: Dict[Any, List[Dict[str, Any]]] = {}
    for task in selected:
        key = (task.get("task_id", -1), task.get("run", 0))
        if key in completed_ok:
            print(f"  [task_id={key[0]} run={key[1]}] Already done, skipping.")
            continue
        attempt_histories[key] = []
        if key in retry_keys:
            previous = next(
                r for r in results if (r.get("task_id"), r.get("run")) == key
            )
            attempt_histories[key] = previous.get("attempt_history", []) + [
                {k: v for k, v in previous.items() if k != "attempt_history"}
            ]
            results = [r for r in results if (r.get("task_id"), r.get("run")) != key]
            retry_keys.discard(key)
        todo.append(task)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(evaluate_one, t): (t.get("task_id", -1), t.get("run", 0))
            for t in todo
        }
        for fut in as_completed(futures):
            record = fut.result()
            record["attempt_history"] = attempt_histories[futures[fut]]
            results.append(record)
            # Checkpoint after every task
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

    successful = len(
        [
            r
            for r in results
            if not r.get("failed", False) and not r.get("inconclusive", False)
        ]
    )
    inconclusive = len([r for r in results if r.get("inconclusive", False)])
    print(
        f"\nCompleted: {successful}/{len(results)} tasks evaluated, {inconclusive} inconclusive (will retry)"
    )
    print(f"Saved to {out_p}")


if __name__ == "__main__":
    main()
