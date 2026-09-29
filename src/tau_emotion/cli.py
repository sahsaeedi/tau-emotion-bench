import argparse
import json
from copy import deepcopy

from tau_emotion.config import (
    DEFAULT_AGENT_IMPLEMENTATION,
    DEFAULT_LLM_AGENT,
    DEFAULT_LLM_EVAL_USER_SIMULATOR,
    DEFAULT_LLM_LOG_MODE,
    DEFAULT_LLM_TEMPERATURE_AGENT,
    DEFAULT_LLM_TEMPERATURE_USER,
    DEFAULT_LLM_USER,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_ERRORS,
    DEFAULT_MAX_STEPS,
    DEFAULT_NUM_TRIALS,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_MIN_WAIT,
    DEFAULT_SEED,
    DEFAULT_USER_IMPLEMENTATION,
)
from tau_emotion.data_model.simulation import TextRunConfig
from tau_emotion.run import get_options, run_domain


def add_run_args(parser):
    """Add run arguments to a parser."""
    domains = get_options().domains
    parser.add_argument(
        "--domain",
        "-d",
        type=str,
        choices=domains,
        help="The domain to run the simulation on",
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        default=DEFAULT_NUM_TRIALS,
        help="The number of times each task is run. Default is 1.",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=DEFAULT_AGENT_IMPLEMENTATION,
        choices=get_options().agents,
        help=f"The agent implementation to use. Default is {DEFAULT_AGENT_IMPLEMENTATION}.",
    )
    parser.add_argument(
        "--agent-llm",
        type=str,
        default=DEFAULT_LLM_AGENT,
        help=f"The LLM to use for the agent. Default is {DEFAULT_LLM_AGENT}.",
    )
    parser.add_argument(
        "--agent-llm-args",
        type=json.loads,
        default={"temperature": DEFAULT_LLM_TEMPERATURE_AGENT},
        help=f"The arguments to pass to the LLM for the agent. Default is '{{\"temperature\": {DEFAULT_LLM_TEMPERATURE_AGENT}}}'.",
    )
    parser.add_argument(
        "--agent-temperature",
        type=float,
        default=None,
        help="The agent LLM's temperature. Overrides the temperature in --agent-llm-args "
        f"(default {DEFAULT_LLM_TEMPERATURE_AGENT}).",
    )
    parser.add_argument(
        "--agent-api-base",
        type=str,
        default=None,
        help="Base URL of the agent's OpenAI-compatible server, e.g. http://localhost:8000/v1. "
        "Default: the provider's (OPENAI_API_BASE for OpenAI models, gpt-4.1 included, "
        "and bare model names).",
    )
    parser.add_argument(
        "--agent-api-key",
        type=str,
        default=None,
        help="API key for the agent's server. Default: the provider's env var "
        "(OPENAI_API_KEY for bare and openai/ model names), or no key when --agent-api-base "
        "is given, so the key isn't sent to another server. Not saved in the results.",
    )
    parser.add_argument(
        "--agent-enable-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Turn the agent model's thinking on or off through its chat template "
        "(vLLM chat_template_kwargs.enable_thinking). Default: the model's own default.",
    )
    parser.add_argument(
        "--user",
        type=str,
        choices=get_options().users,
        default=DEFAULT_USER_IMPLEMENTATION,
        help=f"The user implementation to use. Default is {DEFAULT_USER_IMPLEMENTATION}.",
    )
    parser.add_argument(
        "--user-llm",
        type=str,
        default=DEFAULT_LLM_USER,
        help=f"The LLM to use for the user. Default is {DEFAULT_LLM_USER}.",
    )
    parser.add_argument(
        "--user-llm-args",
        type=json.loads,
        default={"temperature": DEFAULT_LLM_TEMPERATURE_USER},
        help=f"The arguments to pass to the LLM for the user. Default is '{{\"temperature\": {DEFAULT_LLM_TEMPERATURE_USER}}}'.",
    )
    parser.add_argument(
        "--user-api-base",
        type=str,
        default=None,
        help="Base URL of the user's OpenAI-compatible server, e.g. http://localhost:8000/v1. "
        "Default: the provider's (OPENAI_API_BASE for OpenAI models, gpt-4.1 included, "
        "and bare model names).",
    )
    parser.add_argument(
        "--user-api-key",
        type=str,
        default=None,
        help="API key for the user's server. Default: the provider's env var "
        "(OPENAI_API_KEY for bare and openai/ model names), or no key when --user-api-base "
        "is given, so the key isn't sent to another server. Not saved in the results.",
    )
    parser.add_argument(
        "--user-enable-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Turn the user model's thinking on or off through its chat template "
        "(vLLM chat_template_kwargs.enable_thinking). Default: the model's own default.",
    )
    parser.add_argument(
        "--task-set-name",
        type=str,
        default=None,
        choices=get_options().task_sets,
        help="The task set to run the simulation on. If not provided, will load default task set for the domain.",
    )
    parser.add_argument(
        "--task-split-name",
        type=str,
        default="base",
        help="The task split to run the simulation on. If not provided, will load 'base' split.",
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        nargs="+",
        help="(Optional) run only the tasks with the given IDs. If not provided, will run all tasks.",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=None,
        help="The number of tasks to run.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"The maximum number of steps to run the simulation. Default is {DEFAULT_MAX_STEPS}.",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=DEFAULT_MAX_ERRORS,
        help=f"The maximum number of tool errors in a simulation before it is stopped. Default is {DEFAULT_MAX_ERRORS}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Maximum wallclock time in seconds for each simulation. No timeout by default.",
    )
    parser.add_argument(
        "--save-to",
        type=str,
        required=False,
        help="Where to save the results: data/simulations/<save_to>/results.json. "
        "Default: <domain>/<agent model>, plus suffixes for a non-default agent, "
        "thinking/reasoning settings, a non-default user model and the train split. "
        "If the file already exists, the run is resumed.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=DEFAULT_MAX_CONCURRENCY,
        help=f"The maximum number of concurrent simulations to run. Default is {DEFAULT_MAX_CONCURRENCY}.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"The seed to use for the simulation. Default is {DEFAULT_SEED}.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=DEFAULT_LOG_LEVEL,
        help=f"The log level to use for the simulation. Default is {DEFAULT_LOG_LEVEL}.",
    )
    parser.add_argument(
        "--verbose-logs",
        action="store_true",
        default=False,
        help="Enable verbose logging: saves LLM call logs and per-task logs. "
        "Files are saved to the save directory (auto-generated if --save-to not specified).",
    )
    parser.add_argument(
        "--llm-log-mode",
        type=str,
        choices=["all", "latest"],
        default=DEFAULT_LLM_LOG_MODE,
        help="LLM debug logging mode. Only takes effect when --verbose-logs is enabled. "
        "'all' saves every LLM call (can generate many files), "
        "'latest' keeps only the most recent call of each type (saves space). "
        f"Default is '{DEFAULT_LLM_LOG_MODE}'. Ignored if --verbose-logs is not specified.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_RETRY_ATTEMPTS,
        help=f"Maximum number of retries for failed tasks. Default is {DEFAULT_RETRY_ATTEMPTS}.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_MIN_WAIT,
        help=f"Delay in seconds between retries. Default is {DEFAULT_RETRY_MIN_WAIT}.",
    )
    parser.add_argument(
        "--enforce-communication-protocol",
        action="store_true",
        default=False,
        help="Enforce communication protocol rules (e.g., no mixed messages with text and tool calls). Default is False.",
    )

    # Resume mode
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        default=False,
        help="Automatically resume from existing save file without prompting (for non-interactive runs).",
    )

    # Auto-review mode
    parser.add_argument(
        "--auto-review",
        action="store_true",
        default=False,
        help="Automatically run LLM conversation review after each simulation.",
    )
    parser.add_argument(
        "--review-mode",
        type=str,
        choices=["full", "user"],
        default="full",
        help="Review mode when --auto-review is enabled: 'full' (agent+user errors, default) or 'user' (user simulator only).",
    )
    parser.add_argument(
        "--no-emotion",
        action="store_true",
        default=False,
        help="Do not give the user simulator the task's emotion instruction.",
    )


def _llm_args(args, side: str) -> dict:
    """The --<side>-llm-args with the --<side>-api-base, --<side>-api-key,
    --<side>-enable-thinking and --agent-temperature flags folded in."""
    llm_args = deepcopy(getattr(args, f"{side}_llm_args"))
    temperature = getattr(args, f"{side}_temperature", None)
    if temperature is not None:
        llm_args["temperature"] = temperature
    api_base = getattr(args, f"{side}_api_base")
    api_key = getattr(args, f"{side}_api_key")
    enable_thinking = getattr(args, f"{side}_enable_thinking")
    if api_base is not None:
        llm_args["api_base"] = api_base
        # Otherwise litellm falls back to the provider's env key and sends it
        # to this server. "EMPTY" is what vLLM's docs use for no key.
        llm_args.setdefault("api_key", "EMPTY")
    if api_key is not None:
        llm_args["api_key"] = api_key
    if enable_thinking is not None:
        extra_body = llm_args.setdefault("extra_body", {})
        extra_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = (
            enable_thinking
        )
    return llm_args


def _get_version() -> str:
    from tau_emotion.utils.utils import get_tau_emotion_version

    return get_tau_emotion_version()


def run_intro():
    """Display a rich intro page describing what tau-emotion-bench can do."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    version = _get_version()

    # ── Banner ──────────────────────────────────────────────────────────
    banner = Text(justify="center")
    banner.append("\n")
    banner.append("tau-emotion-bench", style="bold cyan")
    banner.append(f"  v{version}\n", style="dim")
    banner.append(
        "A benchmark for conversational customer-service agents\n"
        "under emotional user behavior\n",
        style="italic",
    )
    console.print(
        Panel(
            banner,
            border_style="cyan",
            padding=(1, 4),
        )
    )

    # ── Modes ───────────────────────────────────────────────────────────
    modes_table = Table(
        title="Communication Modes",
        box=box.SIMPLE_HEAVY,
        title_style="bold magenta",
        show_edge=False,
        pad_edge=False,
        padding=(0, 2),
    )
    modes_table.add_column("Mode", style="bold", no_wrap=True)
    modes_table.add_column("Description")
    modes_table.add_row(
        "Half-duplex (text)",
        "Turn-based text conversations. Agent and user take turns exchanging messages.",
    )
    console.print(modes_table)
    console.print()

    # ── Domains ─────────────────────────────────────────────────────────
    domain_table = Table(
        title="Domains",
        box=box.SIMPLE_HEAVY,
        title_style="bold magenta",
        show_edge=False,
        pad_edge=False,
        padding=(0, 2),
    )
    domain_table.add_column("Domain", style="bold", no_wrap=True)
    domain_table.add_column("Description")
    domain_table.add_row(
        "airline", "Flight booking, cancellation, and customer support"
    )
    domain_table.add_row("retail", "Order management, returns, and product inquiries")
    domain_table.add_row("telecom", "Telecom account management and troubleshooting")
    domain_table.add_row(
        "telehealth",
        "Patient appointments, prescriptions, and provider scheduling",
    )
    domain_table.add_row(
        "school",
        "Course registration, schedule changes, and tuition payments",
    )
    domain_table.add_row(
        "restaurant",
        "Ticket lookup, order modification, cancellation, and tips",
    )
    domain_table.add_row(
        "movie",
        "Showtimes, seat booking, and ticket cancellation",
    )
    domain_table.add_row(
        "travel",
        "Package search, trip booking, and itinerary changes",
    )
    domain_table.add_row(
        "basketball",
        "Club, player and game lookup, scoring, and statistics",
    )
    domain_table.add_row(
        "bank",
        "Account, card, loan and beneficiary management, and transfers",
    )
    domain_table.add_row("mock", "Lightweight test domain for development")
    console.print(domain_table)
    console.print()

    # ── Commands ────────────────────────────────────────────────────────
    cmd_table = Table(
        title="Commands",
        box=box.SIMPLE_HEAVY,
        title_style="bold magenta",
        show_edge=False,
        pad_edge=False,
        padding=(0, 2),
    )
    cmd_table.add_column("Command", style="bold green", no_wrap=True)
    cmd_table.add_column("What it does")
    cmd_table.add_row("tau-emotion run", "Run a benchmark evaluation against a domain")
    cmd_table.add_row("tau-emotion view", "Browse and inspect simulation results")
    cmd_table.add_row(
        "tau-emotion domain <name>", "Show detailed documentation for a domain"
    )
    cmd_table.add_row(
        "tau-emotion review <path>", "Run LLM-based conversation review on results"
    )
    cmd_table.add_row(
        "tau-emotion evaluate-trajs <paths>",
        "Re-evaluate trajectories and recompute rewards",
    )
    cmd_table.add_row(
        "tau-emotion check-data", "Verify data directory is set up correctly"
    )
    cmd_table.add_row("tau-emotion start", "Start background servers")
    cmd_table.add_row("tau-emotion intro", "Show this page")
    console.print(cmd_table)
    console.print()

    # ── Quick Start ─────────────────────────────────────────────────────
    from rich.syntax import Syntax

    quick_start = (
        "# 1. Verify your setup\n"
        "tau-emotion check-data\n"
        "\n"
        "# 2. Run a text (half-duplex) evaluation\n"
        "tau-emotion run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 "
        "--num-trials 1 --num-tasks 5\n"
        "\n"
        "# 3. Browse results\n"
        "tau-emotion view"
    )
    console.print(
        Panel(
            Syntax(quick_start, "bash", theme="monokai", line_numbers=False),
            title="[bold yellow]Quick Start[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    # ── Tip ─────────────────────────────────────────────────────────────
    console.print(
        "\n[dim]Tip: Run any command with [bold]--help[/bold] for detailed usage, "
        "e.g. [bold green]tau-emotion run --help[/bold green][/dim]\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Tau-Emotion command line interface")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a benchmark")
    add_run_args(run_parser)

    def run_command(args):
        # Set global LLM log mode (used by verbose logging)
        from tau_emotion.utils.llm_utils import set_llm_log_mode

        set_llm_log_mode(args.llm_log_mode)

        # Shared config kwargs
        shared_kwargs = dict(
            domain=args.domain,
            task_set_name=args.task_set_name,
            task_split_name=args.task_split_name,
            task_ids=args.task_ids,
            num_tasks=args.num_tasks,
            llm_user=args.user_llm,
            llm_args_user=_llm_args(args, "user"),
            num_trials=args.num_trials,
            max_errors=args.max_errors,
            timeout=args.timeout,
            save_to=args.save_to,
            max_concurrency=args.max_concurrency,
            seed=args.seed,
            log_level=args.log_level,
            verbose_logs=args.verbose_logs,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            auto_resume=args.auto_resume,
            auto_review=args.auto_review,
            review_mode=args.review_mode,
            no_emotion=args.no_emotion,
        )

        config = TextRunConfig(
            **shared_kwargs,
            agent=args.agent,
            llm_agent=args.agent_llm,
            llm_args_agent=_llm_args(args, "agent"),
            user=args.user,
            max_steps=args.max_steps,
            enforce_communication_protocol=args.enforce_communication_protocol,
        )

        return run_domain(config)

    run_parser.set_defaults(func=run_command)

    # View command
    view_parser = subparsers.add_parser("view", help="View simulation results")
    view_parser.add_argument(
        "--dir",
        type=str,
        help="Directory containing simulation files. Defaults to data/simulations if not specified.",
    )
    view_parser.add_argument(
        "--file",
        type=str,
        help="Path to the simulation results file to view",
    )
    view_parser.add_argument(
        "--only-show-failed",
        action="store_true",
        help="Only show failed tasks.",
    )
    view_parser.add_argument(
        "--only-show-all-failed",
        action="store_true",
        help="Only show tasks that failed in all trials.",
    )
    view_parser.set_defaults(func=lambda args: run_view_simulations(args))

    # Domain command
    domain_parser = subparsers.add_parser("domain", help="Show domain documentation")
    domain_parser.add_argument(
        "domain",
        type=str,
        help="Name of the domain to show documentation for (e.g., 'airline', 'mock')",
    )
    domain_parser.set_defaults(func=lambda args: run_show_domain(args))

    # Start command
    start_parser = subparsers.add_parser("start", help="Start all servers")
    start_parser.set_defaults(func=lambda args: run_start_servers())

    # Intro command
    intro_parser = subparsers.add_parser(
        "intro", help="Show an overview of tau-emotion-bench and available commands"
    )
    intro_parser.set_defaults(func=lambda args: run_intro())

    # Check data command
    check_data_parser = subparsers.add_parser(
        "check-data", help="Check if data directory is properly configured"
    )
    check_data_parser.set_defaults(func=lambda args: run_check_data())

    # Evaluate trajectories command
    evaluate_parser = subparsers.add_parser(
        "evaluate-trajs", help="Evaluate trajectories and update rewards"
    )
    evaluate_parser.add_argument(
        "paths",
        nargs="+",
        help="Paths to trajectory files, directories, or glob patterns",
    )
    evaluate_parser.add_argument(
        "-o",
        "--output-dir",
        help="Directory to save updated trajectory files with recomputed rewards. If not provided, only displays metrics.",
    )
    evaluate_parser.set_defaults(func=lambda args: run_evaluate_trajectories(args))

    # Review command - LLM-based conversation review
    review_parser = subparsers.add_parser(
        "review", help="Run LLM-based conversation review on simulation results"
    )
    review_parser.add_argument(
        "path",
        help="Path to a results.json file or a directory containing results.json files",
    )
    review_parser.add_argument(
        "-m",
        "--mode",
        type=str,
        choices=["full", "user"],
        default="full",
        help="Review mode: 'full' (agent+user, default) or 'user' (user simulator only)",
    )
    review_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output path for the reviewed results (only used for single file)",
    )
    review_parser.add_argument(
        "--show-details",
        action="store_true",
        help="Show detailed review results for each simulation",
    )
    review_parser.add_argument(
        "-c",
        "--max-concurrency",
        type=int,
        default=32,
        help="Maximum number of concurrent reviews (default: 32)",
    )
    review_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit review to first N simulations",
    )
    review_parser.add_argument(
        "--task-ids",
        type=str,
        nargs="+",
        default=None,
        help="Only review simulations for these task IDs",
    )
    review_parser.add_argument(
        "--judge-llm",
        type=str,
        default=None,
        help=f"The LLM used as the review judge. Default: {DEFAULT_LLM_EVAL_USER_SIMULATOR}. "
        "A bare model name (e.g. qwen3-235b-a22b-instruct-2507) goes to OPENAI_API_BASE.",
    )
    review_parser.add_argument(
        "--judge-llm-args",
        type=json.loads,
        default={},
        help="The arguments to pass to the judge LLM, as JSON. Default: '{}'.",
    )
    review_parser.add_argument(
        "--judge-api-base",
        type=str,
        default=None,
        help="Base URL of the judge's OpenAI-compatible server. "
        "Default: the provider's (OPENAI_API_BASE for OpenAI models, gpt-4.1 included, "
        "and bare model names).",
    )
    review_parser.add_argument(
        "--judge-api-key",
        type=str,
        default=None,
        help="API key for the judge's server. Default: the provider's env var, "
        "or no key when --judge-api-base is given.",
    )
    review_parser.add_argument(
        "--judge-enable-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Turn the judge model's thinking on or off through its chat template "
        "(vLLM chat_template_kwargs.enable_thinking). Default: the model's own default.",
    )
    review_parser.add_argument(
        "--failed-only",
        action="store_true",
        help="Only review failed simulations (reward not 1). Default: review all",
    )
    review_parser.add_argument(
        "--log-llm",
        action="store_true",
        help="Log LLM request/response for each review call",
    )
    review_parser.set_defaults(func=lambda args: run_review(args))

    # Convert results format command
    convert_parser = subparsers.add_parser(
        "convert-results",
        help="Convert simulation results between storage formats",
    )
    convert_parser.add_argument(
        "path",
        help="Path to results.json or results directory to convert",
    )
    convert_parser.add_argument(
        "--to",
        dest="target_format",
        choices=["json", "dir"],
        default=None,
        help="Target format: 'json' (monolithic) or 'dir' (directory with individual sim files). "
        "If omitted, converts to the opposite of the current format.",
    )
    convert_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a .bak backup of the original file",
    )
    convert_parser.set_defaults(func=lambda args: run_convert_results(args))

    args = parser.parse_args()
    if not hasattr(args, "func"):
        run_intro()
        return

    args.func(args)


def run_view_simulations(args):
    from tau_emotion.scripts.view_simulations import main as view_main

    view_main(
        sim_file=args.file,
        only_show_failed=args.only_show_failed,
        only_show_all_failed=args.only_show_all_failed,
        sim_dir=args.dir,
    )


def run_show_domain(args):
    from tau_emotion.scripts.show_domain_doc import main as domain_main

    domain_main(args.domain)


def run_start_servers():
    from tau_emotion.scripts.start_servers import main as start_main

    start_main()


def run_check_data():
    from tau_emotion.scripts.check_data import main as check_data_main

    check_data_main()


def run_evaluate_trajectories(args):
    import sys

    from loguru import logger

    from tau_emotion.scripts.evaluate_trajectories import evaluate_trajectories

    logger.configure(handlers=[{"sink": sys.stderr, "level": "ERROR"}])

    evaluate_trajectories(args.paths, args.output_dir)


def run_review(args):
    """Run LLM-based conversation review."""
    import sys
    from pathlib import Path

    from loguru import logger
    from rich.console import Console

    from tau_emotion.evaluator.judge_llm import set_judge_llm
    from tau_emotion.scripts.review_conversation import (
        ReviewMode,
        find_results_files,
        review,
    )

    logger.configure(handlers=[{"sink": sys.stderr, "level": "WARNING"}])
    set_judge_llm(model=args.judge_llm, llm_args=_llm_args(args, "judge"))

    # Find all results files
    input_path = Path(args.path)
    results_files = find_results_files(input_path)

    if not results_files:
        console = Console()
        console.print(f"[red]No results.json files found in: {args.path}[/red]")
        sys.exit(1)

    # Run review for each results file
    mode = ReviewMode.FULL if args.mode == "full" else ReviewMode.USER
    console = Console()

    if len(results_files) > 1:
        console.print(
            f"\n📁 Found {len(results_files)} results files to review:",
            style="bold blue",
        )
        for i, rf in enumerate(results_files, 1):
            console.print(f"  {i}. {rf.parent.name}/results.json")
        console.print()

    for i, results_file in enumerate(results_files):
        if len(results_files) > 1:
            console.print(
                f"\n{'=' * 60}\n[bold cyan]Processing ({i + 1}/{len(results_files)}): {results_file.parent.name}[/bold cyan]\n{'=' * 60}"
            )

        review(
            results_path=str(results_file),
            mode=mode,
            output_path=args.output if len(results_files) == 1 else None,
            show_details=args.show_details,
            max_concurrency=args.max_concurrency,
            limit=args.limit,
            task_ids=args.task_ids,
            log_llm=args.log_llm,
            failed_only=args.failed_only,
        )


def run_convert_results(args):
    """Convert simulation results between storage formats."""
    import shutil
    from pathlib import Path

    from tau_emotion.data_model.simulation import Results

    path = Path(args.path)
    current_fmt = Results._detect_format(path)
    target_fmt = args.target_format

    if target_fmt is None:
        target_fmt = "json" if current_fmt == "dir" else "dir"

    if current_fmt == target_fmt:
        print(f"Results at {path} are already in '{target_fmt}' format.")
        return

    print(f"Converting {path}: '{current_fmt}' -> '{target_fmt}'")
    results = Results.load(path)

    meta_path = path if path.suffix == ".json" else path / "results.json"

    if not args.no_backup:
        if current_fmt == "json":
            backup = meta_path.with_suffix(".json.bak")
            shutil.copy2(meta_path, backup)
            print(f"  Backup: {backup}")
        else:
            sims_dir = meta_path.parent / "simulations"
            backup_dir = meta_path.parent / "simulations.bak"
            if sims_dir.exists():
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.copytree(sims_dir, backup_dir)
            backup = meta_path.with_suffix(".json.bak")
            shutil.copy2(meta_path, backup)
            print(f"  Backup: {backup}")
            if backup_dir.exists():
                print(f"  Backup: {backup_dir}")

    if target_fmt == "dir":
        results.save(meta_path, format="dir")
    else:
        sims_dir = meta_path.parent / "simulations"
        results.save(meta_path, format="json")
        if sims_dir.exists():
            shutil.rmtree(sims_dir)

    n = len(results.simulations)
    print(f"  Done. {n} simulation(s) converted to '{target_fmt}' format.")


if __name__ == "__main__":
    main()
