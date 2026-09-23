"""
STORY FORGE Preprocessor Data Models & Contracts (Step 3)
================================================================================
Defines canonical contracts for the FFmpeg Preprocessing & Aspect-Ratio Normalizer:
  - AspectRatioStrategy: CENTER_CROP, FRAMING_AWARE_CROP, BLURRED_PADDING, LETTERBOX
  - PreprocessingStatus: PENDING, COMPLETED, CACHED, NO_VALID_VISUAL, FAILED
  - PreprocessedVisualAsset: Typed container for standardized 1080x1920 intermediate visual segments
"""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from engines.movie_retrieval_engine import ShotScale


class AspectRatioStrategy(str, Enum):
    """Strategy for normalizing footage/images into 9:16 (1080x1920)."""
    FULL_BLEED_RECENTERED = "FULL_BLEED_RECENTERED" # 100% vertical screen occupancy with dynamic subject tracking
    HYBRID_MODERATE_CROP = "HYBRID_MODERATE_CROP"   # ~80% vertical screen occupancy with subtle ambient padding
    CENTER_CROP = "CENTER_CROP"                 # Scale to fill 1080x1920 and center crop
    FRAMING_AWARE_CROP = "FRAMING_AWARE_CROP"   # Offset crop based on framing intent (close-up, two-shot, etc.)
    BLURRED_PADDING = "BLURRED_PADDING"         # Fit foreground with blurred background fill
    LETTERBOX = "LETTERBOX"                     # Uniform scale with solid padding bars


class PreprocessingStatus(str, Enum):
    """Lifecycle status of preprocessed intermediate assets."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CACHED = "CACHED"
    NO_VALID_VISUAL = "NO_VALID_VISUAL"
    FAILED = "FAILED"


@dataclass
class PreprocessedVisualAsset:
    """
    Standardized lightweight visual segment prepared for the downstream Remotion editor.
    Guaranteed: 1080x1920, 9:16, 30fps, H.264, yuv420p, audio-muted (-an).
    """
    asset_id: str
    source_path: Optional[str] = None
    source_media_type: str = "VIDEO"                        # "VIDEO", "IMAGE", "NONE"
    source_timestamps: Optional[Tuple[float, float]] = None # (clip_start_sec, clip_end_sec)
    requested_start: float = 0.0
    requested_end: float = 0.0
    output_path: Optional[str] = None
    output_width: int = 1080
    output_height: int = 1920
    fps: float = 30.0
    duration: float = 0.0
    aspect_ratio_strategy: AspectRatioStrategy = AspectRatioStrategy.CENTER_CROP
    framing_intent: ShotScale = ShotScale.MEDIUM_SHOT
    status: PreprocessingStatus = PreprocessingStatus.PENDING
    fingerprint: str = ""
    source_provenance: Optional[Dict[str, Any]] = None
    ffmpeg_cmd: Optional[List[str]] = None
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["aspect_ratio_strategy"] = (
            self.aspect_ratio_strategy.value
            if isinstance(self.aspect_ratio_strategy, AspectRatioStrategy)
            else str(self.aspect_ratio_strategy)
        )
        d["framing_intent"] = (
            self.framing_intent.value
            if isinstance(self.framing_intent, ShotScale)
            else str(self.framing_intent)
        )
        d["status"] = (
            self.status.value
            if isinstance(self.status, PreprocessingStatus)
            else str(self.status)
        )
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreprocessedVisualAsset":
        strat = data.get("aspect_ratio_strategy", AspectRatioStrategy.CENTER_CROP.value)
        if isinstance(strat, str):
            strat = AspectRatioStrategy(strat)

        fi = data.get("framing_intent", ShotScale.MEDIUM_SHOT.value)
        if isinstance(fi, str):
            fi = ShotScale(fi)

        st = data.get("status", PreprocessingStatus.PENDING.value)
        if isinstance(st, str):
            st = PreprocessingStatus(st)

        st_stamps = data.get("source_timestamps")
        if isinstance(st_stamps, list):
            st_stamps = tuple(st_stamps)

        return cls(
            asset_id=data.get("asset_id", ""),
            source_path=data.get("source_path"),
            source_media_type=data.get("source_media_type", "VIDEO"),
            source_timestamps=st_stamps,
            requested_start=data.get("requested_start", 0.0),
            requested_end=data.get("requested_end", 0.0),
            output_path=data.get("output_path"),
            output_width=data.get("output_width", 1080),
            output_height=data.get("output_height", 1920),
            fps=data.get("fps", 30.0),
            duration=data.get("duration", 0.0),
            aspect_ratio_strategy=strat,
            framing_intent=fi,
            status=st,
            fingerprint=data.get("fingerprint", ""),
            source_provenance=data.get("source_provenance"),
            ffmpeg_cmd=data.get("ffmpeg_cmd"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
