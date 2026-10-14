from tau_emotion.data_model.simulation import (
    AgentInfo,
    Info,
    Results,
    RewardInfo,
    SimulationRun,
    TerminationReason,
    UserInfo,
)
from tau_emotion.environment.environment import EnvironmentInfo
from tau_emotion.registry import registry
from tau_emotion.scripts.submission import (
    REQUIRED_USER_LLM,
    check_results,
    compute_results,
    user_llm_name,
)
from tau_emotion.user.user_simulator import get_global_user_sim_guidelines


def airline_run(user_llm_args: dict) -> Results:
    """An airline run with every leaderboard setting, built without running anything."""
    tasks = registry.get_tasks_loader("airline")("base")
    info = Info(
        git_commit="abc",
        num_trials=3,
        max_steps=200,
        max_errors=10,
        user_info=UserInfo(
            implementation="user_simulator",
            llm=f"openai/{REQUIRED_USER_LLM}",
            llm_args=user_llm_args,
            global_simulation_guidelines=get_global_user_sim_guidelines(),
        ),
        agent_info=AgentInfo(implementation="llm_agent", llm="qwen3-8b"),
        environment_info=EnvironmentInfo(
            domain_name="airline",
            policy=registry.get_env_constructor("airline")().get_policy(),
        ),
    )
    # Each task fails its first trial and succeeds in the other two.
    sims = [
        SimulationRun(
            id=f"{t.id}-{trial}",
            task_id=t.id,
            start_time="2026-01-01T00:00:00",
            end_time="2026-01-01T00:01:00",
            duration=60.0,
            termination_reason=TerminationReason.USER_STOP,
            reward_info=RewardInfo(reward=1.0 if trial else 0.0),
            messages=[],
            trial=trial,
            seed=42,
        )
        for t in tasks
        for trial in range(3)
    ]
    return Results(info=info, tasks=tasks, simulations=sims)


def test_user_llm_name_drops_provider():
    assert (
        user_llm_name("openai/Qwen/Qwen3-235B-A22B-Instruct-2507") == REQUIRED_USER_LLM
    )


def test_leaderboard_settings_pass():
    run = airline_run({"temperature": 0.0, "api_base": "http://host/v1"})
    errors = check_results([run])
    # Only the other nine domains are missing.
    assert len(errors) == 1 and "missing domains" in errors[0]
    assert "airline" not in errors[0]


def test_wrong_user_temperature_fails():
    errors = check_results([airline_run({"temperature": 0.7})])
    assert any("user simulator args" in e for e in errors)


def test_scores_per_domain_and_overall():
    scores = compute_results([airline_run({"temperature": 0.0})])[REQUIRED_USER_LLM]
    assert scores["airline"] == scores["overall"]
    assert scores["airline"].pass_1 == 66.67
    assert scores["airline"].pass_3 == 0.0
    assert scores["airline"].avg_reward == 0.6667


def test_too_few_trials_fails():
    run = airline_run({"temperature": 0.0})
    run.info.num_trials = 2
    assert any("need at least 3" in e for e in check_results([run]))
