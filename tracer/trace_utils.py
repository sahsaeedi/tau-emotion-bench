import json
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Tool:
    idx: int
    name: str
    info: Dict[str, Any]
    is_root: Optional[bool] = None
    is_root_reason: Optional[str] = None
    neighbors: List[int] = field(default_factory=list)
    neighbor_reasons: Dict[int, str] = field(default_factory=dict)


TURN = List[Tool]  # one or more tools in a single "turn"
TRACE = List[TURN]  # sequence of turns


def load_graph_tools(json_path: str):
    """
    Load the tool graph from the JSON file produced by graph_builder.py.

    This populates each Tool with:
      - neighbors: list of neighbor tool indices
      - neighbor_reasons: mapping neighbor index -> textual reason for the edge
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tools_raw = data["tools"]
    adjacency_matrix = data["adjacency_matrix"]
    reason_matrix = data.get("reason_matrix", None)
    tools_is_root = data.get("is_root", None)
    tools_is_root_reason = data.get("is_root_reason", None)

    for i in range(len(adjacency_matrix)):
        if len(adjacency_matrix[i]) != len(tools_raw):
            raise ValueError(
                f"Adjacency matrix row {i} length mismatch: expected {len(tools_raw)}, got {len(adjacency_matrix[i])}"
            )
    for i in range(len(reason_matrix)):
        if len(reason_matrix[i]) != len(tools_raw):
            raise ValueError(
                f"Reason matrix row {i} length mismatch: expected {len(tools_raw)}, got {len(reason_matrix[i])}"
            )

    tools: List[Tool] = [
        Tool(idx=i, name=t["name"], info=t["info"], is_root=t_r, is_root_reason=t_rr)
        for i, (t, t_r, t_rr) in enumerate(
            zip(tools_raw, tools_is_root, tools_is_root_reason)
        )
    ]

    # Populate neighbor information directly on each Tool instance
    if adjacency_matrix is not None:
        for i, row in enumerate(adjacency_matrix):
            for j, is_neigh in enumerate(row):
                if not is_neigh:
                    continue
                tools[i].neighbors.append(j)
                if reason_matrix is not None:
                    # reason_matrix is expected to be aligned with adjacency_matrix
                    tools[i].neighbor_reasons[j] = reason_matrix[i][j]
    return tools


def random_walk(
    tools: List[Tool],
    walk_steps: List[int] = [1, 3],
    start_tool: Optional[Tool] = None,
    rng: random.Random = None,
    extra_turn_prob: float = 0.3,
    visited: Optional[set] = None,
) -> TRACE:
    """
    Simple random walk on neighbour graph starting from a given tool.

    - Uses Tool.neighbors (indices) to move.
    - Avoids loops: once a tool would be revisited, the walk stops.
    - Accepts an optional external `visited` set to prevent duplicates across intents.

    Returns an TRACE with shape: [[tool1], [tool2], ..., [toolH]].
    """
    if rng is None:
        rng = random

    if visited is None:
        visited = set()

    if start_tool is None:
        start_tools = [t for t in tools if t.is_root and t.idx not in visited]
        if not start_tools:
            return []
        current_idx = rng.choice(start_tools).idx
    else:
        current_idx = start_tool.idx

    visited.add(current_idx)

    trace_turn: TURN = [tools[current_idx]]
    trace: TRACE = []
    while True:
        steps = rng.choice(walk_steps)
        for _ in range(steps - 1):
            nbrs = tools[current_idx].neighbors
            if not nbrs:
                # dead end; stop the walk
                break

            # filter out already visited neighbors to avoid loops
            candidates = [j for j in nbrs if j not in visited]
            if not candidates:
                # all neighbors already visited -> adding any would create a loop
                break

            next_idx = rng.choice(candidates)

            current_idx = next_idx
            visited.add(current_idx)
            trace_turn.append(tools[current_idx])
        trace.append(trace_turn)
        trace_turn = []
        if rng.random() < extra_turn_prob:
            start_tools = [t for t in tools if t.is_root and t.idx not in visited]
            if not start_tools:
                break
            start_tool = rng.choice(start_tools)
            current_idx = start_tool.idx
            visited.add(current_idx)
            trace_turn.append(tools[current_idx])
        else:
            break

    return trace


def build_random_walks(
    tools: List[Tool],
    num_walks: int,
    walk_steps: List[int] = [1, 3],
    rng: Optional[random.Random] = None,
    extra_turn_prob: float = 0.3,
) -> List[TRACE]:
    """
    Build multiple random-walk TRACEs on the tool graph.
    """
    if rng is None:
        rng = random.Random(42)

    traces: List[TRACE] = []
    for _ in range(num_walks):
        trace = random_walk(
            tools, walk_steps=walk_steps, rng=rng, extra_turn_prob=extra_turn_prob
        )
        traces.append(trace)

    return traces
