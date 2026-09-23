"""
STORY FORGE Editorial Data Models & Timeline Contracts (Step 4)
================================================================================
Defines canonical contracts for the Remotion Editorial & Kinetic Typography Engine:
  - MotionIntent: NONE, SUBTLE_PUSH, SLOW_PUSH_IN, MICRO_PUNCH, HORIZONTAL_DRIFT, VERTICAL_DRIFT
  - EditorialEmphasis: STANDARD, ANCHOR_FOCAL, REACTION_INTENSE, IRONIC_HIGHLIGHT, PAYOFF_RESOLVE
  - CaptionWord & CaptionSegment: Frame-synchronized kinetic typography with safe-zone anchoring
  - TypographyConfig: Harry Potter serif styling (white, 84px, 4.5px black outline, lower-middle safe zone)
  - EditorialClip & EditorialTimeline: Frame-locked timeline container consumed by Remotion
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from core.storyboard_types import VisualRole, TransitionIntent
from core.preprocessor_types import PreprocessedVisualAsset, AspectRatioStrategy


class MotionIntent(str, Enum):
    """Controlled camera motion intent for editorial emphasis."""
    NONE = "NONE"
    SUBTLE_PUSH = "SUBTLE_PUSH"             # Gentle 1.0 -> 1.05 slow zoom
    SLOW_PUSH_IN = "SLOW_PUSH_IN"           # Controlled anchor focal push 1.0 -> 1.08
    MICRO_PUNCH = "MICRO_PUNCH"             # Subtle punch cut 1.04 on key reveal
    HORIZONTAL_DRIFT = "HORIZONTAL_DRIFT"   # Subtle pan (-15px -> +15px)
    VERTICAL_DRIFT = "VERTICAL_DRIFT"       # Subtle tilt (-15px -> +15px)


class EditorialEmphasis(str, Enum):
    """Directorial emphasis assigned based on narrative/visual role."""
    STANDARD = "STANDARD"
    ANCHOR_FOCAL = "ANCHOR_FOCAL"           # Anchor revelation: prolonged hold, push-in
    REACTION_INTENSE = "REACTION_INTENSE"   # Character reaction: emotional focus
    IRONIC_HIGHLIGHT = "IRONIC_HIGHLIGHT"   # Book vs movie contrast: visual contradiction
    PAYOFF_RESOLVE = "PAYOFF_RESOLVE"       # Climax / looping payoff: clean resolve


@dataclass
class CaptionWord:
    """Individual word within a kinetic caption cluster."""
    word: str
    start_frame: int
    end_frame: int
    is_emphasized: bool = False             # Highlighted keyword (lore term, anchor noun)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CaptionSegment:
    """
    Frame-synchronized caption display phrase (3–5 words).
    Positioned strictly in the lower-middle safe area (clearing TikTok/Shorts UI).
    """
    segment_id: str
    text: str
    start_frame: int
    end_frame: int
    words: List[CaptionWord] = field(default_factory=list)
    position_y: int = 1400                  # Y-coordinate safe zone (~520px from bottom in 1920h)
    style_name: str = "HP_Default"
    is_multiline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["words"] = [w.to_dict() for w in self.words]
        return d


@dataclass
class TypographyConfig:
    """
    Canonical Harry Potter visual caption style:
    White text, heavy black outline, 84px equivalent, lower-middle safe area.
    """
    font_family: str = "Harry P, Georgia, serif"
    font_size_px: int = 84
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width_px: float = 4.5
    margin_v_px: int = 520                  # Distance from bottom (safe zone)
    margin_h_px: int = 80                   # Distance from left/right edges
    safe_zone_bottom_px: int = 1400         # Center Y target in 1920 vertical canvas
    max_chars_per_line: int = 30
    line_height: float = 1.15
    letter_spacing_px: float = 0.5
    emphasis_color: str = "#FFD700"         # Subtle gold accent for lore keywords

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EditorialClip:
    """
    Frame-locked, Remotion-ready visual clip unit.
    Preserves complete lineage from StoryboardBeatContract through PreprocessedVisualAsset.
    """
    clip_id: str
    storyboard_beat_id: str
    source_asset_id: str
    source_preprocessed_path: Optional[str] = None
    source_media_type: str = "VIDEO"        # "VIDEO", "IMAGE", "NONE"
    start_frame: int = 0
    end_frame: int = 0
    duration_frames: int = 0
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    duration_seconds: float = 0.0
    visual_role: VisualRole = VisualRole.DIRECT_EVIDENCE
    is_anchor: bool = False
    transition_intent: TransitionIntent = TransitionIntent.HARD_CUT
    transition_duration_frames: int = 0
    motion_intent: MotionIntent = MotionIntent.NONE
    editorial_emphasis: EditorialEmphasis = EditorialEmphasis.STANDARD
    captions: List[CaptionSegment] = field(default_factory=list)
    source_provenance: Optional[Dict[str, Any]] = None
    validation_status: str = "VALID"        # "VALID", "NO_VALID_VISUAL", "UNRESOLVED_SOURCE"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["visual_role"] = self.visual_role.value if isinstance(self.visual_role, VisualRole) else str(self.visual_role)
        d["transition_intent"] = self.transition_intent.value if isinstance(self.transition_intent, TransitionIntent) else str(self.transition_intent)
        d["motion_intent"] = self.motion_intent.value if isinstance(self.motion_intent, MotionIntent) else str(self.motion_intent)
        d["editorial_emphasis"] = self.editorial_emphasis.value if isinstance(self.editorial_emphasis, EditorialEmphasis) else str(self.editorial_emphasis)
        d["captions"] = [c.to_dict() for c in self.captions]
        return d


@dataclass
class EditorialTimeline:
    """
    Complete directorial editorial timeline for Remotion.
    Frame-accurate, gapless, deterministic, and fully auditable.
    """
    composition_id: str
    storyboard_id: str
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    total_duration_seconds: float = 0.0
    total_frames: int = 0
    clips: List[EditorialClip] = field(default_factory=list)
    typography_config: TypographyConfig = field(default_factory=TypographyConfig)
    deterministic_fingerprint: str = ""
    is_production_ready: bool = True
    validation_errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Tuple[bool, List[str]]:
        """Validates temporal continuity, bounds, and safety invariants."""
        errors: List[str] = []

        if not self.composition_id:
            errors.append("composition_id is required")
        if not self.clips:
            errors.append("EditorialTimeline must contain at least one clip")

        # Frame continuity and bounds checks
        expected_frame = 0
        for i, clip in enumerate(self.clips):
            if clip.start_frame != expected_frame:
                errors.append(
                    f"Temporal gap/overlap at clip index {i} ({clip.clip_id}): "
                    f"expected start {expected_frame}, got {clip.start_frame}"
                )
            if clip.duration_frames <= 0:
                errors.append(f"Clip {clip.clip_id} has invalid duration: {clip.duration_frames} frames")
            if clip.validation_status == "NO_VALID_VISUAL":
                errors.append(f"Clip {clip.clip_id} has NO_VALID_VISUAL status")

            expected_frame = clip.end_frame

        if self.total_frames != expected_frame:
            errors.append(
                f"total_frames mismatch: declared {self.total_frames}, sum of clips {expected_frame}"
            )

        is_valid = len(errors) == 0
        return is_valid, errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "storyboard_id": self.storyboard_id,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_duration_seconds": self.total_duration_seconds,
            "total_frames": self.total_frames,
            "clips": [c.to_dict() for c in self.clips],
            "typography_config": self.typography_config.to_dict(),
            "deterministic_fingerprint": self.deterministic_fingerprint,
            "is_production_ready": self.is_production_ready,
            "validation_errors": self.validation_errors,
            "metadata": self.metadata,
        }

    def to_remotion_props(self) -> Dict[str, Any]:
        """Formats the timeline into the exact JSON props consumed by Remotion Root component."""
        return {
            "compositionId": self.composition_id,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "durationInFrames": self.total_frames,
            "clips": [
                {
                    "clipId": c.clip_id,
                    "beatId": c.storyboard_beat_id,
                    "sourcePath": c.source_preprocessed_path,
                    "mediaType": c.source_media_type,
                    "startFrame": c.start_frame,
                    "endFrame": c.end_frame,
                    "durationFrames": c.duration_frames,
                    "visualRole": c.visual_role.value if isinstance(c.visual_role, VisualRole) else str(c.visual_role),
                    "isAnchor": c.is_anchor,
                    "transition": {
                        "intent": c.transition_intent.value if isinstance(c.transition_intent, TransitionIntent) else str(c.transition_intent),
                        "durationFrames": c.transition_duration_frames,
                    },
                    "motion": {
                        "intent": c.motion_intent.value if isinstance(c.motion_intent, MotionIntent) else str(c.motion_intent),
                        "emphasis": c.editorial_emphasis.value if isinstance(c.editorial_emphasis, EditorialEmphasis) else str(c.editorial_emphasis),
                    },
                    "captions": [
                        {
                            "segmentId": cap.segment_id,
                            "text": cap.text,
                            "startFrame": cap.start_frame,
                            "endFrame": cap.end_frame,
                            "positionY": cap.position_y,
                            "styleName": cap.style_name,
                            "words": [w.to_dict() for w in cap.words],
                        }
                        for cap in c.captions
                    ],
                }
                for c in self.clips
            ],
            "typography": self.typography_config.to_dict(),
            "fingerprint": self.deterministic_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EditorialTimeline":
        raw_clips = data.get("clips", [])
        clips: List[EditorialClip] = []
        for c_data in raw_clips:
            vr = c_data.get("visual_role", VisualRole.DIRECT_EVIDENCE.value)
            if isinstance(vr, str):
                vr = VisualRole(vr)

            ti = c_data.get("transition_intent", TransitionIntent.HARD_CUT.value)
            if isinstance(ti, str):
                ti = TransitionIntent(ti)

            mi = c_data.get("motion_intent", MotionIntent.NONE.value)
            if isinstance(mi, str):
                mi = MotionIntent(mi)

            ee = c_data.get("editorial_emphasis", EditorialEmphasis.STANDARD.value)
            if isinstance(ee, str):
                ee = EditorialEmphasis(ee)

            caps: List[CaptionSegment] = []
            for cap_data in c_data.get("captions", []):
                words = [CaptionWord(**w) for w in cap_data.get("words", [])]
                caps.append(
                    CaptionSegment(
                        segment_id=cap_data.get("segment_id", ""),
                        text=cap_data.get("text", ""),
                        start_frame=cap_data.get("start_frame", 0),
                        end_frame=cap_data.get("end_frame", 0),
                        words=words,
                        position_y=cap_data.get("position_y", 1400),
                        style_name=cap_data.get("style_name", "HP_Default"),
                        is_multiline=cap_data.get("is_multiline", False),
                    )
                )

            clips.append(
                EditorialClip(
                    clip_id=c_data.get("clip_id", ""),
                    storyboard_beat_id=c_data.get("storyboard_beat_id", ""),
                    source_asset_id=c_data.get("source_asset_id", ""),
                    source_preprocessed_path=c_data.get("source_preprocessed_path"),
                    source_media_type=c_data.get("source_media_type", "VIDEO"),
                    start_frame=c_data.get("start_frame", 0),
                    end_frame=c_data.get("end_frame", 0),
                    duration_frames=c_data.get("duration_frames", 0),
                    start_seconds=c_data.get("start_seconds", 0.0),
                    end_seconds=c_data.get("end_seconds", 0.0),
                    duration_seconds=c_data.get("duration_seconds", 0.0),
                    visual_role=vr,
                    is_anchor=c_data.get("is_anchor", False),
                    transition_intent=ti,
                    transition_duration_frames=c_data.get("transition_duration_frames", 0),
                    motion_intent=mi,
                    editorial_emphasis=ee,
                    captions=caps,
                    source_provenance=c_data.get("source_provenance"),
                    validation_status=c_data.get("validation_status", "VALID"),
                )
            )

        typo = TypographyConfig(**data.get("typography_config", {}))

        return cls(
            composition_id=data.get("composition_id", ""),
            storyboard_id=data.get("storyboard_id", ""),
            width=data.get("width", 1080),
            height=data.get("height", 1920),
            fps=data.get("fps", 30.0),
            total_duration_seconds=data.get("total_duration_seconds", 0.0),
            total_frames=data.get("total_frames", 0),
            clips=clips,
            typography_config=typo,
            deterministic_fingerprint=data.get("deterministic_fingerprint", ""),
            is_production_ready=data.get("is_production_ready", True),
            validation_errors=data.get("validation_errors", []),
            metadata=data.get("metadata", {}),
        )
