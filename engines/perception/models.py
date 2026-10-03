"""
STORY FORGE — Absolute Monster Perception Data Models (Phase 2)
===============================================================
Defines strongly typed, serializable schemas for:
  - CharacterIdentity: Multi-exemplar reference identity records with face embeddings
  - IdentityMatchStatus: Graduated certainty states (FACE_CONFIRMED to UNKNOWN)
  - IdentityMatchResult: Result of facial/body matching against the Character Bank
  - FaceDetection: Face bounding boxes, landmarks, quality, and embeddings
  - VisualObject: Grounded props (wands, swords, hats, etc.) with state and optional mask
  - EntityTrack: Persistent spatio-temporal track across frames with CMC and Re-ID history
  - EntityTimeline: Per-clip structured timeline consumed by action/temporal verifiers
  - PerceptionLineage: Cryptographic lineage and version tracking for perception evidence
"""

from __future__ import annotations
import hashlib
import json
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field


class IdentityMatchStatus(str, Enum):
    """
    Graduated certainty states for character identity perception.
    Preserves strict uncertainty without forcing false identity guesses.
    """
    FACE_CONFIRMED = "FACE_CONFIRMED"                     # High-confidence face embedding match above threshold
    FACE_PARTIAL = "FACE_PARTIAL"                         # Partial/angled/low-res face, moderate confidence
    BODY_CONTEXT_SUPPORTED = "BODY_CONTEXT_SUPPORTED"     # Supported by attire/body context following confirmed face
    TRACKED_FROM_PRIOR = "TRACKED_FROM_PRIOR"             # Active track propagated from prior confirmed identity
    UNKNOWN = "UNKNOWN"                                   # Insufficient evidence, low similarity, or lookalike ambiguity


class IdentityRejectionReason(str, Enum):
    """
    Canonical rejection reasons when character identity cannot be confirmed.
    """
    SIMILARITY_BELOW_THRESHOLD = "SIMILARITY_BELOW_THRESHOLD"
    AMBIGUOUS_MARGIN_RUNNER_UP = "AMBIGUOUS_MARGIN_RUNNER_UP"
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    HEAVILY_OCCLUDED_OR_BACK_FACING = "HEAVILY_OCCLUDED_OR_BACK_FACING"
    TRACK_DISCONTINUITY = "TRACK_DISCONTINUITY"
    LOW_DETECTION_CONFIDENCE = "LOW_DETECTION_CONFIDENCE"
    CHARACTER_NOT_IN_BANK = "CHARACTER_NOT_IN_BANK"
    NONE = "NONE"


class CharacterIdentity(BaseModel):
    """
    Story Forge character identity record.
    Maintains multiple reference exemplars across movies, lighting, expressions, and angles.
    """
    character_id: str = Field(..., description="Unique canonical identifier, e.g. 'char_harry_potter'")
    canonical_name: str = Field(..., description="Full canonical character name, e.g. 'Harry Potter'")
    aliases: List[str] = Field(default_factory=list, description="Common aliases, e.g. ['harry', 'the boy who lived']")
    face_embeddings: List[List[float]] = Field(
        default_factory=list,
        description="List of 512-dim L2-normalized ArcFace/OpenCLIP embedding vectors"
    )
    reference_frames: List[str] = Field(
        default_factory=list,
        description="Frame identifiers or timestamps from which exemplars were drawn"
    )
    reference_face_crops: List[str] = Field(
        default_factory=list,
        description="Relative file paths or identifiers of reference face crops"
    )
    costume_descriptors: List[str] = Field(
        default_factory=list,
        description="Attire features, e.g. ['gryffindor robes', 'red-and-gold scarf']"
    )
    visual_descriptors: List[str] = Field(
        default_factory=list,
        description="Visual attributes, e.g. ['round spectacles', 'lightning bolt scar', 'black messy hair']"
    )
    source_movie_ids: List[int] = Field(
        default_factory=list,
        description="List of movie numbers (1..8) represented in exemplars"
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Base confidence in reference exemplars")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Metadata on exemplar extraction and bank version")

    def compute_embedding_hash(self) -> str:
        """Computes deterministic SHA256 of all stored embeddings for lineage verification."""
        hasher = hashlib.sha256()
        hasher.update(self.character_id.encode("utf-8"))
        for emb in self.face_embeddings:
            hasher.update(bytearray(json.dumps([round(x, 5) for x in emb]).encode("utf-8")))
        return hasher.hexdigest()[:16]


class IdentityMatchResult(BaseModel):
    """
    Result of comparing an observed face/person against the Character Bank.
    """
    matched_character_id: Optional[str] = None
    canonical_name: Optional[str] = None
    status: IdentityMatchStatus = IdentityMatchStatus.UNKNOWN
    confidence: float = 0.0
    similarity_score: float = 0.0
    runner_up_id: Optional[str] = None
    runner_up_similarity: float = 0.0
    margin: float = 0.0
    rejection_reason: IdentityRejectionReason = IdentityRejectionReason.NONE
    explanation: str = ""


from py_visual_evidence.schema import BoundingBox


class FaceDetection(BaseModel):
    """
    Observed face candidate in a video frame.
    """
    face_id: str
    bbox: BoundingBox = Field(..., description="Normalized bounding box (x, y, w, h)")
    confidence: float = Field(..., ge=0.0, le=1.0)
    landmarks: Optional[Dict[str, List[float]]] = None
    crop_quality: float = Field(1.0, ge=0.0, le=1.0, description="Sharpness / resolution score")
    embedding: Optional[List[float]] = None


class VisualObject(BaseModel):
    """
    Observed physical object / prop in a video frame.
    """
    object_id: str
    label: str = Field(..., description="Canonical prop label, e.g. 'elder_wand', 'sorting_hat'")
    aliases: List[str] = Field(default_factory=list)
    bbox: BoundingBox = Field(..., description="Normalized bounding box (x, y, w, h)")
    mask: Optional[List[List[int]]] = Field(None, description="Optional 2D binary segmentation mask or polygon")
    confidence: float = Field(..., ge=0.0, le=1.0)
    track_id: Optional[int] = None
    state: str = Field("INTACT", description="Physical state: INTACT, BROKEN, HELD, PLACED, UNCERTAIN")
    timestamp: float = 0.0
    source_movie: Optional[int] = None
    source_shot: Optional[str] = None


class EntityTrack(BaseModel):
    """
    Persistent spatio-temporal entity trajectory across video frames.
    Maintains Kalman-predicted bboxes, camera motion compensation, and identity history.
    """
    track_id: int
    entity_type: str = Field("person", description="'person' or 'object'")
    identity_id: Optional[str] = None
    canonical_name: Optional[str] = None
    character_name: Optional[str] = None
    class_label: str = "person"
    identity_status: IdentityMatchStatus = IdentityMatchStatus.UNKNOWN
    start_time: float = 0.0
    end_time: float = 0.0
    start_time_sec: float = 0.0
    end_time_sec: float = 0.0
    history: Optional[List[Any]] = None
    bounding_boxes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'timestamp': float, 'bbox': BoundingBox, 'confidence': float}"
    )
    confidence: float = 0.0
    visibility: float = 1.0
    identity_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Records identity match audits at sampled frames across the track"
    )
    source_movie: Optional[int] = None
    source_shot: Optional[str] = None

    @property
    def duration_sec(self) -> float:
        end = self.end_time or self.end_time_sec
        start = self.start_time or self.start_time_sec
        return max(0.0, end - start)

    def get_bbox_at(self, timestamp: float) -> Optional[BoundingBox]:
        """Returns the linearly interpolated or nearest bounding box at the given timestamp."""
        if not self.bounding_boxes:
            return None
        closest = min(self.bounding_boxes, key=lambda b: abs(b["timestamp"] - timestamp))
        bb = closest["bbox"]
        if isinstance(bb, BoundingBox):
            return bb
        if isinstance(bb, dict):
            return BoundingBox(**bb)
        return None


class EntityTimeline(BaseModel):
    """
    Structured spatio-temporal entity timeline for a candidate video interval.
    Serves as perception evidence for downstream action and composition verifiers.
    """
    clip_id: str = "candidate_clip"
    duration: float = 0.0
    source_video: Optional[str] = None
    start_sec: float = 0.0
    end_sec: float = 0.0
    tracks: List[EntityTrack] = Field(default_factory=list)
    object_detections: List[VisualObject] = Field(default_factory=list)
    timestamps: List[float] = Field(default_factory=list)
    active_tracks_by_time: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Keyed by timestamp string (e.g. '10.20'), list of active person tracks with identities"
    )
    active_objects_by_time: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Keyed by timestamp string, list of active grounded objects"
    )
    spatial_relations_by_time: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Keyed by timestamp string, pairwise geometric proximities (distance, overlap, hand-near-prop)"
    )
    uncertainty_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Audit log of track occlusions, identity degradations to UNKNOWN, or lookalike ambiguities"
    )
    lineage: Dict[str, Any] = Field(
        default_factory=dict,
        description="Perception model versions, bank version, movie fingerprint, and run timestamp"
    )
