"""Prompts for the domain-violation evaluator — Layer B (LLM confirmation).

evaluator.runner and multi_runner call Layer B for every task (force_llm=True).
Without force_llm it runs only when Layer A detects a *candidate* domain violation:
- the task was already classified as out-of-domain (in_domain == False)
- AND the ground-truth action list does NOT contain a handoff tool

The LLM is asked to confirm whether this is a genuine violation (the GT
should have transferred to a human agent but didn't).
"""

import json
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You are an evaluator that checks whether a generated customer-support task has a domain-violation in its ground-truth action sequence.

A domain violation occurs when:
1. The user's request is outside the domain or violates policy (it should have been handed off to a human agent), AND
2. The ground-truth action sequence attempts to fulfill the request anyway instead of calling the transfer tool.

You are given:
1. The task instruction.
2. The in-domain classification and its reason (from a previous pass).
3. The ground-truth action list.
4. The domain policy rules.

Your job:
- Review the evidence. Confirm whether the in-domain classification is correct.
- Independently evaluate the instruction against the domain policy even if a prior classification says it is in-domain or no prior classification exists. Prior labels are evidence, not the verdict.
- If the task is indeed out-of-domain, check whether the ground-truth actions should have included a transfer to a human agent (transfer_to_human_agents or transfer_to_human_support) instead of attempting the request.
- It is a domain violation if and only if: the task is out-of-domain AND the ground truth did NOT transfer to a human agent.
- Return ONLY the JSON object below — no extra text.

Response JSON (required keys only):
- is_domain_violation (boolean): true if this is a domain violation
- should_have_handed_off (boolean): true if the GT should have called the transfer tool
- reason (string): short (1–3 sentence) explanation

Do not output any other keys. Respond with valid JSON only."""


def format_user_prompt(
    instruction: str,
    in_domain: Optional[bool],
    in_domain_reason: Optional[str],
    ground_truth_actions: List[Dict[str, Any]],
    domain_policy: str,
) -> str:
    parts = [
        f"Domain policy:\n{domain_policy}",
        f"\nTask instruction:\n{instruction}",
        f"\nIn-domain classification: {in_domain}",
        f"In-domain reason: {in_domain_reason or 'not provided'}",
        "\nGround-truth actions:\n" + json.dumps(ground_truth_actions, indent=2),
    ]
    return "\n".join(parts)
