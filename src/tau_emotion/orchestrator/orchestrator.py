import json
import time
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from litellm.exceptions import ContextWindowExceededError
from loguru import logger

from tau_emotion.agent.base_agent import (
    AgentError,
    HalfDuplexAgent,
    is_valid_agent_history_message,
)
from tau_emotion.agent.llm_agent import LLMSoloAgent
from tau_emotion.config import DEFAULT_MAX_ERRORS, DEFAULT_MAX_STEPS, TERMINATE_TOOLS
from tau_emotion.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau_emotion.data_model.simulation import SimulationRun, TerminationReason
from tau_emotion.data_model.tasks import EnvFunctionCall, InitializationData, Task
from tau_emotion.environment.environment import Environment
from tau_emotion.orchestrator.modes import CommunicationMode
from tau_emotion.user.user_simulator import DummyUser, UserSimulator, UserState
from tau_emotion.user.user_simulator_base import (
    HalfDuplexUser,
    UserError,
    is_valid_user_history_message,
)
from tau_emotion.utils.llm_utils import get_cost
from tau_emotion.utils.utils import format_time, get_now


class Role(str, Enum):
    AGENT = "agent"
    USER = "user"
    ENV = "env"


DEFAULT_FIRST_AGENT_MESSAGE = AssistantMessage(
    role="assistant", content="Hi! How can I help you today?", cost=0.0
)

# Type variables for generic orchestrators
# Base types for BaseOrchestrator
BaseAgentT = TypeVar("BaseAgentT")
BaseUserT = TypeVar("BaseUserT")
TrajectoryItemT = TypeVar("TrajectoryItemT")  # Message for half-duplex

# Half-duplex specific types for Orchestrator
AgentT = TypeVar("AgentT", bound=HalfDuplexAgent)
UserT = TypeVar("UserT", bound=HalfDuplexUser)


class BaseOrchestrator(ABC, Generic[BaseAgentT, BaseUserT, TrajectoryItemT]):
    """
    Abstract base class for orchestrators.

    Provides the common infrastructure for managing simulations between Agent, User,
    and Environment. Subclasses implement specific communication patterns:
    - Orchestrator: Half-duplex (turn-based) communication, trajectory of Messages

    Type Parameters:
        BaseAgentT: The agent type
        BaseUserT: The user type
        TrajectoryItemT: The trajectory item type (Message for half-duplex)

    Shared Responsibilities:
        - Environment initialization and tool execution
        - Termination tracking (max steps, max errors, done state)
        - Trajectory management
        - Simulation run lifecycle (initialize, step loop, finalize)

    Subclass Responsibilities:
        - Communication-specific initialization
        - Step implementation for their communication pattern
        - Mode-specific termination checks
    """

    def __init__(
        self,
        domain: str,
        agent: BaseAgentT,
        user: BaseUserT,
        environment: Environment,
        task: Task,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_errors: int = DEFAULT_MAX_ERRORS,
        seed: Optional[int] = None,
        simulation_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize the base orchestrator.

        Args:
            domain: The domain name of the simulation (e.g., 'airline', 'retail', 'telecom').
            agent: The agent instance.
            user: The user instance.
            environment: The environment instance that handles tool execution.
            task: The task specification containing initial state, goals, and evaluation criteria.
            max_steps: Maximum number of simulation steps before termination. Defaults to 100.
            max_errors: Maximum number of tool execution errors before termination. Defaults to 10.
            seed: Optional random seed for reproducibility. Defaults to None.
            simulation_id: Optional simulation ID. Defaults to generated UUID.
            timeout: Maximum wallclock time in seconds. None means no timeout.
        """
        self.domain = domain
        self.agent: BaseAgentT = agent
        self.user: BaseUserT = user
        self.environment = environment
        self.task = task
        self.seed = seed
        self.simulation_id = simulation_id or str(uuid.uuid4())

        # State tracking
        self.agent_state: Optional[Any] = None
        self.user_state: Optional[UserState] = None

        # Termination tracking
        self.max_steps: int = max_steps
        self.max_errors: int = max_errors
        self.timeout: Optional[float] = timeout
        self.step_count: int = 0
        self.done: bool = False
        self.termination_reason: Optional[TerminationReason] = None
        self.num_errors: int = 0
        self._run_start_time: Optional[str] = None
        self._run_start_perf: Optional[float] = None

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the orchestrator for simulation.

        Subclasses must implement mode-specific initialization:
        - Set up environment state
        - Initialize agent and user states
        - Set up initial messages
        """
        pass

    @abstractmethod
    def step(self) -> None:
        """
        Perform one step of the simulation.

        Subclasses implement their communication pattern:
        - Half-duplex: Turn-based message passing
        """
        pass

    @abstractmethod
    def get_trajectory(self) -> list[TrajectoryItemT]:
        """
        Get the trajectory of the simulation.

        Returns:
            List of trajectory items. Type depends on orchestrator mode:
            - Orchestrator (half-duplex): list[Message]
        """
        pass

    @abstractmethod
    def get_messages(self) -> list[Message]:
        """
        Get all messages from the simulation as a flat list.

        This provides a consistent way to get messages regardless of orchestrator mode.
        For half-duplex, this is the same as get_trajectory().

        Returns:
            List of all messages sorted by timestamp with turn_idx assigned.
        """
        pass

    @abstractmethod
    def _validate_mode_compatibility(self) -> None:
        """
        Validate that the agent and user support this communication mode.

        Raises:
            ValueError: If agent or user don't support the required mode.
        """
        pass

    @abstractmethod
    def _check_termination(self) -> None:
        """
        Check for termination conditions specific to this communication mode.

        Sets self.done and self.termination_reason if termination conditions are met.
        """
        pass

    @abstractmethod
    def _finalize(self) -> SimulationRun:
        """
        Finalize the simulation and create the SimulationRun result.

        Called after the simulation loop completes. Should:
        - Send stop signals to agent and user
        - Calculate costs
        - Build and return SimulationRun

        Returns:
            SimulationRun with all simulation data.
        """
        pass

    def _check_timeout(self) -> None:
        if (
            self.timeout is not None
            and self._run_start_perf is not None
            and not self.done
        ):
            elapsed = time.perf_counter() - self._run_start_perf
            if elapsed >= self.timeout:
                self.done = True
                self.termination_reason = TerminationReason.TIMEOUT
                logger.info(
                    f"Simulation timed out after {elapsed:.1f}s (timeout={self.timeout}s)"
                )

    def _cleanup(self) -> None:
        """Best-effort cleanup of agent and user resources.

        Called from the ``finally`` block of :meth:`run` so that background
        threads and other resources are released
        even when ``step()`` raises an unexpected exception.

        On the normal (non-error) path ``_finalize()`` handles cleanup
        as part of building the result, so this method is a no-op.
        """
        try:
            if hasattr(self, "agent") and self.agent is not None:
                self.agent.stop(None, getattr(self, "agent_state", None))
        except Exception as e:
            logger.warning(f"Error during agent cleanup: {e}")

        try:
            if hasattr(self, "user") and self.user is not None:
                self.user.stop(None, getattr(self, "user_state", None))
        except Exception as e:
            logger.warning(f"Error during user cleanup: {e}")

    def run(self) -> SimulationRun:
        """
        Run the simulation.

        Template method that orchestrates the simulation lifecycle:
        1. Initialize the simulation
        2. Step until done
        3. Check termination conditions after each step
        4. Finalize and return results

        Returns:
            SimulationRun: The simulation run with all results.
        """
        self._run_start_time = get_now()
        self._run_start_perf = time.perf_counter()
        self.initialize()

        finalized = False
        try:
            while not self.done:
                self.step()
                self._check_termination()
            result = self._finalize()
            finalized = True
            return result
        finally:
            if not finalized:
                logger.warning(
                    "Simulation loop exited with an exception — "
                    "running emergency cleanup"
                )
                self._cleanup()

    def _initialize_environment(
        self,
        initialization_data: Optional[InitializationData],
        initialization_actions: Optional[list[EnvFunctionCall]],
        message_history: list[Message],
    ) -> None:
        """
        Initialize the environment with the given state.

        Args:
            initialization_data: Optional data to initialize environment state.
            initialization_actions: Optional actions to execute during initialization.
            message_history: Message history for context.
        """
        self.environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )

    @staticmethod
    def _apply_tau_bench_message_conventions(agent_msg: AssistantMessage) -> None:
        """Apply τ-bench's conventions to the agent's message, then validate it.

        τ-bench's tool-calling agent keeps only the first tool call of a message
        (tracer/tracer/agents/tool_calling_agent.py: `tool_calls[:1]`) and passes
        a reply with no content on to the user as it is (`message_to_action`)
        instead of failing the run; here it goes out as an empty message. The
        message is edited in place, so the agent's own history carries the same
        one forward.
        """
        if agent_msg.tool_calls and len(agent_msg.tool_calls) > 1:
            logger.debug(
                f"Keeping the first of {len(agent_msg.tool_calls)} tool calls, "
                "as τ-bench does"
            )
            del agent_msg.tool_calls[1:]
        if not agent_msg.has_content() and not agent_msg.is_tool_call():
            logger.warning(
                "Agent returned no content and no tool call; sending an empty "
                "message to the user, as τ-bench does"
            )
            agent_msg.content = ""
            return
        agent_msg.validate()

    def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolMessage]:
        """
        Execute tool calls and return results.

        Args:
            tool_calls: List of tool calls to execute.

        Returns:
            List of ToolMessage results from the environment.
        """
        tool_results = []
        for tool_call in tool_calls:
            tool_result = self.environment.get_response(tool_call)
            if tool_result.error:
                self.num_errors += 1
            tool_results.append(tool_result)
        return tool_results

    def _wrap_tool_results(self, tool_results: list[ToolMessage]) -> Message:
        """
        Wrap tool results in appropriate message type.

        Args:
            tool_results: List of tool message results.

        Returns:
            Single ToolMessage if one result, MultiToolMessage if multiple.
        """
        if len(tool_results) > 1:
            return MultiToolMessage(role="tool", tool_messages=tool_results)
        return tool_results[0]


class Orchestrator(BaseOrchestrator[AgentT, UserT, Message]):
    """
    Orchestrator for half-duplex (turn-based) simulation.

    Passes messages between the Agent, User, and Environment in alternating turns.

    Communication Protocol:
        The orchestrator manages message flow between three roles: AGENT, USER, and ENV(ironment).
        Messages are passed in a turn-based manner following these rules:

        Message Types:
            - AssistantMessage: Sent by the agent
            - UserMessage: Sent by the user
            - ToolMessage: Sent by the environment in response to tool calls
            - MultiToolMessage: Wraps multiple tool messages when multiple tool calls are made

        Message Content Rules:
            1. Messages must contain EITHER text content OR tool calls, never both
            2. Messages cannot be empty (must have either text or tool calls)
            3. Tool calls must be followed by corresponding tool messages from the environment

        Communication Flow:
            - AGENT -> USER: Agent sends text response to user
            - AGENT -> ENV: Agent makes tool call(s) to environment
            - USER -> AGENT: User sends text message to agent
            - USER -> ENV: User makes tool call(s) to environment
            - ENV -> AGENT: Environment returns tool results to agent (after agent's tool call)
            - ENV -> USER: Environment returns tool results to user (after user's tool call)

        Solo Mode:
            In solo mode, the user is replaced by a DummyUser and the agent operates autonomously:
            - Agent can ONLY send tool calls (no text messages to user)
            - Exception: Agent can send stop signal (###STOP###) to end simulation
            - Agent interacts exclusively with the environment until completion

        Termination:
            Simulation ends when:
            - Agent sends stop signal (###STOP###)
            - User sends stop signal
            - Maximum steps (max_steps) reached
            - Maximum errors (max_errors) reached
            - Communication protocol violation detected (if validate_communication=True)
    """

    def __init__(
        self,
        domain: str,
        agent: AgentT,
        user: UserT,
        environment: Environment,
        task: Task,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_errors: int = DEFAULT_MAX_ERRORS,
        seed: Optional[int] = None,
        solo_mode: bool = False,
        simulation_id: Optional[str] = None,
        validate_communication: bool = False,
        timeout: Optional[float] = None,
    ):
        """
        Initialize the Orchestrator for managing simulation between Agent, User, and Environment.

        This orchestrator implements half-duplex (turn-based) communication where agent and user
        alternate sending complete messages.

        Args:
            domain: The domain name of the simulation (e.g., 'airline', 'retail', 'telecom').
            agent: The agent instance that will respond to user requests and make tool calls.
            user: The user instance that interacts with the agent (can be UserSimulator or DummyUser).
            environment: The environment instance that handles tool execution and maintains state.
            task: The task specification containing initial state, goals, and evaluation criteria.
            max_steps: Maximum number of simulation steps before termination. Defaults to 100.
            max_errors: Maximum number of tool execution errors before termination. Defaults to 10.
            seed: Optional random seed for reproducibility of agent and user behavior. Defaults to None.
            solo_mode: If True, agent operates without user interaction (only tool calls allowed).
                      Requires agent to be LLMSoloAgent, and user to be DummyUser.
                      Defaults to False.
            validate_communication: If True, validates communication protocol rules (e.g., no mixed
                                   messages with both text and tool calls). Defaults to False.
            timeout: Maximum wallclock time in seconds. None means no timeout.
        """
        # Initialize base class
        super().__init__(
            domain=domain,
            agent=agent,
            user=user,
            environment=environment,
            task=task,
            max_steps=max_steps,
            max_errors=max_errors,
            seed=seed,
            simulation_id=simulation_id,
            timeout=timeout,
        )

        # Half-duplex specific attributes
        self.mode = CommunicationMode.HALF_DUPLEX
        self.trajectory: list[Message] = []
        self.solo_mode = solo_mode
        self.validate_communication = validate_communication

        # Turn-based routing state
        self.from_role: Optional[Role] = None
        self.to_role: Optional[Role] = None
        self.message: Optional[Message] = None

        # Validate mode compatibility
        self._validate_mode_compatibility()

    def _validate_mode_compatibility(self):
        """
        Validate that the agent and user support half-duplex communication.

        Raises:
            ValueError: If agent or user don't support half-duplex mode.
        """
        if not hasattr(self.agent, "generate_next_message"):
            raise ValueError(
                f"Agent {self.agent.__class__.__name__} must have 'generate_next_message' method."
            )

        if not hasattr(self.user, "generate_next_message"):
            raise ValueError(
                f"User {self.user.__class__.__name__} must have 'generate_next_message' method."
            )

        logger.info(
            f"Orchestrator initialized in HALF_DUPLEX mode (turn-based) with "
            f"agent={self.agent.__class__.__name__}, "
            f"user={self.user.__class__.__name__}"
        )

    def initialize(self):
        """
        Initialize the orchestrator.
        - If the tasks specifies an initial state, use it to initialize the environment.
        - Initialize the agent and user states.
        - Send the first message (default message from the agent to the user).
        """
        initial_state = self.task.initial_state
        initialization_data = (
            initial_state.initialization_data if initial_state is not None else None
        )
        initialization_actions = (
            initial_state.initialization_actions if initial_state is not None else None
        )
        message_history = (
            deepcopy(initial_state.message_history)
            if initial_state is not None and initial_state.message_history is not None
            else []
        )
        for msg in message_history:
            msg.turn_idx = None

        # Add timestamps to the message history
        message_history = self._add_timestamps(message_history)

        if self.solo_mode:
            assert self.environment.solo_mode, "Environment should be in solo mode"
            assert isinstance(self.agent, LLMSoloAgent), (
                "Agent must be a LLMSoloAgent in solo mode"
            )
            assert isinstance(self.user, DummyUser), (
                "User must be a DummyUser in solo mode"
            )

        # Initialize Environment state
        self._initialize_environment(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )

        # Set seeds for the agent, user
        if self.seed is not None:
            self.agent.set_seed(self.seed)
            self.user.set_seed(self.seed)

        # Initialize the agent and user states
        if len(message_history) > 0:
            self.validate_message_history(message_history)

            last_message = message_history[-1]
            # Last message is an assistant message
            if isinstance(last_message, AssistantMessage):
                self.from_role = Role.AGENT
                if not last_message.is_tool_call():  # Last message is for the user
                    self.to_role = Role.USER
                else:  # Last message is for the environment
                    self.to_role = Role.ENV
                self.agent_state = self.agent.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history
                        if is_valid_agent_history_message(msg)
                    ]
                )
                self.user_state = self.user.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history[:-1]
                        if is_valid_user_history_message(msg)
                    ]
                )
                self.message = last_message
                if self.agent.is_stop(last_message):
                    self.done = True
                    self.termination_reason = TerminationReason.AGENT_STOP
            # Last message is a user message
            elif isinstance(last_message, UserMessage):
                self.from_role = Role.USER
                if not last_message.is_tool_call():  # Last message is for the agent
                    self.to_role = Role.AGENT
                else:  # Last message is for the environment
                    self.to_role = Role.ENV
                self.user_state = self.user.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history
                        if is_valid_user_history_message(msg)
                    ]
                )
                self.agent_state = self.agent.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history[:-1]
                        if is_valid_agent_history_message(msg)
                    ]
                )
                self.message = last_message
                self.done = UserSimulator.is_stop(last_message)
                if self.done:
                    if UserSimulator.is_unsatisfied(last_message):
                        self.termination_reason = TerminationReason.USER_UNSATISFIED
                    else:
                        self.termination_reason = TerminationReason.USER_STOP
            # Last message is a tool message
            elif isinstance(last_message, ToolMessage):
                self.from_role = Role.ENV
                if last_message.requestor == "assistant":
                    self.to_role = Role.AGENT
                    self.agent_state = self.agent.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history[:-1]
                            if is_valid_agent_history_message(msg)
                        ]
                    )
                    self.user_state = self.user.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history
                            if is_valid_user_history_message(msg)
                        ]
                    )
                else:
                    self.to_role = Role.USER
                    self.agent_state = self.agent.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history
                            if is_valid_agent_history_message(msg)
                        ]
                    )
                    self.user_state = self.user.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history[:-1]
                            if is_valid_user_history_message(msg)
                        ]
                    )
                self.message = last_message
            else:
                raise ValueError(
                    f"Last message should be of type AssistantMessage, UserMessage, or ToolMessage, got {type(last_message)}"
                )
            self.trajectory = message_history
        else:
            # No message history - initialize fresh
            self.user_state = self.user.get_init_state()
            if not self.solo_mode:
                first_message = deepcopy(DEFAULT_FIRST_AGENT_MESSAGE)
                first_message.timestamp = get_now()
                # τ-bench seeds only the user simulator with this greeting; its
                # agent starts from the user's first message.
                self.agent_state = self.agent.get_init_state()
                self.trajectory = [first_message]
                self.message = first_message
                self.from_role = Role.AGENT
                self.to_role = Role.USER
            else:
                self.agent_state = self.agent.get_init_state()
                first_message, self.agent_state = self.agent.generate_next_message(
                    None, self.agent_state
                )
                self.trajectory = [first_message]
                self.message = first_message
                # In solo mode, there is no user, so if the message is not a tool call, then we end and report an agent error
                if not first_message.is_tool_call():
                    self.from_role = Role.AGENT
                    self.to_role = Role.USER
                    self.done = True
                    if self.agent.is_stop(first_message):
                        # If the agent is stopping (###STOP###)
                        self.termination_reason = TerminationReason.AGENT_STOP
                    else:
                        self.termination_reason = TerminationReason.AGENT_ERROR
                else:
                    self.from_role = Role.AGENT
                    self.to_role = Role.ENV
                    self.done = self.agent.is_stop(first_message)
                    if self.done:
                        self.to_role = Role.USER  # FIXIT: For now, we assume last message cannot be to the environment
                        self.termination_reason = TerminationReason.AGENT_STOP

        if self.validate_communication:
            self.check_communication_error()
        self.environment.sync_tools()

    def check_communication_error(self) -> None:
        """
        Check the orchestrator state for communication errors and handle them appropriately.

        Communication errors occur when agents or users violate the communication protocol rules:
        - Empty messages (no text content and no tool calls)
        - Mixed messages (both text content and tool calls in the same message)
        - Solo mode violations (agents sending text content instead of tool calls)

        When a communication error is detected:
        - Sets `self.done = True` to terminate the simulation
        - Sets `self.termination_reason` to either `AGENT_ERROR` or `USER_ERROR`
        - Re-raises any other exceptions that are not communication-related
        """
        try:
            self._check_communication_error()
        except AgentError:
            self.done = True
            self.termination_reason = TerminationReason.AGENT_ERROR
        except UserError:
            self.done = True
            self.termination_reason = TerminationReason.USER_ERROR
        except Exception:
            # Re-raise all other exceptions
            raise

    def _check_communication_error(self) -> None:
        """
        Check the orchestrator state for communication protocol violations.

        Validates that messages follow the communication rules:
        1. Messages must have either text content OR tool calls, not both
        2. Messages cannot be empty (no text content and no tool calls)
        3. In solo mode, agents can only send tool calls (except for stop messages)

        Raises:
            AgentError: When the agent violates communication rules
            UserError: When the user violates communication rules
            ValueError: When from_role is invalid
        """
        if self.from_role == Role.ENV:
            return
        if self.from_role == Role.USER:
            exception_type = UserError
        elif self.from_role == Role.AGENT:
            exception_type = AgentError
        else:
            raise ValueError(f"Invalid from role: {self.from_role}")
        # Check if the message is empty
        if not self.message.is_tool_call() and not self.message.has_text_content():
            raise exception_type(
                f"{self.from_role.value} sent an empty message. {self.message}"
            )
        # Check if the message has both text content and tool calls
        if self.message.is_tool_call() and self.message.has_text_content():
            raise exception_type(
                f"{self.from_role.value} sent both text content and tool calls. {self.message}"
            )

        # Check if the agent is allowed to send a message to the user
        if self.from_role == Role.AGENT and self.solo_mode:
            if self.message.has_text_content() and not self.agent.is_stop(self.message):
                raise exception_type(
                    f"{self.from_role.value} can only send tool calls. {self.message}"
                )

    def _check_termination(self) -> None:
        """
        Check for half-duplex specific termination conditions.

        Only checks max_steps/max_errors/timeout when not waiting for environment response.
        """
        # Skip termination checks if we're waiting for environment to respond
        if self.to_role == Role.ENV:
            return

        if self.step_count >= self.max_steps:
            self.done = True
            self.termination_reason = TerminationReason.MAX_STEPS
        if self.num_errors >= self.max_errors:
            self.done = True
            self.termination_reason = TerminationReason.TOO_MANY_ERRORS
        self._check_timeout()

    def _finalize(self) -> SimulationRun:
        """
        Finalize the half-duplex simulation and create the SimulationRun result.

        Sends stop signals to agent and user, calculates costs, and builds the result.

        Returns:
            SimulationRun with all simulation data.
        """
        # Send stop signal to the agent, user, and environment
        has_error = self.termination_reason in [
            TerminationReason.USER_ERROR,
            TerminationReason.AGENT_ERROR,
        ]

        last_msg_to_agent = None
        last_msg_to_user = None
        if self.to_role == Role.AGENT:
            last_msg_to_agent = self.message
        elif self.to_role == Role.USER:
            last_msg_to_user = self.message
        elif self.to_role == Role.ENV and not has_error:
            raise ValueError(
                "Environment should not receive the last message. Last message: "
                + str(self.message)
            )
        try:
            self.agent.stop(last_msg_to_agent, self.agent_state)
        except Exception as e:
            logger.warning(f"Error stopping agent during finalization: {e}")
        try:
            self.user.stop(last_msg_to_user, self.user_state)
        except Exception as e:
            logger.warning(f"Error stopping user during finalization: {e}")

        # Wrap up the simulation
        duration = time.perf_counter() - self._run_start_perf
        messages = self.get_trajectory()
        res = get_cost(messages)
        if res is None:
            agent_cost, user_cost = None, None
        else:
            agent_cost, user_cost = res

        simulation_run = SimulationRun(
            id=self.simulation_id,
            task_id=self.task.id,
            start_time=self._run_start_time,
            end_time=get_now(),
            duration=duration,
            termination_reason=self.termination_reason.value,
            reward_info=None,
            user_cost=user_cost,
            agent_cost=agent_cost,
            messages=messages,
            seed=self.seed,
            mode=self.mode.value,
        )
        return simulation_run

    def step(self):
        """
        Perform one step of the simulation using half-duplex (turn-based) communication.

        Sends self.message from self.from_role to self.to_role.
        This can either be a message from agent to user/environment, environment to agent,
        or user to agent. Updates self.trajectory.
        """
        if self.done:
            raise ValueError("Simulation is done")
        logger.debug(
            f"Step {self.step_count}. Sending message from {self.from_role} to {self.to_role}"
        )
        logger.debug(
            f"Step {self.step_count}.\nFrom role: {self.from_role}\nTo role: {self.to_role}\nMessage: {self.message}"
        )
        # AGENT/ENV -> USER
        if self.from_role in [Role.AGENT, Role.ENV] and self.to_role == Role.USER:
            user_msg, self.user_state = self.user.generate_next_message(
                self.message, self.user_state
            )
            user_msg.validate()
            if UserSimulator.is_stop(user_msg):
                self.done = True
                if UserSimulator.is_unsatisfied(user_msg):
                    self.termination_reason = TerminationReason.USER_UNSATISFIED
                else:
                    self.termination_reason = TerminationReason.USER_STOP

            self.trajectory.append(user_msg)
            self.message = user_msg
            self.from_role = Role.USER
            if user_msg.is_tool_call():
                self.to_role = Role.ENV
            else:
                self.to_role = Role.AGENT
        # USER/ENV -> AGENT
        elif (
            self.from_role == Role.USER or self.from_role == Role.ENV
        ) and self.to_role == Role.AGENT:
            try:
                agent_msg, self.agent_state = self.agent.generate_next_message(
                    self.message, self.agent_state
                )
            except (json.JSONDecodeError, ContextWindowExceededError) as e:
                # The agent model's own failure (unparsable tool arguments, or a
                # conversation longer than its context): the run scores 0, as in
                # τ-bench, instead of being retried and left out of the metrics
                # as an infrastructure error.
                logger.warning(f"Agent error, ending the simulation: {e}")
                self.done = True
                self.termination_reason = (
                    TerminationReason.CONTEXT_WINDOW_EXCEEDED
                    if isinstance(e, ContextWindowExceededError)
                    else TerminationReason.AGENT_ERROR
                )
                return
            self._apply_tau_bench_message_conventions(agent_msg)
            if self.agent.is_stop(agent_msg):
                self.done = True
                self.termination_reason = TerminationReason.AGENT_STOP

            self.trajectory.append(agent_msg)
            self.message = agent_msg
            self.from_role = Role.AGENT
            if agent_msg.is_tool_call():
                self.to_role = Role.ENV
            else:
                self.to_role = Role.USER
                # In solo mode, there is no user, so if the message is not a tool call and not a stop, then we end and report an agent error
                if self.solo_mode and not self.agent.is_stop(agent_msg):
                    self.done = True
                    self.termination_reason = TerminationReason.AGENT_ERROR
        # AGENT/USER -> ENV
        elif self.from_role in [Role.AGENT, Role.USER] and self.to_role == Role.ENV:
            if not self.message.is_tool_call():
                raise ValueError("Agent or User should send tool call to environment")
            requestor = self.from_role
            called_tools = {tool_call.name for tool_call in self.message.tool_calls}
            tool_results = self._execute_tool_calls(self.message.tool_calls)
            assert len(self.message.tool_calls) == len(tool_results), (
                "Number of tool calls and tool messages should be the same"
            )
            self.trajectory.extend(tool_results)
            self.message = self._wrap_tool_results(tool_results)
            self.to_role = self.from_role
            self.from_role = Role.ENV
            # τ-bench ends the conversation once the agent has called a terminate
            # tool (transfer to a human) and scores the run from here.
            if requestor == Role.AGENT and (called_tools & TERMINATE_TOOLS):
                self.done = True
                self.termination_reason = TerminationReason.AGENT_STOP
        else:
            raise ValueError(
                f"Invalid role combination. From role: {self.from_role}, To role: {self.to_role}"
            )
        if self.validate_communication:
            self.check_communication_error()
        self.step_count += 1
        self.environment.sync_tools()

    def get_trajectory(self) -> list[Message]:
        """
        Get the trajectory of the simulation.
        The trajectory is sorted by timestamp, turn_idx are added to messages, trajectory is returned.
        """
        messages: list[Message] = sorted(
            deepcopy(self.trajectory),
            key=lambda x: x.timestamp,
        )
        trajectory = []
        for i, msg in enumerate(messages):
            msg = deepcopy(msg)
            msg.turn_idx = i
            trajectory.append(msg)
        return trajectory

    def get_messages(self) -> list[Message]:
        """
        Get all messages from the simulation.

        For half-duplex mode, this is the same as get_trajectory().
        """
        return self.get_trajectory()

    @classmethod
    def validate_message_history(cls, message_history: list[Message]):
        """
        Validate a message history.
            - Should only contain AssistantMessage, UserMessage, ToolMessage
            - All assistant/user messages should be either to user or tool call, not both.
            - If n tool calls are made by a participant, exactly n tool messages should follow with requestor matching the participant.
        """
        num_expected_tool_messages = 0
        requestor = None
        for msg in message_history:
            if isinstance(msg, AssistantMessage) or isinstance(msg, UserMessage):
                msg.validate()
                if msg.is_tool_call():
                    if num_expected_tool_messages > 0:
                        raise ValueError(
                            f"{num_expected_tool_messages} tool messages are missing. Got {msg.role} message."
                        )
                    num_expected_tool_messages = len(msg.tool_calls)
                    requestor = msg.role
                else:
                    if num_expected_tool_messages > 0:
                        raise ValueError(
                            f"{num_expected_tool_messages} tool messages are missing. Got {msg.role} message."
                        )
                    requestor = None
            elif isinstance(msg, ToolMessage):
                if num_expected_tool_messages == 0 or requestor is None:
                    raise ValueError("No tool messages expected.")
                if requestor != msg.requestor:
                    raise ValueError(
                        f"Got tool message from {msg.requestor}, expected {requestor}."
                    )
                num_expected_tool_messages -= 1
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")

    def _add_timestamps(
        self, message_history: list[Message]
    ) -> list[tuple[str, Message]]:
        """
        Add timestamps to the message history.
        This is used to sort the messages by timestamp.
        """
        time_offset = datetime.now() - timedelta(seconds=len(message_history))
        for i, msg in enumerate(message_history):
            # Use ISO format (use_compact_format=False) to match get_now() default
            msg.timestamp = format_time(
                time_offset + timedelta(seconds=i), use_compact_format=False
            )
        return message_history
