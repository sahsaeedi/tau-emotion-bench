"""
tau_emotion.run -- Entry point for running simulations.

Thin facade that delegates to the tau_emotion.runner package. All simulation
logic lives in the runner's layered architecture:

    Layer 1 (simulation.py):  run_simulation()
    Layer 2 (build.py):       build_* functions
    Layer 3 (batch.py):       run_domain, run_tasks, run_single_task
    Helpers (helpers.py):     get_tasks, get_options, etc.

Usage:
    # High-level: run all tasks in a domain
    from tau_emotion.run import run_domain
    from tau_emotion.data_model.simulation import TextRunConfig
    results = run_domain(TextRunConfig(domain="retail", agent="llm_agent", ...))

    # Mid-level: run a single task
    from tau_emotion.run import get_tasks, run_single_task
    tasks = get_tasks("mock", task_ids=["create_task_1"])
    result = run_single_task(config, tasks[0], seed=42)

    # Low-level: build and run manually
    from tau_emotion.run import build_orchestrator, run_simulation
    orch = build_orchestrator(config, task, seed=42)
    sim_run = run_simulation(orch)
"""

from tau_emotion.data_model.simulation import (
    RunConfig,
    TextRunConfig,
)
from tau_emotion.evaluator.evaluator import EvaluationType
from tau_emotion.runner import (
    build_agent,
    build_environment,
    build_orchestrator,
    build_text_orchestrator,
    build_user,
    get_environment_info,
    get_info,
    get_options,
    get_tasks,
    load_task_splits,
    load_tasks,
    make_run_name,
    run_domain,
    run_simulation,
    run_single_task,
)
from tau_emotion.runner.batch import run_tasks

__all__ = [
    # Layer 1: Execute
    "run_simulation",
    # Layer 2: Build
    "build_environment",
    "build_agent",
    "build_user",
    "build_orchestrator",
    "build_text_orchestrator",
    # Layer 3: Batch
    "run_domain",
    "run_tasks",
    "run_single_task",
    # Helpers
    "get_options",
    "get_environment_info",
    "load_task_splits",
    "load_tasks",
    "get_tasks",
    "make_run_name",
    "get_info",
    # Re-exports
    "RunConfig",
    "TextRunConfig",
    "EvaluationType",
]
