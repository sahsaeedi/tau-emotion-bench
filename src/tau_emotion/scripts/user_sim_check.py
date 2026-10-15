"""Check that a submission's user turns came from the leaderboard's user simulator.

For a sample of conversations, the simulator's own model scores the recorded user
turns as the simulator saw them: its prompt and the conversation up to each turn.
The model's own text is its top choice at almost every token; another model's is
not. On airline reference runs, Qwen3-235B and GLM-5.2 each scored about 96% on
their own conversations, and 74-80% on those of the other one, Qwen3-30B-A3B or
Gemma 4 31B. This tells models apart, not temperatures: Qwen3-235B's turns at
temperature 0.7 still scored 95.5%.

The ASU API returns prompt log-probabilities only from /completions, so the
conversation is rendered with the model's chat template here, as vLLM would.
"""

import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional

import httpx
from jinja2.ext import loopcontrols
from jinja2.sandbox import ImmutableSandboxedEnvironment
from rich.console import Console
from rich.table import Table

from tau_emotion.data_model.message import (
    AssistantMessage,
    Message,
    ToolMessage,
    UserMessage,
)
from tau_emotion.data_model.simulation import Results, SimulationRun
from tau_emotion.data_model.tasks import Task
from tau_emotion.user.user_simulator import UserSimulator
from tau_emotion.utils.llm_utils import _reasoning_content, to_litellm_messages

# Leaderboard user simulator: (its name on the ASU API, its Hugging Face repo,
# whose chat template renders the prompt)
SIMULATORS = {
    "qwen3-235b-a22b-instruct-2507": (
        "qwen3-235b-a22b-instruct-2507",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
    ),
    "glm-5.2": ("glm-5-2", "zai-org/GLM-5.2"),
}
# The share of user-turn tokens that must be the simulator's top choice, between
# the reference runs and the other models above.
MIN_TOP1_RATE = 0.9
MAX_WORKERS = 8


def user_sim_messages(simulation: SimulationRun) -> list[Message]:
    """The messages the user simulator saw by the end of the conversation."""
    return [
        m
        for m in simulation.messages
        if isinstance(m, UserMessage)
        or (
            isinstance(m, AssistantMessage) and m.has_content() and not m.is_tool_call()
        )
        or (isinstance(m, ToolMessage) and m.requestor == "user")
    ]


def user_sim_prompt(simulation: SimulationRun, task: Task) -> list[dict]:
    """Those messages as the simulator sent them, with its own turns as assistant
    messages (UserSimulator._generate_next_message)."""
    user = UserSimulator(
        llm="", instructions=task.user_scenario.to_tau_bench_instruction()
    )
    state = user.get_init_state(user_sim_messages(simulation))
    return to_litellm_messages(state.system_messages + state.flip_roles())


@lru_cache(maxsize=None)
def chat_template(repo: str):
    """A render function for the repo's chat template, set up like transformers'."""
    url = f"https://huggingface.co/{repo}/resolve/main"
    config = httpx.get(f"{url}/tokenizer_config.json", follow_redirects=True)
    config = config.raise_for_status().json()
    source = config.get("chat_template")
    if not source:
        response = httpx.get(f"{url}/chat_template.jinja", follow_redirects=True)
        source = response.raise_for_status().text

    def tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False):
        return json.dumps(
            x,
            ensure_ascii=ensure_ascii,
            indent=indent,
            separators=separators,
            sort_keys=sort_keys,
        )

    def raise_exception(message):
        raise ValueError(message)

    env = ImmutableSandboxedEnvironment(
        trim_blocks=True, lstrip_blocks=True, extensions=[loopcontrols]
    )
    env.filters["tojson"] = tojson
    env.globals["raise_exception"] = raise_exception
    template = env.from_string(source)
    special_tokens = {
        k: v if isinstance(v, str) else v.get("content")
        for k, v in config.items()
        if k.endswith("_token") and v
    }
    return lambda messages: template.render(
        messages=messages, add_generation_prompt=False, **special_tokens
    )


def prompt_token_ranks(
    model: str, prompt: str, api_base: str, api_key: str
) -> list[tuple[int, int]]:
    """Each token of the prompt as (its offset in the prompt, its rank among the
    model's choices there)."""
    response = httpx.post(
        f"{api_base.rstrip('/')}/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "prompt": prompt,
            "max_tokens": 1,
            "temperature": 0.0,
            "echo": True,
            "logprobs": 1,
        },
        timeout=300,
    )
    choice = response.raise_for_status().json()["choices"][0]
    if not choice.get("prompt_logprobs"):
        raise RuntimeError(f"{model}: the server returned no prompt_logprobs")
    return [
        # The prompt's own token is listed next to the top one when it isn't the top
        (offset, max(t["rank"] for t in position.values()))
        for offset, position in zip(
            choice["logprobs"]["text_offset"], choice["prompt_logprobs"]
        )
        if position  # the first token has none
    ]


def score_simulation(
    simulation: SimulationRun,
    task: Task,
    simulator: str,
    api_base: str,
    api_key: str,
) -> tuple[int, int, int]:
    """(user-turn tokens, how many were the top choice, user turns not found
    in the rendered prompt)."""
    model, repo = SIMULATORS[simulator]
    render = chat_template(repo)
    messages = user_sim_prompt(simulation, task)
    reasoning = [
        _reasoning_content(m)
        for m in user_sim_messages(simulation)
        if isinstance(m, UserMessage)
    ]
    full = render(messages)

    # Each turn as the simulator wrote it: after the conversation so far, and after
    # its reasoning, which templates show only for the latest turn. Turns that
    # render as a prefix of the whole conversation are scored in one request.
    prompts: dict[str, list[tuple[int, int]]] = {}
    missing = 0
    turns = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    for i, thought in zip(turns, reasoning):
        if not messages[i]["content"]:
            continue
        turn = dict(messages[i], reasoning_content=thought) if thought else messages[i]
        text = render(messages[:i] + [turn])
        content = messages[i]["content"].strip()
        start = text.rfind(content)
        if start < 0:
            missing += 1
            continue
        prompt = full if full.startswith(text) else text
        prompts.setdefault(prompt, []).append((start, start + len(content)))

    n_tokens = n_top = 0
    for prompt, spans in prompts.items():
        for offset, rank in prompt_token_ranks(model, prompt, api_base, api_key):
            if any(start <= offset < end for start, end in spans):
                n_tokens += 1
                n_top += rank == 1
    return n_tokens, n_top, missing


def check_user_simulator(
    all_results: list[Results],
    sample: int = 10,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[str]:
    """Score a random sample of conversations per run; the problems found."""
    from tau_emotion.scripts.submission import user_llm_name

    api_base = api_base or os.environ.get("OPENAI_API_BASE")
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_base or not api_key:
        return ["user simulator check: set OPENAI_API_BASE and OPENAI_API_KEY"]

    jobs = []
    for results in all_results:
        tasks = {t.id: t for t in results.tasks}
        simulator = user_llm_name(results.info.user_info.llm)
        domain = results.info.environment_info.domain_name
        sims = random.sample(results.simulations, min(sample, len(results.simulations)))
        jobs += [(simulator, domain, sim, tasks[sim.task_id]) for sim in sims]

    def run(job):
        simulator, _, sim, task = job
        try:
            return job, score_simulation(sim, task, simulator, api_base, api_key)
        except Exception as e:
            return job, e

    console = Console()
    console.print(f"Scoring {len(jobs)} conversations with their user simulators...")
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        outcomes = list(pool.map(run, jobs))

    errors = []
    totals: dict[tuple[str, str], list[int]] = {}
    for (simulator, domain, sim, _), outcome in outcomes:
        if isinstance(outcome, Exception):
            errors.append(f"user simulator check, {domain} {sim.id}: {outcome}")
            continue
        total = totals.setdefault((simulator, domain), [0, 0, 0])
        for i, n in enumerate(outcome):
            total[i] += n

    table = Table(title="User-turn tokens that are the simulator's top choice")
    for column in (
        "User simulator",
        "Domain",
        "Tokens",
        "Top choice",
        "Turns not found",
    ):
        table.add_column(column)
    for (simulator, domain), (n_tokens, n_top, missing) in sorted(totals.items()):
        rate = n_top / n_tokens if n_tokens else 0.0
        table.add_row(simulator, domain, str(n_tokens), f"{rate:.1%}", str(missing))
        if rate < MIN_TOP1_RATE:
            errors.append(
                f"{simulator} {domain}: {rate:.1%} of user-turn tokens are the "
                f"simulator's top choice, expected at least {MIN_TOP1_RATE:.0%}"
            )
    console.print(table)
    return errors
