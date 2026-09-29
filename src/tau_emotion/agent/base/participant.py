"""
Base participant class defining the communication protocol.

- HalfDuplexParticipant: Turn-based communication (generate_next_message)
"""

from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from loguru import logger

from tau_emotion.data_model.message import Message

# Generic type variables for conversation participants
InputMessageType = TypeVar("InputMessageType", bound=Message)
OutputMessageType = TypeVar("OutputMessageType", bound=Message)
StateType = TypeVar("StateType")


# =============================================================================
# HALF-DUPLEX PROTOCOL
# =============================================================================


class HalfDuplexParticipant(
    ABC, Generic[InputMessageType, OutputMessageType, StateType]
):
    """
    Protocol for turn-based (half-duplex) communication.

    Participants take turns: receive a message, produce a response.
    One party speaks at a time.

    Type Parameters:
        InputMessageType: The type of messages this participant receives
        OutputMessageType: The type of messages this participant produces
        StateType: The type of internal state this participant maintains
    """

    @abstractmethod
    def generate_next_message(
        self, message: InputMessageType, state: StateType
    ) -> tuple[OutputMessageType, StateType]:
        """
        Generate the next message from an input message and current state.

        Args:
            message: The input message to respond to.
            state: The current state.

        Returns:
            A tuple of (output_message, updated_state).
        """
        raise NotImplementedError

    @abstractmethod
    def get_init_state(
        self,
        message_history: Optional[list[Message]] = None,
    ) -> StateType:
        """
        Get the initial state of the participant.

        Args:
            message_history: The message history.

        Returns:
            The initial state.
        """
        raise NotImplementedError

    def stop(
        self,
        message: Optional[InputMessageType] = None,
        state: Optional[StateType] = None,
    ) -> None:
        """
        Stop the participant.

        Args:
            message: The last message to the participant.
            state: The last state of the participant.
        """
        pass

    @classmethod
    def is_stop(cls, message: OutputMessageType) -> bool:
        """
        Check if the message is a stop message.

        By default the participant does not stop.

        Args:
            message: The output message to check.

        Returns:
            True if the message indicates stopping, False otherwise.
        """
        return False

    def set_seed(self, seed: int):
        """
        Set the seed for the participant. [Optional]

        Args:
            seed: The random seed to set.
        """
        logger.warning(
            f"Setting seed for participant is not implemented for class "
            f"{self.__class__.__name__}"
        )
