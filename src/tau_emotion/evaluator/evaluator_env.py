from typing import Callable

from loguru import logger

from tau_emotion.data_model.message import (
    Message,
)
from tau_emotion.data_model.simulation import DBCheck, EnvAssertionCheck, RewardInfo
from tau_emotion.data_model.tasks import RewardType, Task
from tau_emotion.environment.environment import Environment
from tau_emotion.evaluator.evaluator_base import EvaluatorBase


class EnvironmentEvaluator(EvaluatorBase[Message]):
    """
    Evaluator focuses on endstate of the simulation environment.
    """

    @classmethod
    def calculate_reward(
        cls,
        environment_constructor: Callable[[], Environment],
        task: Task,
        full_trajectory: list[
            Message
        ],  # FIXME: It would be better to be able to get only the messages that are after the initial state
        solo_mode: bool = False,
        env_kwargs: dict = None,
    ) -> RewardInfo:
        """
        Calculate the reward for the simulation.
        Args:
            environment_constructor: Callable[[], Environment]
            task: Task
            full_trajectory: list[Message] (Must include the message history from task initial state)
            solo_mode: bool
        Returns:
            RewardInfo
        """
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                info={"note": "No evaluation criteria"},
            )
        expected_actions = task.evaluation_criteria.actions
        env_assertions = task.evaluation_criteria.env_assertions
        if expected_actions is None and env_assertions is None:
            return RewardInfo(
                reward=1.0,
                db_check=DBCheck(db_match=True, db_reward=1.0),
                info={"note": "No expected actions or env assertions"},
            )

        initialization_data = None
        if (
            task.initial_state is not None
            and task.initial_state.initialization_data is not None
        ):
            initialization_data = task.initial_state.initialization_data

        initialization_actions = None
        if (
            task.initial_state is not None
            and task.initial_state.initialization_actions is not None
        ):
            initialization_actions = task.initial_state.initialization_actions

        message_history = []
        if (
            task.initial_state is not None
            and task.initial_state.message_history is not None
        ):
            message_history = task.initial_state.message_history

        if env_kwargs is None:
            env_kwargs = {}

        predicted_environment = environment_constructor(
            solo_mode=solo_mode, **env_kwargs
        )

        predicted_environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=list(full_trajectory),
        )

        # Setting up gold environment
        gold_environment = environment_constructor(**env_kwargs)
        gold_environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )
        golden_actions = task.evaluation_criteria.actions or []
        for action in golden_actions:
            try:
                gold_environment.make_tool_call(
                    tool_name=action.name,
                    requestor=action.requestor,
                    **action.arguments,
                )
            except Exception as e:
                logger.warning(
                    f"Error in golden actions {action.name}({action.arguments}): {e}"
                )

        # Comparing the environments
        agent_db_hash = gold_environment.get_db_hash()
        user_db_hash = gold_environment.get_user_db_hash()
        predicted_agent_db_hash = predicted_environment.get_db_hash()
        predicted_user_db_hash = predicted_environment.get_user_db_hash()
        agent_db_match = agent_db_hash == predicted_agent_db_hash
        user_db_match = user_db_hash == predicted_user_db_hash
        if agent_db_match and user_db_match:
            db_reward = 1.0
            db_match = True
        else:
            db_reward = 0.0
            db_match = False

        db_check = DBCheck(db_match=db_match, db_reward=db_reward)

        # Run env assertions
        env_assertions = task.evaluation_criteria.env_assertions or []
        env_assertion_checks = []
        env_assertion_reward = 1.0
        for env_assertion in env_assertions:
            success = predicted_environment.run_env_assertion(
                env_assertion,
                raise_assertion_error=False,
            )
            res = EnvAssertionCheck(
                env_assertion=env_assertion,
                met=success,
                reward=1.0 if success else 0.0,
            )
            env_assertion_checks.append(res)
            env_assertion_reward *= res.reward

        reward = 1.0
        reward_breakdown = {}
        if RewardType.DB in task.evaluation_criteria.reward_basis:
            reward_breakdown[RewardType.DB] = db_reward
            reward *= db_reward
        if RewardType.ENV_ASSERTION in task.evaluation_criteria.reward_basis:
            reward_breakdown[RewardType.ENV_ASSERTION] = env_assertion_reward
            reward *= env_assertion_reward

        return RewardInfo(
            reward=reward,
            db_check=db_check,
            env_assertions=env_assertion_checks,
            reward_basis=task.evaluation_criteria.reward_basis,
            reward_breakdown=reward_breakdown,
        )
