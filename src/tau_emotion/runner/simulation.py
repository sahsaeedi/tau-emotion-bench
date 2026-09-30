"""
Layer 1: Simulation execution.

Runs a pre-built orchestrator and evaluates the result.
No registry dependency, no config parsing, no side effects.
"""

from typing import Optional

from loguru import logger

from tau_emotion.data_model.simulation import SimulationRun
from tau_emotion.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau_emotion.orchestrator.orchestrator import Orchestrator


def run_simulation(
    orchestrator: Orchestrator,
    *,
    evaluation_type: EvaluationType = EvaluationType.ALL,
    env_kwargs: Optional[dict] = None,
) -> SimulationRun:
    """Run a simulation and evaluate the result.

    Takes a fully constructed orchestrator (with agent, user, environment, and task
    already wired in), runs the simulation, evaluates it, and returns the result
    with reward_info attached.

    This is the lowest-level entry point: it needs no RunConfig. The evaluator
    rebuilds the task's environment from the registry to score the run, so the
    domain must be registered.

    Args:
        orchestrator: A fully constructed Orchestrator. Must have agent, user,
            environment, and task set.
        evaluation_type: The type of evaluation to perform. Defaults to ALL.
        env_kwargs: Additional kwargs passed to the evaluator's environment
            constructor, e.g. {"db_split": "train"} for a train task.

    Returns:
        SimulationRun with reward_info attached.

    Example:
        # Build your own instances (the domain must still be registered,
        # since scoring rebuilds its environment):
        env = MyEnvironment()
        agent = MyAgent(tools=env.get_tools(), domain_policy=env.get_policy())
        user = UserSimulator(
            llm="gpt-4.1",
            instructions=task.user_scenario.to_tau_bench_instruction(),
            tools=env.get_user_tools(),
        )
        orchestrator = Orchestrator(
            domain="airline", agent=agent, user=user, environment=env, task=task,
        )
        result = run_simulation(orchestrator)
        print(result.reward_info.reward)
    """
    # Run the orchestrator
    simulation = orchestrator.run()

    # Save the actual policy used for this simulation
    simulation.policy = orchestrator.environment.get_policy()

    # Extract context from the orchestrator -- no external params needed
    domain = orchestrator.environment.get_domain_name()
    task = orchestrator.task
    solo_mode = getattr(orchestrator, "solo_mode", False)

    # Evaluate
    reward_info = evaluate_simulation(
        simulation=simulation,
        task=task,
        evaluation_type=evaluation_type,
        solo_mode=solo_mode,
        domain=domain,
        env_kwargs=env_kwargs,
    )
    simulation.reward_info = reward_info

    logger.info(
        f"Simulation complete: domain={domain}, task={task.id}, "
        f"reward={reward_info.reward}"
    )

    return simulation
