"""
Layer 3: Batch runner.

Orchestrates batch execution with concurrency, checkpointing, retries,
logging, and optional side effects (auto-review).

Uses Layer 2 (build) to construct instances and Layer 1 (simulation) to
execute them.
"""

import asyncio
import asyncio.base_events
import json
import multiprocessing
import os
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from loguru import logger

from tau_emotion.data_model.simulation import (
    Results,
    RunConfig,
    SimulationRun,
    TextRunConfig,
    UserInfo,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.evaluator.evaluator import EvaluationType
from tau_emotion.metrics.agent_metrics import compute_metrics
from tau_emotion.registry import registry
from tau_emotion.runner.build import _build_env_kwargs, build_orchestrator
from tau_emotion.runner.checkpoint import (
    create_checkpoint_fns,
    try_resume,
)
from tau_emotion.runner.helpers import get_info, get_tasks, make_run_name
from tau_emotion.runner.progress import StatusMonitor, run_with_retry
from tau_emotion.runner.simulation import run_simulation
from tau_emotion.user.user_simulator import get_global_user_sim_guidelines
from tau_emotion.utils.display import ConsoleDisplay, Text
from tau_emotion.utils.llm_utils import llm_log_mode, set_llm_log_dir, set_llm_log_mode
from tau_emotion.utils.utils import DATA_DIR

# Context variable to track current simulation_id for log filtering
# This ensures task-specific log handlers only receive their own messages
_current_simulation_id: ContextVar[Optional[str]] = ContextVar(
    "_current_simulation_id", default=None
)


# =============================================================================
# Asyncio event loop management for worker threads
# =============================================================================

_original_del = asyncio.base_events.BaseEventLoop.__del__


def _patched_del(self):
    try:
        _original_del(self)
    except AttributeError:
        pass


asyncio.base_events.BaseEventLoop.__del__ = _patched_del


def _close_event_loop_safely(loop):
    if loop is None or loop.is_closed():
        return
    try:
        if hasattr(loop, "_ssock") and loop._ssock is not None:
            loop.close()
        elif hasattr(loop, "_closed") and not loop._closed:
            loop._closed = True
            if hasattr(loop, "_selector") and loop._selector is not None:
                loop._selector.close()
                loop._selector = None
    except (AttributeError, OSError):
        pass


def _init_thread_event_loop():
    try:
        old_loop = asyncio.get_event_loop_policy().get_event_loop()
        _close_event_loop_safely(old_loop)
    except RuntimeError:
        pass

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass


def _cleanup_thread_event_loop():
    """Close the thread-local event loop so it doesn't leak into GC."""
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        _close_event_loop_safely(loop)
    except RuntimeError:
        pass
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass


# =============================================================================
# Side-effect helpers
# =============================================================================


def run_auto_review(
    simulation: SimulationRun,
    task: Task,
    review_mode: str,
    user: str,
    llm_user: Optional[str],
    llm_args_user: Optional[dict],
    policy: str,
) -> None:
    """Run LLM conversation review on a simulation and attach results.

    Args:
        simulation: The completed simulation to review.
        task: The task specification.
        review_mode: "full" (agent+user) or "user" (user only).
        user: User implementation name.
        llm_user: LLM used by user simulator.
        llm_args_user: LLM args for user simulator.
        policy: Environment policy string.
    """
    from tau_emotion.evaluator.reviewer import ReviewMode, review_simulation

    review_mode_enum = ReviewMode.FULL if review_mode == "full" else ReviewMode.USER

    review_guidelines = get_global_user_sim_guidelines()

    review_user_info = UserInfo(
        implementation=user,
        llm=llm_user,
        llm_args=llm_args_user,
        global_simulation_guidelines=review_guidelines,
    )

    logger.info(f"Starting review for task {task.id} (mode: {review_mode})...")

    review_result, auth_result = review_simulation(
        simulation=simulation,
        task=task,
        mode=review_mode_enum,
        user_info=review_user_info,
        policy=policy,
    )

    if review_mode == "full":
        simulation.review = review_result
        simulation.auth_classification = auth_result
    else:
        simulation.user_only_review = review_result

    logger.info(
        f"Review completed for task {task.id}: has_errors={review_result.has_errors}"
    )


# =============================================================================
# Per-task logging context manager
# =============================================================================


class _TaskLogContext:
    """Manages per-task log files and LLM debug logging."""

    def __init__(
        self,
        simulation_id: str,
        save_dir: Optional[Path],
        task: Task,
        verbose_logs: bool,
    ):
        self.simulation_id = simulation_id
        self.save_dir = save_dir
        self.task = task
        self.verbose_logs = verbose_logs
        self.task_log_dir: Optional[Path] = None
        self._handler_id = None

    def __enter__(self):
        if self.save_dir:
            self.task_log_dir = (
                self.save_dir
                / "artifacts"
                / f"task_{self.task.id}"
                / f"sim_{self.simulation_id}"
            )

        if self.verbose_logs and self.task_log_dir:
            self.task_log_dir.mkdir(parents=True, exist_ok=True)
            _current_simulation_id.set(self.simulation_id)

            def make_simulation_filter(sim_id: str):
                def simulation_filter(record):
                    return _current_simulation_id.get() == sim_id

                return simulation_filter

            log_file_path = self.task_log_dir / "task.log"
            self._handler_id = logger.add(
                log_file_path,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                level="DEBUG",
                rotation=None,
                enqueue=True,
                filter=make_simulation_filter(self.simulation_id),
            )
            logger.debug(f"Task log file: {log_file_path}")

        if self.task_log_dir and self.verbose_logs:
            llm_log_dir = self.task_log_dir / "llm_debug"
            set_llm_log_dir(llm_log_dir)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and self.task_log_dir and self.task_log_dir.exists():
            status = {
                "status": "failed",
                "reason": "infrastructure_error",
                "error": str(exc_val),
                "error_type": exc_type.__name__,
            }
            try:
                status_path = self.task_log_dir / "sim_status.json"
                with open(status_path, "w") as f:
                    json.dump(status, f, indent=2)
            except Exception:
                pass

        if self.save_dir:
            set_llm_log_dir(None)
        if self._handler_id is not None:
            logger.remove(self._handler_id)
            _current_simulation_id.set(None)
        return False


# =============================================================================
# Single task runner (Layer 3 wrapper over Layers 1+2)
# =============================================================================


def run_single_task(
    config: RunConfig,
    task: Task,
    *,
    seed: Optional[int] = None,
    evaluation_type: EvaluationType = EvaluationType.ALL,
    save_dir: Optional[Path] = None,
    verbose_logs: bool = False,
    auto_review: bool = False,
    review_mode: str = "full",
) -> SimulationRun:
    """Run a single task simulation with logging and optional side effects.

    This is the Layer 3 per-task function. It:
    1. Sets up per-task logging.
    2. Builds an orchestrator via Layer 2 (build_orchestrator).
    3. Runs the simulation via Layer 1 (run_simulation).
    4. Optionally runs auto-review.
    5. Cleans up logging.

    Args:
        config: The run configuration.
        task: The task to run.
        seed: Random seed for this trial.
        evaluation_type: Evaluation type to use.
        save_dir: Directory for saving logs.
        verbose_logs: Enable per-task log files.
        auto_review: Run LLM conversation review after simulation.
        review_mode: Review mode ("full" or "user").

    Returns:
        The completed SimulationRun with reward_info attached.
    """
    simulation_id = str(uuid.uuid4())

    logger.info(
        f"STARTING SIMULATION: Domain: {config.domain}, Task: {task.id}, "
        f"Agent: {config.effective_agent}, User: {config.effective_user}"
    )

    with _TaskLogContext(simulation_id, save_dir, task, verbose_logs):
        # Layer 2: Build the orchestrator
        orchestrator = build_orchestrator(
            config,
            task,
            seed=seed,
            simulation_id=simulation_id,
        )

        # Layer 1: Run the simulation
        env_kwargs = _build_env_kwargs(config, task) or None
        simulation = run_simulation(
            orchestrator, evaluation_type=evaluation_type, env_kwargs=env_kwargs
        )

        # Side effects
        if auto_review:
            run_auto_review(
                simulation=simulation,
                task=task,
                review_mode=review_mode,
                user=config.effective_user,
                llm_user=config.llm_user,
                llm_args_user=config.llm_args_user,
                policy=orchestrator.environment.get_policy(),
            )

        logger.info(
            f"FINISHED SIMULATION: Domain: {config.domain}, Task: {task.id}, "
            f"Reward: {simulation.reward_info.reward if simulation.reward_info else 'N/A'}"
        )

        return simulation


# =============================================================================
# Batch runner
# =============================================================================


def run_tasks(
    config: RunConfig,
    tasks: list[Task],
    *,
    save_path: Optional[Path] = None,
    save_dir: Optional[Path] = None,
    evaluation_type: EvaluationType = EvaluationType.ALL,
    console_display: bool = True,
    results_format: str = "json",
) -> Results:
    """Run simulations for a list of tasks with concurrency, checkpointing, and retries.

    This is the main batch execution function. It handles:
    - Seed management and trial repetition
    - Checkpoint save/resume
    - Concurrent execution via thread pool
    - Progress monitoring
    - Retry on failure

    Args:
        config: Full run configuration (includes domain, agent, user, LLM settings,
            num_trials, max_concurrency, retry settings, etc.).
        tasks: The tasks to run.
        save_path: Path to the results JSON file. If None, results are not persisted.
        save_dir: Directory for saving logs, etc. If None, derived from save_path.
        evaluation_type: Evaluation type to use for all simulations.
        console_display: Whether to show console output for each simulation.

    Returns:
        Results object with all simulation runs.

    Raises:
        ValueError: If no tasks are provided, or trial/step/error counts are invalid.
    """
    if isinstance(save_path, str):
        save_path = Path(save_path)

    # Set log level from config
    logger.remove()
    logger.add(lambda msg: print(msg), level=config.log_level)

    if len(tasks) == 0:
        raise ValueError("No tasks to run")
    if config.num_trials <= 0:
        raise ValueError("Number of trials must be greater than 0")

    if config.effective_max_steps <= 0:
        raise ValueError("Max steps must be greater than 0")
    if config.max_errors <= 0:
        raise ValueError("Max errors must be greater than 0")

    # Seed management
    random.seed(config.seed)
    seeds = [random.randint(0, 1000000) for _ in range(config.num_trials)]
    if (
        isinstance(config, TextRunConfig)
        and config.llm_args_agent
        and "seed" in config.llm_args_agent
    ):
        logger.warning("Each trial will modify the seed for the agent")
    if config.llm_args_user and "seed" in config.llm_args_user:
        logger.warning("Each trial will modify the seed for the user")

    lock = multiprocessing.Lock()

    # Build Info and initial Results
    policy_override = None
    info = get_info(
        config,
        policy_override=policy_override,
    )
    simulation_results = Results(
        info=info,
        tasks=tasks,
        simulations=[],
    )

    # Checkpoint resume
    done_runs: set = set()
    if save_path is not None:
        simulation_results, done_runs, tasks = try_resume(
            save_path=save_path,
            simulation_results=simulation_results,
            tasks=tasks,
            num_trials=config.num_trials,
            auto_resume=config.auto_resume,
            results_format=results_format,
        )

    # Create checkpoint saver and replacer (shared state for dir format)
    save_fn, _ = create_checkpoint_fns(save_path, lock)

    # Build argument list (skip already-completed runs)
    args = []
    for trial in range(config.num_trials):
        for i, task in enumerate(tasks):
            if (trial, task.id, seeds[trial]) in done_runs:
                console_text = Text(
                    text=f"Skipping task {task.id}, trial {trial + 1} because it has already been run.",
                    style="bold yellow",
                )
                ConsoleDisplay.console.print(console_text)
                continue
            progress_str = f"{i}/{len(tasks)} (trial {trial + 1}/{config.num_trials})"
            args.append((task, trial, seeds[trial], progress_str))

    # Status monitor
    total_count = len(tasks) * config.num_trials
    monitor = StatusMonitor(total_count, initial_completed=len(done_runs))
    monitor.set_results(simulation_results)
    monitor.start()

    shutdown_event = threading.Event()

    # Capture ContextVar values from the main thread so worker threads
    # (which get a fresh default context) can re-apply them.
    _main_thread_llm_log_mode = llm_log_mode.get()

    def _run_tracked(
        task: Task, trial: int, seed: int, progress_str: str
    ) -> SimulationRun:
        """Run a single task with tracking and retry."""
        if shutdown_event.is_set():
            raise KeyboardInterrupt("Shutdown requested")

        _init_thread_event_loop()
        set_llm_log_mode(_main_thread_llm_log_mode)
        task_key = f"{task.id}.{trial}"
        monitor.task_started(task_key, trial)

        console_text = Text(
            text=f"{progress_str}. Running task {task.id}, trial {trial + 1}",
            style="bold green",
        )
        ConsoleDisplay.console.print(console_text)

        def _execute(run_seed: int = seed):
            return run_single_task(
                config,
                task,
                seed=run_seed,
                evaluation_type=evaluation_type,
                save_dir=save_dir,
                verbose_logs=config.verbose_logs,
                auto_review=config.auto_review,
                review_mode=config.review_mode,
            )

        try:
            result = run_with_retry(
                _execute,
                task=task,
                trial=trial,
                seed=seed,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                console_display=console_display,
                save_fn=save_fn,
                on_retry=lambda: monitor.task_restarted(task_key),
                shutdown_event=shutdown_event,
            )

            # Mark the final sim as the one used in results
            if save_dir is not None:
                sim_dir = (
                    save_dir / "artifacts" / f"task_{task.id}" / f"sim_{result.id}"
                )
                if sim_dir.exists():
                    try:
                        status = {"status": "used"}
                        status_path = sim_dir / "sim_status.json"
                        with open(status_path, "w") as f:
                            json.dump(status, f, indent=2)
                    except Exception:
                        pass

            return result
        finally:
            monitor.task_finished(task_key)
            _cleanup_thread_event_loop()

    executor = ThreadPoolExecutor(max_workers=config.max_concurrency)
    futures: dict = {}
    try:
        futures = {executor.submit(_run_tracked, *arg): arg for arg in args}
        for future in as_completed(futures):
            result = future.result()
            simulation_results.simulations.append(result)
    except KeyboardInterrupt:
        ConsoleDisplay.console.print(
            "\n[bold red]Ctrl+C received — cancelling remaining tasks...[/bold red]"
        )
        shutdown_event.set()
        executor.shutdown(wait=False, cancel_futures=True)

        n = len(simulation_results.simulations)
        ConsoleDisplay.console.print(
            f"[bold yellow]{n} simulation(s) already checkpointed. "
            f"Use --auto-resume to continue later.[/bold yellow]"
        )
        monitor.stop()

        # Force-exit: background threads (litellm's, etc.)
        # hold the process alive and produce noisy errors during interpreter
        # shutdown.  All completed results are already on disk via save_fn.
        os._exit(130)
    finally:
        monitor.stop()
        if not shutdown_event.is_set():
            executor.shutdown(wait=True)

    ConsoleDisplay.console.print(
        "\n[bold green]Successfully completed all simulations![/bold green]\n"
        "To review the simulations, run: [bold blue]tau-emotion view[/bold blue]"
    )
    return simulation_results


# =============================================================================
# Top-level entry points
# =============================================================================


def run_domain(config: RunConfig) -> Results:
    """Run simulations for a domain from a RunConfig.

    This is the main entry point for the CLI and API. It:
    1. Validates the config.
    2. Loads and filters tasks.
    3. Determines save paths.
    4. Delegates to run_tasks() for batch execution.
    5. Computes and displays metrics.

    Args:
        config: Full run configuration.

    Returns:
        Results object with all simulation runs.
    """
    config.validate()
    ConsoleDisplay.display_run_config(config)

    # Load tasks
    task_set_name = config.task_set_name or config.domain
    tasks = get_tasks(
        task_set_name=task_set_name,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
        num_tasks=config.num_tasks,
    )

    # Filter tasks based on agent's registered task filter (if any)
    effective_agent = config.effective_agent
    task_filter = registry.get_agent_task_filter(effective_agent)
    if task_filter is not None:
        total_num_tasks = len(tasks)
        tasks = [task for task in tasks if task_filter(task)]
        num_tasks = len(tasks)
        console_text = Text(
            text=f"Running {num_tasks} out of {total_num_tasks} tasks for {effective_agent} (filtered).",
            style="bold green",
        )
        ConsoleDisplay.console.print(console_text)

    # Determine save paths
    run_name = config.save_to or make_run_name(config)
    save_dir = DATA_DIR / "simulations" / run_name
    save_path = save_dir / "results.json"

    # Run batch
    simulation_results = run_tasks(
        config,
        tasks,
        save_path=save_path,
        save_dir=save_dir,
    )

    # Compute and display metrics
    metrics = compute_metrics(simulation_results)
    ConsoleDisplay.display_agent_metrics(metrics)

    return simulation_results
