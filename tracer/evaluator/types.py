"""Pydantic output types for the evaluator subproject."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CriterionResult(BaseModel):
    name: str
    passed: bool
    violation: bool  # convenience: == not passed
    reason: str
    raw_llm_output: Optional[Dict[str, Any]] = None
    layer: Optional[str] = None  # "deterministic" | "llm" | "hybrid"
    status: str = "evaluated"  # evaluated | inconclusive | error
    error: Optional[str] = None


class InstructionEvaluation(BaseModel):
    instruction: str
    instruction_index: (
        int  # index into instructions[]; -1 for the preference_instruction pass
    )
    is_preference_pass: bool
    goal_orientation: CriterionResult
    template: CriterionResult


class CategoryGroup(BaseModel):
    name: str
    description: str
    count: int
    examples: List[str]  # "task_id=X run=Y" labels


class CriterionStats(BaseModel):
    name: str
    violations: int
    total_evaluated: int
    rate: float  # violations / total_evaluated
    categories: List[CategoryGroup] = []


class TaskVerdict(BaseModel):
    task_id: int
    run: int
    user_id: str
    passed: bool
    violations: List[str]  # criterion names that failed


class EvaluationSummary(BaseModel):
    input_path: str
    domain: str
    total_tasks: int  # rows in the eval file (including errored)
    evaluated: int  # rows that were not failed-during-eval
    errored: int  # rows where the evaluator itself crashed
    passed: int  # tasks that passed all criteria
    failed: int  # tasks that failed at least one criterion
    pass_rate: float  # passed / evaluated
    per_criterion: Dict[str, CriterionStats]
    co_occurrence: Dict[str, int]  # e.g. "goal_oriented+template": 3
    good_tasks: List[TaskVerdict]
    bad_tasks: List[TaskVerdict]
    llm_summary: Optional[str] = None  # free-text insight from the LLM


class TaskEvaluation(BaseModel):
    task_id: int
    run: int
    user_id: str
    domain: str
    preference_instruction_eval: Optional[InstructionEvaluation] = (
        None  # sole source for criteria 1 & 2
    )
    solvability: CriterionResult  # task-level
    domain_violation: CriterionResult  # task-level
    overall_passed: bool
    overall_violations: List[str]  # names of failed criteria
    inconclusive: bool = False
    criterion_errors: List[str] = []
    attempt_history: List[Dict[str, Any]] = []
