import argparse
import json
import os
import random
from collections import Counter
from dataclasses import asdict

import trace_utils as utils
from trace_utils import TRACE, Tool


def generate_trace(
    tools: list[Tool], walk_step: int, num_intents: int, rng: random.Random
) -> TRACE:
    """Generate a single trace by concatenating `num_intents` independent walks.
    A shared visited set is passed across intents to ensure no tool appears twice in the trace.
    """
    trace: TRACE = []
    visited: set[int] = set()
    for _ in range(num_intents):
        intent = utils.random_walk(
            tools, walk_steps=[walk_step], rng=rng, extra_turn_prob=0.0, visited=visited
        )
        if not intent:
            break
        trace.extend(intent)
    return trace


def print_stats(
    traces: list[TRACE],
    step_assignments: list[int],
    walk_steps: list[int],
    walk_steps_dist: list[float],
    num_intents: list[int],
    num_intents_dist: list[float],
):
    total = len(traces)
    pattern_counts: Counter = Counter(
        tuple(len(turn) for turn in trace) for trace in traces
    )

    print("\n=== Dataset Stats ===")
    print(f"Total traces: {total}\n")

    # --- num intents distribution ---
    print(
        f"{'Num Intents':<12} {'Requested':>10} {'Requested%':>11} {'Generated':>10} {'Generated%':>11}"
    )
    print("-" * 58)
    for n, req_pct in zip(num_intents, num_intents_dist):
        req_count = round(req_pct * total)
        gen_count = sum(v for p, v in pattern_counts.items() if len(p) == n)
        label = f"{n} intent" if n == 1 else f"{n} intents"
        print(
            f"  {label:<10} {req_count:>10}  {100 * req_pct:>9.1f}%  {gen_count:>10}  {100 * gen_count / total:>9.1f}%"
        )

    print()

    # --- walk steps distribution (per trace, not per turn) ---
    step_trace_counts: Counter = Counter(step_assignments)

    print(
        f"{'Walk Step':<12} {'Requested':>10} {'Requested%':>11} {'Generated':>10} {'Generated%':>11}"
    )
    print("-" * 58)
    for s, req_pct in zip(walk_steps, walk_steps_dist):
        req_count = round(req_pct * total)
        gen_count = step_trace_counts.get(s, 0)
        print(
            f"  step={s:<6}  {req_count:>10}  {100 * req_pct:>9.1f}%  {gen_count:>10}  {100 * gen_count / total:>9.1f}%"
        )

    print()

    # --- uniqueness ---
    trace_keys = [
        tuple(tuple(t.name for t in turn) for turn in trace) for trace in traces
    ]
    unique = len(set(trace_keys))
    print(f"Unique traces:     {unique:>6}  ({100 * unique / total:.1f}%)")
    print(
        f"Duplicate traces:  {total - unique:>6}  ({100 * (total - unique) / total:.1f}%)"
    )
    print()

    # --- intent pattern breakdown ---
    print("Traces by intent pattern (tools per turn):")
    col = max(len(str(list(p))) for p in pattern_counts)
    for pattern, count in sorted(
        pattern_counts.items(), key=lambda x: (len(x[0]), x[0])
    ):
        label = str(list(pattern))
        print(f"  {label:<{col}} : {count:>6}  ({100 * count / total:.1f}%)")


def make_assignments(pool: list, dist: list[float], total: int) -> list:
    """Pre-assign values from pool to `total` traces based on distribution."""
    counts = [round(p * total) for p in dist]
    counts[-1] += total - sum(counts)
    assignments = []
    for val, count in zip(pool, counts):
        assignments.extend([val] * count)
    return assignments


def main(
    graph_json_path: str,
    num_traces: int,
    walk_steps: list[int],
    walk_steps_dist: list[float],
    num_intents: list[int],
    num_intents_dist: list[float],
    random_seed: int = 42,
):
    if not os.path.exists(graph_json_path):
        raise FileNotFoundError(graph_json_path)
    if len(walk_steps) != len(walk_steps_dist):
        raise ValueError("walk_steps and walk_steps_dist must have the same length")
    if abs(sum(walk_steps_dist) - 1.0) > 1e-6:
        raise ValueError(f"walk_steps_dist must sum to 1.0, got {sum(walk_steps_dist)}")
    if len(num_intents) != len(num_intents_dist):
        raise ValueError("num_intents and num_intents_dist must have the same length")
    if abs(sum(num_intents_dist) - 1.0) > 1e-6:
        raise ValueError(
            f"num_intents_dist must sum to 1.0, got {sum(num_intents_dist)}"
        )

    tools: list[Tool] = utils.load_graph_tools(graph_json_path)
    rng = random.Random(random_seed)

    step_assignments = make_assignments(walk_steps, walk_steps_dist, num_traces)
    intent_assignments = make_assignments(num_intents, num_intents_dist, num_traces)
    rng.shuffle(step_assignments)
    rng.shuffle(intent_assignments)

    traces: list[TRACE] = []
    for step, n_intents in zip(step_assignments, intent_assignments):
        trace = generate_trace(tools, walk_step=step, num_intents=n_intents, rng=rng)
        traces.append(trace)

    # Deduplicate traces (preserve first occurrence, maintain order)
    seen: set = set()
    unique_traces: list[TRACE] = []
    for trace in traces:
        key = tuple(tuple(t.name for t in turn) for turn in trace)
        if key not in seen:
            seen.add(key)
            unique_traces.append(trace)

    out_path = os.path.join(
        "output",
        "traces",
        os.path.basename(graph_json_path).replace(".json", "_traces.json"),
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    json_traces = [
        [[asdict(tool) for tool in turn] for turn in trace] for trace in unique_traces
    ]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(json_traces, f, indent=2, ensure_ascii=False)

    config_path = out_path.replace("_traces.json", "_traces_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "graph_json_path": graph_json_path,
                "num_traces": num_traces,
                "walk_steps": walk_steps,
                "walk_steps_dist": walk_steps_dist,
                "num_intents": num_intents,
                "num_intents_dist": num_intents_dist,
                "random_seed": random_seed,
                "num_unique_traces_saved": len(unique_traces),
            },
            f,
            indent=2,
        )

    print(
        f"Saved {len(unique_traces)} unique TRACEs (removed {len(traces) - len(unique_traces)} duplicates) to {out_path}"
    )
    print(f"Saved run config to {config_path}")
    print_stats(
        traces,
        step_assignments,
        walk_steps,
        walk_steps_dist,
        num_intents,
        num_intents_dist,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph_json_path", required=True)
    parser.add_argument("--num-traces", type=int, default=50)
    parser.add_argument("--walk-steps", nargs="+", type=int, default=[2, 3, 4])
    parser.add_argument(
        "--walk-steps-dist", nargs="+", type=float, default=[0.5, 0.3, 0.2]
    )
    parser.add_argument("--num-intents", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument(
        "--num-intents-dist", nargs="+", type=float, default=[0.6, 0.3, 0.1]
    )
    parser.add_argument("--random-seed", type=int, default=10)
    args = parser.parse_args()
    print(args)
    main(
        args.graph_json_path,
        args.num_traces,
        walk_steps=args.walk_steps,
        walk_steps_dist=args.walk_steps_dist,
        num_intents=args.num_intents,
        num_intents_dist=args.num_intents_dist,
        random_seed=args.random_seed,
    )
