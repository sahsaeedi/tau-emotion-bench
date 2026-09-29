from typing import Callable, Dict, Optional

from loguru import logger
from pydantic import BaseModel

from tau_emotion.agent.llm_agent import (
    LLMGTAgent,
    LLMSoloAgent,
    create_llm_agent,
    create_llm_gt_agent,
    create_llm_solo_agent,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.domains.airline.environment import (
    get_environment as airline_domain_get_environment,
)
from tau_emotion.domains.airline.environment import (
    get_tasks as airline_domain_get_tasks,
)
from tau_emotion.domains.airline.environment import (
    get_tasks_split as airline_domain_get_tasks_split,
)
from tau_emotion.domains.bank.environment import (
    get_environment as bank_domain_get_environment,
)
from tau_emotion.domains.bank.environment import (
    get_tasks as bank_domain_get_tasks,
)
from tau_emotion.domains.bank.environment import (
    get_tasks_split as bank_domain_get_tasks_split,
)
from tau_emotion.domains.basketball.environment import (
    get_environment as basketball_domain_get_environment,
)
from tau_emotion.domains.basketball.environment import (
    get_tasks as basketball_domain_get_tasks,
)
from tau_emotion.domains.basketball.environment import (
    get_tasks_split as basketball_domain_get_tasks_split,
)
from tau_emotion.domains.mock.environment import (
    get_environment as mock_domain_get_environment,
)
from tau_emotion.domains.mock.environment import get_tasks as mock_domain_get_tasks
from tau_emotion.domains.movie.environment import (
    get_environment as movie_domain_get_environment,
)
from tau_emotion.domains.movie.environment import (
    get_tasks as movie_domain_get_tasks,
)
from tau_emotion.domains.movie.environment import (
    get_tasks_split as movie_domain_get_tasks_split,
)
from tau_emotion.domains.restaurant.environment import (
    get_environment as restaurant_domain_get_environment,
)
from tau_emotion.domains.restaurant.environment import (
    get_tasks as restaurant_domain_get_tasks,
)
from tau_emotion.domains.restaurant.environment import (
    get_tasks_split as restaurant_domain_get_tasks_split,
)
from tau_emotion.domains.retail.environment import (
    get_environment as retail_domain_get_environment,
)
from tau_emotion.domains.retail.environment import get_tasks as retail_domain_get_tasks
from tau_emotion.domains.retail.environment import (
    get_tasks_split as retail_domain_get_tasks_split,
)
from tau_emotion.domains.school.environment import (
    get_environment as school_domain_get_environment,
)
from tau_emotion.domains.school.environment import (
    get_tasks as school_domain_get_tasks,
)
from tau_emotion.domains.school.environment import (
    get_tasks_split as school_domain_get_tasks_split,
)
from tau_emotion.domains.telecom.environment import (
    get_environment as telecom_domain_get_environment,
)
from tau_emotion.domains.telecom.environment import (
    get_tasks as telecom_domain_get_tasks,
)
from tau_emotion.domains.telecom.environment import (
    get_tasks_split as telecom_domain_get_tasks_split,
)
from tau_emotion.domains.telehealth.environment import (
    get_environment as telehealth_domain_get_environment,
)
from tau_emotion.domains.telehealth.environment import (
    get_tasks as telehealth_domain_get_tasks,
)
from tau_emotion.domains.telehealth.environment import (
    get_tasks_split as telehealth_domain_get_tasks_split,
)
from tau_emotion.domains.travel.environment import (
    get_environment as travel_domain_get_environment,
)
from tau_emotion.domains.travel.environment import (
    get_tasks as travel_domain_get_tasks,
)
from tau_emotion.domains.travel.environment import (
    get_tasks_split as travel_domain_get_tasks_split,
)
from tau_emotion.environment.environment import Environment
from tau_emotion.user.user_simulator import DummyUser, UserSimulator
from tau_emotion.user.user_simulator_base import HalfDuplexUser


class RegistryInfo(BaseModel):
    """Options for the registry"""

    domains: list[str]
    agents: list[str]
    users: list[str]
    task_sets: list[str]


class Registry:
    """Registry for Users, Agents, and Domains"""

    def __init__(self):
        self._users: Dict[str, type] = {}  # HalfDuplexUser
        self._agent_factories: Dict[str, Callable] = {}  # Factory functions for agents
        self._agent_task_filters: Dict[
            str, Callable[[Task], bool]
        ] = {}  # Optional task filters per agent
        self._agent_metadata: Dict[str, dict] = {}  # Optional metadata per agent
        self._domains: Dict[str, Callable[[], Environment]] = {}
        self._tasks: Dict[str, Callable[[Optional[str]], list[Task]]] = {}
        self._task_splits: Dict[str, Callable[[], dict[str, list[str]]]] = {}

    def register_user(
        self,
        user_constructor: type,
        name: Optional[str] = None,
    ):
        """Decorator to register a new User implementation"""
        try:
            if not issubclass(user_constructor, HalfDuplexUser):
                raise TypeError(
                    f"{user_constructor.__name__} must implement HalfDuplexUser"
                )
            key = name or user_constructor.__name__
            if key in self._users:
                raise ValueError(f"User {key} already registered")
            self._users[key] = user_constructor
        except Exception as e:
            logger.error(f"Error registering user {name}: {str(e)}")
            raise

    def register_agent_factory(
        self,
        factory: Callable,
        name: str,
        task_filter: Optional[Callable[[Task], bool]] = None,
        metadata: Optional[dict] = None,
    ):
        """Register an agent factory function.

        A factory function encapsulates agent construction logic, following
        the same pattern as domain factories (get_environment). The factory
        signature is: factory(tools, domain_policy, **kwargs) -> agent instance.

        Args:
            factory: A callable that creates an agent instance.
            name: The name to register the factory under.
            task_filter: Optional callable that takes a Task and returns True if
                the task is valid for this agent. Used by batch runners to filter
                tasks before building agents. If None, all tasks are accepted.
            metadata: Optional dict of agent metadata (e.g., {"solo_mode": True}).
                Retrieved via get_agent_metadata().
        """
        if name in self._agent_factories:
            raise ValueError(f"Agent factory {name} already registered")
        self._agent_factories[name] = factory
        if task_filter is not None:
            self._agent_task_filters[name] = task_filter
        if metadata is not None:
            self._agent_metadata[name] = metadata

    def get_agent_factory(self, name: str) -> Optional[Callable]:
        """Get a registered agent factory by name.

        Returns None if no factory is registered for the given name.

        Args:
            name: The name of the agent factory.

        Returns:
            The factory callable, or None if not found.
        """
        return self._agent_factories.get(name)

    def get_agent_task_filter(self, name: str) -> Optional[Callable[[Task], bool]]:
        """Get the task filter for a registered agent.

        Returns None if no task filter is registered for the given agent,
        meaning all tasks are accepted.

        Args:
            name: The name of the agent.

        Returns:
            A callable that takes a Task and returns True if valid, or None.
        """
        return self._agent_task_filters.get(name)

    def get_agent_metadata(self, name: str, key: str, default=None):
        """Get a metadata value for a registered agent.

        Args:
            name: The name of the agent.
            key: The metadata key to look up.
            default: Value to return if the key is not found.

        Returns:
            The metadata value, or default if not found.
        """
        agent_meta = self._agent_metadata.get(name, {})
        return agent_meta.get(key, default)

    def register_domain(
        self,
        get_environment: Callable[[], Environment],
        name: str,
    ):
        """Register a new Domain implementation"""
        try:
            if name in self._domains:
                raise ValueError(f"Domain {name} already registered")
            self._domains[name] = get_environment
        except Exception as e:
            logger.error(f"Error registering domain {name}: {str(e)}")
            raise

    def register_tasks(
        self,
        get_tasks: Callable[[Optional[str]], list[Task]],
        name: str,
        get_task_splits: Optional[Callable[[], dict[str, list[str]]]] = None,
    ):
        """Register a new Domain implementation.
        Args:
            get_tasks: A function that returns a list of tasks for the domain. If a task split name is provided, it returns the tasks for that split.
            name: The name of the domain.
            get_task_splits: A function that returns a dictionary of task splits for the domain.
        """
        try:
            if name in self._tasks:
                raise ValueError(f"Tasks {name} already registered")
            self._tasks[name] = get_tasks
            if get_task_splits is not None:
                self._task_splits[name] = get_task_splits
        except Exception as e:
            logger.error(f"Error registering tasks {name}: {str(e)}")
            raise

    def get_user_constructor(self, name: str) -> type:
        """Get a registered User implementation by name"""
        if name not in self._users:
            raise KeyError(f"User {name} not found in registry")
        return self._users[name]

    def get_env_constructor(self, name: str) -> Callable[[], Environment]:
        """Get a registered Domain by name"""
        if name not in self._domains:
            raise KeyError(f"Domain {name} not found in registry")
        return self._domains[name]

    def get_tasks_loader(self, name: str) -> Callable[[Optional[str]], list[Task]]:
        """Get a registered Task Set by name.
        Args:
            name: The name of the task set.
        Returns:
            A function that takes an optional task_split_name parameter and returns the corresponding tasks.
            Can be called as: func() or func(task_split_name="base") or func("base").
        """
        if name not in self._tasks:
            raise KeyError(f"Task Set {name} not found in registry")
        return self._tasks[name]

    def get_task_splits_loader(
        self, name: str
    ) -> Optional[Callable[[], dict[str, list[str]]]]:
        """Get a registered task split dict loader."""
        if name not in self._task_splits:
            return None
        return self._task_splits[name]

    def get_users(self) -> list[str]:
        """Get all registered Users"""
        return list(self._users.keys())

    def get_agents(self) -> list[str]:
        """Get all registered Agents"""
        return list(self._agent_factories.keys())

    def get_domains(self) -> list[str]:
        """Get all registered Domains"""
        return list(self._domains.keys())

    def get_task_sets(self) -> list[str]:
        """Get all registered Task Sets"""
        return list(self._tasks.keys())

    def get_info(self) -> RegistryInfo:
        """
        Returns information about the registry.
        """
        try:
            info = RegistryInfo(
                users=self.get_users(),
                agents=self.get_agents(),
                domains=self.get_domains(),
                task_sets=self.get_task_sets(),
            )
            return info
        except Exception as e:
            logger.error(f"Error getting registry info: {str(e)}")
            raise


# Create a global registry instance
try:
    registry = Registry()
    logger.debug("Registering default components...")
    # User implementations
    registry.register_user(UserSimulator, "user_simulator")
    registry.register_user(DummyUser, "dummy_user")

    # Agent factories
    registry.register_agent_factory(create_llm_agent, "llm_agent")
    registry.register_agent_factory(
        create_llm_gt_agent,
        "llm_agent_gt",
        task_filter=LLMGTAgent.check_valid_task,
    )
    registry.register_agent_factory(
        create_llm_solo_agent,
        "llm_agent_solo",
        task_filter=LLMSoloAgent.check_valid_task,
        metadata={"solo_mode": True},
    )
    registry.register_domain(mock_domain_get_environment, "mock")
    registry.register_tasks(mock_domain_get_tasks, "mock")

    registry.register_domain(airline_domain_get_environment, "airline")
    registry.register_tasks(
        airline_domain_get_tasks,
        "airline",
        get_task_splits=airline_domain_get_tasks_split,
    )

    registry.register_domain(retail_domain_get_environment, "retail")
    registry.register_tasks(
        retail_domain_get_tasks,
        "retail",
        get_task_splits=retail_domain_get_tasks_split,
    )

    registry.register_domain(telecom_domain_get_environment, "telecom")
    registry.register_tasks(
        telecom_domain_get_tasks,
        "telecom",
        get_task_splits=telecom_domain_get_tasks_split,
    )

    registry.register_domain(telehealth_domain_get_environment, "telehealth")
    registry.register_tasks(
        telehealth_domain_get_tasks,
        "telehealth",
        get_task_splits=telehealth_domain_get_tasks_split,
    )

    registry.register_domain(bank_domain_get_environment, "bank")
    registry.register_tasks(
        bank_domain_get_tasks,
        "bank",
        get_task_splits=bank_domain_get_tasks_split,
    )

    registry.register_domain(basketball_domain_get_environment, "basketball")
    registry.register_tasks(
        basketball_domain_get_tasks,
        "basketball",
        get_task_splits=basketball_domain_get_tasks_split,
    )

    registry.register_domain(travel_domain_get_environment, "travel")
    registry.register_tasks(
        travel_domain_get_tasks,
        "travel",
        get_task_splits=travel_domain_get_tasks_split,
    )

    registry.register_domain(movie_domain_get_environment, "movie")
    registry.register_tasks(
        movie_domain_get_tasks,
        "movie",
        get_task_splits=movie_domain_get_tasks_split,
    )

    registry.register_domain(restaurant_domain_get_environment, "restaurant")
    registry.register_tasks(
        restaurant_domain_get_tasks,
        "restaurant",
        get_task_splits=restaurant_domain_get_tasks_split,
    )

    registry.register_domain(school_domain_get_environment, "school")
    registry.register_tasks(
        school_domain_get_tasks,
        "school",
        get_task_splits=school_domain_get_tasks_split,
    )

    logger.debug("Default components registered")

except Exception as e:
    logger.error(f"Error initializing registry: {str(e)}")
