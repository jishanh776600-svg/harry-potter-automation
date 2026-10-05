"""
Domain-Agnostic Visual Evidence & Assertion Schema
Defines the machine-readable contracts for visual assertions, entity grounding,
kinematic trajectories, state transitions, crop verification, and verdicts.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


class EvidenceVerdict(str, Enum):
    PASS = "PASS"
    NO_REQUIRED_ENTITY = "NO_REQUIRED_ENTITY"
    CHARACTER_MISMATCH = "CHARACTER_MISMATCH"
    OBJECT_MISMATCH = "OBJECT_MISMATCH"
    ACTION_ABSENT = "ACTION_ABSENT"
    RELATIONSHIP_ABSENT = "RELATIONSHIP_ABSENT"
    STATE_TRANSITION_ABSENT = "STATE_TRANSITION_ABSENT"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    CAUSAL_VIOLATION = "CAUSAL_VIOLATION"
    CROP_SUBJECT_LOST = "CROP_SUBJECT_LOST"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SHOT_BOUNDARY_CONFLICT = "SHOT_BOUNDARY_CONFLICT"


class BoundingBox(BaseModel):
    """Normalized [0.0, 1.0] bounding box: x, y, width, height."""
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., ge=0.0, le=1.0)
    h: float = Field(..., ge=0.0, le=1.0)

    @property
    def x_max(self) -> float:
        return round(min(1.0, self.x + self.w), 6)

    @property
    def y_max(self) -> float:
        return round(min(1.0, self.y + self.h), 6)

    @property
    def centroid(self) -> Tuple[float, float]:
        return (round(self.x + self.w / 2.0, 6), round(self.y + self.h / 2.0, 6))

    @property
    def area(self) -> float:
        return round(self.w * self.h, 6)

    def to_pixels(self, img_w: int, img_h: int) -> Tuple[int, int, int, int]:
        px_x = int(self.x * img_w)
        px_y = int(self.y * img_h)
        px_w = int(self.w * img_w)
        px_h = int(self.h * img_h)
        return px_x, px_y, px_w, px_h

    def intersection(self, other: BoundingBox) -> Optional[BoundingBox]:
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(self.x_max, other.x_max)
        iy2 = min(self.y_max, other.y_max)
        if ix2 > ix1 and iy2 > iy1:
            return BoundingBox(x=ix1, y=iy1, w=ix2 - ix1, h=iy2 - iy1)
        return None

    def iou(self, other: BoundingBox) -> float:
        inter = self.intersection(other)
        if inter is None:
            return 0.0
        inter_area = inter.area
        union_area = self.area + other.area - inter_area
        return inter_area / union_area if union_area > 0 else 0.0


class EntitySpec(BaseModel):
    """Specification of an entity required by an assertion."""
    name: str
    role: str = "subject"  # "subject", "object", "recipient", "secondary"
    description: Optional[str] = None
    forbidden: bool = False
    min_confidence: float = 0.35


class StateTransitionSpec(BaseModel):
    """Specification of a physical state transition (e.g. INTACT -> SHATTERED)."""
    initial_state: str
    final_state: str
    transition_nature: str = "structural"  # "structural", "kinematic", "spatial"
    min_disruption_threshold: float = 1.50


class CropSpec(BaseModel):
    """Specification for target vertical crop validation."""
    aspect_ratio: str = "9:16"
    safe_margin_top: float = 0.10
    safe_margin_bottom: float = 0.22
    safe_margin_horizontal: float = 0.05
    min_retained_subject_area: float = 0.70
    allow_scale_adjustment: bool = True
    max_scale_down: float = 0.45
    allow_letterbox: bool = False
    min_evidence_preservation_score: float = 0.65


class VisualAssertion(BaseModel):
    """Machine-readable visual hypothesis to verify against video footage."""
    assertion_id: str
    source_script_line: str
    context_before: Optional[str] = None
    context_current: Optional[str] = None
    context_after: Optional[str] = None
    subject: EntitySpec
    action: str
    object: Optional[EntitySpec] = None
    recipient: Optional[EntitySpec] = None
    secondary_entities: List[EntitySpec] = Field(default_factory=list)
    location: Optional[str] = None
    required_relationship: Optional[List[str]] = None
    expected_state_transition: Optional[StateTransitionSpec] = None
    temporal_requirements: Optional[Dict[str, Any]] = None
    causal_sequence_index: Optional[int] = None
    direct_visual_requirement: bool = True
    forbidden_visuals: List[str] = Field(default_factory=list)
    confidence_threshold: float = 0.65
    crop_spec: CropSpec = Field(default_factory=CropSpec)


class GroundedEntity(BaseModel):
    """An entity detected on a keyframe."""
    entity_name: str
    role: str
    bbox: BoundingBox
    confidence: float
    frame_index: int
    timestamp_sec: float


class TrajectoryPoint(BaseModel):
    """Spatio-temporal position of an entity at a specific frame."""
    frame_index: int
    timestamp_sec: float
    bbox: BoundingBox
    centroid: Tuple[float, float]
    velocity: Tuple[float, float] = (0.0, 0.0)


class EntityTrajectory(BaseModel):
    """Temporal trajectory of an entity across multiple frames."""
    entity_name: str
    role: str
    points: List[TrajectoryPoint] = Field(default_factory=list)

    @property
    def peak_velocity(self) -> float:
        vels = [((p.velocity[0] ** 2) + (p.velocity[1] ** 2)) ** 0.5 for p in self.points]
        return max(vels, default=0.0)

    @property
    def mean_velocity(self) -> float:
        vels = [((p.velocity[0] ** 2) + (p.velocity[1] ** 2)) ** 0.5 for p in self.points]
        return sum(vels) / len(vels) if vels else 0.0


class ActionResult(BaseModel):
    action_name: str
    detected: bool
    confidence: float
    peak_metric_value: float
    threshold_used: float
    details: Dict[str, Any] = Field(default_factory=dict)


class StateTransitionResult(BaseModel):
    detected: bool
    initial_state_metric: float
    final_state_metric: float
    disruption_ratio: float
    details: Dict[str, Any] = Field(default_factory=dict)


class CropVerificationResult(BaseModel):
    aspect_ratio: str
    crop_window: Dict[str, int]
    retained_subject_ratio: float
    inside_safe_zone: bool
    passed: bool
    rejection_reason: Optional[str] = None
    crop_strategy: str = "subject_aware_horizontal"
    subject_retention: float = 1.0
    required_entity_retention: Dict[str, float] = Field(default_factory=dict)
    relationship_retention: float = 1.0
    crop_evidence_preserved: bool = True
    crop_failure_reason: Optional[str] = None


class ObservationEvidence(BaseModel):
    """Comprehensive machine-readable proof of actual video inspection."""
    assertion_id: str
    video_path: str
    time_range: Tuple[float, float]
    shot_count: int
    parent_candidate_interval: Optional[Tuple[float, float]] = None
    sub_shot_id: Optional[str] = None
    sub_shot_start: Optional[float] = None
    sub_shot_end: Optional[float] = None
    sub_shot_index: Optional[int] = None
    contains_internal_cut: bool = False
    grounded_entities: List[GroundedEntity] = Field(default_factory=list)
    trajectories: Dict[str, EntityTrajectory] = Field(default_factory=dict)
    action_result: Optional[ActionResult] = None
    state_transition_result: Optional[StateTransitionResult] = None
    relationship_verified: bool = False
    relationship_summary: str = ""
    causal_order_passed: bool = True
    crop_result: Optional[CropVerificationResult] = None
    verdict: EvidenceVerdict
    rejection_reason: Optional[str] = None
    confidence: float
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp_iso: str

