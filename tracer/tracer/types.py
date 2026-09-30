# Copyright Sierra

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel


class Persona(BaseModel):
    emotional_state: Literal[
        "angry",
        "stressed",
        "calm",
        "anxious",
        "confused",
        "impatient",
        "polite",
    ]
    urgency: Literal["low", "medium", "high"]
    communication_style: Literal[
        "brief",
        "detailed",
        "persistent",
        "cooperative",
        "demanding",
    ]


class TracerAgentOutput(BaseModel):
    """Final JSON emitted by the main task generator agent.

    `trace` is a list of TURNs: [[TURN1],[TURN2],...]. The generator must emit one
    instruction per TURN, each containing all required params needed to execute
    that TURN's tool calls. Emotional tone (`feeling`) is produced by a separate pass.
    `actions` is a flat list of ground-truth Action (name, kwargs).
    """

    user_id: str
    instructions: List[str]
    story: str
    actions: List["Action"]


class Action(BaseModel):
    name: str
    kwargs: Dict[str, Any]


# Type alias for list of Action (use where a list of Action is needed; Action itself is unchanged)
Actions = List[Action]


class GeneratedTaskCandidate(BaseModel):
    # Candidate produced by the generator agent from a tool trace
    user_id: str
    instructions: List[str]
    story: str
    feeling: str = ""
    action_trace: Any  # raw trace JSON
    actions: Actions = []  # list of Action (name, kwargs)
    attempt: int = 0
    verifier_feedback: Optional[str] = None


class VerificationReport(BaseModel):
    solved: bool
    termination_reason: str
    stop_seen: bool
    max_steps_hit: bool
    tool_errors: List[Dict[str, Any]]
    unknown_actions: List[Dict[str, Any]]
    critique: str
    transcript: List[Dict[str, Any]]
    actions: Actions = []  # list of Action (name, kwargs)


RESPOND_ACTION_NAME = "respond"
RESPOND_ACTION_FIELD_NAME = "content"


class Task(BaseModel):
    user_id: str
    actions: List[Action]
    instruction: str
    outputs: List[str]
    emotion_family: Optional[str] = None
    emotion_leaf: Optional[str] = None
    dimension_politeness: Optional[float] = None
    dimension_urgency: Optional[float] = None
    dimension_trust_in_agent: Optional[float] = None


class RewardOutputInfo(BaseModel):
    r_outputs: float
    outputs: Dict[str, bool]


class RewardActionInfo(BaseModel):
    r_actions: float
    gt_data_hash: str


class RewardResult(BaseModel):
    reward: float
    info: Union[RewardOutputInfo, RewardActionInfo]
    actions: List[Action]


class SolveResult(BaseModel):
    reward: float
    messages: List[Dict[str, Any]]
    info: Dict[str, Any]
    total_cost: Optional[float] = None
    usage_prompt_tokens: Optional[int] = None
    usage_completion_tokens: Optional[int] = None
    usage_total_tokens: Optional[int] = None
    usage_complete: bool = True


class EnvInfo(BaseModel):
    task: Optional[Task] = None
    source: Optional[str] = None
    user_cost: Optional[float] = None
    reward_info: Optional[RewardResult] = None


class EnvResponse(BaseModel):
    observation: str
    reward: float
    done: bool
    info: EnvInfo


class EnvResetResponse(BaseModel):
    observation: str
    info: EnvInfo
