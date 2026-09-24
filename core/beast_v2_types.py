"""
STORY FORGE — BEAST V2 Data Contracts & Proposition Evidence Models
================================================================================
Defines proposition-aware visual verification contracts for BEAST V2:
  - EvidenceType: DIRECT_EVIDENCE, OBJECT_PROP_EVIDENCE, ORIENTATION_BRIDGE,
                  CONTEXTUAL_EVIDENCE, IRONIC_CONTRAST
  - SourceEvidenceType: FILM, BOOK_TEXT, BTS, INTERVIEW, ARCHIVAL, ARTWORK, etc.
  - ActionCategory: Explicit extensible action taxonomy
  - BeastV2Decision: Structured verdict (ACCEPT_DIRECT, ACCEPT_OBJECT, etc.)
  - TemporalMicroInterval: Sub-interval [source_start, action_peak, source_end]
  - PropositionAlignmentBreakdown: Multi-vector alignment audit trail
  - BeastV2MatchResult: Production visual match verdict contract
  - FactPropositionCoverage: Short -> Fact -> Proposition coverage tracking
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_visual_types import NarrativeEra
from core.composition_models import ShotScale
from core.storyboard_types import VisualRole
from core.multi_fact_types import VisualProposition


class EvidenceType(str, Enum):
    """Semantic evidence role required or fulfilled by candidate visual."""
    DIRECT_EVIDENCE = "DIRECT_EVIDENCE"
    OBJECT_PROP_EVIDENCE = "OBJECT_PROP_EVIDENCE"
    ORIENTATION_BRIDGE = "ORIENTATION_BRIDGE"
    CONTEXTUAL_EVIDENCE = "CONTEXTUAL_EVIDENCE"
    IRONIC_CONTRAST = "IRONIC_CONTRAST"


class SourceEvidenceType(str, Enum):
    """Source authority and provenance category."""
    FILM = "FILM"
    BOOK_TEXT = "BOOK/TEXT"
    BTS = "BTS"
    INTERVIEW = "INTERVIEW"
    ARCHIVAL = "ARCHIVAL"
    ARTWORK = "ARTWORK"
    PHOTOGRAPH = "PHOTOGRAPH"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class ActionCategory(str, Enum):
    """Extensible canonical action categories for temporal grounding."""
    HOLD = "HOLD"
    LOOK = "LOOK"
    WALK = "WALK"
    RUN = "RUN"
    TALK = "TALK"
    ARGUE = "ARGUE"
    PLEAD = "PLEAD"
    ATTACK = "ATTACK"
    DEFEND = "DEFEND"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    DESTROY = "DESTROY"
    STRIKE = "STRIKE"
    CAST = "CAST"
    PICK_UP = "PICK_UP"
    DROP = "DROP"
    TURN = "TURN"
    ENTER = "ENTER"
    EXIT = "EXIT"
    REACT = "REACT"
    CRY = "CRY"
    LAUGH = "LAUGH"
    FIGHT = "FIGHT"
    TRANSFORM = "TRANSFORM"
    OTHER = "OTHER"


class BeastV2Decision(str, Enum):
    """BEAST V2 formal verdict on candidate asset."""
    ACCEPT_DIRECT = "ACCEPT_DIRECT"
    ACCEPT_OBJECT = "ACCEPT_OBJECT"
    ACCEPT_ORIENTATION = "ACCEPT_ORIENTATION"
    ACCEPT_CONTEXT = "ACCEPT_CONTEXT"
    ACCEPT_CONTRAST = "ACCEPT_CONTRAST"
    NO_VALID_VISUAL = "NO_VALID_VISUAL"


class TemporalPhase(str, Enum):
    """Phases inspected during multi-frame temporal action verification."""
    BEFORE = "BEFORE"
    DURING = "DURING"
    AFTER = "AFTER"


@dataclass
class TemporalMicroInterval:
    """
    Sub-second temporal micro-interval grounding where the action occurs.
    Replaces blind center-of-scene extraction with exact action alignment.
    """
    source_start: float
    source_end: float
    action_start: Optional[float] = None
    action_peak: Optional[float] = None
    action_end: Optional[float] = None
    duration: float = 0.0
    target_duration: float = 2.0

    def __post_init__(self):
        if self.duration == 0.0:
            self.duration = max(0.0, round(self.source_end - self.source_start, 3))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_start": round(self.source_start, 3),
            "source_end": round(self.source_end, 3),
            "action_start": round(self.action_start, 3) if self.action_start is not None else None,
            "action_peak": round(self.action_peak, 3) if self.action_peak is not None else None,
            "action_end": round(self.action_end, 3) if self.action_end is not None else None,
            "duration": round(self.duration, 3),
            "target_duration": round(self.target_duration, 3),
        }


@dataclass
class MultiFrameTemporalAnalysis:
    """
    Audit for an individual temporal inspection phase (BEFORE, DURING, AFTER).
    """
    phase: TemporalPhase
    timestamp: float
    subjects_detected: List[str] = field(default_factory=list)
    objects_detected: List[str] = field(default_factory=list)
    action_detected: Optional[str] = None
    action_category: ActionCategory = ActionCategory.OTHER
    action_state: str = "STATIC"  # "PREPARATION", "PEAK_IMPACT", "AFTERMATH", "REACTION_ONLY", "STATIC"
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "timestamp": round(self.timestamp, 3),
            "subjects_detected": self.subjects_detected,
            "objects_detected": self.objects_detected,
            "action_detected": self.action_detected,
            "action_category": self.action_category.value,
            "action_state": self.action_state,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class PropositionAlignmentBreakdown:
    """
    Multi-criteria proposition alignment scoring vector.
    Gating failures trigger immediate disqualification rather than blind averaging.
    """
    subject_alignment: float = 0.0               # 0.0 - 100.0
    action_alignment: float = 0.0                # 0.0 - 100.0
    object_alignment: float = 0.0                # 0.0 - 100.0
    context_alignment: float = 0.0               # 0.0 - 100.0
    temporal_alignment: float = 0.0              # 0.0 - 100.0
    visual_role_alignment: float = 0.0           # 0.0 - 100.0
    source_evidence_compatibility: float = 0.0   # 0.0 - 100.0
    contradiction_penalty: float = 0.0          # Subtracted penalty
    composite_score: float = 0.0                 # 0.0 - 100.0 final score
    gating_passed: bool = True
    gating_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_alignment": round(self.subject_alignment, 2),
            "action_alignment": round(self.action_alignment, 2),
            "object_alignment": round(self.object_alignment, 2),
            "context_alignment": round(self.context_alignment, 2),
            "temporal_alignment": round(self.temporal_alignment, 2),
            "visual_role_alignment": round(self.visual_role_alignment, 2),
            "source_evidence_compatibility": round(self.source_evidence_compatibility, 2),
            "contradiction_penalty": round(self.contradiction_penalty, 2),
            "composite_score": round(self.composite_score, 2),
            "gating_passed": self.gating_passed,
            "gating_failures": self.gating_failures,
        }


@dataclass
class BeastV2MatchResult:
    """
    Structured outcome of candidate evaluation against a VisualProposition.
    """
    candidate_id: str
    asset_id: str
    source: str                                                # "MOVIE_ARCHIVE", "ASSET_ACQUISITION", "CLOUD_REGISTRY"
    source_start: float
    source_end: float
    action_start: Optional[float] = None
    action_peak: Optional[float] = None
    action_end: Optional[float] = None
    evidence_type: EvidenceType = EvidenceType.DIRECT_EVIDENCE
    source_evidence_type: SourceEvidenceType = SourceEvidenceType.FILM
    visual_role: VisualRole = VisualRole.DIRECT_EVIDENCE
    decision: BeastV2Decision = BeastV2Decision.NO_VALID_VISUAL
    alignment_scores: Optional[PropositionAlignmentBreakdown] = None
    contradictions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    verification_metadata: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "asset_id": self.asset_id,
            "source": self.source,
            "source_start": round(self.source_start, 3),
            "source_end": round(self.source_end, 3),
            "action_start": round(self.action_start, 3) if self.action_start is not None else None,
            "action_peak": round(self.action_peak, 3) if self.action_peak is not None else None,
            "action_end": round(self.action_end, 3) if self.action_end is not None else None,
            "evidence_type": self.evidence_type.value,
            "source_evidence_type": self.source_evidence_type.value,
            "visual_role": self.visual_role.value if isinstance(self.visual_role, VisualRole) else str(self.visual_role),
            "decision": self.decision.value,
            "alignment_scores": self.alignment_scores.to_dict() if self.alignment_scores else None,
            "contradictions": self.contradictions,
            "confidence": round(self.confidence, 2),
            "verification_metadata": self.verification_metadata,
            "reason": self.reason,
        }


@dataclass
class FactPropositionCoverage:
    """
    Tracks hierarchical visual coverage:
    Short -> Fact -> Proposition -> Visual Segment.
    """
    short_id: str
    fact_id: str
    proposition_id: str
    covered: bool = False
    decision: BeastV2Decision = BeastV2Decision.NO_VALID_VISUAL
    match_result: Optional[BeastV2MatchResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "short_id": self.short_id,
            "fact_id": self.fact_id,
            "proposition_id": self.proposition_id,
            "covered": self.covered,
            "decision": self.decision.value,
            "match_result": self.match_result.to_dict() if self.match_result else None,
        }
