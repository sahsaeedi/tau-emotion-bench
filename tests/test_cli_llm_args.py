import argparse

import pytest

from tau_emotion.cli import _llm_args, add_run_args
from tau_emotion.runner.helpers import _without_api_key


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_run_args(parser)
    return parser.parse_args(list(argv))


def test_defaults_leave_llm_args_alone():
    args = parse()
    assert _llm_args(args, "agent") == {"temperature": 0.0}
    assert _llm_args(args, "user") == {"temperature": 0.7}


def test_agent_temperature_overrides_llm_args():
    args = parse(
        "--agent-llm-args",
        '{"temperature": 0.2, "top_p": 0.9}',
        "--agent-temperature",
        "0.6",
    )
    assert _llm_args(args, "agent") == {"temperature": 0.6, "top_p": 0.9}


@pytest.mark.parametrize("side, temperature", [("agent", 0.0), ("user", 0.7)])
def test_api_base_without_key_sends_no_real_key(side: str, temperature: float):
    args = parse(f"--{side}-api-base", "http://localhost:8000/v1")
    assert _llm_args(args, side) == {
        "temperature": temperature,
        "api_base": "http://localhost:8000/v1",
        "api_key": "EMPTY",
    }


def test_api_key_and_thinking_merge_into_llm_args():
    args = parse(
        "--agent-llm-args",
        '{"temperature": 0.5, "extra_body": {"skip_special_tokens": false}}',
        "--agent-api-base",
        "http://host/v1",
        "--agent-api-key",
        "secret",
        "--no-agent-enable-thinking",
    )
    assert _llm_args(args, "agent") == {
        "temperature": 0.5,
        "api_base": "http://host/v1",
        "api_key": "secret",
        "extra_body": {
            "skip_special_tokens": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }
    # The flags don't leak into the other side.
    assert _llm_args(args, "user") == {"temperature": 0.7}


def test_api_key_is_not_saved():
    assert _without_api_key({"api_key": "secret", "api_base": "x"}) == {"api_base": "x"}
    assert _without_api_key(None) is None
