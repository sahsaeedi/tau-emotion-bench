import importlib.util
import json
from pathlib import Path

from tau_emotion.data_model.message import (
    AssistantMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
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
from tau_emotion.scripts import submission, user_sim_check
from tau_emotion.scripts.submission import (
    REQUIRED_USER_LLM,
    Contact,
    Methodology,
    Submission,
    benchmark_domains,
    check_results,
    compute_results,
    load_results,
    rescore,
    submission_id,
    user_llm_name,
    with_task_results,
    write_leaderboard,
    write_trajectories,
)
from tau_emotion.user.user_simulator import get_global_user_sim_guidelines


def domain_run(domain: str = "airline", user_llm_args: dict | None = None) -> Results:
    """A run with every leaderboard setting, built without running anything."""
    tasks = registry.get_tasks_loader(domain)("base")
    info = Info(
        git_commit="abc",
        num_trials=3,
        max_steps=200,
        max_errors=10,
        user_info=UserInfo(
            implementation="user_simulator",
            llm=f"openai/{REQUIRED_USER_LLM}",
            llm_args=user_llm_args or {"temperature": 0.0},
            global_simulation_guidelines=get_global_user_sim_guidelines(),
        ),
        agent_info=AgentInfo(implementation="llm_agent", llm="qwen3-8b"),
        environment_info=EnvironmentInfo(
            domain_name=domain,
            policy=registry.get_env_constructor(domain)().get_policy(),
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
    assert user_llm_name("openai/glm-5-2") == "glm-5.2"


def test_leaderboard_settings_pass():
    run = domain_run(user_llm_args={"temperature": 0.0, "api_base": "http://host/v1"})
    errors = check_results([run])
    # Only the other nine domains are missing.
    assert len(errors) == 1 and "missing domains" in errors[0]
    assert "airline" not in errors[0]


def test_wrong_user_temperature_fails():
    errors = check_results([domain_run(user_llm_args={"temperature": 0.7})])
    assert any("user simulator args" in e for e in errors)


def test_too_few_trials_fails():
    run = domain_run()
    run.info.num_trials = 2
    assert any("need at least 3" in e for e in check_results([run]))


def test_infrastructure_errors_fail():
    run = domain_run()
    run.simulations[0].termination_reason = TerminationReason.INFRASTRUCTURE_ERROR
    errors = check_results([run])
    assert any("infrastructure errors" in e for e in errors)
    assert any("1 tasks without 3 trials" in e for e in errors)


def test_scores_per_domain_and_averages():
    airline = domain_run("airline")
    retail = domain_run("retail")
    # Retail succeeds on every trial.
    for sim in retail.simulations:
        sim.reward_info = RewardInfo(reward=1.0)
    scores = compute_results([airline, retail])[REQUIRED_USER_LLM]
    assert scores.domains["airline"].pass_1 == 66.67
    assert scores.domains["airline"].pass_3 == 0.0
    assert scores.domains["airline"].avg_reward == 0.6667
    assert scores.domains["retail"].pass_3 == 100.0
    # Each domain counts once, whatever its number of tasks.
    assert scores.avg_at_3 == round((200 / 3 + 100) / 2, 2)
    assert scores.avg_hat_3 == 50.0
    # Trials solved per task, every task of every domain
    assert len(scores.tasks) == len(airline.tasks) + len(retail.tasks)
    assert scores.tasks[airline.tasks[0].id] == 2
    assert scores.tasks[retail.tasks[0].id] == 3


def test_rescore_catches_edited_rewards():
    # No conversation took place, so no task can be done.
    runs = [domain_run("airline"), domain_run("retail")]
    for run in runs:
        run.simulations = run.simulations[:6]  # two tasks, three trials each
    rescored, changed = rescore(runs)
    assert all(s.reward_info.reward == 0.0 for r in rescored for s in r.simulations)
    assert changed == 2 * 4


def _submission(all_results: list[Results], submission_type: str) -> Submission:
    return Submission(
        model_name="qwen3-8b",
        model_organization="Qwen",
        submitting_organization="ASU",
        submission_date="2026-10-14",
        submission_type=submission_type,
        contact=Contact(name="A", email="a@b.c"),
        trajectories_url="https://example.com",
        results=compute_results(all_results),
        methodology=Methodology(
            benchmark_version="0",
            benchmark_commit="abc",
            agent_implementation="my_agent",
            user_simulator_provider="ASU",
        ),
    )


def test_custom_agent_must_be_custom_submission(tmp_path, monkeypatch):
    all_results = [domain_run(d) for d in benchmark_domains()]
    for results in all_results:
        results.info.agent_info.implementation = "my_agent"
    runs = [str(tmp_path / str(i)) for i in range(len(all_results))]
    for run, results in zip(runs, all_results):
        results.save(f"{run}/results.json", format="dir")
    # The runs' saved rewards stand: this test is about the submission type.
    monkeypatch.setattr(submission, "rescore", lambda all_results: (all_results, 0))

    path = tmp_path / "submission.json"
    path.write_text(_submission(all_results, "standard").model_dump_json())
    assert not submission.validate(str(path), runs)

    custom = _submission(all_results, "custom")
    custom.methodology.notes = "a ReAct loop"
    custom.methodology.references = ["https://example.com/code"]
    path.write_text(custom.model_dump_json())
    assert submission.validate(str(path), runs)


def conversation() -> SimulationRun:
    messages = [
        AssistantMessage(role="assistant", content="Hi! How can I help you today?"),
        UserMessage(role="user", content="I want to cancel my flight."),
        AssistantMessage(
            role="assistant",
            tool_calls=[ToolCall(id="1", name="get_reservation", arguments={})],
        ),
        ToolMessage(id="1", role="tool", content="{}", requestor="assistant"),
        AssistantMessage(role="assistant", content="Which reservation?"),
        UserMessage(role="user", content="The one to Boston, please."),
    ]
    return SimulationRun(
        id="s",
        task_id="t",
        start_time="2026-01-01T00:00:00",
        end_time="2026-01-01T00:01:00",
        duration=60.0,
        termination_reason=TerminationReason.USER_STOP,
        messages=messages,
    )


def test_user_sim_prompt_is_what_the_simulator_saw():
    task = registry.get_tasks_loader("airline")("base")[0]
    messages = user_sim_check.user_sim_prompt(conversation(), task)
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert task.user_scenario.to_tau_bench_instruction() in messages[0]["content"]
    assert messages[2]["content"] == "I want to cancel my flight."


def chatml(messages):
    return "".join(f"<|{m['role']}|>\n{m['content']}<|end|>\n" for m in messages)


def test_score_simulation_counts_top_choices_in_user_turns(monkeypatch):
    def fake_server(model, prompt, api_base, api_key):
        # One token per word, all the top choice but two
        tokens, offset = [], 0
        for word in prompt.split(" "):
            tokens.append((offset, 2 if word in ("cancel", "Boston,") else 1))
            offset += len(word) + 1
        return tokens

    monkeypatch.setattr(user_sim_check, "chat_template", lambda repo: chatml)
    monkeypatch.setattr(user_sim_check, "prompt_token_ranks", fake_server)
    task = registry.get_tasks_loader("airline")("base")[0]
    n_tokens, n_top, missing = user_sim_check.score_simulation(
        conversation(), task, REQUIRED_USER_LLM, "http://host/v1", "key"
    )
    # Words of the two user turns, less the first of each, which shares a token
    # with the role tag before it
    assert (n_tokens, n_top, missing) == (9, 7, 0)


def test_trajectory_zips_round_trip(tmp_path):
    airline, retail = domain_run("airline"), domain_run("retail")
    reasoning = {"choices": [{"message": {"reasoning_content": "Be curt."}}]}
    airline.simulations[0].messages = [
        AssistantMessage(role="assistant", content="Hi!", raw_data={"id": "x"}),
        UserMessage(role="user", content="Cancel it.", raw_data=reasoning),
    ]
    (path,) = write_trajectories([airline, retail], tmp_path)
    assert path.name == "trajectories.zip"
    loaded = {r.info.environment_info.domain_name: r for r in load_results([str(path)])}
    assert loaded.keys() == {"airline", "retail"}
    messages = loaded["airline"].simulations[0].messages
    # The raw responses are dropped, all but the user simulator's reasoning.
    assert messages[0].raw_data is None and messages[1].raw_data == reasoning
    assert loaded["retail"].simulations == retail.simulations
    assert check_results(list(loaded.values())) == check_results([airline, retail])

    parts = write_trajectories([airline, retail], tmp_path, limit=1)
    assert [p.name for p in parts] == ["trajectories-1.zip", "trajectories-2.zip"]
    assert len(load_results([str(p) for p in parts])) == 2


def test_leaderboard_lists_submissions_best_first(tmp_path):
    runs = [domain_run("airline")]
    worse = _submission(runs, "standard")
    better = _submission(runs, "standard")
    better.model_name = "Better Model 2"
    better.results[REQUIRED_USER_LLM].avg_at_3 = 99.0
    for entry in (worse, better):
        path = tmp_path / submission_id(entry) / "submission.json"
        path.parent.mkdir()
        path.write_text(entry.model_dump_json())
    entries = json.loads(write_leaderboard(str(tmp_path)).read_text())
    assert [e["id"] for e in entries] == [
        "better-model-2_qwen_2026-10-14",
        "qwen3-8b_qwen_2026-10-14",
    ]
    assert "contact" not in entries[0]


def submission_issue_script():
    path = Path(__file__).parents[1] / ".github/scripts/submission_issue.py"
    spec = importlib.util.spec_from_file_location("submission_issue", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_issue_form_is_parsed():
    script = submission_issue_script()
    body = """### Model

Qwen3-8B, Qwen

### submission.json

```json
{"model_name": "qwen3-8b"}
```

### Trajectories

[trajectories-1.zip](https://github.com/user-attachments/files/123/trajectories-1.zip)
[trajectories-2.zip](https://github.com/user-attachments/files/124/trajectories-2.zip)

### Trajectories link

_No response_
"""
    fields = script.parse_form(body)
    assert fields["Model"] == "Qwen3-8B, Qwen"
    assert json.loads(script.submission_json(fields)) == {"model_name": "qwen3-8b"}
    assert script.trajectory_urls(fields) == [
        "https://github.com/user-attachments/files/123/trajectories-1.zip",
        "https://github.com/user-attachments/files/124/trajectories-2.zip",
    ]


def test_thinking_default_comes_from_the_agent_args():
    thinking = {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
    assert submission._thinking(thinking)
    assert submission._thinking({"extra_body": {"reasoning_effort": "high"}})
    assert not submission._thinking({"temperature": 0.0})
    assert not submission._thinking(None)


def test_accepting_takes_task_results_from_the_trajectories():
    airline = domain_run("airline")
    scores = compute_results([airline])[REQUIRED_USER_LLM]
    # The submitter's file claims every task was solved three times
    claimed = scores.model_copy(update={"tasks": {t: 3 for t in scores.tasks}})
    submission = Submission(
        model_name="m",
        model_organization="o",
        submitting_organization="self",
        submission_date="2026-01-01",
        contact=Contact(name="n", email="e@x.org"),
        results={REQUIRED_USER_LLM: claimed},
        methodology=Methodology(
            benchmark_version="1",
            benchmark_commit="abc",
            agent_implementation="llm_agent",
            user_simulator_provider="own",
        ),
    )
    accepted = with_task_results(submission, [airline])
    assert accepted.results[REQUIRED_USER_LLM].tasks == scores.tasks
    assert accepted.results[REQUIRED_USER_LLM].tasks[airline.tasks[0].id] == 2
    assert accepted.results[REQUIRED_USER_LLM].domains == scores.domains
