#!/usr/bin/env python3
from collections import defaultdict
from pathlib import Path
from typing import Optional

from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from tau_emotion.data_model.simulation import (
    Results,
    SimulationRun,
    TerminationReason,
)
from tau_emotion.data_model.tasks import Task
from tau_emotion.metrics.agent_metrics import compute_metrics, is_successful
from tau_emotion.utils.display import ConsoleDisplay
from tau_emotion.utils.utils import DATA_DIR


def get_available_simulations(sim_dir: Optional[Path] = None):
    """Get list of available simulation result files.

    Searches sim_dir at any depth, since default runs are saved under
    <domain>/<agent model>/. Prefers results_reviewed.json (with embedded
    reviews) over results.json in the same run directory.
    """
    if sim_dir is None:
        sim_dir = Path(DATA_DIR) / "simulations"

    if not sim_dir.exists():
        return []

    run_dirs = {
        f.parent
        for name in ("results.json", "results_reviewed.json")
        for f in sim_dir.rglob(name)
    }
    sim_files = []
    for run_dir in run_dirs:
        reviewed_file = run_dir / "results_reviewed.json"
        if reviewed_file.exists():
            sim_files.append(reviewed_file)
        else:
            sim_files.append(run_dir / "results.json")

    return sorted(sim_files)


def display_simulation_list(
    results: Results, only_show_failed: bool = False, only_show_all_failed: bool = False
):
    """Display a numbered list of simulations with basic info using a table."""
    # Calculate number of successful and total trials for each task
    num_success = defaultdict(int)
    for sim in results.simulations:
        reward = sim.reward_info.reward if sim.reward_info else None
        if reward is not None and is_successful(reward):
            num_success[sim.task_id] += 1

    # Filter simulations
    filtered_sims = []
    for i, sim in enumerate(results.simulations, 1):
        reward = sim.reward_info.reward if sim.reward_info else None
        if only_show_failed:
            if reward is None or is_successful(reward):
                continue
        if only_show_all_failed:
            if num_success[sim.task_id] > 0:
                continue
        filtered_sims.append((i, sim))

    if not filtered_sims:
        ConsoleDisplay.console.print("\n[yellow]No simulations match the filter.[/]")
        return

    # Create table with fixed column widths
    table = Table(
        title="Simulations",
        show_header=True,
        header_style="bold cyan",
        box=None,
        pad_edge=False,
        collapse_padding=True,
    )

    # Add columns with fixed widths for alignment
    table.add_column("#", width=4, justify="right", style="dim")
    table.add_column("Task", width=12, no_wrap=True)
    table.add_column("Trial", width=5, justify="center")
    table.add_column("Reward", width=6, justify="center")
    table.add_column("DB", width=2, justify="center")
    table.add_column("Read Acts", width=9, justify="center")
    table.add_column("Write Acts", width=10, justify="center")
    table.add_column("Auth", width=4, justify="center")
    table.add_column("Stop", width=4, justify="center")
    table.add_column("🤖 Err", width=6, justify="center")  # Agent errors
    table.add_column("👤 Err", width=6, justify="center")  # User errors
    table.add_column("🤖 Tags", no_wrap=False)  # Agent error tags
    table.add_column("👤 Tags", no_wrap=False)  # User error tags

    termination_color_map = {
        TerminationReason.USER_STOP: "green",
        TerminationReason.AGENT_STOP: "green",
        TerminationReason.MAX_STEPS: "yellow",
        TerminationReason.TOO_MANY_ERRORS: "red",
        TerminationReason.AGENT_ERROR: "red",
        TerminationReason.USER_ERROR: "red",
        TerminationReason.USER_UNSATISFIED: "red",
        TerminationReason.TIMEOUT: "yellow",
        TerminationReason.CONTEXT_WINDOW_EXCEEDED: "yellow",
        TerminationReason.UNEXPECTED_ERROR: "red",
    }

    termination_icon_map = {
        TerminationReason.USER_STOP: "👤",
        TerminationReason.AGENT_STOP: "🤖",
        TerminationReason.MAX_STEPS: "⏱",
        TerminationReason.TOO_MANY_ERRORS: "💥",
        TerminationReason.AGENT_ERROR: "💥",
        TerminationReason.USER_ERROR: "💥",
        TerminationReason.USER_UNSATISFIED: "😤",
        TerminationReason.TIMEOUT: "⏱",
        TerminationReason.CONTEXT_WINDOW_EXCEEDED: "⏱",
        TerminationReason.UNEXPECTED_ERROR: "💥",
    }

    for i, sim in filtered_sims:
        reward = sim.reward_info.reward if sim.reward_info else None

        # Pass/Fail
        if reward is not None:
            pass_str = "[green]✓[/]" if is_successful(reward) else "[red]✗[/]"
        else:
            pass_str = "[dim]-[/]"

        # DB Match
        if sim.reward_info and sim.reward_info.db_check:
            db_str = "[green]✓[/]" if sim.reward_info.db_check.db_match else "[red]✗[/]"
        else:
            db_str = "[dim]-[/]"

        # Read/Write actions
        read_str = "[dim]-[/]"
        write_str = "[dim]-[/]"
        if sim.reward_info and sim.reward_info.action_checks:
            partial = sim.reward_info.partial_action_reward
            if partial:
                # Show read/write breakdown if tool_type is populated
                if partial.get("read"):
                    r = partial["read"]
                    color = (
                        "green"
                        if r["correct"] == r["count"]
                        else ("yellow" if r["correct"] > 0 else "red")
                    )
                    read_str = f"[{color}]{r['correct']}/{r['count']}[/]"
                if partial.get("write"):
                    w = partial["write"]
                    color = (
                        "green"
                        if w["correct"] == w["count"]
                        else ("yellow" if w["correct"] > 0 else "red")
                    )
                    write_str = f"[{color}]{w['correct']}/{w['count']}[/]"
                # If no read/write breakdown, show total in read column as fallback
                if (
                    not partial.get("read")
                    and not partial.get("write")
                    and partial.get("total")
                ):
                    t = partial["total"]
                    color = (
                        "green"
                        if t["correct"] == t["count"]
                        else ("yellow" if t["correct"] > 0 else "red")
                    )
                    read_str = f"[{color}]{t['correct']}/{t['count']}[/]"
                    write_str = "[dim]n/a[/]"

        # Authentication
        auth_str = "[dim]-[/]"
        if sim.auth_classification:
            if sim.auth_classification.status == "succeeded":
                auth_str = "[green]✓[/]"
            elif sim.auth_classification.status == "failed":
                auth_str = "[red]✗[/]"
            else:  # not_needed
                auth_str = "[dim]n/a[/]"

        # Termination reason
        term_color = termination_color_map.get(sim.termination_reason, "white")
        term_icon = termination_icon_map.get(sim.termination_reason, "?")
        stop_str = f"[{term_color}]{term_icon}[/]"

        # Tag abbreviations
        tag_abbrev = {
            "hallucination": "halluc",
            "incorrect_interpretation": "mis_interp",
            "guideline_violation": "guideline",
            "revealed_info_early": "early_reveal",
            "inconsistent_behavior": "inconsist",
            "tool_call_schema_error": "tc_schema",
            "tool_call_argument_error": "tc_arg",
            "irrelevant_tool_call": "tc_irrel",
            "premature_termination": "early_term",
            "missed_required_action": "missed_act",
            "wrong_sequence": "wrong_seq",
            "other": "other",
        }

        def format_tags_with_severity(errors, is_user: bool = False) -> str:
            """Format error tags with color based on severity."""
            if not errors:
                return "[dim]-[/]"

            # Collect tags with their max severity
            tag_severity: dict[str, str] = {}  # tag -> worst severity
            for e in errors:
                severity = getattr(e, "severity", None)
                for tag in e.error_tags:
                    existing = tag_severity.get(tag)
                    if is_user:
                        # For user errors: critical_helped/critical_hindered > minor > None
                        if severity in ("critical_helped", "critical_hindered"):
                            tag_severity[tag] = "critical"
                        elif existing != "critical":
                            tag_severity[tag] = severity or "minor"
                    else:
                        # For agent errors: critical > minor > None
                        if severity == "critical":
                            tag_severity[tag] = "critical"
                        elif existing != "critical":
                            tag_severity[tag] = severity or "minor"

            # Format with colors
            parts = []
            for tag in sorted(tag_severity.keys()):
                abbrev = tag_abbrev.get(tag, tag[:8])
                sev = tag_severity[tag]
                if sev == "critical":
                    parts.append(f"[red]{abbrev}[/]")
                else:  # minor or None
                    parts.append(f"[yellow]{abbrev}[/]")

            return ", ".join(parts) if parts else "[dim]-[/]"

        # Agent and user errors
        agent_err_str = "[dim]-[/]"
        user_err_str = "[dim]-[/]"
        agent_tags_str = "[dim]-[/]"
        user_tags_str = "[dim]-[/]"

        if sim.review is not None:
            agent_errors = [e for e in sim.review.errors if e.source == "agent"]
            user_errors = [e for e in sim.review.errors if e.source == "user"]

            # Agent errors with severity coloring
            if agent_errors:
                has_critical = any(e.severity == "critical" for e in agent_errors)
                if has_critical:
                    agent_err_str = f"[red]{len(agent_errors)}![/]"
                else:
                    agent_err_str = f"[yellow]{len(agent_errors)}[/]"
                agent_tags_str = format_tags_with_severity(agent_errors, is_user=False)
            else:
                agent_err_str = "[green]0[/]"

            # User errors with severity coloring
            if user_errors:
                has_critical = any(
                    e.severity in ("critical_helped", "critical_hindered")
                    for e in user_errors
                )
                if has_critical:
                    user_err_str = f"[red]{len(user_errors)}![/]"
                else:
                    user_err_str = f"[yellow]{len(user_errors)}[/]"
                user_tags_str = format_tags_with_severity(user_errors, is_user=True)
            else:
                user_err_str = "[green]0[/]"

        elif sim.user_only_review is not None:
            user_errors = sim.user_only_review.errors
            if user_errors:
                has_critical = any(
                    e.severity in ("critical_helped", "critical_hindered")
                    for e in user_errors
                )
                if has_critical:
                    user_err_str = f"[red]{len(user_errors)}![/]"
                else:
                    user_err_str = f"[yellow]{len(user_errors)}[/]"
                user_tags_str = format_tags_with_severity(user_errors, is_user=True)
            else:
                user_err_str = "[green]0[/]"

        # Truncate task ID if needed
        task_id = sim.task_id
        if len(task_id) > 12:
            task_id = task_id[:9] + "..."

        table.add_row(
            str(i),
            task_id,
            str(sim.trial),
            pass_str,
            db_str,
            read_str,
            write_str,
            auth_str,
            stop_str,
            agent_err_str,
            user_err_str,
            agent_tags_str,
            user_tags_str,
        )

    ConsoleDisplay.console.print()
    ConsoleDisplay.console.print(table)

    if only_show_all_failed:
        num_all_failed = len([1 for v in num_success.values() if v == 0])
        ConsoleDisplay.console.print(
            f"\nTotal number of failed tasks: {num_all_failed}"
        )


def display_available_files(files, sim_dir: Optional[Path] = None):
    """Display a numbered list of available simulation files, by run directory."""
    ConsoleDisplay.console.print("\n[bold blue]Available Simulation Files:[/]")
    for i, file in enumerate(files, 1):
        run_dir = file.parent
        if sim_dir is not None and run_dir.is_relative_to(sim_dir):
            run_dir = run_dir.relative_to(sim_dir)
        ConsoleDisplay.console.print(f"[cyan]{i}.[/] {run_dir}")


def display_simulation_with_task(
    simulation: SimulationRun,
    task: Task,
    show_details: bool = True,
):
    """Display a simulation along with its associated task."""
    ConsoleDisplay.console.print("\n" + "=" * 80)  # Separator
    ConsoleDisplay.console.print("[bold blue]Task Details:[/]")
    ConsoleDisplay.display_task(task)

    ConsoleDisplay.console.print("\n" + "=" * 80)  # Separator
    ConsoleDisplay.console.print("[bold blue]Simulation Details:[/]")
    ConsoleDisplay.display_simulation(
        simulation,
        show_details=show_details,
    )


def parse_key(key: str) -> tuple[str, int]:
    """Parse a key into a task ID and trial number."""
    task_id, trial = key.split("-")
    return task_id, int(trial)


def find_task_by_id(tasks, task_id):
    """Find a task in the task list by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
    return None


def find_simulation_by_task_id_and_trial(results, task_id, trial):
    """Get a simulation by its task ID and trial number."""
    return next(
        (
            sim
            for sim in results.simulations
            if sim.task_id == task_id and sim.trial == trial
        ),
        None,
    )


def main(
    sim_file: Optional[str] = None,
    only_show_failed: bool = False,
    only_show_all_failed: bool = False,
    sim_dir: Optional[str] = None,
):
    # Get available simulation files
    if sim_file is None:
        list_root = Path(sim_dir) if sim_dir else Path(DATA_DIR) / "simulations"
        sim_files = get_available_simulations(list_root)
    else:
        list_root = None
        sim_files = [Path(sim_file)]

    if not sim_files:
        dir_path = sim_dir if sim_dir else f"{DATA_DIR}/simulations"
        ConsoleDisplay.console.print(f"[red]No simulation files found in {dir_path}[/]")
        return

    results = None
    current_file = None
    current_sim_path = None
    while True:
        # Show main menu
        ConsoleDisplay.console.print("\n[bold yellow]Main Menu:[/]")
        ConsoleDisplay.console.print("1. Select simulation file")
        ConsoleDisplay.console.print(
            "   [dim]Choose a simulation results file to load and analyze[/]"
        )
        if results:
            ConsoleDisplay.console.print("2. View agent performance metrics")
            ConsoleDisplay.console.print("   [dim]Display agent performance metrics[/]")
            ConsoleDisplay.console.print("3. View simulation")
            ConsoleDisplay.console.print(
                "   [dim]Examine a specific simulation in detail with all its data[/]"
            )
            ConsoleDisplay.console.print("4. View task details")
            ConsoleDisplay.console.print(
                "   [dim]Look at the configuration and parameters of a specific task[/]"
            )
            ConsoleDisplay.console.print("5. View run configuration")
            ConsoleDisplay.console.print(
                "   [dim]Display the configuration used for this simulation run[/]"
            )

            ConsoleDisplay.console.print("6. Exit")
            ConsoleDisplay.console.print("   [dim]Close the simulation viewer[/]")
            choices = ["1", "2", "3", "4", "5", "6"]
            default_choice = "3"
        else:
            ConsoleDisplay.console.print("2. Exit")
            ConsoleDisplay.console.print("   [dim]Close the simulation viewer[/]")
            choices = ["1", "2"]
            default_choice = "1"

        choice = Prompt.ask(
            "\nWhat would you like to do?", choices=choices, default=default_choice
        )

        if choice == "1":
            # Show available files and get selection
            display_available_files(sim_files, list_root)
            # default to view the last file
            file_num = IntPrompt.ask(
                f"\nSelect file number (1-{len(sim_files)})", default=len(sim_files)
            )

            if 1 <= file_num <= len(sim_files):
                try:
                    current_sim_path = sim_files[file_num - 1].parent
                    current_file = current_sim_path.name
                    results = Results.load(sim_files[file_num - 1])
                    ConsoleDisplay.console.print(
                        f"\n[bold green]Loaded {len(results.simulations)} simulations from {current_file}[/]"
                    )

                    # Sort by task_id (as int if possible), then trial
                    def sort_key(sim):
                        task_id = sim.task_id
                        try:
                            return (0, int(task_id), sim.trial)
                        except ValueError:
                            return (1, task_id, sim.trial)

                    results.simulations = sorted(results.simulations, key=sort_key)
                except Exception as e:
                    ConsoleDisplay.console.print(
                        f"[red]Error loading results:[/] {str(e)}"
                    )
            else:
                ConsoleDisplay.console.print("[red]Invalid file number[/]")

        elif choice == "2" and not results:
            break

        elif results and choice == "2":
            # Display metrics
            ConsoleDisplay.console.clear()
            metrics = compute_metrics(results)
            ConsoleDisplay.display_agent_metrics(metrics)
            continue

        elif results and choice == "3":
            # Show list of simulations
            display_simulation_list(results, only_show_failed, only_show_all_failed)

            # Get simulation selection by index
            sim_count = len(results.simulations)
            sim_index = IntPrompt.ask(
                f"\nEnter simulation number (1-{sim_count})", default=1
            )

            if 1 <= sim_index <= sim_count:
                sim = results.simulations[sim_index - 1]
                task = find_task_by_id(results.tasks, sim.task_id)
                if task:
                    display_simulation_with_task(
                        sim,
                        task,
                        show_details=True,
                    )
                else:
                    ConsoleDisplay.console.print(
                        f"[red]Warning: Could not find task for simulation {sim.id}[/]"
                    )
                    ConsoleDisplay.display_simulation(
                        sim,
                        show_details=True,
                    )
                continue
            else:
                ConsoleDisplay.console.print("[red]Invalid simulation number[/]")
                continue

        elif results and choice == "4":
            # Show list of tasks
            ConsoleDisplay.console.print("\n[bold blue]Available Tasks:[/]")
            for i, task in enumerate(results.tasks, 1):
                task_text = Text()
                task_text.append(f"{i}.", style="cyan")
                task_text.append(" Task ID: ")
                task_text.append(task.id)  # This will display square brackets correctly
                ConsoleDisplay.console.print(task_text)

            # Get task selection
            task_count = len(results.tasks)
            task_num = IntPrompt.ask(f"\nEnter task number (1-{task_count})", default=1)

            if 1 <= task_num <= task_count:
                ConsoleDisplay.console.clear()
                ConsoleDisplay.display_task(results.tasks[task_num - 1])
                continue
            else:
                ConsoleDisplay.console.print("[red]Invalid task number[/]")
                continue

        elif results and choice == "5":
            # Display run configuration
            ConsoleDisplay.console.clear()
            ConsoleDisplay.display_info(results.info)
            continue

        else:
            break

    ConsoleDisplay.console.print("\n[green]Thanks for using the simulation viewer![/]")


if __name__ == "__main__":
    main()
