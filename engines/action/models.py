"""
STORY FORGE — Phase 3 Physical Action & Temporal Evidence Models
================================================================
Machine-readable contracts for physical actions, kinematic pose,
human-object interactions (HOI), geometric relationships, temporal states,
causal evidence graphs, and fail-closed evidence verdicts.
"""

from __future__ import annotations
import hashlib
import json
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from py_visual_evidence.schema import BoundingBox


# ---------------------------------------------------------------------------
# Part 2: Action Taxonomy
# ---------------------------------------------------------------------------

class PhysicalActionType(str, Enum):
    """
    Domain-general physical action taxonomy for evidence verification.
    """
    HIT = "HIT"
    PUNCH = "PUNCH"
    KICK = "KICK"
    PUSH = "PUSH"
    PULL = "PULL"
    GRAB = "GRAB"
    HANDOVER = "HANDOVER"
    PICK_UP = "PICK_UP"
    PUT_DOWN = "PUT_DOWN"
    THROW = "THROW"
    CATCH = "CATCH"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    DRAW = "DRAW"
    SHEATHE = "SHEATHE"
    RAISE = "RAISE"
    LOWER = "LOWER"
    POINT = "POINT"
    WAVE = "WAVE"
    REACH = "REACH"
    HOLD = "HOLD"
    RELEASE = "RELEASE"
    BREAK = "BREAK"
    SNAP = "SNAP"
    STRIKE_WITH_OBJECT = "STRIKE_WITH_OBJECT"
    FALL = "FALL"
    RUN = "RUN"
    WALK = "WALK"


# ---------------------------------------------------------------------------
# Part 12: Verdicts & Explicit Failure Reasons
# ---------------------------------------------------------------------------

class ActionEvidenceVerdict(str, Enum):
    """Evidence verdict levels for physical action claims."""
    VERIFIED = "VERIFIED"
    CONTEXT = "CONTEXT"
    NO_VALID_VISUAL = "NO_VALID_VISUAL"


class ActionFailureReason(str, Enum):
    """
    Granular physical evidence failure reasons.
    Must never be collapsed into a generic failure string.
    """
    ACTION_NOT_OBSERVED = "ACTION_NOT_OBSERVED"
    ACTOR_NOT_CONFIRMED = "ACTOR_NOT_CONFIRMED"
    TARGET_NOT_CONFIRMED = "TARGET_NOT_CONFIRMED"
    OBJECT_NOT_CONFIRMED = "OBJECT_NOT_CONFIRMED"
    CONTACT_NOT_CONFIRMED = "CONTACT_NOT_CONFIRMED"
    STATE_TRANSITION_NOT_CONFIRMED = "STATE_TRANSITION_NOT_CONFIRMED"
    TEMPORAL_ORDER_INVALID = "TEMPORAL_ORDER_INVALID"
    INTERACTION_NOT_CONFIRMED = "INTERACTION_NOT_CONFIRMED"
    INSUFFICIENT_MOTION = "INSUFFICIENT_MOTION"
    OCCLUDED_ACTION = "OCCLUDED_ACTION"
    ACTION_NOT_VERIFIED_ACROSS_CUT = "ACTION_NOT_VERIFIED_ACROSS_CUT"
    CAUSAL_ORDER_VIOLATED = "CAUSAL_ORDER_VIOLATED"
    CAMERA_MOTION_CONFOUND = "CAMERA_MOTION_CONFOUND"


# ---------------------------------------------------------------------------
# Part 6: Geometric Relationships
# ---------------------------------------------------------------------------

class GeometricRelation(str, Enum):
    """Normalized geometric relationship between two entities."""
    NEAR = "NEAR"
    TOUCHING = "TOUCHING"
    OVERLAPPING = "OVERLAPPING"
    MOVING_TOWARD = "MOVING_TOWARD"
    MOVING_AWAY = "MOVING_AWAY"
    BETWEEN = "BETWEEN"
    INSIDE = "INSIDE"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    LEFT_OF = "LEFT_OF"
    RIGHT_OF = "RIGHT_OF"


class TimestampedRelation(BaseModel):
    """A verified geometric relationship at a given timestamp."""
    timestamp_sec: float
    frame_index: int
    entity_a: str
    entity_b: str
    relation: GeometricRelation
    distance: float
    iou: float = 0.0
    relative_velocity: float = 0.0
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Part 4: Pose / Body Kinematics
# ---------------------------------------------------------------------------

class Keypoint(BaseModel):
    """2D keypoint in normalized coordinates [0.0, 1.0]."""
    x: float
    y: float
    confidence: float = 0.0


class PoseKeypoints(BaseModel):
    """Standardized upper and lower body keypoints."""
    frame_index: int
    timestamp_sec: float
    track_id: int
    character_name: str
    nose: Optional[Keypoint] = None
    left_shoulder: Optional[Keypoint] = None
    right_shoulder: Optional[Keypoint] = None
    left_elbow: Optional[Keypoint] = None
    right_elbow: Optional[Keypoint] = None
    left_wrist: Optional[Keypoint] = None
    right_wrist: Optional[Keypoint] = None
    left_hip: Optional[Keypoint] = None
    right_hip: Optional[Keypoint] = None
    left_knee: Optional[Keypoint] = None
    right_knee: Optional[Keypoint] = None
    left_ankle: Optional[Keypoint] = None
    right_ankle: Optional[Keypoint] = None


class LimbKinematics(BaseModel):
    """Derived physical motion metrics for a limb."""
    limb_name: str  # e.g. "right_arm", "left_arm", "right_leg"
    extension_angle_deg: float  # e.g. elbow or knee angle
    wrist_velocity: Tuple[float, float] = (0.0, 0.0)
    wrist_speed: float = 0.0
    velocity_toward_target: float = 0.0
    distance_to_target: Optional[float] = None


# ---------------------------------------------------------------------------
# Part 5: Human-Object Interaction (HOI)
# ---------------------------------------------------------------------------

class HOIInteractionType(str, Enum):
    """Types of physical interactions between humans and objects."""
    NONE = "NONE"
    PROXIMITY_ONLY = "PROXIMITY_ONLY"  # Near, but not in possession
    HELD = "HELD"                      # Synchronized motion, sustained proximity
    TRANSFERRING = "TRANSFERRING"      # In transit between actors
    RELEASED = "RELEASED"              # Separating from actor
    DEFORMING = "DEFORMING"            # Structural breaking/bending under contact


class HOIState(BaseModel):
    """Human-Object Interaction state at a specific frame."""
    frame_index: int
    timestamp_sec: float
    actor_id: str
    object_id: str
    interaction_type: HOIInteractionType
    actor_hand_distance: float
    motion_correlation: float = 0.0  # Velocity vector correlation
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Part 1: Visual Action Assertion
# ---------------------------------------------------------------------------

class VisualActionAssertion(BaseModel):
    """
    Machine-readable declarative physical action hypothesis.
    Extends VisualAssertion requirements with explicit physical evidence constraints.
    """
    assertion_id: str
    actor: str
    action: PhysicalActionType
    target: Optional[str] = None
    object: Optional[str] = None
    required_entities: List[str] = Field(default_factory=list)
    required_motion: Optional[str] = None
    required_interaction: Optional[str] = None
    expected_target_response: Optional[str] = None
    expected_state_transition: Optional[Tuple[str, str]] = None
    temporal_order: List[str] = Field(default_factory=list)
    direct_visual_requirement: bool = True
    min_confidence: float = 0.65

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VisualActionAssertion:
        raw_action = str(data.get("action", "HOLD")).upper()
        # Normalization of synonyms
        action_map = {
            "PUNCHING": PhysicalActionType.PUNCH,
            "HITTING": PhysicalActionType.HIT,
            "KICKING": PhysicalActionType.KICK,
            "PUSHING": PhysicalActionType.PUSH,
            "PULLING": PhysicalActionType.PULL,
            "GRABBING": PhysicalActionType.GRAB,
            "HANDING": PhysicalActionType.HANDOVER,
            "HANDOVER": PhysicalActionType.HANDOVER,
            "PICKING_UP": PhysicalActionType.PICK_UP,
            "PUTTING_DOWN": PhysicalActionType.PUT_DOWN,
            "THROWING": PhysicalActionType.THROW,
            "CATCHING": PhysicalActionType.CATCH,
            "OPENING": PhysicalActionType.OPEN,
            "CLOSING": PhysicalActionType.CLOSE,
            "DRAWING": PhysicalActionType.DRAW,
            "SHEATHING": PhysicalActionType.SHEATHE,
            "RAISING": PhysicalActionType.RAISE,
            "LOWERING": PhysicalActionType.LOWER,
            "POINTING": PhysicalActionType.POINT,
            "WAVING": PhysicalActionType.WAVE,
            "REACHING": PhysicalActionType.REACH,
            "HOLDING": PhysicalActionType.HOLD,
            "RELEASING": PhysicalActionType.RELEASE,
            "BREAKING": PhysicalActionType.BREAK,
            "SNAPPING": PhysicalActionType.SNAP,
            "STRIKING": PhysicalActionType.HIT,
            "FALLING": PhysicalActionType.FALL,
            "RUNNING": PhysicalActionType.RUN,
            "WALKING": PhysicalActionType.WALK,
        }
        action_type = action_map.get(raw_action, None)
        if action_type is None:
            try:
                action_type = PhysicalActionType(raw_action)
            except ValueError:
                action_type = PhysicalActionType.HOLD

        req_entities = list(data.get("required_entities", []))
        if data.get("actor") and data["actor"] not in req_entities:
            req_entities.append(data["actor"])
        if data.get("target") and data["target"] not in req_entities:
            req_entities.append(data["target"])
        if data.get("object") and data["object"] not in req_entities:
            req_entities.append(data["object"])

        return cls(
            assertion_id=data.get("assertion_id", "act_001"),
            actor=data.get("actor", ""),
            action=action_type,
            target=data.get("target"),
            object=data.get("object"),
            required_entities=req_entities,
            required_motion=data.get("required_motion"),
            required_interaction=data.get("required_interaction"),
            expected_target_response=data.get("expected_target_response"),
            expected_state_transition=data.get("expected_state_transition"),
            temporal_order=data.get("temporal_order", []),
            direct_visual_requirement=data.get("direct_visual_requirement", True),
            min_confidence=float(data.get("min_confidence", 0.65)),
        )


# ---------------------------------------------------------------------------
# Part 7 & 8: Temporal State, Events & Causal Graph
# ---------------------------------------------------------------------------

class TemporalEvent(BaseModel):
    """A detected discrete physical micro-event in the timeline."""
    event_id: str
    name: str  # e.g. "approach", "contact", "reaction", "transfer", "break"
    timestamp_sec: float
    frame_index: int
    confidence: float
    entity_source: Optional[str] = None
    entity_target: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class CausalEdge(BaseModel):
    """Causal relationship: cause must precede effect with physical link."""
    cause_event_id: str
    effect_event_id: str
    min_time_delta_sec: float = 0.0
    max_time_delta_sec: float = 2.5
    verified: bool = False
    rejection_reason: Optional[str] = None


class CausalEvidenceGraph(BaseModel):
    """Directed Acyclic Graph of verified temporal events."""
    events: List[TemporalEvent] = Field(default_factory=list)
    edges: List[CausalEdge] = Field(default_factory=list)
    is_valid: bool = False
    violation_reason: Optional[str] = None

    def get_event(self, event_id: str) -> Optional[TemporalEvent]:
        for ev in self.events:
            if ev.event_id == event_id:
                return ev
        return None


# ---------------------------------------------------------------------------
# Part 16: Structured Evidence Trace & Final Result
# ---------------------------------------------------------------------------

class ActionEvidenceTrace(BaseModel):
    """Auditable chronological physical evidence log."""
    assertion_id: str
    action_type: PhysicalActionType
    actor: str
    target: Optional[str] = None
    object: Optional[str] = None
    timeline_events: List[Dict[str, Any]] = Field(default_factory=list)
    identity_confirmed: bool = False
    motion_confirmed: bool = False
    contact_confirmed: bool = False
    interaction_confirmed: bool = False
    temporal_order_confirmed: bool = False
    state_transition_confirmed: bool = False
    cut_continuity_confirmed: bool = True
    action_model_hypothesis: Optional[Dict[str, Any]] = None
    failure_reasons: List[ActionFailureReason] = Field(default_factory=list)
    explanation: str = ""


class ActionVerificationResult(BaseModel):
    """Authoritative physical evidence verification output."""
    assertion_id: str
    verdict: ActionEvidenceVerdict
    confidence: float
    is_verified: bool
    failure_reasons: List[ActionFailureReason] = Field(default_factory=list)
    primary_failure_reason: Optional[ActionFailureReason] = None
    trace: ActionEvidenceTrace
    lineage_hash: str

    @classmethod
    def compute_lineage_hash(
        cls,
        assertion: VisualActionAssertion,
        actor_id_hash: str,
        target_id_hash: str,
        object_id_hash: str,
        track_hash: str,
        motion_hash: str,
        causal_graph_hash: str,
        model_versions: Dict[str, str],
    ) -> str:
        """
        Cryptographic SHA-256 lineage hash over all upstream physical evidence stages.
        Invalidating any upstream stage automatically invalidates downstream verdict.
        """
        payload = {
            "assertion": assertion.model_dump(),
            "actor_id_hash": actor_id_hash,
            "target_id_hash": target_id_hash,
            "object_id_hash": object_id_hash,
            "track_hash": track_hash,
            "motion_hash": motion_hash,
            "causal_graph_hash": causal_graph_hash,
            "model_versions": model_versions,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def extract_track_boxes(track: Any) -> List[Tuple[float, int, BoundingBox]]:
    """
    Extracts a list of (timestamp_sec, frame_index, BoundingBox) tuples from an EntityTrack.
    Supports track.bounding_boxes being dicts, tuples, or custom objects.
    """
    pts: List[Tuple[float, int, BoundingBox]] = []
    bboxes = getattr(track, "bounding_boxes", [])
    if not bboxes and hasattr(track, "history"):
        bboxes = getattr(track, "history", [])

    for item in bboxes:
        if isinstance(item, dict):
            ts = float(item.get("timestamp", 0.0))
            f_idx = int(item.get("frame_index", int(ts * 24.0)))
            b = item.get("bbox")
            if isinstance(b, dict):
                b = BoundingBox(**b)
            if isinstance(b, BoundingBox):
                pts.append((ts, f_idx, b))
        elif isinstance(item, (tuple, list)):
            if len(item) == 2:
                first, b = item
                if isinstance(b, dict):
                    b = BoundingBox(**b)
                if isinstance(first, int):
                    pts.append((first / 24.0, first, b))
                else:
                    pts.append((float(first), int(float(first) * 24.0), b))
            elif len(item) == 3:
                b = item[2]
                if isinstance(b, dict):
                    b = BoundingBox(**b)
                pts.append((float(item[0]), int(item[1]), b))
    pts.sort(key=lambda x: x[0])
    return pts
