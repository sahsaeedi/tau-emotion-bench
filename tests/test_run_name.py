from tau_emotion.config import DEFAULT_LLM_USER
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


def test_run_name_includes_non_default_user_model():
    config = TextRunConfig(
        domain="airline",
        llm_agent="gpt-4.1",
        llm_user="openai/gpt-4.1",
    )
    assert make_run_name(config) == "airline/gpt-4.1_user-openai_gpt-4.1"


def test_run_name_leaves_out_default_user_model():
    config = TextRunConfig(
        domain="airline", llm_agent="gpt-4.1", llm_user=DEFAULT_LLM_USER
    )
    assert make_run_name(config) == "airline/gpt-4.1"


def test_run_name_includes_train_split():
    config = TextRunConfig(domain="bank", llm_agent="gpt-4.1", task_split_name="train")
    assert make_run_name(config) == "bank/gpt-4.1_train"


def test_run_name_suffix_order():
    config = TextRunConfig(
        domain="bank",
        agent="llm_agent_gt",
        llm_agent="qwen3-8b",
        llm_args_agent={
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
        },
        llm_user="gpt-4.1",
        task_split_name="train",
    )
    assert (
        make_run_name(config)
        == "bank/llm_agent_gt_qwen3-8b_thinking_user-gpt-4.1_train"
    )
