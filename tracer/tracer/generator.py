import argparse
import functools
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm

# Allow running as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

import litellm

litellm.drop_params = True

from tracer.agents.feeling_generator_agent import FeelingGeneratorAgent
from tracer.agents.in_domain_checker_agent import InDomainCheckerAgent
from tracer.agents.task_generator_agent import TraceTaskGeneratorAgent
from tracer.agents.task_post_processor_agent import TaskPostProcessorAgent
from tracer.envs.base import Env
from tracer.llm_utils import empty_usage_record
from tracer.types import Task


def _run_level_llm_usage(
    phase_usages: List[Dict[str, Any]],
) -> tuple[Optional[int], bool]:
    """Sum per-phase ``total`` only if every phase has ``complete``; else run total is null."""
    if not phase_usages:
        return None, True
    if not all(u.get("complete") for u in phase_usages):
        return None, False
    run_total = 0
    for u in phase_usages:
        t = u.get("total")
        if t is None:
            return None, False
        run_total += int(t)
    return run_total, True


def _default_output_path(trace_path: str) -> str:
    p = Path(trace_path)
    name = p.name
    if "traces" in name:
        name = name.replace("traces", "generated_tasks")
    else:
        name = name + ".generated_tasks.json"
    return str(p.with_name(name))


def _build_airline_env(task: Task, tools_mode: str, split: str = "train") -> Env:
    from tracer.envs.airline import tools as airline_tools
    from tracer.envs.airline.data import load_data
    from tracer.envs.airline.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.airline.rules import RULES
    from tracer.envs.airline.wiki import WIKI

    env = Env(
        data_load_func=lambda: load_data(split),
        tools=airline_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy="instruction",
        user_model="gpt-4o",
        user_provider=None,
        task_index=0,
        enable_reward=True,
    )
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _build_retail_env(task: Task, tools_mode: str, split: str = "train") -> Env:
    from tracer.envs.retail import tools as retail_tools
    from tracer.envs.retail.data import load_data
    from tracer.envs.retail.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.retail.rules import RULES
    from tracer.envs.retail.wiki import WIKI

    env = Env(
        data_load_func=lambda: load_data(split),
        tools=retail_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy="instruction",
        user_model="gpt-4o",
        user_provider=None,
        task_index=0,
        enable_reward=True,
    )
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _build_telecom_env(task: Task, tools_mode: str, split: str = "train") -> Env:
    from tracer.envs.telecom import tools as telecom_tools
    from tracer.envs.telecom.data import load_data
    from tracer.envs.telecom.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.telecom.rules import RULES
    from tracer.envs.telecom.wiki import WIKI

    env = Env(
        data_load_func=lambda: load_data(split),
        tools=telecom_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy="instruction",
        user_model="gpt-4o",
        user_provider=None,
        task_index=0,
        enable_reward=True,
    )
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _build_generic_env(
    domain: str, task: Task, tools_mode: str, split: str = "train"
) -> Env:
    """Env builder for any domain laid out as tracer/envs/<domain>/{data,tools,
    reverse_tools,rules,wiki}. The four original domains keep their explicit builders
    above; new domains (bank, basketball, movie, school, travel, restaurant) route here
    instead of each getting a near-identical copy."""
    import importlib

    pkg = f"tracer.envs.{domain}"
    load_data = importlib.import_module(f"{pkg}.data").load_data
    fwd = importlib.import_module(f"{pkg}.tools").ALL_TOOLS
    rev = importlib.import_module(f"{pkg}.reverse_tools").ALL_TOOLS
    rules = importlib.import_module(f"{pkg}.rules").RULES
    wiki = importlib.import_module(f"{pkg}.wiki").WIKI

    env = Env(
        data_load_func=lambda: load_data(split),
        tools=fwd if tools_mode == "forward" else rev,
        tasks=[task],
        wiki=wiki,
        rules=rules,
        user_strategy="instruction",
        user_model="gpt-4o",
        user_provider=None,
        task_index=0,
        enable_reward=True,
    )
    # only domains that actually register a transfer tool get a terminator
    names = {t.get_info()["function"]["name"] for t in fwd}
    env.terminate_tools = [
        n
        for n in ("transfer_to_human_agents", "transfer_to_human_support")
        if n in names
    ]
    return env


def _build_telehealth_env(task: Task, tools_mode: str, split: str = "train") -> Env:
    from tracer.envs.telehealth import tools as telehealth_tools
    from tracer.envs.telehealth.data import load_data
    from tracer.envs.telehealth.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.telehealth.rules import RULES
    from tracer.envs.telehealth.wiki import WIKI

    env = Env(
        data_load_func=lambda: load_data(split),
        tools=telehealth_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy="instruction",
        user_model="gpt-4o",
        user_provider=None,
        task_index=0,
        enable_reward=True,
    )
    env.terminate_tools = ["transfer_to_human_support"]
    return env


def _combine_instruction(user_id: str, instructions: List[str]) -> str:
    """Create a single 2nd-person instruction with the goals (same as generate_verify)."""
    if len(instructions) == 1:
        goals = f"You want: {instructions[0]}"
    else:
        goal_lines = [f"{i + 1}. {inst}" for i, inst in enumerate(instructions)]
        goals = "You want to accomplish these, in order:\n" + "\n".join(goal_lines)
    return f"You are {user_id}. {goals}"


def _load_config_defaults(config_path: str) -> Dict[str, Any]:
    """Load a JSON config file. Keys should match argparse dest names (e.g. trace_path, generator_model)."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate tasks from traces, build env, and compute reward via env.calculate_reward()."
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to JSON config file. Config keys override script defaults; CLI overrides config.",
    )
    p.add_argument(
        "--env",
        default="airline",
        choices=[
            "airline",
            "retail",
            "telecom",
            "telehealth",
            "bank",
            "basketball",
            "movie",
            "school",
            "travel",
            "restaurant",
        ],
        help="Domain env.",
    )
    p.add_argument(
        "--trace-path",
        default="output/traces/airline_adjacency_matrix_0.0_traces.json",
        help="Path to traces JSON file.",
    )
    p.add_argument(
        "--output-path", default=None, help="Where to write generated tasks JSON."
    )
    p.add_argument(
        "--split",
        default="train",
        choices=["train", "test", "dev"],
        help="Which data split to generate tasks FROM. Train is the flat layout; "
        "test/dev read tracer/envs/<domain>/data/<split>/ when present.",
    )

    p.add_argument("--generator-model-provider", default="openai")
    p.add_argument("--generator-model", default="gpt-5.2")
    p.add_argument("--generator-temperature", type=float, default=0.2)
    p.add_argument(
        "--feeling-temperature",
        type=float,
        default=0.9,
        help="Temperature for the separate feeling-generation pass (same model/provider as generator).",
    )
    p.add_argument(
        "--api-base",
        default=None,
        help="Optional base URL for the LLM API (e.g. https://your-vllm-host/v1 for hosted vLLM).",
    )

    p.add_argument("--start-index", "--start-idx", type=int, default=0)
    p.add_argument("--end-index", "--end-idx", type=int, default=None)
    p.add_argument("--task-ids", nargs="*", default=None)
    p.add_argument(
        "--tasks-per-trace",
        type=int,
        default=3,
        help="Number of tasks to generate per trace (default: 3).",
    )
    p.add_argument(
        "--print-thoughts",
        action="store_true",
        help="Print ReAct Thought lines and think-tool content from the generator agent (needs --debug).",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Verbose mode: every agent step, tool call and observation on stdout (the pre-progress-bar "
        "behaviour). Without it stdout is silenced and only the progress bar (stderr) is shown.",
    )

    # First pass: get --config if present
    args_pre, _ = p.parse_known_args()
    if args_pre.config is not None:
        cfg = _load_config_defaults(args_pre.config)
        for action in p._actions:
            if action.dest != "config" and action.dest in cfg:
                action.default = cfg[action.dest]
    return p.parse_args()


def main():
    args = parse_args()
    # Default = quiet: the per-step chatter of four ReAct agents goes to /dev/null and the
    # terminal shows only the stderr progress bar. --debug restores the full stream.
    if not getattr(args, "debug", False):
        sys.stdout = open(os.devnull, "w")
    with open(args.trace_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    # Support both `*_traces.json` (list of traces) and `*_tasks.json` (list of dicts with action_trace).
    if (
        isinstance(loaded, list)
        and len(loaded) > 0
        and isinstance(loaded[0], dict)
        and "action_trace" in loaded[0]
    ):
        traces = [item.get("action_trace") for item in loaded]
    else:
        traces = loaded

    output_path = args.output_path or _default_output_path(args.trace_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Select env-specific data loader, tools, prompts, and env builder (same as generate_verify)
    preference_system_prompt = None
    format_preference_user_prompt = None
    if args.env == "airline":
        from tracer.envs.airline.data import load_data
        from tracer.envs.airline.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_airline import SYSTEM_PROMPT, USER_PROMPT

        build_env = _build_airline_env
    elif args.env == "retail":
        from tracer.envs.retail.data import load_data
        from tracer.envs.retail.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_retail import SYSTEM_PROMPT, USER_PROMPT
        from tracer.prompts.task_preference_retail import (
            PREFERENCE_SYSTEM_PROMPT as RETAIL_PREFERENCE_SYSTEM_PROMPT,
        )
        from tracer.prompts.task_preference_retail import (
            format_preference_user_prompt as retail_format_preference_user_prompt,
        )

        build_env = _build_retail_env
        preference_system_prompt = RETAIL_PREFERENCE_SYSTEM_PROMPT
        format_preference_user_prompt = retail_format_preference_user_prompt
    elif args.env == "telecom":
        from tracer.envs.telecom.data import load_data
        from tracer.envs.telecom.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_telecom import SYSTEM_PROMPT, USER_PROMPT
        from tracer.prompts.task_preference_telecom import (
            PREFERENCE_SYSTEM_PROMPT as TELECOM_PREFERENCE_SYSTEM_PROMPT,
        )
        from tracer.prompts.task_preference_telecom import (
            format_preference_user_prompt as telecom_format_preference_user_prompt,
        )

        build_env = _build_telecom_env
        preference_system_prompt = TELECOM_PREFERENCE_SYSTEM_PROMPT
        format_preference_user_prompt = telecom_format_preference_user_prompt
    elif args.env == "telehealth":
        from tracer.envs.telehealth.data import load_data
        from tracer.envs.telehealth.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_telehealth import SYSTEM_PROMPT, USER_PROMPT
        from tracer.prompts.task_preference_telehealth import (
            PREFERENCE_SYSTEM_PROMPT as TELEHEALTH_PREFERENCE_SYSTEM_PROMPT,
        )
        from tracer.prompts.task_preference_telehealth import (
            format_preference_user_prompt as telehealth_format_preference_user_prompt,
        )

        build_env = _build_telehealth_env
        preference_system_prompt = TELEHEALTH_PREFERENCE_SYSTEM_PROMPT
        format_preference_user_prompt = telehealth_format_preference_user_prompt
    else:
        # Generic path for domains laid out in the standard way. Generator prompts are
        # produced by scripts/taskgen/make_prompt.py. The preference prompt comes from
        # tracer/prompts/task_preference_<env>.py, else the domain-neutral task_preference.py
        # (leaving it None would fall back to the airline prompt in the post-processor).
        import importlib

        _pkg = f"tracer.envs.{args.env}"
        load_data = importlib.import_module(f"{_pkg}.data").load_data
        REVERSE_TOOLS = importlib.import_module(f"{_pkg}.reverse_tools").ALL_TOOLS
        _prompts = importlib.import_module(f"tracer.prompts.task_generator_{args.env}")
        SYSTEM_PROMPT, USER_PROMPT = _prompts.SYSTEM_PROMPT, _prompts.USER_PROMPT
        build_env = functools.partial(_build_generic_env, args.env)
        _pref_name = f"tracer.prompts.task_preference_{args.env}"
        try:
            _pref = importlib.import_module(_pref_name)
        except ModuleNotFoundError as e:
            if e.name != _pref_name:
                raise
            _pref = importlib.import_module("tracer.prompts.task_preference")
        preference_system_prompt = _pref.PREFERENCE_SYSTEM_PROMPT
        format_preference_user_prompt = _pref.format_preference_user_prompt
        print(f"[generator] preference prompt: {_pref.__name__}")

    # Bind the split once: the task generator reads the env DB through load_data, and
    # build_env constructs the scoring Env from the same split. Test tasks must be
    # generated FROM test data or they will reference entities that split cannot see.
    split = args.split
    build_env = functools.partial(build_env, split=split)
    print(f"[generator] env={args.env} split={split}")

    generator = TraceTaskGeneratorAgent(
        tools=REVERSE_TOOLS,
        data_load_func=lambda: load_data(split),
        model=args.generator_model,
        provider=args.generator_model_provider,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
        temperature=args.generator_temperature,
        api_base=args.api_base,
        print_thoughts=getattr(args, "print_thoughts", False),
    )

    post_processor = TaskPostProcessorAgent(
        model=args.generator_model,
        provider=args.generator_model_provider,
        temperature=0.0,
        api_base=args.api_base,
    )

    in_domain_checker = InDomainCheckerAgent(
        model=args.generator_model,
        provider=args.generator_model_provider,
        temperature=0.0,
        api_base=args.api_base,
    )

    feeling_agent = FeelingGeneratorAgent(
        model=args.generator_model,
        provider=args.generator_model_provider,
        temperature=args.feeling_temperature,
        api_base=args.api_base,
    )

    if args.task_ids is not None and len(args.task_ids) > 0:
        idxs = [int(x) for x in args.task_ids]
    else:
        end = args.end_index if args.end_index is not None else len(traces)
        idxs = list(range(args.start_index, min(end, len(traces))))

    results: List[Dict[str, Any]] = []
    if out_p.exists():
        with open(out_p, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(
            f"Resuming: loaded {len(results)} existing entries from {out_p}",
            file=sys.stderr,
        )

    completed_ok = {
        (r["task_id"], r["run"]) for r in results if not r.get("failed", False)
    }
    failed_keys = {(r["task_id"], r["run"]) for r in results if r.get("failed", False)}
    print(
        f"  Skipping {len(completed_ok)} completed, retrying {len(failed_keys)} failed",
        file=sys.stderr,
    )

    # Progress bar on STDERR (stdout carries the verbose per-step log, which run_all.sh
    # sends to the log file; the terminal shows only this bar).
    n_target = len(idxs) * args.tasks_per_trace
    done_ok = [
        r for r in results if not r.get("failed", False) and r["task_id"] in set(idxs)
    ]
    tally = {
        "solvable": sum(1 for r in done_ok if r.get("solvable") is True),
        "unsolvable": sum(1 for r in done_ok if r.get("solvable") is False),
        "unchecked": sum(1 for r in done_ok if r.get("solvable") is None),
        "failed": 0,
    }
    span = (
        f"[{idxs[0]}:{idxs[-1] + 1}]"
        if idxs and args.task_ids is None
        else f"ids={args.task_ids}"
    )
    print(
        f"domain={args.env} split={split} traces={args.trace_path} {span} x{args.tasks_per_trace} -> {out_p}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"target={n_target} tasks, already done={len(done_ok)}, model={args.generator_model}",
        file=sys.stderr,
        flush=True,
    )
    bar = tqdm(
        total=n_target,
        initial=len(done_ok),
        desc=f"{args.env}/{split}",
        unit="task",
        file=sys.stderr,
        dynamic_ncols=True,
    )
    bar.set_postfix(tally, refresh=True)

    # Grounding guard. The prompts' format examples quote ids from the SHIPPED data
    # (ana.silva@example.pt, olivia_smith_4705, ...). A model that copies one yields a
    # task whose user does not exist in this split; base.py:107 turns the resulting
    # tool errors into an observation on both sides, so the reward silently PASSES.
    # Cheapest complete check: the user_id must occur verbatim in the split's data.
    db_blob = json.dumps(load_data(split), ensure_ascii=False)

    for idx in idxs:
        trace = traces[idx]

        print(f"\n{'=' * 60}")
        print(f"Trace idx={idx} (generating {args.tasks_per_trace} tasks)")
        print(f"{'=' * 60}")

        batch_candidates: List[
            tuple
        ] = []  # (candidate, reward_result, run, result_dict or None)
        trace_changed = False
        for run in range(args.tasks_per_trace):
            key = (idx, run)
            if key in completed_ok:
                print(f"  [run {run}] Already done, skipping.")
                continue
            if key in failed_keys:
                results = [
                    r for r in results if not (r["task_id"] == idx and r["run"] == run)
                ]
                failed_keys.discard(key)
            try:
                # Step 1: Generate task candidate (same as generate_verify)
                (
                    candidate,
                    generator_messages,
                    _,
                    _,
                    llm_usage_generator,
                ) = generator.generate(trace=trace, attempt=0, verifier_feedback=None)

                for attempt in (1, 2):
                    if str(candidate.user_id) in db_blob:
                        break
                    print(
                        f"  [run {run}] user_id {candidate.user_id!r} is NOT in the {split} "
                        f"data (copied from the prompt examples?) -- regenerating, attempt {attempt}"
                    )
                    (
                        candidate,
                        generator_messages,
                        _,
                        _,
                        llm_usage_generator,
                    ) = generator.generate(
                        trace=trace,
                        attempt=attempt,
                        verifier_feedback=(
                            f"REJECTED: user_id {candidate.user_id!r} does not exist in the "
                            f"database. The ids in the prompt's format examples are placeholders "
                            f"-- never copy them. Call the candidates tool, pick a real user from "
                            f"its output, and use that user's exact email/id everywhere."
                        ),
                    )
                else:
                    raise RuntimeError(
                        f"user_id {candidate.user_id!r} not found in {split} data after 2 retries"
                    )

                feeling_text, feeling_traj, llm_usage_feeling = (
                    feeling_agent.generate_feeling(domain=args.env, candidate=candidate)
                )
                candidate = candidate.model_copy(update={"feeling": feeling_text})

                print(f"  [run {run}] User ID: {candidate.user_id}")
                print(f"  [run {run}] Story: {candidate.story[:80]}...")
                _feel_preview = (candidate.feeling or "")[:80]
                print(f"  [run {run}] Feeling: {_feel_preview}...")
                print(f"  [run {run}] Num instructions: {len(candidate.instructions)}")

                combined_instruction = _combine_instruction(
                    user_id=candidate.user_id,
                    instructions=candidate.instructions,
                )

                # Step 2: Build Task and env (same as generate_verify)
                task = Task(
                    user_id=candidate.user_id,
                    instruction=combined_instruction,
                    actions=candidate.actions or [],
                    outputs=[],
                )
                env = build_env(
                    task=task,
                    tools_mode="forward",
                )

                # Step 3: Get reward via env.calculate_reward() (replays task.actions internally)
                env.reset(task_index=0)
                # reward_result = env.calculate_reward()
                # reward_result_dump = reward_result.model_dump()

                result_dict = {
                    "task_id": idx,
                    "run": run,
                    "user_id": candidate.user_id,
                    "instructions": candidate.instructions,
                    "instruction": combined_instruction,
                    "story": candidate.story,
                    "feeling": candidate.feeling,
                    "feeling_traj": feeling_traj,
                    "action_trace": candidate.action_trace,
                    "ground_truth_actions": [
                        a.model_dump() for a in (candidate.actions or [])
                    ],
                    # "reward_result": reward_result_dump,
                    "generator_traj": generator_messages,
                    "llm_usage_generator": llm_usage_generator,
                    "llm_usage_feeling": llm_usage_feeling,
                }
                llm_usage_preference = empty_usage_record()
                # Step 4: Preference agent rewrites instructions to preference form (same tools as generator); add new keys only
                try:
                    (
                        preference_instructions,
                        preference_traj,
                        llm_usage_preference,
                    ) = post_processor.add_preference_instructions(
                        candidate,
                        lambda: load_data(split),  # NOT bare load_data: that is train
                        REVERSE_TOOLS,
                        preference_system_prompt=preference_system_prompt,
                        format_preference_user_prompt=format_preference_user_prompt,
                    )
                    if preference_instructions is not None:
                        result_dict["preference_instructions"] = preference_instructions
                        if preference_instructions:
                            result_dict["preference_instruction"] = (
                                preference_instructions[0]
                            )
                        print(
                            f"  [preference] added 1 combined preference instruction (customer-only)"
                        )
                    result_dict["preference_traj"] = preference_traj
                except Exception as pref_err:
                    print(f"  [preference] skip: {pref_err}")
                    result_dict["preference_traj"] = []
                    llm_usage_preference = empty_usage_record()
                result_dict["llm_usage_preference"] = llm_usage_preference
                llm_usage_task_checker = empty_usage_record()
                # Step 5: Solvability checker — use forward tools to test the task and estimate difficulty
                try:
                    task_analysis = in_domain_checker.check_in_domain(
                        domain=args.env,
                        env=env,
                        instruction=result_dict["instruction"],
                        ground_truth_actions=result_dict["ground_truth_actions"],
                        preferred_output=result_dict.get("preference_instructions"),
                        num_instructions=len(candidate.instructions),
                    )
                    result_dict["in_domain"] = task_analysis.get("in_domain")
                    result_dict["in_domain_reason"] = task_analysis.get(
                        "in_domain_reason"
                    )
                    result_dict["solvable"] = task_analysis.get("solvable")
                    result_dict["not_solvable"] = task_analysis.get("not_solvable")
                    result_dict["solvable_reason"] = task_analysis.get(
                        "solvable_reason"
                    )
                    result_dict["difficulty"] = task_analysis.get("difficulty")
                    result_dict["difficulty_reason"] = task_analysis.get(
                        "difficulty_reason"
                    )
                    result_dict["task_checker_traj"] = task_analysis.get(
                        "trajectory", []
                    )
                    result_dict["task_checker_action_replay"] = task_analysis.get(
                        "action_replay", []
                    )
                    llm_usage_task_checker = (
                        task_analysis.get("llm_usage") or empty_usage_record()
                    )
                    if task_analysis.get("solvable") is not None:
                        print(
                            "  [task_check] "
                            f"in_domain={task_analysis.get('in_domain')} "
                            f"solvable={task_analysis.get('solvable')} "
                            f"not_solvable={task_analysis.get('not_solvable')} "
                            f"difficulty={task_analysis.get('difficulty')} "
                            f"— {task_analysis.get('solvable_reason') or ''}"
                        )
                except Exception as id_err:
                    print(f"  [task_check] skip: {id_err}")
                    result_dict["in_domain"] = None
                    result_dict["in_domain_reason"] = None
                    result_dict["solvable"] = None
                    result_dict["not_solvable"] = None
                    result_dict["solvable_reason"] = None
                    result_dict["difficulty"] = None
                    result_dict["difficulty_reason"] = None
                    result_dict["task_checker_traj"] = []
                    result_dict["task_checker_action_replay"] = []
                    llm_usage_task_checker = empty_usage_record()
                result_dict["llm_usage_task_checker"] = llm_usage_task_checker
                run_total, run_complete = _run_level_llm_usage(
                    [
                        result_dict["llm_usage_generator"],
                        result_dict["llm_usage_feeling"],
                        result_dict["llm_usage_preference"],
                        result_dict["llm_usage_task_checker"],
                    ]
                )
                result_dict["llm_usage_run_total"] = run_total if run_complete else None
                result_dict["llm_usage_run_complete"] = run_complete
                batch_candidates.append((candidate, run, result_dict))
                print(f"  ✓ Success idx={idx} run={run}")
                tally[
                    "solvable"
                    if result_dict.get("solvable") is True
                    else "unsolvable"
                    if result_dict.get("solvable") is False
                    else "unchecked"
                ] += 1
                bar.update(1)
                bar.set_postfix(tally, refresh=True)
                trace_changed = True

            except Exception as e:
                print(f"  ✗ Failed idx={idx} run={run}: {e}")
                tqdm.write(
                    f"  ✗ Failed idx={idx} run={run}: {str(e)[:160]}", file=sys.stderr
                )
                tally["failed"] += 1
                bar.set_postfix(tally, refresh=True)
                results.append(
                    {
                        "task_id": idx,
                        "run": run,
                        "error": str(e),
                        "failed": True,
                    }
                )
                trace_changed = True

        for _, _, result_dict in batch_candidates:
            results.append(result_dict)

        # Checkpoint after each trace (only if something changed)
        if trace_changed:
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

    successful = len([r for r in results if not r.get("failed", False)])
    bar.close()
    print(
        f"Completed: {successful}/{len(results)} tasks successfully generated -> {out_p}",
        file=sys.stderr,
    )
    print(f"\nCompleted: {successful}/{len(results)} tasks successfully generated")
    print(f"Saved to {out_p}")


if __name__ == "__main__":
    main()
