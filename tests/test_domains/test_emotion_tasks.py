"""Checks on the TRACER-generated task files shared by every emotion domain.

Each domain ships its test tasks in tasks.json and its training tasks in
tasks_train.json; every task's user carries an emotion instruction.
"""

import importlib
import inspect
import json

import pytest

from tau_emotion.environment.db import DB
from tau_emotion.registry import registry

EMOTION_DOMAINS = [
    "airline",
    "retail",
    "telecom",
    "telehealth",
    "bank",
    "basketball",
    "movie",
    "restaurant",
    "school",
    "travel",
]


def _environment(domain: str):
    return importlib.import_module(f"tau_emotion.domains.{domain}.environment")


def _dropped_field(raw, dumped, path=""):
    if isinstance(raw, dict) and isinstance(dumped, dict):
        for k, v in raw.items():
            if k not in dumped:
                return f"{path}.{k}"
            found = _dropped_field(v, dumped[k], f"{path}.{k}")
            if found:
                return found
    elif isinstance(raw, list) and isinstance(dumped, list):
        for i, (x, y) in enumerate(zip(raw, dumped)):
            found = _dropped_field(x, y, f"{path}[{i}]")
            if found:
                return found
    return None


def test_registry_lists_exactly_the_emotion_domains():
    assert set(registry.get_info().domains) == set(EMOTION_DOMAINS) | {"mock"}


@pytest.mark.parametrize("split", ["test", "train"])
@pytest.mark.parametrize("domain", EMOTION_DOMAINS)
def test_every_task_carries_emotion(domain: str, split: str):
    tasks = _environment(domain).get_tasks(split)

    assert tasks, f"{domain} has no {split} tasks"
    assert all(t.user_scenario.emotion_instruction for t in tasks)
    assert all("Emotion Instruction:" in str(t.user_scenario) for t in tasks)
    assert all(t.user_scenario.emotion_metadata for t in tasks)


@pytest.mark.parametrize("domain", EMOTION_DOMAINS)
def test_every_action_names_a_real_tool(domain: str):
    env = _environment(domain)
    tool_names = set(env.get_environment().tools.get_tools())
    used = {
        a.name for t in env.get_tasks("test") for a in t.evaluation_criteria.actions
    }
    assert used <= tool_names, f"unknown tools in {domain}: {sorted(used - tool_names)}"


@pytest.mark.parametrize("domain", EMOTION_DOMAINS)
def test_task_splits_match_the_task_file(domain: str):
    env = _environment(domain)
    splits = env.get_tasks_split()
    assert splits["base"] == [t.id for t in env.get_tasks("base")]
    assert splits["test"] == [t.id for t in env.get_tasks("test")]


@pytest.mark.parametrize("domain", EMOTION_DOMAINS)
def test_data_model_keeps_every_db_field(domain: str):
    """Sub-models ignore unknown keys, so a missing field would silently vanish
    from what the agent sees."""
    mod = importlib.import_module(f"tau_emotion.domains.{domain}.data_model")
    db_cls = next(
        obj
        for _, obj in inspect.getmembers(mod, inspect.isclass)
        if issubclass(obj, DB) and obj is not DB and obj.__module__ == mod.__name__
    )
    utils = importlib.import_module(f"tau_emotion.domains.{domain}.utils")
    db_path = next(v for k, v in vars(utils).items() if k.endswith("_DB_PATH"))
    raw = json.loads(db_path.read_text())
    assert _dropped_field(raw, db_cls.model_validate(raw).model_dump()) is None
