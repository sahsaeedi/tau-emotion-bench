import argparse
import json
import os
from collections import defaultdict
from typing import List, Optional

# ---------------------------------------------------------------------
# Domain tools
# ---------------------------------------------------------------------
import tracer.envs.airline.tools as airline_tools
import tracer.envs.bank.tools as bank_tools
import tracer.envs.basketball.tools as basketball_tools
import tracer.envs.movie.tools as movie_tools
import tracer.envs.restaurant.tools as restaurant_tools
import tracer.envs.retail.tools as retail_tools
import tracer.envs.school.tools as school_tools
import tracer.envs.telecom.tools as telecom_tools
import tracer.envs.telehealth.tools as telehealth_tools
import tracer.envs.travel.tools as travel_tools
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tqdm import tqdm
from tracer.envs.airline.wiki import WIKI as AIRLINE_WIKI
from tracer.envs.bank.wiki import WIKI as BANK_WIKI
from tracer.envs.basketball.wiki import WIKI as BASKETBALL_WIKI
from tracer.envs.movie.wiki import WIKI as MOVIE_WIKI
from tracer.envs.restaurant.wiki import WIKI as RESTAURANT_WIKI
from tracer.envs.retail.wiki import WIKI as RETAIL_WIKI
from tracer.envs.school.wiki import WIKI as SCHOOL_WIKI
from tracer.envs.telecom.wiki import WIKI as TELECOM_WIKI
from tracer.envs.telehealth.wiki import WIKI as TELEHEALTH_WIKI
from tracer.envs.travel.wiki import WIKI as TRAVEL_WIKI

load_dotenv()


# ---------------------------------------------------------------------
# Structured output schema for neighbour classification
# ---------------------------------------------------------------------
class IsNeighbourResponse(BaseModel):
    answer: List[bool] = Field(
        ...,
        description=(
            "A list of boolean values indicating whether each candidate function "
            "is a logical neighbour of the target function. True if neighbour, False otherwise. "
            "Order and length must match the provided candidate_functions list."
        ),
    )
    reason: List[str] = Field(
        ...,
        description=(
            "A list of concise reasoning strings (1–3 sentences each) corresponding to each candidate. "
            "For a candidate marked True, the reason must state the realistic customer/agent scenario "
            "that makes the follow-up plausible and explicitly list the specific inputs the user "
            "would need to provide (or that the agent can obtain immediately) to call the candidate tool "
            "(e.g., order_id, account_id, record_id). For a candidate marked False, briefly "
            "explain why the follow-up is implausible (mismatched intent, high cost without trigger, "
            "edge-case only, etc.)."
        ),
    )
    is_root: bool = Field(
        ...,
        description=(
            "Boolean indicating whether the target function can act as a root (entry-point) in a "
            "customer-support interaction. True only if the function can reasonably be the agent's "
            "first meaningful action and its required inputs are naturally available at the start of "
            "an interaction (provided directly by the customer or obtainable without other tool calls)."
        ),
    )
    is_root_reason: str = Field(
        ...,
        description=(
            "A brief justification (1–3 sentences) for the is_root decision. If True, explain why the "
            "function is callable as a first action and what inputs are typically available; if False, "
            "explain which prerequisite steps or inputs are usually required before this function can be called."
        ),
    )


# ---------------------------------------------------------------------
# Prompt (system + human)
# ---------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert software engineer and product-minded conversation designer. Your job is to analyze a single **target_function** and a list of **candidate_functions** (all part of a customer-service automation system) and decide which candidate functions should be considered **logical neighbours** of the target function.

Crucial framing
Imagine a real customer contacting support with a specific problem or request that would cause the agent to use the **target_function** as the primary action for that turn. Judgments must be made from the perspective of the customer’s intent and an agent’s practical workflow. Do **not** require that the target’s outputs map mechanically to candidate inputs — ignore any I/O-mapping rule. Use common sense and agent workflow logic to determine plausibility across any business domain.

Inputs you will receive
• `target_function`: signature, short description, and response schema.
• `candidate_functions`: ordered list of functions; each has signature, short description, and response schema.
• `domain_wiki` (optional): a short domain knowledge note (use it only to resolve ambiguous business rules).
• Representative task categories (optional): when present, a short list of benchmark-style scenario themes for the domain. Use it only as soft guidance for realistic customer/agent follow-ups — it is not exhaustive and must not override the decision rules above.

Few functions will be ommitted from the candidate list; like functions used for authentication and getting the customer deatils, which will be called by the agent as a prerequisite step before calling any domain specific function, so assume that such prerequisite steps have already been taken care of by the agent.

Decision rules (apply in order)
1. Customer-intent & agent-flow (primary): For each candidate, ask whether there exists a realistic, commonly encountered customer-support scenario in which the agent would plausibly call that candidate **immediately after** the target. Think: the customer’s goal, what the agent must do next, and which follow-ups are routine (confirm, change, cancel, refund, compensate, rebook, correct, verify, escalate).
2. Temporal & cost sensitivity: High-friction, costly, or terminal actions (e.g., full cancellations, large refunds, full rebookings, irreversible state changes) require strong, common-sense justification to be neighbours. Prefer conservative linking for such actions.
3. Edge-case exclusion: Do not mark a neighbour if the only plausible justification depends on rare, contrived, or internal/admin scenarios (debugging, system recovery, race conditions). Prefer not connecting unless the follow-up is a normal, customer-facing step.
4. Independent evaluation: Evaluate each candidate **only** in the context of the current target and a single realistic customer interaction. You will be invoked repeatedly with different targets; reciprocal links may appear across runs — that is expected.
5. Use `domain_wiki` only to resolve ambiguous business rules. If the wiki contradicts your intuition, follow the wiki.


Root eligibility (how to judge is_root)

Decide whether the target_function itself can be a realistic root (entry-point) for a customer support interaction.
A function is a root only if all of the following are true:
• A customer could reasonably initiate contact with a problem or request whose first meaningful agent action would be to call this function.
• The function does not require implicit, multi-step prerequisite workflows outside a normal single support turn (e.g., full search + selection + pricing flows, complex eligibility checks, or back-office approvals).
• All required inputs for the function are either human-facing or deterministically derivable, meaning:
	•	The input is typically provided directly by customers or easily stated in natural language (e.g., order number, account id, email, phone number, product name, commonly known SKU), or
	•	The input is not human-facing but can be unambiguously and deterministically derived from the provided domain_wiki using the human-facing inputs (e.g., fixed mappings, documented business rules, or guaranteed lookups described in the wiki).

A function must be marked not a root if:
• It requires internal-only identifiers (opaque database ids, internal product ids, record ids) that customers do not know and that cannot be reliably derived from the domain_wiki.
• It assumes prior discovery, selection, or context that is normally established through other domain-specific tools.
• Deriving required inputs would involve ambiguity, probabilistic inference, or additional multi-step discovery.

If it is unclear whether required inputs are human-facing or safely derivable, prefer is_root = false and explicitly state which inputs or prerequisite steps prevent root eligibility.

Important clarifications:
• **Internal-only identifiers** (internal database ids, internal `product_id`, opaque record ids) are **not** considered human-facing. If a function requires only internal identifiers and there is no declared lightweight helper (e.g., `search_by_name`) in `omitted_tools_light`, mark the function **not** a root.
• If you are given a list `omitted_tools_light` (routine helpers like authenticate, ask_identifier, search_by_name), treat those helpers as single-turn clarifying steps the agent can perform; they do **not** disqualify a function from being a root. If `omitted_tools_heavy` contains required helpers, treat those as multi-step prerequisites that disqualify a function from being a root unless strong justification exists.
• If tool metadata includes `user_facing_inputs`, prefer that authoritative information when judging root eligibility.

If it is ambiguous whether inputs are human-facing, prefer `is_root = false` and explain which prerequisites or discovery steps are typically required.


Rules for the output:
• `answer` must be a boolean list with the same length and order as `candidate_functions`. `true` means the candidate is a plausible immediate follow-up; `false` means it is not.  
• `reason` must be a list of concise justifications (1–3 sentences, max ~50 words each), aligned index-wise with `answer`. For `true`, state the realistic customer/agent scenario that makes the follow-up plausible and list any **user-provided inputs** that the agent would rely on or request at that moment (e.g., reservation id, order number, patient id). For `false`, state briefly why the follow-up is implausible (e.g., mismatched intent, high cost without trigger, only valid in edge cases). If you rely on an assumption, state it briefly.  
• `is_root` is a single boolean indicating whether the target can reasonably be the initial agent action for a customer contact.  
• `is_root_reason` is a concise (1–3 sentences) justification: if `true`, explain why the function is callable as a first action and what inputs are typically available; if `false`, explain which prerequisite steps or inputs are normally required.

Style & constraints
• Be conservative — prefer **not** connecting unless plausibly useful.  
• No self-edges: if a candidate equals the target, set that `answer` entry to `false` and the corresponding `reason` to `"self — ignored"`.  
• Keep reasons direct, plain-language, and short.  
• Do **not** output anything other than the single JSON object (no commentary, no extra formatting).

Failure handling
If you cannot reliably judge a candidate, answer `false` and provide a brief reason explaining insufficient grounds (e.g., "insufficient domain info").

Follow these instructions exactly.
"""

# ---------------------------------------------------------------------
# Optional: representative benchmark task categories per domain
# (aligned to tracer/envs/{telecom,telehealth,airline,retail}/tasks_test.py — soft guidance only)
# ---------------------------------------------------------------------
TASK_CONTEXT_TELECOM = """
• Identity / lookup: find customer by email or phone; load customer/account details.
• Billing: view billing breakdown, record payments, reconcile totals after plan changes, react to unexpected line items.
• Services: list/add/remove/upgrade/downgrade plans; attach services to specific devices.
• Devices: inventory devices, add new hardware, get device details, troubleshoot connectivity or device issues.
• Support tickets: create tickets (billing, account, security, etc.); read ticket status and details.
• Pricing & comparison: fetch service/plan prices; use calculate for deltas and hypothetical savings (often without completing a change).
• Discounts: senior or promotional pricing where the domain supports it.
""".strip()

TASK_CONTEXT_TELEHEALTH = """
• Scheduling: book, cancel, reschedule appointments; check provider schedules and specialties.
• Appointment lifecycle: list/filter by status (e.g. pending_approval, scheduled); fetch appointment details.
• Provider discovery: list available providers by specialty, language, experience; strict constraints may lead to human handoff.
• Billing / payment: insurance vs voucher vs self-pay; payment notes for special accounts.
• Family / multi-member: parent or guardian coordinating care for dependents (multiple patient profiles).
• Medical records: list recent records, fetch full record, append audit or progress notes.
• Pharmacy / sourcing: list medication suppliers (often by country/cost); update prescription supplier on a record.
• Safety: drug interaction checks against current medications.
• Regimen optimization: fetch regimen options; compare costs (often with calculate).
• Telemetry: device inventory snapshots, upload history, single-day upload artifacts; compliance-style audits tied to records/appointments.
""".strip()

TASK_CONTEXT_AIRLINE = """
• New bookings: book_reservation with cabin, route, dates, passengers, baggage counts, insurance yes/no, and split payment (certificates, gift cards, credit cards).
• Cancellations: cancel_reservation (including constraints like basic economy / travel insurance in the scenario text).
• Flight changes: update_reservation_flights for cabin changes, same-day or alternate dates, cheapest options, route or stopover preferences, refunds to original payment.
• Baggage: update_reservation_baggages after or alongside flight updates.
• Passengers: update_reservation_passengers (name/DOB changes on a reservation).
• Discovery / lookup: get_user_details, get_reservation_details, search_direct_flight before changing or rebooking.
• Price arithmetic: calculate for fare differences, refunds, or savings across options.
• Compensation / goodwill: send_certificate where scenarios require issuing credit.
• Escalation: transfer_to_human_agents when the user insists or policy blocks self-serve changes.
""".strip()

TASK_CONTEXT_RETAIL = """
• Identity: find_user_id_by_name_zip or find_user_id_by_email before order or profile actions.
• User profile: get_user_details; modify_user_address when delivery or account address must change.
• Catalog: list_all_product_types, get_product_details for variants (size, color, options) and compatibility.
• Order inspection: get_order_details across multiple orders when the user references items vaguely.
• Delivered orders: exchange_delivered_order_items or return_delivered_order_items with specific item_ids, new_item_ids, payment_method_id; scenarios often branch on confirmations or “if not available, do X instead.”
• Pending orders: modify_pending_order_items (swap variants), modify_pending_order_address, modify_pending_order_payment, cancel_pending_order.
• Counting / simple math: calculate when the user asks for tallies (e.g. number of product options) combined with catalog lookups.
• Escalation: transfer_to_human_agents when the workflow cannot be completed self-serve.
""".strip()

TASK_CONTEXT_BY_DOMAIN: dict[str, str] = {
    "telecom": TASK_CONTEXT_TELECOM,
    "telehealth": TASK_CONTEXT_TELEHEALTH,
    "airline": TASK_CONTEXT_AIRLINE,
    "retail": TASK_CONTEXT_RETAIL,
}
HUMAN_PROMPT = """
{message}

Domain Knowledge Base (wiki):
{wiki}

{task_context_block}Target Function:
{target_function}

Candidate Functions:
{candidate_functions}

Now, identify which candidate functions are neighbours of the Target Function based on the criteria already defined and return the response in the exact structured format:
- answer: list[bool]
- reason: list[str]
- is_root: bool
- is_root_reason: str
"""


# ---------------------------------------------------------------------
# LLM factory (openai or vllm)
# ---------------------------------------------------------------------
def make_llm(provider: str, model_name: str, temperature: float, base_url: str | None):
    rate_limiter = InMemoryRateLimiter(
        requests_per_second=0.1,
        check_every_n_seconds=0.1,
        max_bucket_size=10,
    )

    provider = provider.lower()

    if provider == "openai":
        if model_name not in {"gpt-4.1", "gpt-4o", "gpt-5", "gpt-5.1", "gpt-5.2"}:
            raise ValueError(
                "For provider 'openai', model must be one of: gpt-4.1, gpt-4o, gpt-5, gpt-5.1, gpt-5.2"
            )

        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            max_retries=2,
            rate_limiter=rate_limiter,
        )

    elif provider == "vllm":
        if not base_url:
            raise ValueError(
                "For provider 'vllm', you must supply --base-url (OpenAI-compatible endpoint)."
            )

        # Assumes an OpenAI-compatible endpoint exposed by vLLM.
        # Use VLLM_API_KEY or fall back to a dummy key if not needed.
        api_key = os.getenv("VLLM_API_KEY", "EMPTY")

        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            max_retries=2,
            timeout=900,
            base_url=base_url,
            api_key=api_key,
        )

    else:
        raise RuntimeError(f"Unsupported provider: {provider}")


def build_neighbour_chain(
    provider: str, model_name: str, temperature: float, base_url: str | None
):
    llm = make_llm(provider, model_name, temperature, base_url)
    model = llm.with_structured_output(IsNeighbourResponse)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", HUMAN_PROMPT),
        ]
    )

    # LangChain Runnable: dict -> IsNeighbourResponse
    chain = prompt | model
    return chain


# ---------------------------------------------------------------------
# Tau-bench tool collection
# ---------------------------------------------------------------------
def get_taubench_tools(skip=["think", "calculate", "transfert_to_agent"]):
    domain_names = [
        "airline",
        "retail",
        "telecom",
        "telehealth",
        "bank",
        "basketball",
        "movie",
        "restaurant",
        "school",
        "travel",
    ]
    tools_by_domain = defaultdict(list)

    for d_title, d_tools in zip(
        domain_names,
        [
            airline_tools,
            retail_tools,
            telecom_tools,
            telehealth_tools,
            bank_tools,
            basketball_tools,
            movie_tools,
            restaurant_tools,
            school_tools,
            travel_tools,
        ],
    ):
        for cls in d_tools.ALL_TOOLS:
            if cls.__name__.lower() in skip:
                print(f"Skipping tool: {cls.__name__}")
                continue
            tool = {
                "name": cls.__name__,
                "info": cls.get_info(),
            }
            tools_by_domain[d_title].append(tool)

    return tools_by_domain


# ---------------------------------------------------------------------
# Adjacency matrix builder – uses the chain directly
# ---------------------------------------------------------------------
def _format_task_context_block(task_context: Optional[str]) -> str:
    """Non-empty block inserted into HUMAN_PROMPT when task context is enabled."""
    if not task_context or not task_context.strip():
        return ""
    return (
        "Representative task categories for this domain (from benchmark-style test scenarios; "
        "use as soft guidance for realistic customer/agent follow-ups — the list is not exhaustive):\n"
        f"{task_context.strip()}\n\n"
    )


def build_adjacency_matrix(
    tools,
    wiki,
    neighbour_chain,
    task_context: Optional[str] = None,
):
    """
    tools: list[dict] from get_taubench_tools()[domain]
    neighbour_chain: LangChain runnable returning IsNeighbourResponse
    task_context: optional multi-line summary of typical domain tasks for the neighbour prompt (default: omit)
    """
    task_context_block = _format_task_context_block(task_context)
    results = {
        "tools": tools,
        "adjacency_matrix": [],  # list[list[bool]]
        "reason_matrix": [],  # list[list[str]]
        "is_root": [],  # list[bool]
        "is_root_reason": [],  # list[str]
    }
    expected_len = len(tools)
    for tool in tqdm(tools, desc="Finding neighbours"):
        result: IsNeighbourResponse = neighbour_chain.invoke(
            {
                "message": f"I have {expected_len} candidate functions, so I will expect {expected_len} boolean values and {expected_len} reasoning strings in the response.",
                "wiki": wiki,
                "task_context_block": task_context_block,
                "target_function": tool,
                "candidate_functions": tools,
            }
        )
        if len(result.answer) != expected_len or len(result.reason) != expected_len:
            print("Retrying due to length mismatch...")
            result = neighbour_chain.invoke(
                {
                    "message": f"You gave me {len(result.answer)} boolean values and {len(result.reason)} reasoning strings, I was expecting {expected_len} of each since I have {expected_len} candidate functions. Please try again and ensure the lengths match exactly.",
                    "wiki": wiki,
                    "task_context_block": task_context_block,
                    "target_function": tool,
                    "candidate_functions": tools,
                }
            )
        results["adjacency_matrix"].append(result.answer)
        results["reason_matrix"].append(result.reason)
        results["is_root"].append(result.is_root)
        results["is_root_reason"].append(result.is_root_reason)

    return results


# ---------------------------------------------------------------------
# Main CLI entrypoint
# ---------------------------------------------------------------------
def main(
    domains: list[str],
    provider: str,
    model_name: str,
    temperature: float,
    base_url: str | None,
    include_task_context: bool = False,
):
    # still set envs if some downstream code expects them
    os.environ["model_name"] = model_name
    os.environ["temperature"] = str(temperature)

    neighbour_chain = build_neighbour_chain(provider, model_name, temperature, base_url)

    tau_tools = get_taubench_tools()
    base_output_dir = os.path.join("output", "graphs", f"{provider}_{model_name}")
    os.makedirs(base_output_dir, exist_ok=True)

    for domain, tools in tau_tools.items():
        if domain not in domains:
            continue

        print(f"Building adjacency matrix for domain: {domain} with {len(tools)} tools")
        if domain == "airline":
            wiki = AIRLINE_WIKI
        elif domain == "retail":
            wiki = RETAIL_WIKI
        elif domain == "telecom":
            wiki = TELECOM_WIKI
        elif domain == "telehealth":
            wiki = TELEHEALTH_WIKI
        elif domain == "bank":
            wiki = BANK_WIKI
        elif domain == "basketball":
            wiki = BASKETBALL_WIKI
        elif domain == "movie":
            wiki = MOVIE_WIKI
        elif domain == "restaurant":
            wiki = RESTAURANT_WIKI
        elif domain == "school":
            wiki = SCHOOL_WIKI
        elif domain == "travel":
            wiki = TRAVEL_WIKI
        else:
            wiki = "No wiki available."

        task_context: Optional[str] = None
        if include_task_context:
            task_context = TASK_CONTEXT_BY_DOMAIN.get(domain)
            if task_context is not None and not str(task_context).strip():
                task_context = None

        results = build_adjacency_matrix(
            tools, wiki, neighbour_chain, task_context=task_context
        )

        out_path = os.path.join(
            base_output_dir,
            f"{domain}_adjacency_matrix_{temperature}.json",
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"Adjacency matrix for domain: {domain} saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build tool neighbour adjacency matrices using LLM."
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        type=str,
        default=["airline", "retail", "telecom", "telehealth"],
        help=(
            "List of domains to process (default: all four; also supports bank, basketball, "
            "movie, restaurant, school, travel)."
        ),
    )
    parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=["openai", "vllm"],
        help="LLM provider: openai | vllm (an OpenAI-compatible server).",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model name. For openai: gpt-4.1/gpt-4o/gpt-5.x; for vllm: any model name your server exposes.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature for the model.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL for OpenAI-compatible vLLM server (required when provider=vllm).",
    )
    parser.add_argument(
        "--include-task-context",
        action="store_true",
        default=False,
        help=(
            "If set, inject a short list of representative benchmark task categories for each domain "
            "into the neighbour-finding prompt (soft guidance). Default: off."
        ),
    )
    args = parser.parse_args()
    print(args)
    main(
        args.domains,
        args.provider,
        args.model,
        args.temperature,
        args.base_url,
        include_task_context=args.include_task_context,
    )
