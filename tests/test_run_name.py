from tau_emotion.data_model.simulation import TextRunConfig
from tau_emotion.runner.helpers import make_run_name


def test_run_name_is_domain_and_agent_model():
    config = TextRunConfig(
        domain="airline",
        llm_agent="qwen3-8b",
        llm_args_agent={
            "temperature": 0.0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
        llm_user="qwen3-235b-a22b-instruct-2507",
    )
    assert make_run_name(config) == "airline/qwen3-8b_no-thinking"


def test_run_name_leaves_out_trial_count():
    config = TextRunConfig(
        domain="retail",
        num_trials=3,
        llm_agent="openai/gpt-oss-120b",
        llm_args_agent={"temperature": 0.6},
    )
    assert make_run_name(config) == "retail/openai_gpt-oss-120b"


def test_run_name_includes_thinking_mode():
    config = TextRunConfig(
        domain="airline",
        llm_agent="my-model",
        llm_args_agent={
            "temperature": 1.0,
            "extra_body": {"chat_template_kwargs": {"thinking_mode": "enabled"}},
        },
    )
    assert make_run_name(config) == "airline/my-model_thinking-enabled"


def test_run_name_includes_reasoning_strength():
    config = TextRunConfig(
        domain="airline",
        llm_agent="my-model",
        llm_args_agent={
            "temperature": 1.0,
            "extra_body": {"chat_template_kwargs": {"reasoning_strength": "high"}},
        },
    )
    assert make_run_name(config) == "airline/my-model_reasoning-high"


def test_run_name_includes_reasoning_effort():
    config = TextRunConfig(
        domain="airline",
        llm_agent="my-model",
        llm_args_agent={
            "temperature": 1.0,
            "extra_body": {
                "reasoning_effort": "max",
                "chat_template_kwargs": {"clear_thinking": True},
            },
        },
    )
    assert make_run_name(config) == "airline/my-model_effort-max"
