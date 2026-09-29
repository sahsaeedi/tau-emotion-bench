"""
Base user simulator classes.

This module defines the user base class:
- HalfDuplexUser: For turn-based users (uses generate_next_message)
"""

from abc import ABC
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

from tau_emotion.agent.base.participant import HalfDuplexParticipant
from tau_emotion.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau_emotion.environment.tool import Tool

ValidUserInputMessage = AssistantMessage | ToolMessage | MultiToolMessage


class UserError(Exception):
    """
    Generic exception for user errors.
    """

    pass


def is_valid_user_history_message(message: Message) -> bool:
    """Check if the message is a valid user history message."""
    return (
        isinstance(message, UserMessage)
        or (isinstance(message, AssistantMessage) and not message.is_tool_call())
        or (isinstance(message, ToolMessage) and message.requestor == "user")
    )


STOP = "###STOP###"
TRANSFER = "###TRANSFER###"
OUT_OF_SCOPE = "###OUT-OF-SCOPE###"
# Emission of UNSATISFIED indicates the user ended the conversation early
# because the agent failed emotionally (ignored emotional needs, eroded
# trust, etc.). Treated as a terminal state with reward 0; see
# orchestrator + evaluator integration.
UNSATISFIED = "###UNSATISFIED###"


class UserState(BaseModel):
    """The state of the user simulator."""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage]

    def flip_roles(self) -> list[APICompatibleMessage]:
        """
        Returns a list of messages with the roles flipped.
        """
        # NOTE: also clean the message to a api-compatible format
        flipped_messages = []
        for message in self.messages:
            if isinstance(message, UserMessage):
                flipped_messages.append(
                    AssistantMessage(
                        role="assistant",
                        tool_calls=message.tool_calls,
                        content=message.content,
                    )
                )
            elif isinstance(message, AssistantMessage):
                if not message.is_tool_call():
                    # Only add non tool call messages
                    flipped_messages.append(
                        UserMessage(
                            role="user",
                            content=message.content,
                        )
                    )
                else:
                    raise ValueError(
                        f"Tool calls are not supported in the flipped messages: {message}"
                    )
            elif isinstance(message, ToolMessage):
                if message.requestor == "user":
                    # Only add tool messages for the user
                    flipped_messages.append(
                        ToolMessage(
                            id=message.id,
                            role=message.role,
                            content=message.content,
                        )
                    )
                else:
                    raise ValueError(
                        f"Tool messages should be sent to the user in this message history: {message}"
                    )
            else:
                raise ValueError(f"Unknown message role: {message.role}")
        return flipped_messages


UserStateType = TypeVar("UserStateType", bound=UserState)


# =============================================================================
# HALF-DUPLEX USERS
# =============================================================================


class HalfDuplexUser(
    HalfDuplexParticipant[ValidUserInputMessage, UserMessage, UserStateType],
    ABC,
    Generic[UserStateType],
):
    """
    Base class for half-duplex (turn-based) user simulators.

    Users are conversation participants that:
    - Receive AssistantMessage/ToolMessage/MultiToolMessage
    - Produce UserMessage
    - Maintain UserState

    User developers must implement:
    - generate_next_message: Generate the next message from assistant/tool message(s)
    - get_init_state: Get the initial state of the user
    """

    def __init__(
        self,
        instructions: Optional[str] = None,
        tools: Optional[list[Tool]] = None,
    ):
        self.instructions = instructions
        self.tools = tools

    def stop(
        self,
        message: Optional[ValidUserInputMessage] = None,
        state: Optional[UserStateType] = None,
    ) -> None:
        """
        Stops the user simulator.
        """
        pass
