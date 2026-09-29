"""τ-bench runtime conventions the orchestrator follows.

The prompt side is covered in test_prompts.py. These tests cover
what τ-bench does while a conversation runs: it keeps only the first of
several tool calls, it passes an empty model reply on to the user, and it ends
the conversation as soon as the agent transfers to a human.
"""

from typing import Callable

import pytest

from tau_emotion.agent.llm_agent import LLMAgent
from tau_emotion.config import TERMINATE_TOOLS
from tau_emotion.data_model.message import AssistantMessage, ToolCall
from tau_emotion.data_model.simulation import TerminationReason
from tau_emotion.data_model.tasks import Task
from tau_emotion.environment.environment import Environment
from tau_emotion.orchestrator.orchestrator import Orchestrator, Role
from tau_emotion.registry import registry
from tau_emotion.user.user_simulator import DummyUser


def _tool_call(name: str, call_id: str = "1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments={})


def test_only_the_first_tool_call_is_kept():
    message = AssistantMessage(
        role="assistant",
        content=None,
        tool_calls=[_tool_call("get_task", "1"), _tool_call("update_task", "2")],
    )
    Orchestrator._apply_tau_bench_message_conventions(message)
    assert [tool_call.id for tool_call in message.tool_calls] == ["1"]


def test_a_single_tool_call_is_left_alone():
    message = AssistantMessage(
        role="assistant", content=None, tool_calls=[_tool_call("get_task")]
    )
    Orchestrator._apply_tau_bench_message_conventions(message)
    assert len(message.tool_calls) == 1


@pytest.mark.parametrize("content", [None, "", "   "])
def test_an_empty_reply_becomes_an_empty_message(content):
    message = AssistantMessage(role="assistant", content=content)
    Orchestrator._apply_tau_bench_message_conventions(message)
    assert message.content == ""


def test_a_normal_reply_is_untouched():
    message = AssistantMessage(role="assistant", content="Hello")
    Orchestrator._apply_tau_bench_message_conventions(message)
    assert message.content == "Hello"


def test_an_empty_reply_stays_valid_in_the_request_history():
    """The next request carries the empty turn, so validation must allow it."""
    from tau_emotion.utils.llm_utils import to_litellm_messages, validate_message

    message = AssistantMessage(role="assistant", content="")
    validate_message(message)
    assert to_litellm_messages([message])[0]["content"] == ""


def test_reasoning_goes_back_with_the_next_request():
    from tau_emotion.utils.llm_utils import to_litellm_messages

    message = AssistantMessage(
        role="assistant",
        content="Booked.",
        raw_data={"choices": [{"message": {"reasoning_content": "thinking out loud"}}]},
    )
    assert to_litellm_messages([message])[0]["reasoning_content"] == "thinking out loud"


def test_a_message_without_reasoning_sends_no_reasoning_field():
    from tau_emotion.utils.llm_utils import to_litellm_messages

    message = AssistantMessage(role="assistant", content="Booked.")
    assert "reasoning_content" not in to_litellm_messages([message])[0]


def _orchestrator(
    domain_name: str,
    get_environment: Callable[[], Environment],
    task: Task,
) -> Orchestrator:
    environment = get_environment()
    agent = LLMAgent(
        tools=environment.get_tools(),
        domain_policy=environment.get_policy(),
        llm="gpt-4.1",
        llm_args={"temperature": 0.0},
    )
    orchestrator = Orchestrator(
        domain=domain_name,
        user=DummyUser(),
        agent=agent,
        environment=environment,
        task=task,
    )
    orchestrator.initialize()
    return orchestrator


def test_a_transfer_ends_the_conversation(
    domain_name: str,
    get_environment: Callable[[], Environment],
    base_task: Task,
):
    """τ-bench stops on a terminate tool and scores the run from there.

    The mock domain has no transfer tool, so the call itself comes back as an
    error; what this checks is that the call ends the conversation.
    """
    orchestrator = _orchestrator(domain_name, get_environment, base_task)
    transfer = next(iter(TERMINATE_TOOLS))
    orchestrator.message = AssistantMessage(
        role="assistant", content=None, tool_calls=[_tool_call(transfer)]
    )
    orchestrator.from_role = Role.AGENT
    orchestrator.to_role = Role.ENV

    orchestrator.step()

    assert orchestrator.done
    assert orchestrator.termination_reason == TerminationReason.AGENT_STOP


def test_an_ordinary_tool_call_does_not_end_the_conversation(
    domain_name: str,
    get_environment: Callable[[], Environment],
    base_task: Task,
):
    orchestrator = _orchestrator(domain_name, get_environment, base_task)
    orchestrator.message = AssistantMessage(
        role="assistant", content=None, tool_calls=[_tool_call("get_task")]
    )
    orchestrator.from_role = Role.AGENT
    orchestrator.to_role = Role.ENV

    orchestrator.step()

    assert not orchestrator.done
    assert orchestrator.termination_reason is None


def test_the_domains_that_tau_bench_stops_on_have_the_tool():
    """Every transfer tool τ-bench terminates on is named in the config set."""
    for domain, expected in (
        ("airline", "transfer_to_human_agents"),
        ("telehealth", "transfer_to_human_support"),
    ):
        environment = registry.get_env_constructor(domain)()
        tool_names = {tool.name for tool in environment.get_tools()}
        assert expected in tool_names
        assert expected in TERMINATE_TOOLS
