"""Orchestrator — aggregates TaskEvaluation records into a full evaluation report.

Usage:
    python -m evaluator.orchestrator --domain airline \\
        --eval-path output/evaluations/airline_test_eval.json
    python -m evaluator.orchestrator --eval-path ... --markdown-out report.md \\
        --eval-model gpt-4.1 --eval-model-provider openai

The orchestrator:
  1. Loads the `*_eval.json` written by evaluator/runner.py.
  2. Computes programmatic stats (pass rates, violation counts, co-occurrence).
  3. Builds a clear good-task / bad-task list.
  4. Optionally calls an LLM to categorize failure reasons into themes
     (one LLM call per criterion that has violations, plus one overall summary).
  5. Writes a summary JSON and optionally a human-readable Markdown report.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

import litellm

litellm.drop_params = True

from tracer.llm_utils import completion_with_retry
from tracer.prompts.in_domain_checker import SYSTEM_PROMPTS_BY_DOMAIN

from evaluator.prompts.orchestrator import (
    CATEGORIZE_SYSTEM_PROMPT,
    OVERALL_SUMMARY_SYSTEM_PROMPT,
    format_categorize_user_prompt,
    format_overall_summary_user_prompt,
)
from evaluator.types import (
    CategoryGroup,
    CriterionStats,
    EvaluationSummary,
    TaskVerdict,
)

# Canonical criterion names (display order)
CRITERIA = [
    "goal_oriented",
    "template",
    "solvable_by_ground_truth",
    "no_domain_violation",
]

CRITERION_LABELS = {
    "goal_oriented": "Goal-Oriented",
    "template": "Template (task + preference)",
    "solvable_by_ground_truth": "Solvable by Ground Truth",
    "no_domain_violation": "No Domain Violation",
}


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


def _collect_stats(
    records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition into: evaluated (good+bad), errored."""
    evaluated, errored = [], []
    for r in records:
        if r.get("failed", False) or r.get("inconclusive", False):
            errored.append(r)
        else:
            evaluated.append(r)
    return evaluated, errored


def _build_verdicts(
    evaluated: List[Dict[str, Any]],
) -> Tuple[List[TaskVerdict], List[TaskVerdict]]:
    good, bad = [], []
    for r in evaluated:
        v = TaskVerdict(
            task_id=r.get("task_id", -1),
            run=r.get("run", 0),
            user_id=r.get("user_id", ""),
            passed=r.get("overall_passed", False),
            violations=r.get("overall_violations", []),
        )
        (good if v.passed else bad).append(v)
    return good, bad


def _per_criterion_violations(
    bad: List[TaskVerdict],
    evaluated: List[Dict[str, Any]],
    total_evaluated: int,
) -> Dict[str, Dict[str, Any]]:
    """Counts and reasons for each criterion."""
    counts: Dict[str, int] = Counter()
    reasons: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # Collect violation counts and reasons from the evaluated records
    record_map = {(r["task_id"], r["run"]): r for r in evaluated}
    for v in bad:
        for crit in v.violations:
            counts[crit] += 1
            # Extract the reason from the raw record
            rec = record_map.get((v.task_id, v.run), {})
            reason = _extract_reason(rec, crit)
            reasons[crit].append(
                {
                    "task_id": v.task_id,
                    "run": v.run,
                    "reason": reason,
                }
            )

    result: Dict[str, Dict[str, Any]] = {}
    for crit in CRITERIA:
        result[crit] = {
            "name": crit,
            "violations": counts.get(crit, 0),
            "total_evaluated": total_evaluated,
            "rate": counts.get(crit, 0) / total_evaluated if total_evaluated else 0.0,
            "failure_entries": reasons.get(crit, []),
        }
    return result


def _extract_reason(record: Dict[str, Any], criterion: str) -> str:
    """Pull the evaluator's reason string for a given criterion from a task record."""
    if criterion in ("goal_oriented", "template"):
        # Check preference_instruction_eval first (most authoritative for template);
        # fall back to per_instruction[0] if absent.
        pref = record.get("preference_instruction_eval") or {}
        crit_key = "goal_orientation" if criterion == "goal_oriented" else "template"
        crit_data = pref.get(crit_key, {})
        if crit_data.get("reason"):
            return crit_data["reason"]
    elif criterion == "solvable_by_ground_truth":
        return record.get("solvability", {}).get("reason", "")
    elif criterion == "no_domain_violation":
        return record.get("domain_violation", {}).get("reason", "")
    return ""


def _co_occurrence(bad: List[TaskVerdict]) -> Dict[str, int]:
    counts: Counter = Counter()
    for v in bad:
        viols = sorted(v.violations)
        for size in range(2, len(viols) + 1):
            for combo in combinations(viols, size):
                counts["+".join(combo)] += 1
    return dict(counts.most_common())


# ---------------------------------------------------------------------------
# LLM categorization helpers
# ---------------------------------------------------------------------------


def _call_llm(
    system: str,
    user: str,
    model: str,
    provider: str,
    temperature: float,
    api_base: Optional[str],
) -> Optional[str]:
    try:
        res = completion_with_retry(
            model=model,
            custom_llm_provider=provider,
            api_base=api_base,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"    [LLM] call failed: {e}")
        return None


def _categorize_failures(
    criterion: str,
    failures: List[Dict[str, Any]],
    model: str,
    provider: str,
    temperature: float,
    api_base: Optional[str],
) -> List[CategoryGroup]:
    if not failures:
        return []
    print(f"  [LLM] categorizing {len(failures)} failures for '{criterion}' ...")
    user_prompt = format_categorize_user_prompt(
        criterion_name=criterion, failures=failures
    )
    raw = _call_llm(
        CATEGORIZE_SYSTEM_PROMPT, user_prompt, model, provider, temperature, api_base
    )
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        # Try to strip markdown code fences if present
        stripped = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            data = json.loads(stripped)
        except Exception:
            print(f"    [LLM] could not parse JSON for {criterion}")
            return []
    groups: List[CategoryGroup] = []
    for cat in data.get("categories", []):
        groups.append(
            CategoryGroup(
                name=cat.get("name", ""),
                description=cat.get("description", ""),
                count=int(cat.get("count", 0)),
                examples=cat.get("examples", []),
            )
        )
    return groups


def _generate_overall_summary(
    domain: str,
    stats_dict: Dict[str, Any],
    categories_by_criterion: Dict[str, List[Dict[str, Any]]],
    model: str,
    provider: str,
    temperature: float,
    api_base: Optional[str],
) -> Optional[str]:
    print("  [LLM] generating overall summary ...")
    user_prompt = format_overall_summary_user_prompt(
        domain=domain,
        stats=stats_dict,
        categories_by_criterion=categories_by_criterion,
    )
    return _call_llm(
        OVERALL_SUMMARY_SYSTEM_PROMPT,
        user_prompt,
        model,
        provider,
        temperature,
        api_base,
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _render_markdown(summary: EvaluationSummary) -> str:
    lines = []

    lines.append(f"# Evaluation Report")
    lines.append(f"")
    lines.append(f"**Input**: `{summary.input_path}`  ")
    lines.append(f"**Domain**: {summary.domain}")
    lines.append(f"")

    # Top-level numbers
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total rows in eval file | {summary.total_tasks} |")
    lines.append(f"| Evaluator errors (skipped) | {summary.errored} |")
    lines.append(f"| Evaluated tasks | {summary.evaluated} |")
    lines.append(
        f"| **Passed all criteria** | **{summary.passed} ({summary.pass_rate:.1%})** |"
    )
    lines.append(
        f"| Failed at least one criterion | {summary.failed} ({1 - summary.pass_rate:.1%}) |"
    )
    lines.append("")

    if summary.llm_summary:
        lines.append("## Overall Insight")
        lines.append("")
        lines.append(summary.llm_summary)
        lines.append("")

    # Per-criterion table
    lines.append("## Per-Criterion Violations")
    lines.append("")
    lines.append("| Criterion | Violations | Rate |")
    lines.append("|---|---|---|")
    for crit, cstats in summary.per_criterion.items():
        label = CRITERION_LABELS.get(crit, crit)
        lines.append(f"| {label} | {cstats.violations} | {cstats.rate:.1%} |")
    lines.append("")

    # Co-occurrence
    if summary.co_occurrence:
        lines.append("## Co-occurring Violations")
        lines.append("")
        lines.append("Tasks that failed multiple criteria simultaneously:")
        lines.append("")
        for combo, count in summary.co_occurrence.items():
            parts = " + ".join(CRITERION_LABELS.get(c, c) for c in combo.split("+"))
            lines.append(f"- **{parts}**: {count} task(s)")
        lines.append("")

    # Error categories per criterion
    any_categories = any(cs.categories for cs in summary.per_criterion.values())
    if any_categories:
        lines.append("## Error Categories")
        lines.append("")
        for crit, cstats in summary.per_criterion.items():
            if not cstats.categories:
                continue
            label = CRITERION_LABELS.get(crit, crit)
            lines.append(f"### {label}")
            lines.append("")
            for cat in cstats.categories:
                lines.append(f"**{cat.name}** ({cat.count} task(s))")
                lines.append(f": {cat.description}")
                if cat.examples:
                    lines.append(f"  — examples: {', '.join(cat.examples[:5])}")
                lines.append("")

    # Good tasks
    lines.append("## Good Tasks (passed all criteria)")
    lines.append("")
    if summary.good_tasks:
        for t in summary.good_tasks:
            lines.append(f"- task_id={t.task_id}  run={t.run}  user={t.user_id}")
    else:
        lines.append("_None — all evaluated tasks failed at least one criterion._")
    lines.append("")

    # Bad tasks
    lines.append("## Bad Tasks (failed one or more criteria)")
    lines.append("")
    if summary.bad_tasks:
        for t in summary.bad_tasks:
            viols = ", ".join(t.violations)
            lines.append(
                f"- task_id={t.task_id}  run={t.run}  user={t.user_id}  — **{viols}**"
            )
    else:
        lines.append("_None — all evaluated tasks passed._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------------------------


def orchestrate(
    eval_path: str,
    domain: str = "unknown",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.0,
    api_base: Optional[str] = None,
) -> EvaluationSummary:
    with open(eval_path, "r", encoding="utf-8") as f:
        records: List[Dict[str, Any]] = json.load(f)

    print(f"\n{'=' * 60}")
    print(f"Orchestrating: {eval_path}")
    print(f"{'=' * 60}")

    evaluated, errored = _collect_stats(records)
    good_tasks, bad_tasks = _build_verdicts(evaluated)

    total_evaluated = len(evaluated)
    passed = len(good_tasks)
    failed = len(bad_tasks)
    pass_rate = passed / total_evaluated if total_evaluated else 0.0

    # Per-criterion stats
    per_crit_raw = _per_criterion_violations(bad_tasks, evaluated, total_evaluated)
    co_occur = _co_occurrence(bad_tasks)

    print(
        f"\nStats: {total_evaluated} evaluated, {passed} passed ({pass_rate:.1%}), "
        f"{failed} failed, {len(errored)} errored during eval"
    )
    for crit in CRITERIA:
        raw = per_crit_raw[crit]
        print(f"  {crit}: {raw['violations']} violations ({raw['rate']:.1%})")

    # LLM categorization (optional — runs only when model is configured)
    use_llm = model is not None and provider is not None
    categories_by_criterion: Dict[str, List[Dict[str, Any]]] = {}
    criterion_stats: Dict[str, CriterionStats] = {}

    for crit in CRITERIA:
        raw = per_crit_raw[crit]
        failures = raw["failure_entries"]
        cat_groups: List[CategoryGroup] = []

        if use_llm and failures:
            cat_groups = _categorize_failures(
                criterion=crit,
                failures=failures,
                model=model,
                provider=provider,
                temperature=temperature,
                api_base=api_base,
            )
            categories_by_criterion[crit] = [g.model_dump() for g in cat_groups]

        criterion_stats[crit] = CriterionStats(
            name=crit,
            violations=raw["violations"],
            total_evaluated=total_evaluated,
            rate=raw["rate"],
            categories=cat_groups,
        )

    # Overall LLM summary
    llm_summary: Optional[str] = None
    if use_llm and bad_tasks:
        stats_dict = {
            "pass_rate": pass_rate,
            "passed": passed,
            "evaluated": total_evaluated,
            "per_criterion": {
                c: {"violations": s.violations, "rate": s.rate}
                for c, s in criterion_stats.items()
            },
        }
        llm_summary = _generate_overall_summary(
            domain=domain,
            stats_dict=stats_dict,
            categories_by_criterion=categories_by_criterion,
            model=model,
            provider=provider,
            temperature=temperature,
            api_base=api_base,
        )

    return EvaluationSummary(
        input_path=eval_path,
        domain=domain,
        total_tasks=len(records),
        evaluated=total_evaluated,
        errored=len(errored),
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        per_criterion=criterion_stats,
        co_occurrence=co_occur,
        good_tasks=good_tasks,
        bad_tasks=bad_tasks,
        llm_summary=llm_summary,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_config_defaults(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args():
    p = argparse.ArgumentParser(
        description="Aggregate evaluator results into a summary report."
    )
    p.add_argument("--config", default=None, help="Optional JSON config file.")
    p.add_argument(
        "--eval-path",
        required=False,
        default=None,
        help="Path to *_eval.json output from evaluator/runner.py.",
    )
    p.add_argument(
        "--domain",
        default=None,
        choices=sorted(SYSTEM_PROMPTS_BY_DOMAIN),
        help="Default: the domain the eval file is named after (<domain>_..._eval.json).",
    )
    p.add_argument("--output-path", default=None, help="Where to write summary JSON.")
    p.add_argument(
        "--markdown-out", default=None, help="Optional path for Markdown report."
    )
    p.add_argument(
        "--eval-model",
        default=None,
        help="LLM model for categorization (omit to skip).",
    )
    p.add_argument("--eval-model-provider", default="openai")
    p.add_argument("--eval-temperature", type=float, default=0.0)
    p.add_argument("--api-base", default=None)

    args_pre, _ = p.parse_known_args()
    if args_pre.config is not None:
        cfg = _load_config_defaults(args_pre.config)
        for action in p._actions:
            if action.dest != "config" and action.dest in cfg:
                action.default = cfg[action.dest]
    return p.parse_args()


def main():
    args = parse_args()

    if args.eval_path is None:
        print("Error: --eval-path is required (or set 'eval_path' in your config).")
        sys.exit(1)
    if args.domain is None:
        named = Path(args.eval_path).name.split("_")[0]
        if named not in SYSTEM_PROMPTS_BY_DOMAIN:
            print(
                "Error: --domain is required (the eval file isn't named <domain>_...)."
            )
            sys.exit(1)
        args.domain = named

    summary = orchestrate(
        eval_path=args.eval_path,
        domain=args.domain,
        model=args.eval_model,
        provider=args.eval_model_provider,
        temperature=args.eval_temperature,
        api_base=args.api_base,
    )

    # Write summary JSON
    eval_p = Path(args.eval_path)
    out_path = args.output_path or str(eval_p.with_name(eval_p.stem + "_summary.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2)
    print(f"\nSummary JSON saved to {out_path}")

    # Write Markdown report
    md_path = args.markdown_out
    if md_path:
        md_text = _render_markdown(summary)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"Markdown report saved to {md_path}")

    # Quick human-readable console summary
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(
        f"  Pass rate : {summary.pass_rate:.1%}  ({summary.passed}/{summary.evaluated})"
    )
    print(
        f"  Good tasks: {[f'task_id={t.task_id} run={t.run}' for t in summary.good_tasks]}"
    )
    print(f"  Bad tasks :")
    for t in summary.bad_tasks:
        print(f"    task_id={t.task_id} run={t.run}  violations={t.violations}")
    if summary.llm_summary:
        print(f"\nInsight:\n{summary.llm_summary}")


if __name__ == "__main__":
    main()
