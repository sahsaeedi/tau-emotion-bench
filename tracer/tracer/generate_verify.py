import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running as a script: `python tracer/generate_verify.py ...`
# (without requiring `python -m tracer.generate_verify`).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

import litellm

litellm.drop_params = True

from tracer.agents.feeling_generator_agent import FeelingGeneratorAgent
from tracer.agents.task_critique_agent import TaskCritiqueAgent
from tracer.agents.task_generator_agent import TraceTaskGeneratorAgent
from tracer.agents.task_verifier_agent import TaskVerifierAgent
from tracer.envs.base import Env
from tracer.envs.user import UserStrategy
from tracer.types import Task


def _default_output_path(trace_path: str) -> str:
    p = Path(trace_path)
    name = p.name
    if "traces" in name:
        name = name.replace("traces", "generated_verified_tasks")
    else:
        name = name + ".generated_verified_tasks.json"
    return str(p.with_name(name))


def _build_airline_env(
    task: Task, user_strategy: str, user_model: str, user_provider: str, tools_mode: str
) -> Env:
    from tracer.envs.airline import tools as airline_tools
    from tracer.envs.airline.data import load_data
    from tracer.envs.airline.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.airline.rules import RULES
    from tracer.envs.airline.wiki import WIKI

    env = Env(
        data_load_func=load_data,
        tools=airline_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy=user_strategy,
        user_model=user_model,
        user_provider=user_provider,
        task_index=0,
        enable_reward=False,
    )
    # Match MockAirlineDomainEnv termination behavior
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _build_retail_env(
    task: Task, user_strategy: str, user_model: str, user_provider: str, tools_mode: str
) -> Env:
    from tracer.envs.retail import tools as retail_tools
    from tracer.envs.retail.data import load_data
    from tracer.envs.retail.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
    from tracer.envs.retail.rules import RULES
    from tracer.envs.retail.wiki import WIKI

    env = Env(
        data_load_func=load_data,
        tools=retail_tools.ALL_TOOLS if tools_mode == "forward" else REVERSE_TOOLS,
        tasks=[task],
        wiki=WIKI,
        rules=RULES,
        user_strategy=user_strategy,
        user_model=user_model,
        user_provider=user_provider,
        task_index=0,
        enable_reward=False,
    )
    # Match MockRetailDomainEnv termination behavior
    env.terminate_tools = ["transfer_to_human_agents"]
    return env


def _combine_instruction(user_id: str, instructions: List[str]) -> str:
    """Create a single 2nd-person instruction with the goals."""
    if len(instructions) == 1:
        goals = f"You want: {instructions[0]}"
    else:
        goal_lines = [f"{i + 1}. {inst}" for i, inst in enumerate(instructions)]
        goals = "You want to accomplish these, in order:\n" + "\n".join(goal_lines)

    return f"You are {user_id}. {goals}"


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate tasks from traces and verify them via env tools (generator->verifier->critique loop)."
    )
    p.add_argument(
        "--env",
        default="airline",
        choices=["airline", "retail"],
        help="Domain env.",
    )
    p.add_argument(
        "--trace-path",
        default="output/traces/airline_adjacency_matrix_0.0_traces.json",
        help="Path to traces JSON file.",
    )
    p.add_argument(
        "--output-path", default=None, help="Where to write verified tasks JSON."
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

    p.add_argument("--verifier-model-provider", default="openai")
    p.add_argument("--verifier-model", default="gpt-5.2")
    p.add_argument("--verifier-temperature", type=float, default=0.0)
    p.add_argument("--verifier-max-steps", type=int, default=30)

    p.add_argument("--critique-model-provider", default="openai")
    p.add_argument("--critique-model", default="gpt-4o")
    p.add_argument("--critique-temperature", type=float, default=0.3)

    p.add_argument("--user-model-provider", default="openai")
    p.add_argument("--user-model", default="gpt-4o")
    p.add_argument(
        "--user-strategy",
        default="llm",
        choices=[u.value for u in UserStrategy],
    )

    p.add_argument("--start-index", "--start-idx", type=int, default=0)
    p.add_argument("--end-index", "--end-idx", type=int, default=None)
    p.add_argument("--task-ids", nargs="*", default=None)

    p.add_argument("--max-attempts", type=int, default=3)

    return p.parse_args()


def main():
    args = parse_args()
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

    # Select env-specific data loader, tools, prompts, and env builder
    if args.env == "airline":
        from tracer.envs.airline.data import load_data
        from tracer.envs.airline.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_airline import SYSTEM_PROMPT, USER_PROMPT

        build_env = _build_airline_env
    elif args.env == "retail":
        from tracer.envs.retail.data import load_data
        from tracer.envs.retail.reverse_tools import ALL_TOOLS as REVERSE_TOOLS
        from tracer.prompts.task_generator_retail import SYSTEM_PROMPT, USER_PROMPT

        build_env = _build_retail_env
    else:
        raise ValueError(f"Unsupported env: {args.env}")

    generator = TraceTaskGeneratorAgent(
        tools=REVERSE_TOOLS,
        data_load_func=load_data,
        model=args.generator_model,
        provider=args.generator_model_provider,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
        temperature=args.generator_temperature,
    )

    feeling_agent = FeelingGeneratorAgent(
        model=args.generator_model,
        provider=args.generator_model_provider,
        temperature=args.feeling_temperature,
    )

    verifier = TaskVerifierAgent(
        model=args.verifier_model,
        provider=args.verifier_model_provider,
        temperature=args.verifier_temperature,
        max_steps=args.verifier_max_steps,
    )

    critique = TaskCritiqueAgent(
        model=args.critique_model,
        provider=args.critique_model_provider,
        temperature=args.critique_temperature,
    )

    if args.task_ids is not None and len(args.task_ids) > 0:
        idxs = [int(x) for x in args.task_ids]
    else:
        end = args.end_index if args.end_index is not None else len(traces)
        idxs = list(range(args.start_index, min(end, len(traces))))

    results: List[Dict[str, Any]] = []
    for idx in idxs:
        trace = traces[idx]
        feedback: Optional[str] = None
        verified = False

        for attempt in range(args.max_attempts):
            # Step 1: Generate task candidate
            (
                candidate,
                generator_messages,
                _,
                _,
                _,
            ) = generator.generate(
                trace=trace, attempt=attempt, verifier_feedback=feedback
            )

            feeling_text, feeling_traj, _ = feeling_agent.generate_feeling(
                domain=args.env, candidate=candidate
            )
            candidate = candidate.model_copy(update={"feeling": feeling_text})

            print(f"\n{'=' * 60}")
            print(f"Trace idx={idx}, Attempt={attempt}")
            print(f"{'=' * 60}")
            print(f"User ID: {candidate.user_id}")
            print(f"Story: {candidate.story}")
            print(f"Feeling: {candidate.feeling}")
            print(f"Num instructions: {len(candidate.instructions)}")

            combined_instruction = _combine_instruction(
                user_id=candidate.user_id,
                instructions=candidate.instructions,
            )

            # Step 2: Verify - just attempt to solve the task
            task = Task(
                user_id=candidate.user_id,
                instruction=combined_instruction,
                actions=candidate.actions or [],
                outputs=[],
            )
            env = build_env(
                task=task,
                user_strategy=args.user_strategy,
                user_model=args.user_model,
                user_provider=args.user_model_provider,
                tools_mode="forward",
            )

            print(f"\n[Verifier] Attempting to solve task...")
            report = verifier.verify(env)
            verifier_report = report.model_dump()
            verified_tool_actions = [a.model_dump() for a in report.actions]

            all_solved = report.solved

            if not all_solved:
                # Step 3: Critique - analyze what went wrong
                print(f"[Verifier] Task NOT solved. Running critique agent...")

                # Combine all instructions into one string for critique
                combined_instruction_for_feedback = "\n\n".join(
                    [
                        f"TURN {i}: {inst}"
                        for i, inst in enumerate(candidate.instructions)
                    ]
                )

                feedback = critique.critique(
                    instruction=combined_instruction_for_feedback,
                    transcript=report.transcript,
                    tool_errors=report.tool_errors,
                    stop_seen=report.stop_seen,
                )

                print(f"[Critique] Feedback: {feedback}")
                print(f"FAIL idx={idx} (attempt={attempt})")

            if all_solved:
                verified = True
                results.append(
                    {
                        "task_id": idx,
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
                        "generator_traj": generator_messages,
                        "verifier_report": verifier_report,
                        "verified_tool_actions": verified_tool_actions,
                    }
                )
                print(f"✓ SUCCESS idx={idx} (attempt={attempt})")
                break

        if not verified:
            results.append(
                {
                    "task_id": idx,
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
                    "generator_traj": generator_messages,
                    "verifier_report": verifier_report,
                    "verified_tool_actions": verified_tool_actions,
                    "failed": True,
                    "last_feedback": feedback,
                }
            )
            print(f"✗ FAILED idx={idx} after {args.max_attempts} attempts")

        # checkpoint after each idx
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    successful = len([r for r in results if not r.get("failed", False)])
    print(f"\n{'=' * 60}")
    print(f"COMPLETED: {successful}/{len(results)} tasks verified successfully")
    print(f"Saved to {out_p}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
