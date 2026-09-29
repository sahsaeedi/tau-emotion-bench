"""τ-bench prompting: the agent and user-simulator prompts follow τ-bench's."""

import pytest

from tau_emotion.agent.llm_agent import LLMAgent
from tau_emotion.data_model.simulation import TextRunConfig
from tau_emotion.data_model.tasks import UserScenario
from tau_emotion.registry import registry
from tau_emotion.runner.build import build_text_orchestrator, build_user
from tau_emotion.runner.helpers import get_info, get_tasks
from tau_emotion.user.user_simulator import STOP, UNSATISFIED


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


def test_agent_system_prompt_is_the_policy():
    env = registry.get_env_constructor("airline")()
    agent = LLMAgent(tools=env.get_tools(), domain_policy=env.get_policy(), llm="x")
    assert agent.system_prompt == env.get_policy()


def test_user_system_prompt(airline_task):
    env = registry.get_env_constructor("airline")()
    user = build_user("user_simulator", env, airline_task, llm="x")
    prompt = user.system_prompt
    assert prompt.startswith(
        "You are a user interacting with an agent.\n\nInstruction: "
    )
    assert airline_task.user_scenario.to_tau_bench_instruction() in prompt
    assert STOP in prompt and UNSATISFIED in prompt


def test_agent_context_starts_with_the_user(airline_task):
    config = TextRunConfig(domain="airline", llm_agent="x", llm_user="x")
    orchestrator = build_text_orchestrator(config, airline_task, seed=1)
    orchestrator.initialize()
    assert orchestrator.agent_state.messages == []
    # Only the user simulator is seeded with the greeting, as in τ-bench.
    assert orchestrator.trajectory[0].content == "Hi! How can I help you today?"


def test_results_record_the_user_prompt():
    info = get_info(TextRunConfig(domain="airline", llm_agent="m"))
    guidelines = info.user_info.global_simulation_guidelines
    assert guidelines.startswith("You are a user interacting with an agent.\n")
    assert "Instruction:" not in guidelines
