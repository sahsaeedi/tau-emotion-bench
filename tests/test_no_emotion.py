import argparse

import pytest

from tau_emotion.cli import add_run_args
from tau_emotion.data_model.simulation import TextRunConfig
from tau_emotion.run import get_tasks
from tau_emotion.runner.build import build_environment, build_user
from tau_emotion.runner.helpers import get_info, make_run_name


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_run_args(parser)
    return parser.parse_args(list(argv))


def test_flag_defaults_off():
    assert parse().no_emotion is False
    assert parse("--no-emotion").no_emotion is True


@pytest.mark.parametrize("no_emotion", [False, True])
def test_user_gets_emotion_instruction_unless_disabled(no_emotion):
    task = get_tasks("airline")[0]
    assert task.user_scenario.emotion_instruction is not None
    user = build_user(
        "user_simulator",
        build_environment("airline"),
        task,
        llm="gpt-4.1",
        no_emotion=no_emotion,
    )
    assert ("Emotion Instruction" in user.instructions) is not no_emotion
    # The task itself keeps its emotion instruction for the results and review.
    assert task.user_scenario.emotion_instruction is not None


def test_no_emotion_runs_save_separately():
    assert make_run_name(TextRunConfig(domain="airline", no_emotion=True)).endswith(
        "_no-emotion"
    )
    assert "no-emotion" not in make_run_name(TextRunConfig(domain="airline"))


def test_no_emotion_is_saved_with_the_run():
    """The results record the setting, so a resume can't mix both kinds of run."""
    assert get_info(TextRunConfig(domain="mock", no_emotion=True)).user_info.no_emotion
    assert not get_info(TextRunConfig(domain="mock")).user_info.no_emotion
