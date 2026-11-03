"""Independent research package for first-board right-tail policies."""

from .contracts import (
    CONTROL_RULE,
    TRIGGER_RULES,
    EventRecord,
    ExitResult,
    FillResult,
    LabelRecord,
    RuleUnavailable,
    TriggerCandidate,
    make_candidate_id,
    make_event_id,
)
from .dataset import DecisionSample, make_decision_id
from .event_policy import EventPolicyConfig
from .model import ModelConfig
from .splits import DEFAULT_FOLDS
from .walkforward import WalkforwardResult, run_model_walkforward

RESEARCH_STAGE = "M3-EVENT"

__all__ = [
    "CONTROL_RULE",
    "DEFAULT_FOLDS",
    "RESEARCH_STAGE",
    "TRIGGER_RULES",
    "DecisionSample",
    "EventPolicyConfig",
    "EventRecord",
    "ExitResult",
    "FillResult",
    "LabelRecord",
    "ModelConfig",
    "RuleUnavailable",
    "TriggerCandidate",
    "WalkforwardResult",
    "make_candidate_id",
    "make_decision_id",
    "make_event_id",
    "run_model_walkforward",
]
