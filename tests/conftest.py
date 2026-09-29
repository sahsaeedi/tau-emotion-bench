import os
from typing import Callable

import pytest

from tau_emotion.data_model.tasks import Task
from tau_emotion.environment.environment import Environment
from tau_emotion.registry import registry
from tau_emotion.run import get_tasks

# The LLM that tests marked `llm` call. Point it at a model your key can reach,
# e.g. TAU_EMOTION_TEST_LLM=qwen3-235b-a22b-instruct-2507 with OPENAI_API_BASE set.
TEST_LLM = os.environ.get("TAU_EMOTION_TEST_LLM", "gpt-4.1-mini")


def pytest_collection_modifyitems(config, items):
    """Skip the tests that call an LLM when no API key is set."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and not key.startswith(
        "<"
    ):  # .env.example's placeholder is "<your_key_here>"
        return
    skip = pytest.mark.skip(reason="calls an LLM; set OPENAI_API_KEY to run it")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def domain_name():
    return "mock"


@pytest.fixture
def get_environment() -> Callable[[], Environment]:
    return registry.get_env_constructor("mock")


@pytest.fixture
def base_task() -> Task:
    return get_tasks("mock", task_ids=["create_task_1"])[0]


@pytest.fixture
def task_with_env_assertions() -> Task:
    return get_tasks("mock", task_ids=["create_task_1_with_env_assertions"])[0]


@pytest.fixture
def task_with_message_history() -> Task:
    return get_tasks("mock", task_ids=["update_task_with_message_history"])[0]


@pytest.fixture
def task_with_initialization_data() -> Task:
    return get_tasks("mock", task_ids=["update_task_with_initialization_data"])[0]


@pytest.fixture
def task_with_initialization_actions() -> Task:
    return get_tasks("mock", task_ids=["update_task_with_initialization_actions"])[0]


@pytest.fixture
def task_with_history_and_env_assertions() -> Task:
    return get_tasks("mock", task_ids=["update_task_with_history_and_env_assertions"])[
        0
    ]


@pytest.fixture
def task_with_user_tools() -> Task:
    return get_tasks("mock", task_ids=["update_task_with_user_tools"])[0]


@pytest.fixture
def task_with_action_checks() -> Task:
    return get_tasks("mock", task_ids=["impossible_task_1"])[0]
