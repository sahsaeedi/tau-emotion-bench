from typing import Optional, Union

from tracer.envs.base import Env
from tracer.envs.telecom.data import load_data
from tracer.envs.telecom.reverse_tools import ALL_TOOLS
from tracer.envs.telecom.rules import RULES
from tracer.envs.telecom.wiki import WIKI
from tracer.envs.user import UserStrategy


class MockTelecomDomainEnv(Env):
    def __init__(
        self,
        user_strategy: Union[str, UserStrategy] = UserStrategy.LLM,
        user_model: str = "gpt-4o",
        user_provider: Optional[str] = None,
        task_split: str = "test",
        task_index: Optional[int] = None,
        user_model_base_url: Optional[str] = None,
        # trait_dict: Optional[Dict[str, int]] = None,
        # endpoint: Optional[str] = None,
    ):
        match task_split:
            case "test":
                from tracer.envs.telecom.tasks_test import TASKS_TEST as tasks
            case "train":
                from tracer.envs.telecom.tasks_train import TASKS_TRAIN as tasks
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
            # trait_dict=trait_dict,
            task_index=task_index,
            # endpoint=endpoint,
            user_model_base_url=user_model_base_url,
        )
        self.terminate_tools = ["transfer_to_human_support"]
