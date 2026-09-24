"""
STORY FORGE — Visual Evidence Validation Data Models
=====================================================
Defines strongly-typed data contracts for proposition-level video evidence validation:
  - EvidenceClass: DIRECT, CONTEXT, NO_VALID_VISUAL
  - EvidenceRejectionReason: Canonical human-readable rejection reasons
  - TemporalState: BEFORE, ONSET, DURING, AFTER, UNCERTAIN
  - ObservedProposition: Ground-truth visual observation extracted from video frames
  - EvidenceScore: Fine-grained component scores with hard gate veto tracking
  - EvidenceValidatorConfig: Configurable thresholds for subject, action, object, and context
  - EvidenceValidationResult: Immutable audit result consumed by Editorial Planner
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set


class EvidenceClass(str, Enum):
    """
    Three canonical evidence classes for editorial acceptance:
    - DIRECT: The footage visibly demonstrates the narrated proposition.
    - CONTEXT: The footage establishes relevant character/place/object/scene
               but does NOT literally demonstrate the claim.
    - NO_VALID_VISUAL: The available footage does not provide sufficiently
                       reliable evidence.
    """
    DIRECT = "DIRECT"
    CONTEXT = "CONTEXT"
    NO_VALID_VISUAL = "NO_VALID_VISUAL"


class EvidenceRejectionReason(str, Enum):
    """
    Human-readable rejection reasons for candidate video intervals.
    """
    ACTION_MISMATCH = "ACTION_MISMATCH"
    OBJECT_MISSING = "OBJECT_MISSING"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    BEFORE_PHASE_ONLY = "BEFORE_PHASE_ONLY"
    AFTER_PHASE_ONLY = "AFTER_PHASE_ONLY"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    TEMPORAL_STATE_UNCERTAIN = "TEMPORAL_STATE_UNCERTAIN"
    DIRECT_EVIDENCE_INSUFFICIENT = "DIRECT_EVIDENCE_INSUFFICIENT"
    IMAGE_NOT_PERMITTED = "IMAGE_NOT_PERMITTED"
    INTERVAL_EXCEEDED = "INTERVAL_EXCEEDED"
    NONE = "NONE"


class TemporalState(str, Enum):
    """
    Action temporal phase observed in the video interval.
    """
    BEFORE = "BEFORE"
    ONSET = "ONSET"
    DURING = "DURING"
    AFTER = "AFTER"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class ObservedProposition:
    """
    Actual visual evidence observed from analyzing representative frames
    (beginning, middle, end, transitions) of a candidate video interval.
    """
    subject: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    context: Optional[str] = None
    temporal_state: TemporalState = TemporalState.UNCERTAIN
    detected_subjects: List[str] = field(default_factory=list)
    detected_actions: List[str] = field(default_factory=list)
    detected_objects: List[str] = field(default_factory=list)
    detected_contexts: List[str] = field(default_factory=list)
    frame_observations: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "action": self.action,
            "object": self.object,
            "context": self.context,
            "temporal_state": self.temporal_state.value,
            "detected_subjects": self.detected_subjects,
            "detected_actions": self.detected_actions,
            "detected_objects": self.detected_objects,
            "detected_contexts": self.detected_contexts,
            "frame_observations": self.frame_observations,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class EvidenceScore:
    """
    Component-level alignment scores [0.0 - 1.0].
    Action and Object failures act as primary vetoes.
    """
    subject_alignment: float = 0.0
    action_alignment: float = 0.0
    object_alignment: float = 0.0
    context_alignment: float = 0.0
    temporal_alignment: float = 0.0
    composite_score: float = 0.0
    passed_gates: bool = True
    vetoes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_alignment": round(self.subject_alignment, 3),
            "action_alignment": round(self.action_alignment, 3),
            "object_alignment": round(self.object_alignment, 3),
            "context_alignment": round(self.context_alignment, 3),
            "temporal_alignment": round(self.temporal_alignment, 3),
            "composite_score": round(self.composite_score, 3),
            "passed_gates": self.passed_gates,
            "vetoes": self.vetoes,
        }


@dataclass
class EvidenceValidatorConfig:
    """
    Configurable evaluation thresholds.
    """
    min_subject_threshold: float = 0.70
    min_action_threshold: float = 0.75
    min_object_threshold: float = 0.70
    min_context_threshold: float = 0.60
    min_composite_threshold: float = 0.70
    required_temporal_state: TemporalState = TemporalState.DURING
    max_shot_duration: float = 1.50
    min_micro_interval_duration: float = 0.50
    default_framing: str = "HYBRID_MODERATE_CROP"


@dataclass
class EvidenceValidationResult:
    """
    Structured outcome of the proposition-level video evidence validation.
    """
    candidate_id: str
    asset_id: str
    proposition_id: str
    evidence_class: EvidenceClass
    is_valid: bool
    rejection_reasons: List[EvidenceRejectionReason] = field(default_factory=list)
    primary_rejection_reason: Optional[EvidenceRejectionReason] = None
    rejection_explanation: str = ""
    expected_proposition: Optional[Dict[str, Any]] = None
    observed_proposition: Optional[ObservedProposition] = None
    scores: Optional[EvidenceScore] = None
    source_interval: Tuple[float, float] = (0.0, 0.0)
    validated_interval: Tuple[float, float] = (0.0, 0.0)
    validated_duration: float = 0.0
    temporal_state: TemporalState = TemporalState.UNCERTAIN
    framing: str = "HYBRID_MODERATE_CROP"
    audit_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "asset_id": self.asset_id,
            "proposition_id": self.proposition_id,
            "evidence_class": self.evidence_class.value,
            "is_valid": self.is_valid,
            "rejection_reasons": [r.value for r in self.rejection_reasons],
            "primary_rejection_reason": self.primary_rejection_reason.value if self.primary_rejection_reason else None,
            "rejection_explanation": self.rejection_explanation,
            "expected_proposition": self.expected_proposition,
            "observed_proposition": self.observed_proposition.to_dict() if self.observed_proposition else None,
            "scores": self.scores.to_dict() if self.scores else None,
            "source_interval": (round(self.source_interval[0], 3), round(self.source_interval[1], 3)),
            "validated_interval": (round(self.validated_interval[0], 3), round(self.validated_interval[1], 3)),
            "validated_duration": round(self.validated_duration, 3),
            "temporal_state": self.temporal_state.value,
            "framing": self.framing,
            "audit_metadata": self.audit_metadata,
        }
