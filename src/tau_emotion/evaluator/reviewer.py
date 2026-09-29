"""
Conversation reviewer for analyzing simulation trajectories for errors.

This module provides functionality to review a single simulation using an
LLM judge to identify errors made by the agent and/or user simulator.

Two review modes are supported:
- "full": Review both agent and user simulator errors (also does auth classification)
- "user": Review only user simulator errors

This is different from the evaluator which computes task success rewards/metrics.
The reviewer identifies qualitative conversation errors.

Usage:
    from tau_emotion.evaluator.reviewer import review_simulation, ReviewMode

    # Full review (agent + user errors)
    review, auth = review_simulation(simulation, task, ReviewMode.FULL, ...)
    simulation.review = review
    simulation.auth_classification = auth

    # User-only review
    review, _ = review_simulation(simulation, task, ReviewMode.USER, ...)
    simulation.user_only_review = review
"""

from enum import Enum
from typing import Optional, Union

from tau_emotion.data_model.simulation import (
    AuthenticationClassification,
    Review,
    SimulationRun,
    UserInfo,
    UserOnlyReview,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.evaluator.auth_classifier import AuthenticationClassifier
from tau_emotion.evaluator.review_llm_judge import ConversationReviewer
from tau_emotion.evaluator.review_llm_judge_user_only import UserOnlyReviewer


class ReviewMode(str, Enum):
    """Review mode."""

    FULL = "full"  # Review both agent and user errors
    USER = "user"  # Review only user simulator errors


def review_simulation(
    simulation: SimulationRun,
    task: Task,
    mode: ReviewMode,
    user_info: UserInfo,
    policy: Optional[str] = None,
) -> tuple[Union[Review, UserOnlyReview], Optional[AuthenticationClassification]]:
    """
    Review a single simulation for conversation errors.

    Args:
        simulation: The simulation run to review.
        task: The task specification.
        mode: Review mode - FULL (agent+user) or USER (user only).
        user_info: User info containing simulation guidelines.
        policy: The policy the agent must follow (required for FULL mode).

    Returns:
        Tuple of (review_result, auth_classification).
        - For FULL mode: (Review, AuthenticationClassification)
        - For USER mode: (UserOnlyReview, None)
    """
    if mode == ReviewMode.FULL:
        if not policy:
            raise ValueError("policy is required for FULL review mode")
        # Full review: agent + user errors + auth classification
        review = ConversationReviewer.review(
            user_info=user_info,
            task=task,
            full_trajectory=simulation.messages,
            policy=policy,
        )
        auth_classification = AuthenticationClassifier.classify(
            messages=simulation.messages,
        )
        return review, auth_classification

    else:  # ReviewMode.USER
        # User-only review: user simulator errors only
        review = UserOnlyReviewer.review(
            user_info=user_info,
            task=task,
            full_trajectory=simulation.messages,
        )
        return review, None
