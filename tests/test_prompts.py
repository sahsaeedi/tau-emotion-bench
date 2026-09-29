"""τ-bench prompting (config.TAU_BENCH_PROMPTS, per run via
TextRunConfig.tau_bench_prompts): the prompts must match τ-bench's, the setting
TRACER verified the tasks in, and turning it off must restore upstream tau2's."""

import pytest

from tau_emotion.agent.llm_agent import LLMAgent
from tau_emotion.config import TAU_BENCH_PROMPTS
from tau_emotion.data_model.simulation import Info, TextRunConfig
from tau_emotion.data_model.tasks import UserScenario
from tau_emotion.registry import registry
from tau_emotion.runner.build import build_text_orchestrator, build_user
from tau_emotion.runner.helpers import get_info, get_tasks, make_run_name
from tau_emotion.user.user_simulator import STOP, UNSATISFIED, UserSimulator
from tau_emotion.utils.pydantic_utils import get_pydantic_hash


@pytest.fixture
def airline_task():
    return get_tasks("airline", task_split_name="base")[0]


def test_scenario_renders_tau_bench_instruction_format():
    scenario = UserScenario(
        instructions="You are Daiki Muller, and you want to book a flight.",
        emotion_instruction="You're thrilled about this.",
    )
    assert scenario.to_tau_bench_instruction() == (
        "You are Daiki Muller, and you want to book a flight.\n"
        "Emotion Instruction: You're thrilled about this."
    )


@pytest.mark.parametrize("tau_bench", [True, False])
def test_agent_system_prompt(tau_bench):
    env = registry.get_env_constructor("airline")()
    agent = LLMAgent(
        tools=env.get_tools(),
        domain_policy=env.get_policy(),
        llm="x",
        tau_bench_prompts=tau_bench,
    )
    if tau_bench:
        assert agent.system_prompt == env.get_policy()
    else:
        assert "<policy>" in agent.system_prompt


@pytest.mark.parametrize("tau_bench", [True, False])
def test_user_system_prompt(airline_task, tau_bench):
    env = registry.get_env_constructor("airline")()
    user = build_user(
        "user_simulator", env, airline_task, llm="x", tau_bench_prompts=tau_bench
    )
    prompt = user.system_prompt
    if tau_bench:
        assert prompt.startswith(
            "You are a user interacting with an agent.\n\nInstruction: "
        )
        assert airline_task.user_scenario.to_tau_bench_instruction() in prompt
        assert STOP in prompt and UNSATISFIED in prompt
    else:
        assert "<scenario>" in prompt


@pytest.mark.parametrize("tau_bench", [True, False])
def test_agent_context_starts_with_user_in_tau_bench_mode(airline_task, tau_bench):
    config = TextRunConfig(
        domain="airline", llm_agent="x", llm_user="x", tau_bench_prompts=tau_bench
    )
    orchestrator = build_text_orchestrator(config, airline_task, seed=1)
    orchestrator.initialize()
    greeting_in_agent_context = len(orchestrator.agent_state.messages) > 0
    assert greeting_in_agent_context is not tau_bench
    # The user simulator is seeded with the greeting either way, as in τ-bench.
    assert orchestrator.trajectory[0].content == "Hi! How can I help you today?"


def test_run_config_default_follows_config():
    assert TextRunConfig(domain="airline").tau_bench_prompts is TAU_BENCH_PROMPTS


@pytest.mark.parametrize("tau_bench", [True, False])
def test_setting_is_recorded_and_named(tau_bench):
    config = TextRunConfig(domain="airline", llm_agent="m", tau_bench_prompts=tau_bench)
    assert get_info(config).tau_bench_prompts is tau_bench
    assert make_run_name(config).endswith("tau2-prompts") is not tau_bench
    assert isinstance(UserSimulator(llm="x").tau_bench_prompts, bool)


@pytest.mark.parametrize("agent_prompt", [None, "tau", "tau2"])
def test_agent_prompt_changes_only_the_agent(airline_task, agent_prompt):
    config = TextRunConfig(
        domain="airline",
        llm_agent="m",
        llm_user="x",
        tau_bench_prompts=True,
        agent_prompt=agent_prompt,
    )
    orchestrator = build_text_orchestrator(config, airline_task, seed=1)
    tau2_agent = agent_prompt == "tau2"
    agent_prompt_text = orchestrator.agent.system_prompt
    assert ("<policy>" in agent_prompt_text) is tau2_agent
    # The user simulator and the conversation flow stay τ-bench's.
    assert orchestrator.user.system_prompt.startswith(
        "You are a user interacting with an agent."
    )
    info = get_info(config)
    assert info.tau_bench_prompts is True
    # Only a departure from tau_bench_prompts is recorded and named, so runs
    # saved before this option resume as before.
    assert info.agent_prompt == ("tau2" if tau2_agent else None)
    assert make_run_name(config).endswith("tau2-agent-prompt") is tau2_agent


def test_results_saved_under_the_old_names_still_load():
    """Older results store `v1_compat_prompts` and agent_prompt 'v1'."""
    config = TextRunConfig(
        domain="airline", llm_agent="m", tau_bench_prompts=False, agent_prompt="tau"
    )
    info = get_info(config)
    saved = info.model_dump(mode="json")
    saved["v1_compat_prompts"] = saved.pop("tau_bench_prompts")
    saved["agent_prompt"] = "v1"
    loaded = Info.model_validate(saved)
    assert loaded.tau_bench_prompts is False
    assert loaded.agent_prompt == "tau"
    assert "v1_compat_prompts" not in loaded.model_dump()
    # The resume check compares hashes of the saved and the new Info.
    assert get_pydantic_hash(loaded) == get_pydantic_hash(info)
    old_config = TextRunConfig.model_validate(
        {"domain": "airline", "v1_compat_prompts": False, "agent_prompt": "v1"}
    )
    assert old_config.agent_prompt_override == "tau"
