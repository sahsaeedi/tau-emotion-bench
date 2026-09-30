"""
Helper functions for task loading, run configuration, and metadata.
"""

from typing import Optional

from tau_emotion.config import DEFAULT_AGENT_IMPLEMENTATION, DEFAULT_LLM_USER
from tau_emotion.data_model.simulation import (
    AgentInfo,
    Info,
    RunConfig,
    UserInfo,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.environment.environment import EnvironmentInfo
from tau_emotion.registry import RegistryInfo, registry
from tau_emotion.user.user_simulator import get_global_user_sim_guidelines
from tau_emotion.utils.utils import get_commit_hash


def get_options() -> RegistryInfo:
    """Returns available options (domains, agents, users, task sets) from the registry."""
    return registry.get_info()


def get_environment_info(
    domain_name: str,
    include_tool_info: bool = False,
    env_kwargs: Optional[dict] = None,
) -> EnvironmentInfo:
    """Get information about the environment for a registered domain."""
    env_constructor = registry.get_env_constructor(domain_name)
    if env_kwargs is None:
        env_kwargs = {}
    return env_constructor(**env_kwargs).get_info(include_tool_info=include_tool_info)


def load_task_splits(task_set_name: str) -> Optional[dict[str, list[str]]]:
    """Load the task splits for a given task set."""
    task_split_loader = registry.get_task_splits_loader(task_set_name)
    if task_split_loader is None:
        return None
    return task_split_loader()


def load_tasks(
    task_set_name: str,
    task_split_name: Optional[str] = None,
) -> list[Task]:
    """Load tasks for a given task set, optionally filtering by split."""
    task_loader = registry.get_tasks_loader(task_set_name)
    return task_loader(task_split_name=task_split_name)


def get_tasks(
    task_set_name: str,
    task_split_name: Optional[str] = None,
    task_ids: Optional[list[str]] = None,
    num_tasks: Optional[int] = None,
) -> list[Task]:
    """Load tasks with optional filtering by IDs and count.

    Args:
        task_set_name: The task set to load from.
        task_split_name: Optional split name (e.g., "base").
        task_ids: If provided, only return tasks with these IDs.
        num_tasks: If provided, limit to this many tasks.

    Returns:
        List of tasks matching the criteria.

    Raises:
        ValueError: If task_ids are specified but some are not found.
    """
    if task_ids is None:
        tasks = load_tasks(
            task_set_name=task_set_name,
            task_split_name=task_split_name,
        )
    else:
        tasks = [
            task
            for task in load_tasks(
                task_set_name=task_set_name,
                task_split_name=task_split_name,
            )
            if task.id in task_ids
        ]
    if task_ids is not None and len(tasks) != len(task_ids):
        missing_tasks = set(task_ids) - set([task.id for task in tasks])
        raise ValueError(
            f"Not all tasks were found for task set {task_set_name} - {task_split_name}: {missing_tasks}"
        )
    if num_tasks is not None:
        tasks = tasks[:num_tasks]
    return tasks


def make_run_name(config: RunConfig) -> str:
    """Generate a run name from the run config.

    Text runs get one directory per agent model, so the same command resumes
    its run instead of starting a new one: <domain>/<agent model>, with the
    thinking setting when one is given, a non-default user model, the train
    split and no-emotion, e.g. airline/qwen3-8b_no-thinking_user-gpt-4.1_train.
    The trial count is left out, so rerunning with more trials adds them to the
    same run.
    """
    parts = [config.llm_agent.replace("/", "_")]
    extra_body = config.llm_args_agent.get("extra_body") or {}
    chat_template_kwargs = extra_body.get("chat_template_kwargs") or {}
    thinking = chat_template_kwargs.get("enable_thinking")
    if thinking is not None:
        parts.append("thinking" if thinking else "no-thinking")
    # Chat templates name their reasoning controls differently.
    thinking_mode = chat_template_kwargs.get("thinking_mode")
    if thinking_mode is not None:
        parts.append(f"thinking-{thinking_mode}")
    reasoning_strength = chat_template_kwargs.get("reasoning_strength")
    if reasoning_strength is not None:
        parts.append(f"reasoning-{reasoning_strength}")
    reasoning_effort = extra_body.get("reasoning_effort")
    if reasoning_effort is not None:
        parts.append(f"effort-{reasoning_effort}")
    if config.llm_user != DEFAULT_LLM_USER:
        parts.append(f"user-{config.llm_user.replace('/', '_')}")
    if config.task_split_name == "train":
        parts.append("train")
    if config.no_emotion:
        parts.append("no-emotion")
    if config.effective_agent != DEFAULT_AGENT_IMPLEMENTATION:
        parts.insert(0, config.effective_agent)
    return f"{config.domain}/{'_'.join(parts)}"


def _without_api_key(llm_args: Optional[dict]) -> Optional[dict]:
    """LLM args as saved in the results: without the API key."""
    if not llm_args or "api_key" not in llm_args:
        return llm_args
    return {k: v for k, v in llm_args.items() if k != "api_key"}


def get_info(config: RunConfig, **overrides) -> Info:
    """Create an Info object for storing run configuration metadata.

    Args:
        config: The run configuration.
        **overrides: Override specific fields (e.g., policy_override).

    Returns:
        Info object with run metadata.
    """
    policy_override = overrides.get("policy_override")

    user_info = UserInfo(
        implementation=config.effective_user,
        llm=config.llm_user,
        llm_args=_without_api_key(config.llm_args_user),
        global_simulation_guidelines=get_global_user_sim_guidelines(),
        no_emotion=config.no_emotion,
    )

    agent_llm = config.llm_agent
    agent_llm_args = _without_api_key(config.llm_args_agent)

    agent_info = AgentInfo(
        implementation=config.effective_agent,
        llm=agent_llm,
        llm_args=agent_llm_args,
    )
    environment_info = get_environment_info(
        config.domain, include_tool_info=False, env_kwargs={}
    )
    if policy_override is not None:
        environment_info.policy = policy_override

    return Info(
        git_commit=get_commit_hash(),
        num_trials=config.num_trials,
        max_steps=config.effective_max_steps,
        max_errors=config.max_errors,
        user_info=user_info,
        agent_info=agent_info,
        environment_info=environment_info,
        seed=config.seed,
    )
