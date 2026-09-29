"""Metrics and rescoring scripts: user_unsatisfied runs and train-split tasks."""

import json
import re

from tau_emotion.data_model.message import AssistantMessage, ToolCall
from tau_emotion.data_model.simulation import (
    Info,
    Results,
    RewardInfo,
    SimulationRun,
    TerminationReason,
    UserInfo,
)
from tau_emotion.data_model.tasks import EvaluationCriteria, Task, UserScenario
from tau_emotion.environment.environment import EnvironmentInfo
from tau_emotion.metrics.agent_metrics import compute_metrics
from tau_emotion.registry import registry
from tau_emotion.scripts.evaluate_trajectories import compute_simulation_rewards
from tau_emotion.scripts.recombine_rewards import recombine_results
from tau_emotion.utils.display import ConsoleDisplay


def _info(domain: str = "mock") -> Info:
    return Info(
        git_commit="abc123",
        num_trials=1,
        max_steps=100,
        max_errors=100,
        user_info=UserInfo(implementation="user_simulator"),
        agent_info={"implementation": "llm_agent"},
        environment_info=EnvironmentInfo(domain_name=domain, policy="test policy"),
    )


def _task(task_id: str) -> Task:
    return Task(
        id=task_id,
        user_scenario=UserScenario(instructions="test instruction"),
        evaluation_criteria=EvaluationCriteria(),
    )


def _sim(
    task_id: str,
    termination_reason: TerminationReason,
    reward: float,
    messages: list | None = None,
) -> SimulationRun:
    return SimulationRun(
        id=f"sim-{task_id}",
        task_id=task_id,
        start_time="2026-01-01T00:00:00",
        end_time="2026-01-01T00:01:00",
        duration=60.0,
        termination_reason=termination_reason,
        reward_info=RewardInfo(reward=reward),
        messages=messages or [],
        trial=0,
        seed=42,
    )


def _unsatisfied_results() -> Results:
    ends = [
        (TerminationReason.USER_STOP, 1.0),
        (TerminationReason.AGENT_STOP, 0.0),
        (TerminationReason.USER_UNSATISFIED, -1.0),
        (TerminationReason.USER_UNSATISFIED, -1.0),
        (TerminationReason.MAX_STEPS, 0.0),
    ]
    return Results(
        info=_info(),
        tasks=[_task(f"t{i}") for i in range(len(ends))],
        simulations=[_sim(f"t{i}", end, r) for i, (end, r) in enumerate(ends)],
    )


def test_metrics_count_user_giving_up():
    metrics = compute_metrics(_unsatisfied_results())
    assert metrics.termination_user_unsatisfied == 2
    assert metrics.termination_user_stop == 1
    assert metrics.termination_agent_stop == 1
    assert metrics.termination_max_steps == 1
    assert metrics.avg_reward == -0.2


def test_display_shows_user_giving_up():
    metrics = compute_metrics(_unsatisfied_results())
    with ConsoleDisplay.console.capture() as capture:
        ConsoleDisplay.display_agent_metrics(metrics)
    assert re.search(r"User Gave Up\s+2\b", capture.get())


def test_recombine_keeps_minus_one_for_user_giving_up(tmp_path):
    results = Results(
        info=_info(),
        tasks=[_task("t0"), _task("t1")],
        simulations=[
            _sim("t0", TerminationReason.USER_UNSATISFIED, -1.0),
            _sim("t1", TerminationReason.MAX_STEPS, 0.5),
        ],
    )
    path = tmp_path / "results.json"
    results.save(path, format="json")

    recombine_results(str(tmp_path))

    rewards = {
        s["task_id"]: s["reward_info"]["reward"]
        for s in json.loads(path.read_text())["simulations"]
    }
    assert rewards == {"t0": -1.0, "t1": 0.0}


def test_evaluate_trajs_scores_train_tasks_on_train_db():
    """A perfect run of a train task scores 1. Its records exist only in
    db_train.json, so replaying it on db.json would fail."""
    task = registry.get_tasks_loader("bank")("train")[0]
    assert task.split == "train"
    env = registry.get_env_constructor("bank")(db_split="train")
    messages = []
    for i, action in enumerate(task.evaluation_criteria.actions):
        tool_call = ToolCall(
            id=str(i),
            name=action.name,
            arguments=action.arguments,
            requestor=action.requestor,
        )
        messages.append(
            AssistantMessage(role="assistant", content=None, tool_calls=[tool_call])
        )
        messages.append(env.get_response(tool_call))
    assert task.evaluation_criteria.communicate_info in (None, [])
    results = Results(
        info=_info("bank"),
        tasks=[task],
        simulations=[_sim(task.id, TerminationReason.USER_STOP, 0.0, messages)],
    )

    rescored = compute_simulation_rewards(results)

    assert rescored.simulations[0].reward_info.reward == 1.0
