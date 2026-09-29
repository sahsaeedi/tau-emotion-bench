# Copyright Sierra

import importlib
from typing import Optional, Union

from tracer.envs.base import Env
from tracer.envs.user import UserStrategy

ENV_CLASSES = {
    "airline": "MockAirlineDomainEnv",
    "retail": "MockRetailDomainEnv",
    "telecom": "MockTelecomDomainEnv",
    "telehealth": "MockTelehealthDomainEnv",
    "bank": "MockBankDomainEnv",
    "basketball": "MockBasketballDomainEnv",
    "movie": "MockMovieDomainEnv",
    "restaurant": "MockRestaurantDomainEnv",
    "school": "MockSchoolDomainEnv",
    "travel": "MockTravelDomainEnv",
}


def get_env(
    env_name: str,
    user_strategy: Union[str, UserStrategy],
    user_model: str,
    task_split: str,
    user_provider: Optional[str] = None,
    task_index: Optional[int] = None,
    data_split: Optional[str] = None,
) -> Env:
    if env_name not in ENV_CLASSES:
        raise ValueError(f"Unknown environment: {env_name}")
    module = importlib.import_module(f"tracer.envs.{env_name}.env")
    return getattr(module, ENV_CLASSES[env_name])(
        user_strategy=user_strategy,
        user_model=user_model,
        task_split=task_split,
        user_provider=user_provider,
        task_index=task_index,
        data_split=data_split,
    )
