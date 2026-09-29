from typing import Optional, Union

from tracer.envs.base import Env
from tracer.envs.movie.data import load_data
from tracer.envs.movie.rules import RULES
from tracer.envs.movie.tools import ALL_TOOLS
from tracer.envs.movie.wiki import WIKI
from tracer.envs.user import UserStrategy


class MockMovieDomainEnv(Env):
    def __init__(
        self,
        user_strategy: Union[str, UserStrategy] = UserStrategy.LLM,
        user_model: str = "gpt-4o",
        user_provider: Optional[str] = None,
        task_split: str = "test",
        emotion_enabled: bool = True,
        task_index: Optional[int] = None,
        api_base: Optional[str] = None,
    ):
        match task_split:
            case "test":
                from tracer.envs.movie.tasks_test import TASKS as tasks
            case "train":
                from tracer.envs.movie.tasks_train import TASKS as tasks
            case "dev":
                from tracer.envs.movie.tasks_dev import TASKS as tasks
            case _:
                raise ValueError(f"Unknown task split: {task_split}")
        super().__init__(
            data_load_func=load_data,
            tools=ALL_TOOLS,
            tasks=tasks,
            wiki=WIKI,
            rules=RULES,
            user_strategy=user_strategy,
            user_model=user_model,
            user_provider=user_provider,
            task_index=task_index,
            api_base=api_base,
        )
