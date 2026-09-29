from typing import Optional, Union

from tracer.envs.bank.data import load_data
from tracer.envs.bank.rules import RULES
from tracer.envs.bank.tools import ALL_TOOLS
from tracer.envs.bank.wiki import WIKI
from tracer.envs.base import Env
from tracer.envs.user import UserStrategy


class MockBankDomainEnv(Env):
    def __init__(
        self,
        user_strategy: Union[str, UserStrategy] = UserStrategy.LLM,
        user_model: str = "gpt-4o",
        user_provider: Optional[str] = None,
        task_split: str = "test",
        emotion_enabled: bool = True,
        task_index: Optional[int] = None,
        data_split: str = "train",
    ):
        match task_split:
            case "test":
                from tracer.envs.bank.tasks_test import TASKS as tasks
            case "train":
                from tracer.envs.bank.tasks_train import TASKS as tasks
            case "dev":
                from tracer.envs.bank.tasks_dev import TASKS as tasks
            case _:
                raise ValueError(f"Unknown task split: {task_split}")
        # data_split is separate from task_split, as in the other domains: the flat
        # layout IS the train split, so load_data() with no args is unchanged.
        super().__init__(
            data_load_func=lambda: load_data(data_split),
            tools=ALL_TOOLS,
            tasks=tasks,
            wiki=WIKI,
            rules=RULES,
            user_strategy=user_strategy,
            user_model=user_model,
            user_provider=user_provider,
            task_index=task_index,
        )
