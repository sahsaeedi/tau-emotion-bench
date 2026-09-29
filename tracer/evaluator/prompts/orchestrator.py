"""Prompts for the orchestrator's LLM-based error-categorization pass.

The orchestrator calls the LLM once per criterion (for criteria that have
violations). It sends a list of {task_id, run, reason} failure entries and
asks the LLM to group them into thematic categories so that users can see
*why* tasks are failing — not just *that* they are failing.

A second call synthesizes an overall free-text summary across all criteria.
"""

import json
from typing import Any, Dict, List

CATEGORIZE_SYSTEM_PROMPT = """You are a data quality analyst reviewing failures from a task-generation pipeline.

You will receive a list of evaluation failures for a single quality criterion. Each entry has:
- task_id and run: the task that failed
- reason: the evaluator's explanation for why the criterion was violated

Your job:
1. Read all the failure reasons carefully.
2. Group them into 2–6 thematic categories that capture the root causes.
3. For each category: give a short name (≤6 words), a one-sentence description, and cite the matching task IDs.
4. Return ONLY the JSON object below — no extra text.

Response JSON (required keys only):
{
  "categories": [
    {
      "name": "<short category name>",
      "description": "<one sentence describing the root cause>",
      "count": <number of entries in this category>,
      "examples": ["task_id=X run=Y", ...]
    }
  ],
  "summary": "<1–2 sentence overall observation about this criterion's failures>"
}

Do not output any other keys. Respond with valid JSON only."""


OVERALL_SUMMARY_SYSTEM_PROMPT = """You are a data quality analyst reviewing the results of an automated task-evaluation pipeline.

You will receive a structured summary of violations across four quality criteria:
1. goal_oriented — tasks should be fully specified; no back-and-forth needed
2. template — tasks should combine a concrete tool-calling request with a user preference
3. solvable_by_ground_truth — the ground-truth action sequence should work without errors
4. no_domain_violation — out-of-domain tasks must route to a handoff tool, not attempt execution

For each criterion that has violations, you will see the violation rate and the thematic categories of failures.

Your job: write a concise (3–5 sentence) executive summary that:
- States which criterion is the biggest source of failures
- Calls out the most impactful root causes
- Notes any patterns (e.g. failures clustering in a specific type of task or scenario)
- Ends with one actionable recommendation for improving the generator

Return only the summary as plain text. Do not include any JSON or headers."""


def format_categorize_user_prompt(
    criterion_name: str,
    failures: List[Dict[str, Any]],
) -> str:
    return (
        f"Criterion: {criterion_name}\n\n"
        f"Failures ({len(failures)} entries):\n" + json.dumps(failures, indent=2)
    )


def format_overall_summary_user_prompt(
    domain: str,
    stats: Dict[str, Any],
    categories_by_criterion: Dict[str, List[Dict[str, Any]]],
) -> str:
    parts = [f"Domain: {domain}\n"]
    parts.append(
        f"Pass rate: {stats['pass_rate']:.1%} ({stats['passed']}/{stats['evaluated']} tasks)\n"
    )
    parts.append("Violation rates per criterion:")
    for crit, cstats in stats.get("per_criterion", {}).items():
        rate = cstats.get("rate", 0)
        n = cstats.get("violations", 0)
        parts.append(f"  {crit}: {n} violations ({rate:.1%})")
    if categories_by_criterion:
        parts.append("\nThematic categories per failing criterion:")
        for crit, cats in categories_by_criterion.items():
            parts.append(f"\n{crit}:")
            for cat in cats:
                parts.append(
                    f"  - {cat['name']} ({cat['count']}): {cat['description']}"
                )
    return "\n".join(parts)
