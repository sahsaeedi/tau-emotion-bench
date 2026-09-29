import pytest
from conftest import TEST_LLM

from tau_emotion.data_model.message import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau_emotion.environment.tool import Tool, as_tool
from tau_emotion.utils.llm_utils import generate


@pytest.fixture
def model() -> str:
    return TEST_LLM


@pytest.fixture
def messages() -> list[Message]:
    messages = [
        SystemMessage(role="system", content="You are a helpful assistant."),
        UserMessage(role="user", content="What is the capital of the moon?"),
    ]
    return messages


@pytest.fixture
def tool() -> Tool:
    def calculate_square(x: int) -> int:
        """Calculate the square of a number.
            Args:
            x (int): The number to calculate the square of.
        Returns:
            int: The square of the number.
        """
        return x * x

    return as_tool(calculate_square)


@pytest.fixture
def tool_call_messages() -> list[Message]:
    messages = [
        SystemMessage(role="system", content="You are a helpful assistant."),
        UserMessage(
            role="user",
            content="What is the square of 5? Just give me the number, no explanation.",
        ),
    ]
    return messages


@pytest.mark.llm
def test_generate_no_tool_call(model: str, messages: list[Message]):
    response = generate(model, messages)
    assert isinstance(response, AssistantMessage)
    assert response.content is not None


@pytest.mark.llm
def test_generate_tool_call(model: str, tool_call_messages: list[Message], tool: Tool):
    response = generate(model, tool_call_messages, tools=[tool])
    assert isinstance(response, AssistantMessage)
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calculate_square"
    assert response.tool_calls[0].arguments == {"x": 5}
    follow_up_messages = [
        response,
        ToolMessage(role="tool", id=response.tool_calls[0].id, content="25"),
    ]
    response = generate(
        model,
        tool_call_messages + follow_up_messages,
        tools=[tool],
    )
    assert isinstance(response, AssistantMessage)
    assert response.tool_calls is None
    assert response.content == "25"


@pytest.mark.parametrize(
    "content, expected",
    [
        (None, None),
        ("", ""),
        ("Hello there.", "Hello there."),
        ("<|channel>thought\nThe user wants X.<channel|>Hello there.", "Hello there."),
        ("The user wants X.\n</think>\n\nHello there.", "Hello there."),
        ("<think>The user wants X.</think>Hello there.", "Hello there."),
    ],
)
def test_strip_reasoning(content, expected):
    from tau_emotion.utils.llm_utils import strip_reasoning

    assert strip_reasoning(content) == expected


@pytest.mark.parametrize(
    "model, expected",
    [
        ("qwen3-235b-a22b-instruct-2507", "openai/qwen3-235b-a22b-instruct-2507"),
        ("hosted_vllm/qwen3-8b", "hosted_vllm/qwen3-8b"),
        ("gpt-4.1-2025-04-14", "gpt-4.1-2025-04-14"),
        ("claude-opus-4-5", "claude-opus-4-5"),
    ],
)
def test_resolve_model(model, expected):
    from tau_emotion.utils.llm_utils import resolve_model

    assert resolve_model(model) == expected
