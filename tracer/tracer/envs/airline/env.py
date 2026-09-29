# Copyright Sierra

from typing import Optional, Union

from tracer.envs.airline.data import load_data
from tracer.envs.airline.reverse_tools import ALL_TOOLS
from tracer.envs.airline.rules import RULES

# from tracer.envs.airline.tools import ALL_TOOLS
from tracer.envs.airline.wiki import WIKI
from tracer.envs.base import Env
from tracer.envs.user import UserStrategy


class MockAirlineDomainEnv(Env):
    def __init__(
        self,
        user_strategy: Union[str, UserStrategy] = UserStrategy.LLM,
        user_model: str = "gpt-4o",
        user_provider: Optional[str] = None,
        task_split: str = "test",
        task_index: Optional[int] = None,
        data_split: str = "train",
    ):
        match task_split:
            case "test":
                from tracer.envs.airline.tasks_test import TASKS as tasks
            case _:
                raise ValueError(f"Unknown task split: {task_split}")
        # data_split is deliberately SEPARATE from task_split. The shipped
        # tasks_test.py names entities (mia_li_3668, Z7GOZK, HAT136) that live in the
        # flat layout, i.e. the train split -- so those tasks are train-data tasks.
        # Point data_split at "test" only together with tasks generated from that
        # split (python -m tracer.generator --split test).
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
        self.terminate_tools = ["transfer_to_human_agents"]
