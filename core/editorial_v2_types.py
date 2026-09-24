"""
STORY FORGE — Editorial Intelligence V2 Data Contracts & Types
================================================================================
Defines canonical contracts for the professional short-form editing engine:
  - VisualEmphasisPrimitive: 14 editorial emphasis primitives (PUNCH_IN, SPOTLIGHT, SPLIT_SCREEN, etc.)
  - EditorialTransitionType: HARD_CUT, SMASH_CUT, MATCH_CUT, J_CUT, L_CUT, etc.
  - MotionTreatment: PUNCH_IN_115, SLOW_PUSH_IN, SUBTLE_TRACK_HORIZONTAL, etc.
  - CompositionTreatment: FULL_BLEED_RECENTERED, HYBRID_MODERATE_CROP, SPLIT_SCREEN_VERTICAL, etc.
  - CaptionTreatment: STANDARD_STATIC, CANON_KEYWORD_HIGHLIGHT, REVEAL_WORD_BURST, etc.
  - SFXTreatment: NONE, CLICK, SHORT_TRANSITION, WHOOSH, REVELATION, INTENTIONAL_SILENCE
  - SpotlightCalloutConfig: Precise bounding/magnifier callout geometry
  - EditorialUnit: Atomic editorial decision container for each proposition/evidence event
  - EditorialTimelineV2: Frame-locked directorial timeline with deterministic audit trail
  - VoiceSelectionState: Hard configuration gate enforcing user voice audition & approval
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_v2_types import EvidenceType, BeastV2Decision
from core.storyboard_types import VisualRole
from core.composition_models import ShotScale


class VisualEmphasisPrimitive(str, Enum):
    """14 Core Editorial Emphasis Primitives."""
    PUNCH_IN = "PUNCH_IN"
    PUNCH_OUT = "PUNCH_OUT"
    MICRO_HOLD = "MICRO_HOLD"
    FREEZE_FRAME = "FREEZE_FRAME"
    SUBJECT_SPOTLIGHT = "SUBJECT_SPOTLIGHT"
    OBJECT_SPOTLIGHT = "OBJECT_SPOTLIGHT"
    CROP_EMPHASIS = "CROP_EMPHASIS"
    CALLOUT = "CALLOUT"
    TEXT_CALLOUT = "TEXT_CALLOUT"
    SPLIT_SCREEN = "SPLIT_SCREEN"
    PICTURE_IN_PICTURE = "PICTURE_IN_PICTURE"
    BEFORE_AFTER = "BEFORE_AFTER"
    MATCH_FRAME = "MATCH_FRAME"
    REACTION_INSERT = "REACTION_INSERT"


class EditorialTransitionType(str, Enum):
    """Editorial transitions assigned based on thematic relationship."""
    HARD_CUT = "HARD_CUT"
    SMASH_CUT = "SMASH_CUT"
    MATCH_CUT = "MATCH_CUT"
    J_CUT = "J_CUT"
    L_CUT = "L_CUT"
    MICRO_CROSSFADE = "MICRO_CROSSFADE"
    VISUAL_MATCH = "VISUAL_MATCH"
    OBJECT_MATCH = "OBJECT_MATCH"
    TEXT_BRIDGE = "TEXT_BRIDGE"
    REACTION_BRIDGE = "REACTION_BRIDGE"


class MotionTreatment(str, Enum):
    """Controlled camera motion intent."""
    STATIC = "STATIC"
    PUNCH_IN_115 = "PUNCH_IN_115"                   # Default max ~1.15x
    SLOW_PUSH_IN = "SLOW_PUSH_IN"                   # Anchor focal push (1.0 -> 1.06)
    SUBTLE_TRACK_HORIZONTAL = "SUBTLE_TRACK_HORIZONTAL"
    VERTICAL_REPOSITION = "VERTICAL_REPOSITION"
    HEADROOM_CORRECTION = "HEADROOM_CORRECTION"
    DYNAMIC_CROP = "DYNAMIC_CROP"


class CompositionTreatment(str, Enum):
    """True 9:16 composition framing strategy."""
    FULL_BLEED_RECENTERED = "FULL_BLEED_RECENTERED" # Single character focal shots
    HYBRID_MODERATE_CROP = "HYBRID_MODERATE_CROP"   # Wide / group / action shots
    BLURRED_PADDING = "BLURRED_PADDING"             # Archival / document assets
    SPLIT_SCREEN_VERTICAL = "SPLIT_SCREEN_VERTICAL" # Book vs Movie comparisons
    PICTURE_IN_PICTURE_OVERLAY = "PICTURE_IN_PICTURE_OVERLAY" # Citation / prop inset


class CaptionTreatment(str, Enum):
    """Kinetic caption emphasis mode."""
    STANDARD_STATIC = "STANDARD_STATIC"             # Stable, readable serif
    CANON_KEYWORD_HIGHLIGHT = "CANON_KEYWORD_HIGHLIGHT" # Gold accent on lore nouns
    REVEAL_WORD_BURST = "REVEAL_WORD_BURST"         # Subtle kinetic pulse on revelation
    CONTROLLED_SCALE_PULSE = "CONTROLLED_SCALE_PULSE"
    PHRASE_LOCKED = "PHRASE_LOCKED"


class SFXTreatment(str, Enum):
    """Audio cue intent synchronized with visual events."""
    NONE = "NONE"
    CLICK = "CLICK"
    SHORT_TRANSITION = "SHORT_TRANSITION"
    WHOOSH = "WHOOSH"
    REVELATION = "REVELATION"
    INTENTIONAL_SILENCE = "INTENTIONAL_SILENCE"     # Solemn suppression for tragedy/death


@dataclass
class SpotlightCalloutConfig:
    """Precise visual highlight / callout overlay metadata."""
    callout_type: str = "CIRCULAR_HIGHLIGHT"        # "CIRCULAR_HIGHLIGHT", "MAGNIFIER", "ARROW", "BOUNDING_HIGHLIGHT", "TEXT_POINTER"
    target_x: float = 0.50                          # Normalized 0.0 - 1.0 (center)
    target_y: float = 0.50
    radius: float = 0.15
    label: Optional[str] = None
    start_seconds: float = 0.0
    duration_seconds: float = 1.2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EditorialUnit:
    """
    Atomic editorial decision container for each meaningful proposition/evidence event.
    Replaces arbitrary phrase fragmentation with proposition-locked visual events.
    """
    unit_id: str
    fact_id: str
    proposition_id: str
    asset_id: str
    source_start: float
    source_end: float
    evidence_type: str
    visual_role: str
    narration_start: float
    narration_end: float
    duration_seconds: float
    importance: float
    narrative_weight: float
    pacing_weight: float
    emphasis_level: str                             # "NORMAL", "IMPORTANT", "MAJOR", "CLIMAX"
    emphasis_primitives: List[VisualEmphasisPrimitive] = field(default_factory=list)
    transition_type: EditorialTransitionType = EditorialTransitionType.HARD_CUT
    motion_treatment: MotionTreatment = MotionTreatment.STATIC
    caption_treatment: CaptionTreatment = CaptionTreatment.STANDARD_STATIC
    sfx_treatment: SFXTreatment = SFXTreatment.NONE
    composition_treatment: CompositionTreatment = CompositionTreatment.FULL_BLEED_RECENTERED
    callout: Optional[SpotlightCalloutConfig] = None
    split_screen_asset_id: Optional[str] = None
    pip_asset_id: Optional[str] = None
    audio_offset_seconds: float = 0.0               # J-cut / L-cut offset
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["emphasis_primitives"] = [p.value for p in self.emphasis_primitives]
        d["transition_type"] = self.transition_type.value
        d["motion_treatment"] = self.motion_treatment.value
        d["caption_treatment"] = self.caption_treatment.value
        d["sfx_treatment"] = self.sfx_treatment.value
        d["composition_treatment"] = self.composition_treatment.value
        d["callout"] = self.callout.to_dict() if self.callout else None
        return d


@dataclass
class EditorialTimelineV2:
    """
    Complete directorial editorial timeline container for Remotion execution.
    Deterministic, gapless, and auditable.
    """
    timeline_id: str
    topic_id: str
    total_duration_seconds: float
    total_cuts: int
    units: List[EditorialUnit] = field(default_factory=list)
    deterministic_fingerprint: str = ""
    is_valid: bool = True
    validation_warnings: List[str] = field(default_factory=list)
    quality_audit: Dict[str, Any] = field(default_factory=dict)

    def calculate_fingerprint(self, config_version: str = "v2.0") -> str:
        """Computes deterministic 16-character SHA-256 fingerprint."""
        raw_signature = f"{self.topic_id}:{config_version}:"
        for u in self.units:
            raw_signature += (
                f"[{u.unit_id}|{u.asset_id}|{u.source_start:.2f}-{u.source_end:.2f}|"
                f"{u.transition_type.value}|{u.motion_treatment.value}|{u.sfx_treatment.value}|"
                f"{u.duration_seconds:.2f}]"
            )
        digest = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
        self.deterministic_fingerprint = digest[:16]
        return self.deterministic_fingerprint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timeline_id": self.timeline_id,
            "topic_id": self.topic_id,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "total_cuts": self.total_cuts,
            "deterministic_fingerprint": self.deterministic_fingerprint,
            "is_valid": self.is_valid,
            "validation_warnings": self.validation_warnings,
            "quality_audit": self.quality_audit,
            "units": [u.to_dict() for u in self.units],
        }


@dataclass
class VoiceSelectionState:
    """
    Strict configuration gate state ensuring the user explicitly auditions
    and approves the production voice before any real Short rendering.
    """
    is_selected: bool = False
    selected_voice_id: Optional[str] = None
    auditioned: bool = False
    user_approved: bool = False
    notes: str = "User approval required prior to real production rendering."
