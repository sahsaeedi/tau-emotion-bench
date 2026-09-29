"""Scoring of runs that ended before the task was finished."""

import pytest

from tau_emotion.data_model.simulation import SimulationRun, TerminationReason
from tau_emotion.data_model.tasks import EvaluationCriteria, Task, UserScenario
from tau_emotion.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau_emotion.metrics.agent_metrics import is_successful


def _task() -> Task:
    return Task(
        id="t0",
        user_scenario=UserScenario(instructions="test instruction"),
        evaluation_criteria=EvaluationCriteria(),
    )


def _simulation(termination_reason: TerminationReason) -> SimulationRun:
    return SimulationRun(
        id="sim-t0",
        task_id="t0",
        start_time="2026-01-01T00:00:00",
        end_time="2026-01-01T00:01:00",
        duration=60.0,
        termination_reason=termination_reason,
        messages=[],
        trial=0,
        seed=42,
    )


def _reward(termination_reason: TerminationReason) -> float:
    return evaluate_simulation(
        simulation=_simulation(termination_reason),
        task=_task(),
        evaluation_type=EvaluationType.ALL,
        solo_mode=False,
        domain="mock",
    ).reward


def test_user_giving_up_scores_minus_one():
    """###UNSATISFIED### is penalised with reward -1."""
    assert _reward(TerminationReason.USER_UNSATISFIED) == -1.0
    assert not is_successful(-1.0)


@pytest.mark.parametrize(
    "termination_reason",
    [TerminationReason.MAX_STEPS, TerminationReason.TOO_MANY_ERRORS],
)
def test_other_early_endings_still_score_zero(termination_reason: TerminationReason):
    assert _reward(termination_reason) == 0.0
