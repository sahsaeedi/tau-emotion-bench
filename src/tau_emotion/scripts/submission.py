"""Leaderboard submissions, following tau2-bench's text submission flow.

`tau-emotion submit prepare` turns a model's run results into submission.json, and
`tau-emotion submit validate` checks a submission.json against its trajectories.
See docs/leaderboard-submission.md.
"""

import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Literal, Optional

from pydantic import BaseModel
from rich.console import Console
from rich.prompt import Prompt

from tau_emotion.data_model.simulation import Results, TerminationReason
from tau_emotion.metrics.agent_metrics import AgentMetrics, compute_metrics
from tau_emotion.registry import registry
from tau_emotion.scripts.evaluate_trajectories import compute_simulation_rewards
from tau_emotion.user.user_simulator import get_global_user_sim_guidelines
from tau_emotion.utils.io_utils import expand_paths
from tau_emotion.utils.pydantic_utils import get_pydantic_hash
from tau_emotion.utils.utils import get_dict_hash, get_tau_emotion_version

# Every leaderboard run uses these settings. A submission must include runs with
# the required user simulator; runs with an optional one fill a second leaderboard tab.
REQUIRED_USER_LLM = "qwen3-235b-a22b-instruct-2507"
OPTIONAL_USER_LLMS = {"glm-5.2"}
# Other names of these models, e.g. on the ASU API
USER_LLM_ALIASES = {"glm-5-2": "glm-5.2"}
USER_LLM_ARGS = {"temperature": 0.0}
MIN_TRIALS = 3
MAX_STEPS = 200
TASK_SPLIT = "base"
# Standard submissions run this agent; any other agent makes a custom submission.
STANDARD_AGENT = "llm_agent"
SUBMISSION_FORM_URL = (
    "https://github.com/sahsaeedi/tau-emotion-bench/issues/new"
    "?template=leaderboard_submission.yml"
)


class DomainResults(BaseModel):
    pass_1: float
    pass_2: float
    pass_3: float
    avg_reward: float


class UserSimResults(BaseModel):
    # Means over the domains, each domain counting once
    avg_at_3: float  # Avg@3: mean of the domains' Pass^1
    avg_hat_3: float  # Avg^3: mean of the domains' Pass^3
    domains: dict[str, DomainResults]


class Contact(BaseModel):
    name: str
    email: str


class Methodology(BaseModel):
    benchmark_version: str
    benchmark_commit: str
    agent_implementation: str
    user_simulator_provider: str
    notes: str = ""
    references: list[str] = []


class Submission(BaseModel):
    model_name: str
    model_organization: str
    submitting_organization: str
    submission_date: str
    submission_type: Literal["standard", "custom"] = "standard"
    contact: Contact
    trajectories_url: str
    # user simulator -> scores
    results: dict[str, UserSimResults]
    methodology: Methodology


def user_llm_name(llm: Optional[str]) -> str:
    """The model name without its provider prefix, lowercased: openai/Qwen/X -> x."""
    name = (llm or "").rsplit("/", 1)[-1].lower()
    return USER_LLM_ALIASES.get(name, name)


def _without_api_base(llm_args: Optional[dict]) -> dict:
    # Every submitter serves the models somewhere else, so the server is ignored.
    return {k: v for k, v in (llm_args or {}).items() if k != "api_base"}


def benchmark_domains() -> list[str]:
    return [d for d in registry.get_domains() if d != "mock"]


def load_results(paths: list[str]) -> list[Results]:
    return [Results.load(Path(p)) for p in expand_paths(paths, extension=".json")]


def check_results(all_results: list[Results]) -> list[str]:
    """What keeps these runs off the leaderboard; empty if nothing does."""
    errors = []
    domains = benchmark_domains()
    seen = set()
    agents = set()
    for results in all_results:
        info = results.info
        domain = info.environment_info.domain_name
        user = user_llm_name(info.user_info.llm)
        where = f"{domain} ({info.user_info.llm})"
        if domain not in domains:
            errors.append(f"{where}: not a benchmark domain")
            continue
        if (user, domain) in seen:
            errors.append(f"{where}: appears more than once")
        seen.add((user, domain))

        # The user simulator, exactly as the benchmark runs it
        if user != REQUIRED_USER_LLM and user not in OPTIONAL_USER_LLMS:
            errors.append(f"{where}: not a leaderboard user simulator")
        if info.user_info.implementation != "user_simulator":
            errors.append(f"{where}: user is {info.user_info.implementation}")
        user_args = _without_api_base(info.user_info.llm_args)
        if user_args != USER_LLM_ARGS:
            errors.append(
                f"{where}: user simulator args {user_args}, expected {USER_LLM_ARGS}"
            )
        if info.user_info.no_emotion:
            errors.append(f"{where}: run with --no-emotion")
        if (
            info.user_info.global_simulation_guidelines
            != get_global_user_sim_guidelines()
        ):
            errors.append(f"{where}: user simulator prompt was modified")

        if info.num_trials < MIN_TRIALS:
            errors.append(
                f"{where}: {info.num_trials} trials, need at least {MIN_TRIALS}"
            )
        if info.max_steps != MAX_STEPS:
            errors.append(f"{where}: max steps {info.max_steps}, expected {MAX_STEPS}")

        # Every task unchanged and run num_trials times, the policy unchanged
        official = {
            t.id: get_pydantic_hash(t)
            for t in registry.get_tasks_loader(domain)(TASK_SPLIT)
        }
        submitted = {t.id: get_pydantic_hash(t) for t in results.tasks}
        if official.keys() != submitted.keys():
            errors.append(
                f"{where}: {len(official.keys() - submitted.keys())} tasks missing, "
                f"{len(submitted.keys() - official.keys())} extra"
            )
        elif changed := [tid for tid in official if official[tid] != submitted[tid]]:
            errors.append(f"{where}: {len(changed)} tasks modified")
        # Scoring leaves out simulations that never ran, so they can't count as trials.
        infra = TerminationReason.INFRASTRUCTURE_ERROR
        if n_infra := sum(s.termination_reason == infra for s in results.simulations):
            errors.append(
                f"{where}: {n_infra} simulations hit infrastructure errors; "
                "rerun the same command to redo them"
            )
        trials = Counter(
            s.task_id for s in results.simulations if s.termination_reason != infra
        )
        if wrong := [tid for tid in official if trials[tid] != info.num_trials]:
            errors.append(
                f"{where}: {len(wrong)} tasks without {info.num_trials} trials"
            )
        if (
            info.environment_info.policy
            != registry.get_env_constructor(domain)().get_policy()
        ):
            errors.append(f"{where}: domain policy was modified")

        agent = info.agent_info
        agents.add(
            get_dict_hash(
                {
                    "implementation": agent.implementation,
                    "llm": agent.llm,
                    "llm_args": _without_api_base(agent.llm_args),
                }
            )
        )

    if len(agents) > 1:
        errors.append("the agent or its settings differ between runs")
    users = {u for u, _ in seen if u in OPTIONAL_USER_LLMS} | {REQUIRED_USER_LLM}
    for user in sorted(users):
        if missing := [d for d in domains if (user, d) not in seen]:
            errors.append(f"{user}: missing domains {missing}")
    return errors


def _scores(metrics: AgentMetrics) -> DomainResults:
    return DomainResults(
        pass_1=round(100 * metrics.pass_hat_ks[1], 2),
        pass_2=round(100 * metrics.pass_hat_ks[2], 2),
        pass_3=round(100 * metrics.pass_hat_ks[3], 2),
        avg_reward=round(metrics.avg_reward, 4),
    )


def compute_results(all_results: list[Results]) -> dict[str, UserSimResults]:
    """Scores per user simulator: each domain's, and Avg@3 and Avg^3 over domains."""
    by_user: dict[str, dict[str, AgentMetrics]] = {}
    for results in all_results:
        user = user_llm_name(results.info.user_info.llm)
        domain = results.info.environment_info.domain_name
        by_user.setdefault(user, {})[domain] = compute_metrics(results)

    out = {}
    for user, metrics in by_user.items():
        out[user] = UserSimResults(
            avg_at_3=round(mean(100 * m.pass_hat_ks[1] for m in metrics.values()), 2),
            avg_hat_3=round(mean(100 * m.pass_hat_ks[3] for m in metrics.values()), 2),
            domains={d: _scores(m) for d, m in sorted(metrics.items())},
        )
    return out


def rescore(all_results: list[Results]) -> tuple[list[Results], int]:
    """The runs with every simulation scored again by our evaluator, and how many
    simulations' saved rewards differ from the new ones."""
    # About half a second per simulation, so the runs are scored in parallel.
    Console().print(f"Scoring {len(all_results)} runs again...")
    with ProcessPoolExecutor(min(len(all_results), os.cpu_count() or 1)) as pool:
        rescored = list(pool.map(compute_simulation_rewards, all_results))
    changed = sum(
        abs(old.reward_info.reward - new.reward_info.reward) > 1e-6
        for before, after in zip(all_results, rescored)
        for old, new in zip(before.simulations, after.simulations)
        if old.reward_info is not None
    )
    return rescored, changed


def _print_errors(console: Console, errors: list[str]) -> None:
    console.print(f"❌ {len(errors)} problem(s):", style="red")
    for error in errors:
        console.print(f"  • {error}", style="red")


def prepare(paths: list[str], output_dir: str) -> bool:
    """Check the runs, ask for the submission details and write submission.json."""
    console = Console()
    all_results = load_results(paths)
    if errors := check_results(all_results):
        _print_errors(console, errors)
        return False

    agent = all_results[0].info.agent_info.implementation
    if agent == STANDARD_AGENT:
        submission_type = Prompt.ask(
            "Submission type", choices=["standard", "custom"], default="standard"
        )
    else:
        console.print(
            f"The runs use the {agent} agent, so this is a custom submission."
        )
        submission_type = "custom"
    references = []
    if submission_type == "custom":
        references = [Prompt.ask("Link to the code or paper")]
    submission = Submission(
        model_name=Prompt.ask("Model name", default=all_results[0].info.agent_info.llm),
        model_organization=Prompt.ask("Model organization"),
        submitting_organization=Prompt.ask("Submitting organization"),
        submission_date=date.today().isoformat(),
        submission_type=submission_type,
        contact=Contact(
            name=Prompt.ask("Contact name"), email=Prompt.ask("Contact email")
        ),
        trajectories_url=Prompt.ask("Link where you will share the trajectories"),
        results=compute_results(all_results),
        methodology=Methodology(
            benchmark_version=get_tau_emotion_version(),
            benchmark_commit=all_results[0].info.git_commit,
            agent_implementation=agent,
            user_simulator_provider=Prompt.ask(
                "Who served the user simulator (e.g. own vLLM, OpenRouter)"
            ),
            notes=Prompt.ask("Notes (required for custom submissions)", default=""),
            references=references,
        ),
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "submission.json").write_text(submission.model_dump_json(indent=2) + "\n")
    console.print(f"✅ Wrote {out / 'submission.json'}", style="green")
    console.print(f"Submit it with the form at {SUBMISSION_FORM_URL}")
    return True


def validate(
    submission_path: str,
    paths: list[str],
    check_user_sim: bool = False,
    sample: int = 10,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> bool:
    """Check submission.json against the trajectories it reports, scoring the
    trajectories again rather than trusting their saved rewards."""
    console = Console()
    submission = Submission.model_validate_json(Path(submission_path).read_text())
    all_results = load_results(paths)
    errors = check_results(all_results)
    if errors:
        # Scores can't be computed reliably from runs that miss the requirements.
        _print_errors(console, errors)
        return False

    all_results, changed = rescore(all_results)
    if changed:
        errors.append(
            f"{changed} simulations' saved rewards differ from scoring them again"
        )
    computed = compute_results(all_results)
    for user in submission.results.keys() - computed.keys():
        errors.append(f"{user}: in submission.json but no trajectories")
    for user, expected in computed.items():
        if (reported := submission.results.get(user)) is None:
            errors.append(f"{user}: trajectories but no scores in submission.json")
            continue
        for name in ("avg_at_3", "avg_hat_3"):
            if getattr(reported, name) != getattr(expected, name):
                errors.append(
                    f"{user} {name}: reported {getattr(reported, name)}, "
                    f"trajectories give {getattr(expected, name)}"
                )
        for domain in sorted(reported.domains.keys() | expected.domains.keys()):
            got, want = reported.domains.get(domain), expected.domains.get(domain)
            if got != want:
                errors.append(
                    f"{user} {domain}: reported {got}, trajectories give {want}"
                )

    agent = all_results[0].info.agent_info.implementation
    if submission.submission_type == "standard" and agent != STANDARD_AGENT:
        errors.append(f"the runs use the {agent} agent, so the submission is custom")
    if submission.submission_type == "custom" and not (
        submission.methodology.notes and submission.methodology.references
    ):
        errors.append("custom submissions need methodology notes and a reference link")

    if check_user_sim:
        from tau_emotion.scripts.user_sim_check import check_user_simulator

        errors += check_user_simulator(
            all_results, sample=sample, api_base=api_base, api_key=api_key
        )

    if errors:
        _print_errors(console, errors)
        return False
    console.print("✅ Submission is valid", style="green")
    return True
