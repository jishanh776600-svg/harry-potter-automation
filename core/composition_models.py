"""
STORY FORGE Shot Composition & 9:16 Safety Models (Step 9 Hardening)
================================================================================
Defines canonical composition assessment, shot scales, normalized bounding boxes,
and 9:16 vertical crop safety evaluations for movie shots and visual assets:

Supported Shot Scales:
  - EXTREME_WIDE: Distant panoramic landscape or setting establishing scope.
  - WIDE: Full environment with characters visible in context.
  - MEDIUM_WIDE: Characters from knees up with clear environmental setting.
  - MEDIUM: Characters from waist up; primary workhorse for normal narration.
  - MEDIUM_CLOSE: Characters from chest up.
  - CLOSE_UP: Characters from shoulders up focusing on facial emotion.
  - EXTREME_CLOSE_UP: Tight crop on eyes/mouth/specific object; justified only.
  - TWO_SHOT: Balanced dual-character interaction framing.
  - GROUP_SHOT: Three or more characters framed together in scene context.

Strict Crop Policy (PART C, D, E):
  - No digital post-crop zoom to manufacture subject prominence.
  - Reject candidate shots where 9:16 vertical conversion cuts off faces,
    essential bodies, or removes indispensable narrative context.
  - 9:16-first evaluation: simulate crop before ranking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple


class ShotScale(str, Enum):
    """
    Standard cinematic shot scales for STORY FORGE.
    Preserves backward compatibility aliases with existing codebase.
    """
    EXTREME_WIDE = "EXTREME_WIDE"
    WIDE = "WIDE"
    MEDIUM_WIDE = "MEDIUM_WIDE"
    MEDIUM = "MEDIUM"
    MEDIUM_CLOSE = "MEDIUM_CLOSE"
    CLOSE_UP = "CLOSE_UP"
    EXTREME_CLOSE_UP = "EXTREME_CLOSE_UP"
    TWO_SHOT = "TWO_SHOT"
    GROUP_SHOT = "GROUP_SHOT"

    # Backward-compatibility aliases
    MEDIUM_SHOT = "MEDIUM"
    WIDE_SHOT = "WIDE"
    MEDIUM_CLOSE_UP = "MEDIUM_CLOSE"

    @classmethod
    def from_string(cls, val: str) -> "ShotScale":
        """Normalizes and maps legacy strings to canonical ShotScale."""
        v = str(val).strip().upper()
        if v in ("MEDIUM_SHOT", "MEDIUM"):
            return cls.MEDIUM
        if v in ("WIDE_SHOT", "WIDE"):
            return cls.WIDE
        if v in ("MEDIUM_CLOSE_UP", "MEDIUM_CLOSE"):
            return cls.MEDIUM_CLOSE
        if v == "EXTREME_WIDE":
            return cls.EXTREME_WIDE
        if v == "MEDIUM_WIDE":
            return cls.MEDIUM_WIDE
        if v == "CLOSE_UP":
            return cls.CLOSE_UP
        if v == "EXTREME_CLOSE_UP":
            return cls.EXTREME_CLOSE_UP
        if v == "TWO_SHOT":
            return cls.TWO_SHOT
        if v == "GROUP_SHOT":
            return cls.GROUP_SHOT
        return cls.MEDIUM


@dataclass
class NormalizedBBox:
    """
    Normalized bounding box in coordinate space [0.0, 1.0].
    (x, y) represents the top-left corner; w, h represent width and height.
    """
    x: float
    y: float
    w: float
    h: float

    def __post_init__(self):
        self.x = max(0.0, min(1.0, float(self.x)))
        self.y = max(0.0, min(1.0, float(self.y)))
        self.w = max(0.0, min(1.0 - self.x, float(self.w)))
        self.h = max(0.0, min(1.0 - self.y, float(self.h)))

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return self.w * self.h

    def intersection_area(self, other: "NormalizedBBox") -> float:
        """Calculates overlap area between two normalized bounding boxes."""
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        return (ix2 - ix1) * (iy2 - iy1)

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "w": round(self.w, 4),
            "h": round(self.h, 4),
        }


@dataclass
class ShotCompositionAssessment:
    """
    Explicit composition assessment for a candidate movie shot.
    Evaluates 9:16 vertical crop safety before candidate selection.
    """
    shot_scale: ShotScale
    subject_bbox: Optional[NormalizedBBox] = None
    subject_area_ratio: float = 0.20
    face_visibility: float = 1.0            # 0.0 - 1.0 (1.0 = fully visible)
    head_cutoff: float = 0.0                # 0.0 - 1.0 (fraction of head cut off)
    body_cutoff: float = 0.0                # 0.0 - 1.0 (fraction of body cut off)
    background_visibility: float = 0.80     # 0.0 - 1.0 (context remaining)
    environment_context_score: float = 0.80 # 0.0 - 1.0 (spatial grounding)
    multi_character_visibility: float = 1.0 # 0.0 - 1.0 (if multiple characters)
    center_safe_score: float = 0.85         # 0.0 - 1.0 (subject centeredness)
    vertical_crop_risk: float = 0.10        # 0.0 - 1.0 (risk of vertical chop)
    horizontal_crop_risk: float = 0.10      # 0.0 - 1.0 (risk of 16:9 side loss)
    safe_9x16_score: float = 0.90           # Composite 0.0 - 1.0 crop safety
    is_9x16_crop_safe: bool = True
    crop_rejection_reasons: List[str] = field(default_factory=list)
    optimal_crop_center_x: float = 0.50     # 0.0 - 1.0 horizontal crop center
    has_severe_crop: bool = False
    effective_crop_strategy: str = "FULL_BLEED_RECENTERED" # FULL_BLEED_RECENTERED, HYBRID_MODERATE_CROP, BLURRED_PADDING
    visual_occupancy_ratio: float = 1.0     # 0.0 - 1.0 vertical screen occupancy (1.0 = full bleed, ~0.80 = hybrid, ~0.316 = blurred)
    vertical_screen_utilization: float = 1.0 # Fraction of vertical 1920 height utilized by visual content
    crop_window: Optional[Dict[str, float]] = None

    @property
    def score_9x16_safe(self) -> float:
        """Alias for safe_9x16_score."""
        return self.safe_9x16_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_scale": self.shot_scale.value if isinstance(self.shot_scale, ShotScale) else str(self.shot_scale),
            "subject_bbox": self.subject_bbox.to_dict() if self.subject_bbox else None,
            "subject_area_ratio": round(self.subject_area_ratio, 3),
            "face_visibility": round(self.face_visibility, 3),
            "head_cutoff": round(self.head_cutoff, 3),
            "body_cutoff": round(self.body_cutoff, 3),
            "background_visibility": round(self.background_visibility, 3),
            "environment_context_score": round(self.environment_context_score, 3),
            "multi_character_visibility": round(self.multi_character_visibility, 3),
            "center_safe_score": round(self.center_safe_score, 3),
            "vertical_crop_risk": round(self.vertical_crop_risk, 3),
            "horizontal_crop_risk": round(self.horizontal_crop_risk, 3),
            "safe_9x16_score": round(self.safe_9x16_score, 3),
            "is_9x16_crop_safe": self.is_9x16_crop_safe,
            "crop_rejection_reasons": self.crop_rejection_reasons,
            "optimal_crop_center_x": round(self.optimal_crop_center_x, 3),
            "has_severe_crop": self.has_severe_crop,
            "effective_crop_strategy": self.effective_crop_strategy,
            "visual_occupancy_ratio": round(self.visual_occupancy_ratio, 3),
            "vertical_screen_utilization": round(self.vertical_screen_utilization, 3),
            "crop_window": self.crop_window,
        }
