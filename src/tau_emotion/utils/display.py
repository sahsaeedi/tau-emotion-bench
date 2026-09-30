import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tau_emotion.config import TERM_DARK_MODE
from tau_emotion.data_model.message import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau_emotion.data_model.simulation import (
    Review,
    RunConfig,
    SimulationRun,
    UserOnlyReview,
)
from tau_emotion.data_model.tasks import Action, Task
from tau_emotion.metrics.agent_metrics import AgentMetrics, is_successful

if TYPE_CHECKING:
    from tau_emotion.data_model.simulation import Info


@dataclass
class ColorScheme:
    """Color scheme for console display."""

    # Panel colors
    panel_border: str
    panel_title: str
    secondary_border: str
    secondary_title: str

    # Label colors
    label: str
    section_header: str

    # Message colors
    assistant_role: str
    assistant_content: str
    assistant_tool: str
    user_role: str
    user_content: str
    user_tool: str
    system_role: str
    system_content: str

    # Table colors
    table_header: str
    table_role_column: str
    table_content_column: str
    table_details_column: str


# Dark mode color scheme - optimized for dark terminal backgrounds
DARK_MODE_COLORS = ColorScheme(
    # Panel colors - using bright colors for visibility
    panel_border="bright_cyan",
    panel_title="bold bright_cyan",
    secondary_border="cyan",
    secondary_title="bold cyan",
    # Label colors
    label="white",
    section_header="bold cyan",
    # Message colors - bright variants for dark backgrounds
    assistant_role="bold bright_white",
    assistant_content="bright_white",
    assistant_tool="bright_cyan",
    user_role="bold bright_green",
    user_content="bright_green",
    user_tool="bright_yellow",
    system_role="bold bright_magenta",
    system_content="bright_magenta",
    # Table colors
    table_header="bold bright_magenta",
    table_role_column="cyan",
    table_content_column="bright_green",
    table_details_column="bright_yellow",
)

# Light mode color scheme - optimized for light terminal backgrounds
LIGHT_MODE_COLORS = ColorScheme(
    # Panel colors - using darker colors for visibility on light bg
    panel_border="magenta",
    panel_title="bold magenta",
    secondary_border="dark_cyan",
    secondary_title="bold dark_cyan",
    # Label colors
    label="grey37",
    section_header="bold dark_cyan",
    # Message colors - darker variants for light backgrounds
    assistant_role="bold blue",
    assistant_content="blue",
    assistant_tool="dark_cyan",
    user_role="bold green",
    user_content="green",
    user_tool="dark_orange",
    system_role="bold magenta",
    system_content="magenta",
    # Table colors
    table_header="bold magenta",
    table_role_column="dark_cyan",
    table_content_column="green",
    table_details_column="dark_orange",
)


def get_color_scheme() -> ColorScheme:
    """Get the appropriate color scheme based on TERM_DARK_MODE setting."""
    return DARK_MODE_COLORS if TERM_DARK_MODE else LIGHT_MODE_COLORS


class ConsoleDisplay:
    console = Console()
    colors = get_color_scheme()

    @staticmethod
    def escape_markup(text: str) -> str:
        """
        Escape square brackets in text so Rich Console doesn't interpret them as markup.

        This is necessary for content containing tags like [sneeze] that should be displayed
        literally rather than being interpreted as Rich markup.

        Args:
            text: The text to escape

        Returns:
            Escaped text safe for Rich Console display
        """
        return escape(text)

    @classmethod
    def display_run_config(cls, config: RunConfig):
        c = cls.colors

        # Use effective values from config properties
        effective_max_steps = config.effective_max_steps
        effective_agent = config.effective_agent
        effective_user = config.effective_user
        effective_agent_model = config.effective_agent_model
        effective_user_model = config.effective_user_model

        agent_model_str = effective_agent_model

        # Build compact header with all key info
        if config.task_ids:
            task_ids_str = ", ".join(map(str, config.task_ids))
        elif config.num_tasks is not None:
            task_ids_str = f"first {config.num_tasks}"
        else:
            task_ids_str = "All"
        task_set_str = config.task_set_name if config.task_set_name else "Default"

        header_lines = [
            f"[{c.label}]Domain:[/] {config.domain}  [{c.label}]Task Set:[/] {task_set_str}  [{c.label}]Split:[/] {config.task_split_name}  [{c.label}]Tasks:[/] {task_ids_str}",
            f"[{c.label}]Trials:[/] {config.num_trials}  [{c.label}]Max Steps:[/] {effective_max_steps}  [{c.label}]Max Errors:[/] {config.max_errors}",
            "",
            f"[{c.section_header}]Agent:[/] {effective_agent} → {agent_model_str}",
            f"[{c.section_header}]User:[/]  {effective_user} → {effective_user_model}"
            + ("  (no emotion instructions)" if config.no_emotion else ""),
        ]

        # Add save/run settings on one line
        from tau_emotion.runner.helpers import make_run_name

        # An absolute save_to is used as is (the runner joins it the same way)
        save_to = Path("data/simulations") / (config.save_to or make_run_name(config))
        header_lines.append("")
        header_lines.append(
            f"[{c.label}]Save:[/] {save_to}  [{c.label}]Concurrency:[/] {config.max_concurrency}  [{c.label}]Verbose:[/] {config.verbose_logs}"
        )

        header_content = Panel(
            "\n".join(header_lines),
            title=f"[{c.panel_title}]Simulation Configuration",
            border_style=c.panel_border,
        )
        cls.console.print(header_content)

    @classmethod
    def display_task(cls, task: Task):
        c = cls.colors
        # Build content string showing only non-None fields
        content_parts = []

        if task.id is not None:
            content_parts.append(f"[{c.label}]ID:[/] {task.id}")

        if task.description:
            if task.description.purpose:
                content_parts.append(
                    f"[{c.label}]Purpose:[/] {task.description.purpose}"
                )
            if task.description.relevant_policies:
                content_parts.append(
                    f"[{c.label}]Relevant Policies:[/] {task.description.relevant_policies}"
                )
            if task.description.notes:
                content_parts.append(f"[{c.label}]Notes:[/] {task.description.notes}")

        # User Scenario section
        scenario_parts = []
        # Persona
        if task.user_scenario.persona:
            scenario_parts.append(
                f"[{c.label}]Persona:[/] {task.user_scenario.persona}"
            )

        # User Instruction
        scenario_parts.append(
            f"[{c.label}]Task Instructions:[/] {task.user_scenario.instructions}"
        )

        if scenario_parts:
            content_parts.append(
                f"[{c.section_header}]User Scenario:[/]\n" + "\n".join(scenario_parts)
            )

        # Initial State section
        if task.initial_state:
            initial_state_parts = []
            if task.initial_state.initialization_data:
                initial_state_parts.append(
                    f"[{c.label}]Initialization Data:[/]\n{task.initial_state.initialization_data.model_dump_json(indent=2)}"
                )
            if task.initial_state.initialization_actions:
                initial_state_parts.append(
                    f"[{c.label}]Initialization Actions:[/]\n{json.dumps([a.model_dump() for a in task.initial_state.initialization_actions], indent=2)}"
                )
            if task.initial_state.message_history:
                initial_state_parts.append(
                    f"[{c.label}]Message History:[/]\n{json.dumps([m.model_dump() for m in task.initial_state.message_history], indent=2)}"
                )

            if initial_state_parts:
                content_parts.append(
                    f"[{c.section_header}]Initial State:[/]\n"
                    + "\n".join(initial_state_parts)
                )

        # Evaluation Criteria section
        if task.evaluation_criteria:
            eval_parts = []
            if task.evaluation_criteria.actions:
                eval_parts.append(
                    f"[{c.label}]Required Actions:[/]\n{json.dumps([a.model_dump() for a in task.evaluation_criteria.actions], indent=2)}"
                )
            if task.evaluation_criteria.env_assertions:
                eval_parts.append(
                    f"[{c.label}]Env Assertions:[/]\n{json.dumps([a.model_dump() for a in task.evaluation_criteria.env_assertions], indent=2)}"
                )
            if task.evaluation_criteria.communicate_info:
                eval_parts.append(
                    f"[{c.label}]Information to Communicate:[/]\n{json.dumps(task.evaluation_criteria.communicate_info, indent=2)}"
                )
            if eval_parts:
                content_parts.append(
                    f"[{c.section_header}]Evaluation Criteria:[/]\n"
                    + "\n".join(eval_parts)
                )
        content = "\n\n".join(content_parts)

        # Create and display panel
        task_panel = Panel(
            content,
            title=f"[{c.panel_title}]Task Details",
            border_style=c.panel_border,
            expand=True,
        )

        cls.console.print(task_panel)

    @classmethod
    def display_simulation(
        cls,
        simulation: SimulationRun,
        show_details: bool = True,
    ):
        """
        Display the simulation content in a formatted way using Rich library.

        Args:
            simulation: The simulation object to display
            show_details: Whether to show detailed information
        """
        c = cls.colors
        # Create main simulation info panel
        sim_info = Text()
        if show_details:
            sim_info.append("Simulation ID: ", style=c.section_header)
            sim_info.append(f"{simulation.id}\n")
        sim_info.append("Task ID: ", style=c.section_header)
        sim_info.append(f"{simulation.task_id}\n")
        sim_info.append("Trial: ", style=c.section_header)
        sim_info.append(f"{simulation.trial}\n")
        if show_details:
            sim_info.append("Start Time: ", style=c.section_header)
            sim_info.append(f"{simulation.start_time}\n")
            sim_info.append("End Time: ", style=c.section_header)
            sim_info.append(f"{simulation.end_time}\n")
        sim_info.append("Duration: ", style=c.section_header)
        sim_info.append(f"{simulation.duration:.2f}s\n")
        sim_info.append("Mode: ", style=c.section_header)
        sim_info.append(f"{simulation.mode}\n")
        sim_info.append("Termination Reason: ", style=c.section_header)
        sim_info.append(f"{simulation.termination_reason}\n")
        if simulation.agent_cost is not None:
            sim_info.append("Agent Cost: ", style=c.section_header)
            sim_info.append(f"${simulation.agent_cost:.4f}\n")
        if simulation.user_cost is not None:
            sim_info.append("User Cost: ", style=c.section_header)
            sim_info.append(f"${simulation.user_cost:.4f}\n")
        if simulation.reward_info:
            marker = "✅" if is_successful(simulation.reward_info.reward) else "❌"
            sim_info.append("Reward: ", style=c.section_header)
            if simulation.reward_info.reward_breakdown:
                breakdown = sorted(
                    [
                        f"{k.value}: {v:.1f}"
                        for k, v in simulation.reward_info.reward_breakdown.items()
                    ]
                )
            else:
                breakdown = []

            sim_info.append(
                f"{marker} {simulation.reward_info.reward:.4f} ({', '.join(breakdown)})\n"
            )

            # Add DB check info if present
            if simulation.reward_info.db_check:
                sim_info.append("\nDB Check:", style=c.system_role)
                sim_info.append(
                    f"{'✅' if simulation.reward_info.db_check.db_match else '❌'} {simulation.reward_info.db_check.db_reward}\n"
                )

            # Add env assertions if present
            if simulation.reward_info.env_assertions:
                sim_info.append("\nEnv Assertions:\n", style=c.system_role)
                for i, assertion in enumerate(simulation.reward_info.env_assertions):
                    sim_info.append(
                        f"- {i}: {assertion.env_assertion.env_type} {assertion.env_assertion.func_name} {'✅' if assertion.met else '❌'} {assertion.reward}\n"
                    )

            # Add action checks if present
            if simulation.reward_info.action_checks:
                sim_info.append("\nAction Checks:\n", style=c.system_role)
                for i, check in enumerate(simulation.reward_info.action_checks):
                    tool_type_str = (
                        f" [{check.tool_type.value}]" if check.tool_type else ""
                    )
                    requestor_str = (
                        "user" if check.action.requestor == "user" else "agent"
                    )
                    sim_info.append(
                        f"- {i}: {requestor_str} {check.action.name}{tool_type_str} {'✅' if check.action_match else '❌'} {check.action_reward}\n"
                    )
                # Add partial reward breakdown
                partial = simulation.reward_info.partial_action_reward
                if partial:
                    total = partial["total"]
                    sim_info.append(
                        f"\nPartial Action Reward: ", style=c.section_header
                    )
                    sim_info.append(
                        f"{total['correct']}/{total['count']} ({total['proportion']:.1%})\n"
                    )
                    if partial.get("read"):
                        read = partial["read"]
                        sim_info.append(
                            f"  Read:  {read['correct']}/{read['count']} ({read['proportion']:.1%})\n"
                        )
                    if partial.get("write"):
                        write = partial["write"]
                        sim_info.append(
                            f"  Write: {write['correct']}/{write['count']} ({write['proportion']:.1%})\n"
                        )

            # Add communication checks if present
            if simulation.reward_info.communicate_checks:
                sim_info.append("\nCommunicate Checks:\n", style=c.system_role)
                for i, check in enumerate(simulation.reward_info.communicate_checks):
                    sim_info.append(
                        f"- {i}: {check.info} {'✅' if check.met else '❌'}\n"
                    )

            # Add NL assertions if present
            if simulation.reward_info.nl_assertions:
                sim_info.append("\nNL Assertions:\n", style=c.system_role)
                for i, assertion in enumerate(simulation.reward_info.nl_assertions):
                    sim_info.append(
                        f"- {i}: {assertion.nl_assertion} {'✅' if assertion.met else '❌'}\n\t{assertion.justification}\n"
                    )

            # Add additional info if present
            if simulation.reward_info.info:
                sim_info.append("\nAdditional Info:\n", style=c.system_role)
                for key, value in simulation.reward_info.info.items():
                    sim_info.append(f"{key}: {value}\n")

        cls.console.print(
            Panel(sim_info, title="Simulation Overview", border_style=c.panel_border)
        )

        # Display trajectory
        if show_details:
            if simulation.messages:
                table = Table(
                    title="Messages",
                    show_header=True,
                    header_style=c.table_header,
                    show_lines=True,  # Add horizontal lines between rows
                )
                table.add_column("Role", style=c.table_role_column, no_wrap=True)
                table.add_column("Content", style=c.table_content_column)
                table.add_column("Details", style=c.table_details_column)
                table.add_column("Turn", style=c.table_details_column, no_wrap=True)

                current_turn = None
                for msg in simulation.messages:
                    content = (
                        cls.escape_markup(msg.content)
                        if msg.content is not None
                        else ""
                    )
                    details = ""

                    # Set different colors based on message type
                    if isinstance(msg, AssistantMessage):
                        role_style = c.assistant_role
                        content_style = c.assistant_content
                        tool_style = c.assistant_tool
                    elif isinstance(msg, UserMessage):
                        role_style = c.user_role
                        content_style = c.user_content
                        tool_style = c.user_tool
                    elif isinstance(msg, ToolMessage):
                        # For tool messages, use the color of the requestor's tool style
                        if msg.requestor == "user":
                            role_style = c.user_role
                            content_style = c.user_tool
                        else:  # assistant
                            role_style = c.assistant_role
                            content_style = c.assistant_tool
                        tool_style = content_style
                    else:  # SystemMessage
                        role_style = c.system_role
                        content_style = c.system_content
                        tool_style = c.system_content

                    if isinstance(msg, AssistantMessage) or isinstance(
                        msg, UserMessage
                    ):
                        if msg.tool_calls:
                            tool_calls = []
                            for tool in msg.tool_calls:
                                tool_calls.append(
                                    f"[{tool_style}]Tool: {tool.name}[/]\n[{tool_style}]Args: {json.dumps(tool.arguments, indent=2)}[/]"
                                )
                            details = "\n".join(tool_calls)
                    elif isinstance(msg, ToolMessage):
                        details = f"[{content_style}]Tool ID: {msg.id}. Requestor: {msg.requestor}[/]"
                        if msg.error:
                            details += " [bold red](Error)[/]"

                    # Add empty row between turns
                    if current_turn is not None and msg.turn_idx != current_turn:
                        table.add_row("", "", "", "")
                    current_turn = msg.turn_idx

                    table.add_row(
                        f"[{role_style}]{msg.role}[/]",
                        f"[{content_style}]{content}[/]",
                        details,
                        str(msg.turn_idx) if msg.turn_idx is not None else "",
                    )
                cls.console.print(table)

        # Display reviews if present
        if simulation.review is not None:
            cls.display_review(simulation.review)

        if simulation.user_only_review is not None:
            cls.display_user_only_review(simulation.user_only_review)

    @classmethod
    def display_review(
        cls,
        review: Review,
        title: str = "LLM Conversation Review",
        console: Optional[Console] = None,
    ):
        """
        Display a Review object with summary and errors.

        Args:
            review: The Review object to display.
            title: Title for the review panel.
            console: Optional Console instance. Uses class console if not provided.
        """
        if console is None:
            console = cls.console

        # Build summary panel content
        summary_lines = []
        if review.has_errors:
            if review.critical_user_error:
                status = "❌ Errors Found (Critical User Error)"
            else:
                status = "❌ Errors Found"
        else:
            status = "✅ No Errors"
        summary_lines.append(f"[bold]{status}[/bold]")

        if review.has_errors:
            error_parts = []
            if review.agent_error:
                error_parts.append("[red]🤖 Agent Error[/red]")
            if review.user_error:
                if review.critical_user_error:
                    error_parts.append("[red]👤 User Error (Critical)[/red]")
                else:
                    error_parts.append("[blue]👤 User Error (Minor)[/blue]")
            if error_parts:
                summary_lines.append(" | ".join(error_parts))

        if review.emotional_outcome == "user_abandoned":
            summary_lines.append(
                f"[yellow]💔 User abandoned ({review.emotional_subreason})[/yellow]"
            )

        if review.summary:
            summary_lines.append(f"\n{review.summary}")

        if review.cost is not None:
            summary_lines.append(f"\nReview cost: ${review.cost:.4f}")

        summary_panel = Panel(
            "\n".join(summary_lines),
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
        )
        console.print(summary_panel)

        # Display errors table if there are errors
        if review.errors and review.has_errors:
            table = Table(
                title="[bold]Review Errors[/bold]",
                show_header=True,
                header_style="bold magenta",
                expand=True,
                show_lines=True,
            )
            table.add_column("#", style="white", width=4)
            table.add_column("Source", style="cyan", width=8)
            table.add_column("Severity", width=16)
            table.add_column("Error Type", style="yellow", width=14)
            table.add_column("Tags", style="magenta", no_wrap=False)
            table.add_column("Location", style="green", width=12)
            table.add_column("Reasoning", style="white", ratio=2)
            table.add_column("Correct Behavior", style="white", ratio=1)

            for i, error in enumerate(review.errors, 1):
                if error.source == "unknown":
                    continue
                reasoning_text = error.reasoning
                correct_behavior_text = (
                    error.correct_behavior if error.correct_behavior else "-"
                )
                # Show severity for both agent and user errors with color
                if error.severity:
                    if error.severity == "critical" or error.severity.startswith(
                        "critical_"
                    ):
                        severity_text = f"[red]{error.severity}[/]"
                    elif error.severity == "minor":
                        severity_text = f"[yellow]{error.severity}[/]"
                    else:
                        severity_text = error.severity
                else:
                    severity_text = "[dim]-[/]"
                # Format error tags (one per line)
                if error.error_tags:
                    tags_text = "\n".join(error.error_tags)
                else:
                    tags_text = "-"
                if error.turn_idx is not None:
                    location = f"turn {error.turn_idx}"
                else:
                    location = "-"

                # Color the source based on who made the error
                source_style = "red" if error.source == "agent" else "blue"
                table.add_row(
                    str(i),
                    f"[{source_style}]{error.source}[/{source_style}]",
                    severity_text,
                    error.error_type or "-",
                    tags_text,
                    location,
                    reasoning_text,
                    correct_behavior_text,
                )

            console.print(table)

    @classmethod
    def display_user_only_review(
        cls,
        review: UserOnlyReview,
        title: str = "LLM User Simulator Review",
        console: Optional[Console] = None,
    ):
        """
        Display a UserOnlyReview object with summary and errors.

        Args:
            review: The UserOnlyReview object to display.
            title: Title for the review panel.
            console: Optional Console instance. Uses class console if not provided.
        """
        if console is None:
            console = cls.console

        # Build summary panel content
        summary_lines = []
        if review.has_errors:
            if review.critical_user_error:
                status = "❌ Critical User Errors Found"
            else:
                status = "⚠️ User Errors Found (Minor)"
        else:
            status = "✅ No User Errors"
        summary_lines.append(f"[bold]{status}[/bold]")

        if review.has_errors:
            if review.critical_user_error:
                summary_lines.append(
                    f"[red]👤 {len(review.errors)} User Error(s) - Critical[/red]"
                )
            else:
                summary_lines.append(
                    f"[blue]👤 {len(review.errors)} User Error(s) - Minor[/blue]"
                )

        if review.summary:
            summary_lines.append(f"\n{review.summary}")

        if review.cost is not None:
            summary_lines.append(f"\nReview cost: ${review.cost:.4f}")

        summary_panel = Panel(
            "\n".join(summary_lines),
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
        )
        console.print(summary_panel)

        # Display errors table if there are errors
        if review.errors and review.has_errors:
            table = Table(
                title="[bold]User Simulator Errors[/bold]",
                show_header=True,
                header_style="bold magenta",
                expand=True,
                show_lines=True,
            )
            table.add_column("#", style="white", width=4)
            table.add_column("Severity", style="red", width=10)
            table.add_column("Type", style="yellow", width=14)
            table.add_column("Location", style="green", width=12)
            table.add_column("Message", style="blue", ratio=1)
            table.add_column("Reasoning", style="white", ratio=2)
            table.add_column("Correct Behavior", style="white", ratio=1)

            for i, error in enumerate(review.errors, 1):
                # Color severity
                if error.severity:
                    if error.severity.startswith("critical"):
                        severity_text = f"[red]{error.severity}[/]"
                    elif error.severity == "minor":
                        severity_text = f"[yellow]{error.severity}[/]"
                    else:
                        severity_text = error.severity
                else:
                    severity_text = "[dim]-[/]"
                if error.turn_idx is not None:
                    location = f"turn {error.turn_idx}"
                else:
                    location = "-"

                table.add_row(
                    str(i),
                    severity_text,
                    error.error_type,
                    location,
                    error.user_message or "-",
                    error.reasoning,
                    error.correct_behavior or "-",
                )

            console.print(table)

    @classmethod
    def display_agent_metrics(cls, metrics: AgentMetrics):
        from rich.table import Table

        c = cls.colors

        # Create main metrics table
        table = Table(
            show_header=False,
            box=None,
            padding=(0, 2),
            collapse_padding=True,
        )
        table.add_column("Label", style="bold")
        table.add_column("Value")

        # Overview section
        table.add_row("[cyan]═══ Overview ═══[/]", "")
        if metrics.infra_error_count > 0:
            total_with_infra = metrics.total_simulations + metrics.infra_error_count
            table.add_row("Total Simulations", str(total_with_infra))
            table.add_row(
                "⚠️  Infra Errors",
                f"[red]{metrics.infra_error_count}[/] (excluded from metrics below)",
            )
            table.add_row("Evaluated", str(metrics.total_simulations))
        else:
            table.add_row("Total Simulations", str(metrics.total_simulations))
        table.add_row("Total Tasks", str(metrics.total_tasks))
        table.add_row("", "")

        # Reward metrics
        table.add_row("[cyan]═══ Reward Metrics ═══[/]", "")
        reward_color = (
            "green"
            if metrics.avg_reward > 0.8
            else ("yellow" if metrics.avg_reward > 0.5 else "red")
        )
        table.add_row(
            "🏆 Average Reward", f"[{reward_color}]{metrics.avg_reward:.4f}[/]"
        )
        for k, pass_k in sorted(metrics.pass_hat_ks.items()):
            pk_color = (
                "green" if pass_k > 0.8 else ("yellow" if pass_k > 0.5 else "red")
            )
            table.add_row(f"   Pass^{k}", f"[{pk_color}]{pass_k:.3f}[/]")
        for k, pass_k in sorted(metrics.pass_at_ks.items()):
            pk_color = (
                "green" if pass_k > 0.8 else ("yellow" if pass_k > 0.5 else "red")
            )
            table.add_row(f"   Pass@{k}", f"[{pk_color}]{pass_k:.3f}[/]")
        table.add_row("💰 Avg Cost/Conversation", f"${metrics.avg_agent_cost:.4f}")
        table.add_row("", "")

        # Action metrics
        table.add_row("[cyan]═══ Action Metrics ═══[/]", "")
        if metrics.total_read_actions > 0:
            read_pct = metrics.correct_read_actions / metrics.total_read_actions * 100
            read_color = (
                "green" if read_pct == 100 else ("yellow" if read_pct >= 80 else "red")
            )
            table.add_row(
                "📖 Read Actions",
                f"[{read_color}]{metrics.correct_read_actions}/{metrics.total_read_actions}[/] ({read_pct:.1f}%)",
            )
        else:
            table.add_row("📖 Read Actions", "[dim]-[/]")

        if metrics.total_write_actions > 0:
            write_pct = (
                metrics.correct_write_actions / metrics.total_write_actions * 100
            )
            write_color = (
                "green"
                if write_pct == 100
                else ("yellow" if write_pct >= 80 else "red")
            )
            table.add_row(
                "✏️  Write Actions",
                f"[{write_color}]{metrics.correct_write_actions}/{metrics.total_write_actions}[/] ({write_pct:.1f}%)",
            )
        else:
            table.add_row("✏️  Write Actions", "[dim]-[/]")
        table.add_row("", "")

        # DB Match
        table.add_row("[cyan]═══ DB Match ═══[/]", "")
        db_total = metrics.db_match_count + metrics.db_mismatch_count
        if db_total > 0:
            db_pct = metrics.db_match_count / db_total * 100
            db_color = (
                "green" if db_pct == 100 else ("yellow" if db_pct >= 80 else "red")
            )
            table.add_row(
                "🗄️  DB Match",
                f"[green]✓ {metrics.db_match_count}[/] / [red]✗ {metrics.db_mismatch_count}[/] ([{db_color}]{db_pct:.1f}%[/])",
            )
        else:
            table.add_row(
                "🗄️  DB Match", f"[dim]Not checked: {metrics.db_not_checked}[/]"
            )
        table.add_row("", "")

        # Authentication
        table.add_row("[cyan]═══ Authentication ═══[/]", "")
        auth_total = metrics.auth_succeeded + metrics.auth_failed
        if auth_total > 0:
            auth_pct = metrics.auth_succeeded / auth_total * 100
            auth_color = (
                "green" if auth_pct == 100 else ("yellow" if auth_pct >= 80 else "red")
            )
            table.add_row(
                "🔐 Auth Result",
                f"[green]✓ {metrics.auth_succeeded}[/] / [red]✗ {metrics.auth_failed}[/] ([{auth_color}]{auth_pct:.1f}%[/])",
            )
        if metrics.auth_not_needed > 0:
            table.add_row("   Not Needed", f"[dim]{metrics.auth_not_needed}[/]")
        if metrics.auth_not_checked > 0:
            table.add_row("   Not Checked", f"[dim]{metrics.auth_not_checked}[/]")
        table.add_row("", "")

        # Termination
        table.add_row("[cyan]═══ Termination ═══[/]", "")
        term_normal = metrics.termination_user_stop + metrics.termination_agent_stop
        table.add_row(
            "🛑 Normal Stop",
            f"[green]{term_normal}[/] (👤 {metrics.termination_user_stop} / 🤖 {metrics.termination_agent_stop})",
        )
        table.add_row(
            "😤 User Gave Up", f"[red]{metrics.termination_user_unsatisfied}[/]"
        )
        if metrics.termination_max_steps > 0:
            table.add_row("⏱️  Max Steps", f"[yellow]{metrics.termination_max_steps}[/]")
        if metrics.termination_timeout > 0:
            table.add_row("⌛ Timeout", f"[yellow]{metrics.termination_timeout}[/]")
        if metrics.termination_error > 0:
            table.add_row("💥 Error", f"[red]{metrics.termination_error}[/]")
        if metrics.termination_infrastructure_error > 0:
            table.add_row(
                "🔌 Infra Error",
                f"[red]{metrics.termination_infrastructure_error}[/]",
            )
        table.add_row("", "")

        # LLM Judge Review Errors
        table.add_row("[cyan]═══ LLM Judge Review ═══[/]", "")

        # Every reviewed simulation is counted in the sims-by-severity tallies
        has_review = any(metrics.sims_by_max_agent_severity.values()) or any(
            metrics.sims_by_max_user_severity.values()
        )

        if has_review:
            # Agent errors - total by severity
            agent_err_color = "green" if metrics.sims_with_agent_errors == 0 else "red"
            agent_sev_parts = []
            for sev in ["critical", "minor"]:
                count = metrics.agent_errors_by_severity.get(sev, 0)
                if count > 0:
                    color = "red" if sev == "critical" else "yellow"
                    agent_sev_parts.append(f"[{color}]{sev}={count}[/]")
            agent_sev_str = (
                f" ({', '.join(agent_sev_parts)})" if agent_sev_parts else ""
            )
            table.add_row(
                "🤖 Agent Errors",
                f"[{agent_err_color}]{metrics.total_agent_errors}[/] errors{agent_sev_str}",
            )

            # Agent errors - sims by max severity
            agent_sim_parts = []
            for sev in ["critical", "minor", "none"]:
                count = metrics.sims_by_max_agent_severity.get(sev, 0)
                if count > 0:
                    if sev == "critical":
                        agent_sim_parts.append(f"[red]{count} critical[/]")
                    elif sev == "minor":
                        agent_sim_parts.append(f"[yellow]{count} minor[/]")
                    else:
                        agent_sim_parts.append(f"[green]{count} clean[/]")
            table.add_row(
                "   Sims by severity",
                ", ".join(agent_sim_parts) if agent_sim_parts else "[dim]-[/]",
            )

            # User errors - total by severity
            user_err_color = (
                "green"
                if metrics.sims_with_user_errors == 0
                else ("red" if metrics.sims_with_critical_user_errors > 0 else "yellow")
            )
            user_sev_parts = []
            for sev in ["critical_helped", "critical_hindered", "minor"]:
                count = metrics.user_errors_by_severity.get(sev, 0)
                if count > 0:
                    color = "red" if sev.startswith("critical") else "yellow"
                    label = sev.replace("_", " ")
                    user_sev_parts.append(f"[{color}]{label}={count}[/]")
            user_sev_str = f" ({', '.join(user_sev_parts)})" if user_sev_parts else ""
            table.add_row(
                "👤 User Errors",
                f"[{user_err_color}]{metrics.total_user_errors}[/] errors{user_sev_str}",
            )

            # User errors - sims by max severity
            user_sim_parts = []
            for sev in ["critical_helped", "critical_hindered", "minor", "none"]:
                count = metrics.sims_by_max_user_severity.get(sev, 0)
                if count > 0:
                    if sev.startswith("critical"):
                        label = sev.replace("_", " ")
                        user_sim_parts.append(f"[red]{count} {label}[/]")
                    elif sev == "minor":
                        user_sim_parts.append(f"[yellow]{count} minor[/]")
                    else:
                        user_sim_parts.append(f"[green]{count} clean[/]")
            table.add_row(
                "   Sims by severity",
                ", ".join(user_sim_parts) if user_sim_parts else "[dim]-[/]",
            )

            # First critical source
            first_crit_parts = []
            for src in ["agent", "user", "none"]:
                count = metrics.sims_by_first_critical_source.get(src, 0)
                if count > 0:
                    if src == "agent":
                        first_crit_parts.append(f"[red]{count} agent[/]")
                    elif src == "user":
                        first_crit_parts.append(f"[blue]{count} user[/]")
                    else:
                        first_crit_parts.append(f"[green]{count} none[/]")
            if first_crit_parts:
                table.add_row(
                    "⚡ First Critical By",
                    ", ".join(first_crit_parts),
                )
            table.add_row("", "")

            # Error tags breakdown
            if metrics.agent_error_tags_by_severity:
                table.add_row("[cyan]─── 🤖 Agent Error Tags ───[/]", "")
                # Sort by total count descending
                sorted_tags = sorted(
                    metrics.agent_error_tags_by_severity.items(),
                    key=lambda x: sum(x[1].values()),
                    reverse=True,
                )
                for tag, severities in sorted_tags:
                    # Format: tag: minor=X, critical=Y
                    parts = []
                    for sev in ["minor", "critical"]:
                        if sev in severities and severities[sev] > 0:
                            color = "yellow" if sev == "minor" else "red"
                            parts.append(f"[{color}]{sev}={severities[sev]}[/]")
                    if parts:
                        table.add_row(f"   {tag}", ", ".join(parts))
                table.add_row("", "")

            if metrics.user_error_tags_by_severity:
                table.add_row("[cyan]─── 👤 User Error Tags ───[/]", "")
                # Sort by total count descending
                sorted_tags = sorted(
                    metrics.user_error_tags_by_severity.items(),
                    key=lambda x: sum(x[1].values()),
                    reverse=True,
                )
                for tag, severities in sorted_tags:
                    # Format: tag: minor=X, critical_helped=Y, critical_hindered=Z
                    parts = []
                    for sev in ["minor", "critical_helped", "critical_hindered"]:
                        if sev in severities and severities[sev] > 0:
                            color = "yellow" if sev == "minor" else "red"
                            label = sev.replace("_", " ")
                            parts.append(f"[{color}]{label}={severities[sev]}[/]")
                    if parts:
                        table.add_row(f"   {tag}", ", ".join(parts))
        else:
            table.add_row("", "[dim]Not reviewed (see tau-emotion review)[/]")

        # Create and display panel
        metrics_panel = Panel(
            table,
            title=f"[{c.panel_title}]Agent Performance Metrics",
            border_style=c.panel_border,
            expand=True,
        )

        cls.console.print(metrics_panel)

    @classmethod
    def display_info(cls, info: "Info"):
        """
        Display simulation run configuration/info.

        Args:
            info: The Info object containing run configuration details.
        """

        c = cls.colors

        # Build a single header panel with all run info including agent/user
        header_lines = [
            f"[{c.label}]Domain:[/] {info.environment_info.domain_name}",
            f"[{c.label}]Git Commit:[/] {info.git_commit[:12]}...",
            f"[{c.label}]Trials:[/] {info.num_trials}  [{c.label}]Max Steps:[/] {info.max_steps}  [{c.label}]Max Errors:[/] {info.max_errors}",
        ]
        if info.seed is not None:
            header_lines[-1] += f"  [{c.label}]Seed:[/] {info.seed}"

        # Add agent info
        if info.agent_info.llm:
            agent_model = info.agent_info.llm
        else:
            agent_model = "N/A"
        header_lines.append("")
        header_lines.append(
            f"[{c.section_header}]Agent:[/] {info.agent_info.implementation} → {agent_model}"
        )

        # Add user info
        user_model = info.user_info.llm or "N/A"
        header_lines.append(
            f"[{c.section_header}]User:[/]  {info.user_info.implementation} → {user_model}"
        )

        header_content = Panel(
            "\n".join(header_lines),
            title=f"[{c.panel_title}]Run Configuration",
            border_style=c.panel_border,
        )

        cls.console.print(header_content)


class MarkdownDisplay:
    @classmethod
    def display_actions(cls, actions: List[Action]) -> str:
        """Display actions in markdown format."""
        return f"```json\n{json.dumps([action.model_dump() for action in actions], indent=2)}\n```"

    @classmethod
    def display_messages(cls, messages: list[Message]) -> str:
        """Display messages in markdown format."""
        return "\n\n".join(cls.display_message(msg) for msg in messages)

    @classmethod
    def display_simulation(cls, sim: SimulationRun) -> str:
        """Display simulation in markdown format."""
        # Otherwise handle SimulationRun object
        output = []

        # Add basic simulation info
        output.append(f"**Task ID**: {sim.task_id}")
        output.append(f"**Trial**: {sim.trial}")
        output.append(f"**Duration**: {sim.duration:.2f}s")
        output.append(f"**Termination**: {sim.termination_reason}")
        if sim.agent_cost is not None:
            output.append(f"**Agent Cost**: ${sim.agent_cost:.4f}")
        if sim.user_cost is not None:
            output.append(f"**User Cost**: ${sim.user_cost:.4f}")

        # Add reward info if present
        if sim.reward_info:
            breakdown = sorted(
                [
                    f"{k.value}: {v:.1f}"
                    for k, v in sim.reward_info.reward_breakdown.items()
                ]
            )
            output.append(
                f"**Reward**: {sim.reward_info.reward:.4f} ({', '.join(breakdown)})\n"
            )
            output.append(f"**Reward**: {sim.reward_info.reward:.4f}")

            # Add DB check info if present
            if sim.reward_info.db_check:
                output.append("\n**DB Check**")
                output.append(
                    f"- Status: {'✅' if sim.reward_info.db_check.db_match else '❌'} {sim.reward_info.db_check.db_reward}"
                )

            # Add env assertions if present
            if sim.reward_info.env_assertions:
                output.append("\n**Env Assertions**")
                for i, assertion in enumerate(sim.reward_info.env_assertions):
                    output.append(
                        f"- {i}: {assertion.env_assertion.env_type} {assertion.env_assertion.func_name} {'✅' if assertion.met else '❌'} {assertion.reward}"
                    )

            # Add action checks if present
            if sim.reward_info.action_checks:
                output.append("\n**Action Checks**")
                for i, check in enumerate(sim.reward_info.action_checks):
                    tool_type_str = (
                        f" [{check.tool_type.value}]" if check.tool_type else ""
                    )
                    requestor_str = (
                        "user" if check.action.requestor == "user" else "agent"
                    )
                    output.append(
                        f"- {i}: {requestor_str} {check.action.name}{tool_type_str} {'✅' if check.action_match else '❌'} {check.action_reward}"
                    )
                # Add partial reward breakdown
                partial = sim.reward_info.partial_action_reward
                if partial:
                    total = partial["total"]
                    output.append(
                        f"\n**Partial Action Reward**: {total['correct']}/{total['count']} ({total['proportion']:.1%})"
                    )
                    if partial.get("read"):
                        read = partial["read"]
                        output.append(
                            f"  - Read: {read['correct']}/{read['count']} ({read['proportion']:.1%})"
                        )
                    if partial.get("write"):
                        write = partial["write"]
                        output.append(
                            f"  - Write: {write['correct']}/{write['count']} ({write['proportion']:.1%})"
                        )

            # Add communication checks if present
            if sim.reward_info.communicate_checks:
                output.append("\n**Communicate Checks**")
                for i, check in enumerate(sim.reward_info.communicate_checks):
                    output.append(
                        f"- {i}: {check.info} {'✅' if check.met else '❌'} {check.justification}"
                    )

            # Add NL assertions if present
            if sim.reward_info.nl_assertions:
                output.append("\n**NL Assertions**")
                for i, assertion in enumerate(sim.reward_info.nl_assertions):
                    output.append(
                        f"- {i}: {assertion.nl_assertion} {'✅' if assertion.met else '❌'} {assertion.justification}"
                    )

            # Add additional info if present
            if sim.reward_info.info:
                output.append("\n**Additional Info**")
                for key, value in sim.reward_info.info.items():
                    output.append(f"- {key}: {value}")

        # Add messages using the display_message method
        messages = sim.get_messages()
        if messages:
            output.append("\n**Messages**:")
            output.extend(cls.display_message(msg) for msg in messages)

        return "\n\n".join(output)

    @classmethod
    def display_result(
        cls,
        task: Task,
        sim: SimulationRun,
        reward: Optional[float] = None,
        show_task_id: bool = False,
    ) -> str:
        """Display a single result with all its components in markdown format."""
        output = [
            f"## Task {task.id}" if show_task_id else "## Task",
            "\n### User Instruction",
            task.user_scenario.instructions,
            "\n### Ground Truth Actions",
            cls.display_actions(task.evaluation_criteria.actions),
        ]

        if task.evaluation_criteria.communicate_info:
            output.extend(
                [
                    "\n### Communicate Info",
                    "```\n" + str(task.evaluation_criteria.communicate_info) + "\n```",
                ]
            )

        if reward is not None:
            output.extend(["\n### Reward", f"**{reward:.3f}**"])

        output.extend(["\n### Simulation", cls.display_simulation(sim)])

        return "\n".join(output)

    @classmethod
    def display_message(cls, msg: Message) -> str:
        """Display a single message in markdown format."""
        # Common message components
        parts = []

        # Add turn index if present
        turn_prefix = f"[TURN {msg.turn_idx}] " if msg.turn_idx is not None else ""

        # Format based on message type
        if isinstance(msg, AssistantMessage) or isinstance(msg, UserMessage):
            parts.append(f"{turn_prefix}**{msg.role}**:")
            if msg.content:
                parts.append(msg.content)
            if msg.tool_calls:
                tool_calls = []
                for tool in msg.tool_calls:
                    tool_calls.append(
                        f"**Tool Call**: {tool.name}\n```json\n{json.dumps(tool.arguments, indent=2)}\n```"
                    )
                parts.extend(tool_calls)

        elif isinstance(msg, ToolMessage):
            status = " (Error)" if msg.error else ""
            parts.append(f"{turn_prefix}**tool{status}**:")
            parts.append(f"Reponse to: {msg.requestor}")
            if msg.content:
                parts.append(f"```\n{msg.content}\n```")

        elif isinstance(msg, SystemMessage):
            parts.append(f"{turn_prefix}**system**:")
            if msg.content:
                parts.append(msg.content)

        return "\n".join(parts)
