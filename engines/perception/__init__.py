"""
STORY FORGE — Absolute Monster Perception Foundation (Phase 2)
==============================================================
Exports core perception components:
  - CharacterBank: Canonical multi-exemplar character identity bank
  - FaceMatcher: ArcFace/OpenCLIP hypersphere face matcher with strict unknown rejection
  - CameraCompensatedTracker: BoT-SORT / ByteTrack camera motion compensated tracker
  - ObjectGrounder: Small prop grounding and selective mask/state refinement
  - EntityTimelineGenerator: Spatio-temporal timeline generator
  - Data models: CharacterIdentity, FaceDetection, VisualObject, EntityTrack, EntityTimeline
"""

from engines.perception.models import (
    CharacterIdentity,
    IdentityMatchStatus,
    IdentityMatchResult,
    IdentityRejectionReason,
    FaceDetection,
    VisualObject,
    EntityTrack,
    EntityTimeline,
)
from engines.perception.character_bank import (
    CharacterBank,
    BANK_VERSION,
    build_canonical_bank,
)
from engines.perception.face_matcher import FaceMatcher
from engines.perception.tracker import (
    CameraCompensatedTracker,
    CameraMotionCompensator,
    TrackState,
)
from engines.perception.object_grounder import ObjectGrounder, CANONICAL_PROPS
from engines.perception.entity_timeline import EntityTimelineGenerator

__all__ = [
    "CharacterIdentity",
    "IdentityMatchStatus",
    "IdentityMatchResult",
    "IdentityRejectionReason",
    "FaceDetection",
    "VisualObject",
    "EntityTrack",
    "EntityTimeline",
    "CharacterBank",
    "BANK_VERSION",
    "build_canonical_bank",
    "FaceMatcher",
    "CameraCompensatedTracker",
    "CameraMotionCompensator",
    "TrackState",
    "ObjectGrounder",
    "CANONICAL_PROPS",
    "EntityTimelineGenerator",
]
