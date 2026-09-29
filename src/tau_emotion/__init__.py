"""
Tau-Emotion: Conversational Agent Benchmark Framework

Main exports for easy access to key components.
"""

import warnings

# Runner package: clean API for simulation execution
# - Layer 1: run_simulation (execute pre-built orchestrator)
# - Layer 2: build_* functions (construct instances from config/names)
# - Layer 3: run_domain, run_tasks, run_single_task (batch execution)
import tau_emotion.runner as runner
from tau_emotion.agent.base.llm_config import LLMConfigMixin
from tau_emotion.agent.base_agent import HalfDuplexAgent
from tau_emotion.agent.llm_agent import LLMAgent, LLMSoloAgent
from tau_emotion.data_model.simulation import (
    BaseRunConfig,
    RunConfig,
    SimulationRun,
    TextRunConfig,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.environment.environment import Environment
from tau_emotion.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau_emotion.orchestrator.modes import CommunicationMode
from tau_emotion.orchestrator.orchestrator import Orchestrator
from tau_emotion.registry import Registry, registry
from tau_emotion.run import run_domain
from tau_emotion.user.user_simulator import UserSimulator
from tau_emotion.user.user_simulator_base import HalfDuplexUser
from tau_emotion.utils.display import ConsoleDisplay, MarkdownDisplay

__all__ = [
    # Core
    "Orchestrator",
    "LLMAgent",
    "LLMSoloAgent",
    "LLMConfigMixin",
    "UserSimulator",
    "HalfDuplexAgent",
    "HalfDuplexUser",
    "Environment",
    "Registry",
    "registry",
    "SimulationRun",
    "Task",
    "evaluate_simulation",
    "EvaluationType",
    "BaseRunConfig",
    "TextRunConfig",
    "RunConfig",
    "run_domain",
    "runner",
    "CommunicationMode",
    # Utils
    "ConsoleDisplay",
    "MarkdownDisplay",
]
