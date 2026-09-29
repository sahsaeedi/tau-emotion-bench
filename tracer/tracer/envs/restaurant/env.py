from typing import Optional, Union

from tracer.envs.base import Env
from tracer.envs.restaurant.data import load_data
from tracer.envs.restaurant.rules import RULES
from tracer.envs.restaurant.tools import ALL_TOOLS
from tracer.envs.restaurant.wiki import WIKI
from tracer.envs.user import UserStrategy


class MockRestaurantDomainEnv(Env):
    def __init__(
        self,
        user_strategy: Union[str, UserStrategy] = UserStrategy.LLM,
        user_model: str = "gpt-4o",
        user_provider: Optional[str] = None,
        task_split: str = "test",
        task_index: Optional[int] = None,
        data_split: Optional[str] = None,
    ):
        match task_split:
            case "test":
                from tracer.envs.restaurant.tasks_test import TASKS as tasks
            case "train":
                from tracer.envs.restaurant.tasks_train import TASKS as tasks
            case _:
                raise ValueError(f"Unknown task split: {task_split}")
        # The data comes from data/<data_split>/ (test/ or train/), by default the
        # task split's. Set it to the split the tasks were generated from.
        data_split = data_split or task_split
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
