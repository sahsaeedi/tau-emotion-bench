from typing import Generic, Optional, Tuple, TypeVar

from loguru import logger

from tau_emotion.agent.base.llm_config import LLMConfigMixin
from tau_emotion.data_model.message import (
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau_emotion.environment.tool import Tool
from tau_emotion.user.user_simulator_base import (
    OUT_OF_SCOPE,
    STOP,
    TRANSFER,
    UNSATISFIED,
    HalfDuplexUser,
    UserState,
    ValidUserInputMessage,
    is_valid_user_history_message,
)
from tau_emotion.utils.llm_utils import generate

# τ-bench's user prompt (as in tracer/tracer/envs/user.py), extended with the
# emotion rules and ###UNSATISFIED###.
TAU_BENCH_SYSTEM_PROMPT = """You are a user interacting with an agent.{instruction_display}
Rules:
- Just generate one line at a time to simulate the user's message.
- Do not give away all the instruction at once. Only provide the information that is necessary for the current step.
- Do not hallucinate information that is not provided in the instruction. For example, if the agent asks for the order id but it is not mentioned in the instruction, do not make up an order id, just say you do not remember or have it.
- When the task goal is satisfied and you would reasonably end on good terms, send {stop} as a standalone message with nothing else to end the conversation.
- Do not repeat the exact instruction in the conversation. Instead, use your own words to convey the same information.
- And, if the instruction has Emotion Instruction which describes the emotional state, politeness, urgency, and trust in the agent, you must follow the rules below:
- 1. In every message that you send, you must reflect the emotional profile provided in the instruction aggressively. 
- 2. Always stay in character, and let emotion shape your wording, patience, and how much you cooperate and share information with the agent.
- 3. Try to make the conversation as natural as possible, and stick to the personalities and emotional states in the instruction.
- 4. You can stop the conversation early by sending {unsatisfied} as a standalone message if the agent ignores your emotional needs (e.g. purely transactional replies when you need reassurance), steamrolls cues you already gave, erodes trust (pushy, evasive), or creates procedural friction (excessive redundant questions, circular flow, unexplained delays, dismissive or abusive tone). Do not use {unsatisfied} when the goal is done and you are content; use {stop} only in that case.
- 5. Adjust your tone, response style, patience, and willingness to engage according to the emotional state described in the instruction.
"""


def get_global_user_sim_guidelines() -> str:
    """τ-bench's user prompt without a task's instruction.

    The results record it, and the review judge reads it; each task's own
    instruction is stored with the task.
    """
    return TAU_BENCH_SYSTEM_PROMPT.format(
        instruction_display="", stop=STOP, unsatisfied=UNSATISFIED
    )


UserStateType = TypeVar("UserStateType", bound="UserState")


class UserSimulator(
    LLMConfigMixin, HalfDuplexUser[UserStateType], Generic[UserStateType]
):
    """A half-duplex LLM-based user simulator for turn-based conversations.

    Its system prompt is τ-bench's user prompt (TAU_BENCH_SYSTEM_PROMPT) with the
    task's instruction.
    """

    def __init__(
        self,
        llm: str,
        instructions: Optional[str] = None,
        tools: Optional[list[Tool]] = None,
        llm_args: Optional[dict] = None,
    ):
        super().__init__(
            instructions=instructions,
            tools=tools,
            llm=llm,
            llm_args=llm_args,
        )

    @property
    def system_prompt(self) -> str:
        """
        The system prompt for the user simulator.
        """
        if self.instructions is None:
            logger.warning("No instructions provided for user simulator")

        instruction_display = (
            f"\n\nInstruction: {self.instructions}\n"
            if self.instructions is not None
            else ""
        )
        return TAU_BENCH_SYSTEM_PROMPT.format(
            instruction_display=instruction_display,
            stop=STOP,
            unsatisfied=UNSATISFIED,
        )

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> UserStateType:
        """
        Get the initial state of the user simulator.
        """
        if message_history is None:
            message_history = []
        assert all(is_valid_user_history_message(m) for m in message_history), (
            "Invalid user message history. User messages must be of type UserMessage, AssistantMessage, or ToolMessage to User."
        )

        user_state = UserState(
            system_messages=[SystemMessage(role="system", content=self.system_prompt)],
            messages=message_history,
        )
        return user_state

    @classmethod
    def is_stop(cls, message: UserMessage) -> bool:
        """
        Check if the message is a stop message.

        Recognizes STOP, TRANSFER, OUT_OF_SCOPE, and UNSATISFIED. The latter
        is an emotion-aware early termination (see is_unsatisfied()).
        """
        if message.is_tool_call():
            return False
        # Messages without text content cannot be stop messages
        if message.content is None:
            return False
        return (
            STOP in message.content
            or TRANSFER in message.content
            or OUT_OF_SCOPE in message.content
            or UNSATISFIED in message.content
        )

    @classmethod
    def is_unsatisfied(cls, message: UserMessage) -> bool:
        """Return True iff the user emitted UNSATISFIED on this turn.

        Used by the orchestrator to distinguish an emotion-driven early
        exit (TerminationReason.USER_UNSATISFIED) from a regular
        TerminationReason.USER_STOP.
        """
        if message.is_tool_call():
            return False
        if message.content is None:
            return False
        return UNSATISFIED in message.content

    def generate_next_message(
        self, message: ValidUserInputMessage, state: UserStateType
    ) -> Tuple[UserMessage, UserStateType]:
        user_message = self._generate_next_message(message, state)
        # Updating state with response
        state.messages.append(user_message)
        return user_message, state

    def _generate_next_message(
        self, message: ValidUserInputMessage, state: UserStateType
    ) -> UserMessage:
        """Get the response from the user simulator.

        Args:
            message: The assistant or tool message.
            state: The user simulator's state.

        Returns:
            The user message.
        """
        logger.debug(f"User responds to message: {message}")
        # Updating state with new message
        # Skip empty messages
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        elif isinstance(message, ToolMessage):
            # ToolMessage always has content (tool response)
            state.messages.append(message)
        elif message.has_content() or message.is_tool_call():
            state.messages.append(message)
        messages = state.system_messages + state.flip_roles()

        # Generate response
        assistant_message = generate(
            model=self.llm,
            messages=messages,
            tools=self.tools,
            call_name="user_simulator_response",
            **self.llm_args,
        )

        user_response = assistant_message.content
        logger.debug(f"Response: {user_response}")

        user_message = UserMessage(
            role="user",
            content=user_response,
            cost=assistant_message.cost,
            usage=assistant_message.usage,
            raw_data=assistant_message.raw_data,
        )

        # flip the requestor of the tool calls
        if assistant_message.tool_calls is not None:
            user_message.tool_calls = []
            for tool_call in assistant_message.tool_calls:
                user_message.tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        name=tool_call.name,
                        arguments=tool_call.arguments,
                        requestor="user",
                    )
                )
        return user_message


class DummyUser(UserSimulator):
    """A dummy user to run a agent solo simulation."""

    def __init__(self):
        super().__init__(llm="dummy")

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> UserState:
        return UserState(messages=[], system_messages=[])

    def is_stop(cls, message: UserMessage) -> bool:
        raise NotImplementedError("DummyUser does not support stop messages")

    def set_seed(self, seed: int):
        pass

    def generate_next_message(
        self, message: ValidUserInputMessage, state: UserState
    ) -> tuple[UserMessage, UserState]:
        raise NotImplementedError("DummyUser does not support generate_next_message")
