"""
STORY FORGE — Subject-Aware 16:9 to 9:16 Composition & Post-Crop Verification Engine
==================================================================================
Ensures semantic visibility of required subjects across 9:16 vertical re-framing:
  1. Computes dynamic crop window centered on subject(s) instead of blind center crop.
  2. Multi-subject co-presence verification: keeps both subjects visible or fails closed.
  3. Safe-zone enforcement: prevents subjects from being clipped against 9:16 borders.
  4. Generates deterministic ffmpeg filter strings and cryptographic crop fingerprints.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import math
from typing import Dict, List, Any, Optional, Tuple, Union

from core.composition_models import NormalizedBBox, ShotScale

logger = logging.getLogger("SubjectAwareComposition")


@dataclass
class CropWindow:
    """Exact pixel-level crop window on source video."""
    x: int
    y: int
    w: int
    h: int
    src_w: int
    src_h: int
    strategy: str = "FULL_BLEED_RECENTERED"

    @property
    def ffmpeg_crop_filter(self) -> str:
        """FFmpeg filter string for cropping and scaling to 1080x1920 30fps Lanczos."""
        return f"crop={self.w}:{self.h}:{self.x}:{self.y},scale=1080:1920:flags=lanczos,fps=30"

    @property
    def normalized_center_x(self) -> float:
        return (self.x + self.w / 2.0) / float(self.src_w)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "src_w": self.src_w,
            "src_h": self.src_h,
            "strategy": self.strategy,
            "ffmpeg_filter": self.ffmpeg_crop_filter,
            "normalized_center_x": round(self.normalized_center_x, 4),
        }


@dataclass
class PostCropVerificationResult:
    """Structured outcome of post-crop composition and safe-zone validation."""
    is_valid: bool
    crop_window: CropWindow
    source_bboxes: List[Dict[str, float]] = field(default_factory=list)
    final_subject_positions: List[Dict[str, float]] = field(default_factory=list)
    retained_subject_ratio: float = 1.0
    safe_zone_passed: bool = True
    rejection_reasons: List[str] = field(default_factory=list)
    primary_rejection_reason: Optional[str] = None
    explanation: str = ""
    is_visible: bool = True
    is_clipped: bool = False
    crop_position: Dict[str, int] = field(default_factory=dict)
    dimensions: Dict[str, Any] = field(default_factory=dict)
    crop_fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "crop_window": self.crop_window.to_dict(),
            "source_bboxes": self.source_bboxes,
            "final_subject_positions": self.final_subject_positions,
            "retained_subject_ratio": round(self.retained_subject_ratio, 4),
            "safe_zone_passed": self.safe_zone_passed,
            "rejection_reasons": self.rejection_reasons,
            "primary_rejection_reason": self.primary_rejection_reason,
            "explanation": self.explanation,
            "is_visible": self.is_visible,
            "is_clipped": self.is_clipped,
            "crop_position": self.crop_position,
            "dimensions": self.dimensions,
            "crop_fingerprint": self.crop_fingerprint,
        }


class SubjectAwareCompositionEngine:
    """
    Directs 16:9 -> 9:16 vertical reframing and enforces post-crop subject visibility.
    Deterministic geometric optimizer: positions 9:16 crop window to maximize real subject visibility.
    """

    def __init__(
        self,
        default_src_w: int = 1920,
        default_src_h: int = 800,
        min_retained_ratio: float = 0.85,
        safe_zone_margin_h: float = 0.05,
    ):
        self.default_src_w = default_src_w
        self.default_src_h = default_src_h
        self.min_retained_ratio = min_retained_ratio
        self.safe_zone_margin_h = safe_zone_margin_h

    def _normalize_bbox(
        self,
        b: Union[NormalizedBBox, Dict[str, Any], Any],
        src_w: int,
        src_h: int,
    ) -> NormalizedBBox:
        """Converts arbitrary bounding box or detection format into NormalizedBBox [0.0, 1.0]."""
        if isinstance(b, NormalizedBBox):
            return b
        if hasattr(b, "bbox") and b.bbox is not None:
            return self._normalize_bbox(b.bbox, src_w, src_h)
        if hasattr(b, "x") and hasattr(b, "y") and hasattr(b, "w") and hasattr(b, "h"):
            bx = float(b.x)
            by = float(b.y)
            bw = float(b.w)
            bh = float(b.h)
            if bw > 1.0 or bh > 1.0 or bx > 1.0 or by > 1.0:
                return NormalizedBBox(bx / src_w, by / src_h, bw / src_w, bh / src_h)
            return NormalizedBBox(bx, by, bw, bh)
        if isinstance(b, dict):
            bx = float(b.get("x", 0.0))
            by = float(b.get("y", 0.0))
            bw = float(b.get("w", 0.0))
            bh = float(b.get("h", 0.0))
            if bw > 1.0 or bh > 1.0 or bx > 1.0 or by > 1.0:
                return NormalizedBBox(bx / src_w, by / src_h, bw / src_w, bh / src_h)
            return NormalizedBBox(bx, by, bw, bh)
        raise TypeError(f"Unsupported bounding box type: {type(b)}")

    def compute_crop_and_verify(
        self,
        subject_bboxes: Optional[List[Any]] = None,
        shot_scale: Union[ShotScale, str] = ShotScale.MEDIUM,
        src_w: Optional[int] = None,
        src_h: Optional[int] = None,
        target_aspect_w: int = 9,
        target_aspect_h: int = 16,
        is_two_shot: bool = False,
        focal_region: Optional[Any] = None,
        allow_scale_adjustment: bool = False,
        allow_letterbox: bool = False,
        allow_partial_retention: bool = False,
        min_retained_ratio: Optional[float] = None,
    ) -> PostCropVerificationResult:
        """
        Computes the subject-aware vertical crop window and verifies post-crop visibility.
        Disables silent center-crop fallback: if subject evidence is absent, fails closed.
        """
        sw = src_w or self.default_src_w
        sh = src_h or self.default_src_h
        eff_min_retained = min_retained_ratio if min_retained_ratio is not None else self.min_retained_ratio

        crop_h = sh
        crop_w = round(sh * target_aspect_w / float(target_aspect_h))
        if crop_w % 2 != 0:
            crop_w += 1
        crop_w = min(crop_w, sw)

        # Disallow silent synthetic center crop fallback
        if not subject_bboxes:
            failed_win = CropWindow(x=0, y=0, w=crop_w, h=crop_h, src_w=sw, src_h=sh, strategy="FAILED_NO_SUBJECT")
            fp = compute_crop_fingerprint(failed_win, strategy="FAILED_NO_SUBJECT")
            return PostCropVerificationResult(
                is_valid=False,
                crop_window=failed_win,
                source_bboxes=[],
                final_subject_positions=[],
                retained_subject_ratio=0.0,
                safe_zone_passed=False,
                rejection_reasons=["NO_REQUIRED_ENTITY_FOR_CROP"],
                primary_rejection_reason="NO_REQUIRED_ENTITY_FOR_CROP",
                explanation="No detected subject bounding boxes provided for subject-aware crop. Centered crop fallback is prohibited.",
                is_visible=False,
                is_clipped=True,
                crop_position={"x": 0, "y": 0, "w": crop_w, "h": crop_h},
                dimensions={"source": (sw, sh), "crop": (crop_w, crop_h)},
                crop_fingerprint=fp,
            )

        bboxes = [self._normalize_bbox(b, sw, sh) for b in subject_bboxes]

        rejection_reasons = []
        is_valid = True
        primary_reason = None
        safe_zone_passed = True
        strategy = "SUBJECT_AWARE_OPTIMIZED"

        # Multi-subject co-presence logic
        if len(bboxes) > 1 or is_two_shot:
            min_x_px = min(b.x for b in bboxes) * sw
            max_x_px = max(b.x2 for b in bboxes) * sw
            union_w_px = max_x_px - min_x_px
            usable_crop_w = crop_w * (1.0 - 2.0 * self.safe_zone_margin_h)

            if union_w_px > usable_crop_w:
                if allow_letterbox:
                    strategy = "LETTERBOX_PILLARBOX"
                    crop_x = 0
                elif allow_scale_adjustment and (crop_w / union_w_px) >= 0.70:
                    strategy = "CONTROLLED_SCALE_ADJUSTMENT"
                    crop_x = int(round(max(0, min(sw - crop_w, ((min_x_px + max_x_px) / 2.0) - crop_w / 2.0))))
                else:
                    is_valid = False
                    safe_zone_passed = False
                    rejection_reasons.append("CROP_MULTI_SUBJECT_LOST")
                    primary_reason = "CROP_MULTI_SUBJECT_LOST"
                    expl = (
                        f"Two required subjects span {union_w_px:.1f}px ({min_x_px/sw:.2f} to {max_x_px/sw:.2f}), "
                        f"exceeding usable 9:16 crop width {usable_crop_w:.1f}px. "
                        "Cropping will eliminate one of the required characters."
                    )
                    crop_x = int(round(max(0, min(sw - crop_w, ((min_x_px + max_x_px) / 2.0) - crop_w / 2.0))))
                    crop_win = CropWindow(x=crop_x, y=0, w=crop_w, h=crop_h, src_w=sw, src_h=sh, strategy="FAILED_MULTI_SUBJECT_LOST")
                    fp = compute_crop_fingerprint(crop_win, strategy="FAILED_MULTI_SUBJECT_LOST")
                    return PostCropVerificationResult(
                        is_valid=False,
                        crop_window=crop_win,
                        source_bboxes=[b.to_dict() for b in bboxes],
                        retained_subject_ratio=round(crop_w / union_w_px, 4),
                        safe_zone_passed=False,
                        rejection_reasons=rejection_reasons,
                        primary_rejection_reason=primary_reason,
                        explanation=expl,
                        is_visible=True,
                        is_clipped=True,
                        crop_position={"x": crop_x, "y": 0, "w": crop_w, "h": crop_h},
                        dimensions={"source": (sw, sh), "crop": (crop_w, crop_h)},
                        crop_fingerprint=fp,
                    )
            else:
                strategy = "MULTI_SUBJECT_CO_PRESENCE"
                union_cx = (min_x_px + max_x_px) / 2.0
                crop_x = int(round(max(0, min(sw - crop_w, union_cx - (crop_w / 2.0)))))
        else:
            # Single subject optimization
            b0 = bboxes[0]
            subj_x1_px = b0.x * sw
            subj_x2_px = b0.x2 * sw
            subj_w_px = max(1.0, subj_x2_px - subj_x1_px)
            subj_cx_px = subj_x1_px + subj_w_px / 2.0

            if subj_w_px <= crop_w:
                # Subject fits inside crop window -> center window on subject
                ideal_crop_x = subj_cx_px - (crop_w / 2.0)
                crop_x = int(round(max(0, min(sw - crop_w, ideal_crop_x))))
                strategy = "SUBJECT_AWARE_OPTIMIZED"
            else:
                # Wide entity (e.g. Buckbeak, wingspan > 9:16 crop width)
                strategy = "SUBJECT_AWARE_WIDE_ENTITY"
                if focal_region is not None:
                    f_norm = self._normalize_bbox(focal_region, sw, sh)
                    f_cx_px = f_norm.center_x * sw
                    crop_x = int(round(max(0, min(sw - crop_w, f_cx_px - (crop_w / 2.0)))))
                elif b0.x * sw < sw * 0.25:
                    # Entity situated on left; align with leading edge (head/torso/talons)
                    crop_x = int(max(0, min(sw - crop_w, round(subj_x1_px))))
                elif b0.x2 * sw > sw * 0.75:
                    # Entity situated on right; align with trailing edge
                    crop_x = int(max(0, min(sw - crop_w, round(subj_x2_px - crop_w))))
                else:
                    crop_x = int(round(max(0, min(sw - crop_w, subj_cx_px - (crop_w / 2.0)))))

        crop_y = 0
        crop_win = CropWindow(
            x=crop_x,
            y=crop_y,
            w=crop_w,
            h=crop_h,
            src_w=sw,
            src_h=sh,
            strategy=strategy,
        )

        # Post-Crop Retention & Visibility Evaluation
        final_positions = []
        min_retained = 1.0

        for idx, bbox in enumerate(bboxes):
            subj_x1_px = bbox.x * sw
            subj_x2_px = bbox.x2 * sw
            subj_w_px = max(1.0, subj_x2_px - subj_x1_px)
            subj_y1_px = bbox.y * sh
            subj_y2_px = bbox.y2 * sh
            subj_h_px = max(1.0, subj_y2_px - subj_y1_px)

            overlap_x1 = max(crop_x, subj_x1_px)
            overlap_x2 = min(crop_x + crop_w, subj_x2_px)
            overlap_w_px = max(0.0, overlap_x2 - overlap_x1)

            overlap_y1 = max(0, subj_y1_px)
            overlap_y2 = min(sh, subj_y2_px)
            overlap_h_px = max(0.0, overlap_y2 - overlap_y1)

            overlap_area = overlap_w_px * overlap_h_px
            subj_area = subj_w_px * subj_h_px
            retained = overlap_area / subj_area if subj_area > 0 else 0.0
            min_retained = min(min_retained, retained)

            norm_x1 = (subj_x1_px - crop_x) / float(crop_w)
            norm_x2 = (subj_x2_px - crop_x) / float(crop_w)
            norm_w = norm_x2 - norm_x1
            norm_center = norm_x1 + norm_w / 2.0

            final_positions.append({
                "index": idx,
                "norm_x1": round(norm_x1, 4),
                "norm_x2": round(norm_x2, 4),
                "norm_w": round(norm_w, 4),
                "norm_center": round(norm_center, 4),
                "retained_ratio": round(retained, 4),
            })

            # Check rejection criteria
            if retained <= 0.001:
                is_valid = False
                rejection_reasons.append("CROP_SUBJECT_OUTSIDE")
                if not primary_reason:
                    primary_reason = "CROP_SUBJECT_OUTSIDE"
            elif retained < eff_min_retained:
                # If subject is wider than crop window and partial retention is allowed for wide entities
                is_wide_entity = (subj_w_px > crop_w)
                if not (is_wide_entity and allow_partial_retention):
                    is_valid = False
                    rejection_reasons.append("CROP_SUBJECT_CLIPPED")
                    if not primary_reason:
                        primary_reason = "CROP_SUBJECT_CLIPPED"

            # Safe-zone check
            if subj_w_px <= crop_w:
                if norm_center < 0.10 or norm_center > 0.90 or (norm_x1 < -0.05 and norm_x2 < 0.70) or (norm_x2 > 1.05 and norm_x1 > 0.30):
                    safe_zone_passed = False
                    if "CROP_SAFE_ZONE_VIOLATION" not in rejection_reasons:
                        rejection_reasons.append("CROP_SAFE_ZONE_VIOLATION")
                    if not primary_reason:
                        primary_reason = "CROP_SAFE_ZONE_VIOLATION"

        if not is_valid or not safe_zone_passed:
            is_valid = False
            expl = (
                f"Post-crop validation rejected ({primary_reason}): "
                f"Retained subject ratio {min_retained*100:.1f}% (< {eff_min_retained*100:.0f}%), "
                f"safe zone passed={safe_zone_passed}, crop window x={crop_x}..{crop_x+crop_w} on {sw}x{sh} source."
            )
        else:
            expl = (
                f"Post-crop composition verified: Retained ratio {min_retained*100:.1f}%, "
                f"crop window x={crop_x}..{crop_x+crop_w} on {sw}x{sh} source (strategy={strategy})."
            )

        crop_fp = compute_crop_fingerprint(crop_win, strategy=strategy, safe_zone_margin=self.safe_zone_margin_h)

        return PostCropVerificationResult(
            is_valid=is_valid,
            crop_window=crop_win,
            source_bboxes=[b.to_dict() for b in bboxes],
            final_subject_positions=final_positions,
            retained_subject_ratio=round(min_retained, 4),
            safe_zone_passed=safe_zone_passed,
            rejection_reasons=rejection_reasons,
            primary_rejection_reason=primary_reason,
            explanation=expl,
            is_visible=(min_retained > 0.0),
            is_clipped=(min_retained < 0.999),
            crop_position={"x": crop_x, "y": crop_y, "w": crop_w, "h": crop_h},
            dimensions={"source": (sw, sh), "crop": (crop_w, crop_h)},
            crop_fingerprint=crop_fp,
        )


def compute_crop_fingerprint(
    crop_window: Union[CropWindow, Dict[str, Any]],
    strategy: str = "SUBJECT_AWARE_FULL_BLEED",
    safe_zone_margin: float = 0.05,
) -> str:
    """Computes a deterministic cryptographic fingerprint of the crop configuration."""
    if isinstance(crop_window, dict):
        src_w = crop_window.get("src_w", 1920)
        src_h = crop_window.get("src_h", 800)
        x = crop_window.get("x", 0)
        y = crop_window.get("y", 0)
        w = crop_window.get("w", 450)
        h = crop_window.get("h", 800)
        strat = crop_window.get("strategy", strategy)
    else:
        src_w = crop_window.src_w
        src_h = crop_window.src_h
        x = crop_window.x
        y = crop_window.y
        w = crop_window.w
        h = crop_window.h
        strat = getattr(crop_window, "strategy", strategy)

    raw = (
        f"{strat}:{src_w}x{src_h}->1080x1920:"
        f"x={x},y={y},w={w},h={h}:"
        f"safe_margin={safe_zone_margin:.3f}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
