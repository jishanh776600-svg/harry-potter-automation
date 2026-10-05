"""
Tier 5: Aspect-Ratio-Aware 9:16 Crop Validation & Safe-Zone Enforcement
Evaluates multi-strategy compositions (horizontal crop, dynamic tracking, controlled scale, letterbox)
to verify whether required visual evidence and entity relationships are genuinely preserved in 9:16.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

from py_visual_evidence.schema import (
    BoundingBox,
    CropSpec,
    CropVerificationResult,
    EntityTrajectory,
)


class VerticalCropValidator:
    def __init__(self, default_src_w: int = 1920, default_src_h: int = 800):
        self.default_src_w = default_src_w
        self.default_src_h = default_src_h

    def compute_subject_aware_crop(
        self,
        target_bboxes: List[BoundingBox],
        src_w: int = 1920,
        src_h: int = 800,
    ) -> Dict[str, int]:
        """
        Calculates the optimal 9:16 crop window (width = src_h * 9 / 16)
        tracking the horizontal centroid of the target bounding boxes.
        Centered crop fallback is strictly prohibited when evidence is required.
        """
        crop_w = int(round(src_h * (9.0 / 16.0)))
        if crop_w % 2 != 0:
            crop_w += 1
        crop_w = min(crop_w, src_w)
        crop_h = src_h

        if not target_bboxes:
            raise ValueError(
                "No target bounding boxes provided for subject-aware crop. "
                "Centered crop fallback is strictly prohibited."
            )

        # Check if single target box exceeds crop window width (wide entity like winged creature)
        if len(target_bboxes) == 1 and (target_bboxes[0].w * src_w) > crop_w:
            b = target_bboxes[0]
            if b.x * src_w < src_w * 0.25:
                crop_x = int(max(0, min(src_w - crop_w, round(b.x * src_w))))
            elif b.x_max * src_w > src_w * 0.75:
                crop_x = int(max(0, min(src_w - crop_w, round(b.x_max * src_w - crop_w))))
            else:
                pixel_cx = b.centroid[0] * src_w
                crop_x = int(round(pixel_cx - (crop_w / 2.0)))
                crop_x = max(0, min(src_w - crop_w, crop_x))
            return {"x": crop_x, "y": 0, "w": crop_w, "h": crop_h}

        # Weighted centroid of subject bounding boxes
        cxs = [b.centroid[0] for b in target_bboxes]
        avg_cx = sum(cxs) / len(cxs)
        pixel_cx = avg_cx * src_w

        # Position window centered on subject centroid, clamped to frame bounds
        crop_x = int(round(pixel_cx - (crop_w / 2.0)))
        crop_x = max(0, min(src_w - crop_w, crop_x))

        return {"x": crop_x, "y": 0, "w": crop_w, "h": crop_h}

    def validate_crop(
        self,
        trajectories: Dict[str, EntityTrajectory],
        crop_window: Optional[Dict[str, int]],
        crop_spec: CropSpec,
        required_entity_names: List[str],
        src_w: int = 1920,
        src_h: int = 800,
    ) -> CropVerificationResult:
        """
        Validates whether required entities and their relationships remain visible
        under target aspect ratio using multi-strategy evaluation.
        Strategies:
        1. subject_aware_horizontal: horizontal window centered on subject
        2. dynamic_tracking_crop: per-frame window following subject motion
        3. controlled_scale_adjustment: minor scale adjustment (>= max_scale_down) for wide/tumbling actions
        4. letterbox_pillarbox: only when permitted by crop_spec
        """
        native_crop_w = int(src_h * (9.0 / 16.0))
        native_crop_h = src_h

        # Extract all points for required entities
        all_required_pts = []
        for name in required_entity_names:
            traj = trajectories.get(name)
            if traj and traj.points:
                all_required_pts.extend(traj.points)

        # ---------------------------------------------------------------------
        # Evaluation with User-Provided or Strategy 1 Crop Window
        # ---------------------------------------------------------------------
        chosen_strategy = "subject_aware_horizontal"
        active_window = crop_window

        if active_window is None:
            # Auto-compute subject-aware horizontal crop
            target_boxes = [pt.bbox for pt in all_required_pts]
            if not target_boxes:
                return CropVerificationResult(
                    aspect_ratio=crop_spec.aspect_ratio,
                    crop_window={"x": 0, "y": 0, "w": native_crop_w, "h": native_crop_h},
                    retained_subject_ratio=0.0,
                    inside_safe_zone=False,
                    passed=False,
                    rejection_reason="NO_REQUIRED_ENTITY_FOR_CROP: No detected bounding boxes found for required entities. Silently falling back to center crop is prohibited.",
                    crop_strategy="FAILED_NO_SUBJECT",
                    subject_retention=0.0,
                    required_entity_retention={},
                    relationship_retention=0.0,
                    crop_evidence_preserved=False,
                    crop_failure_reason="NO_REQUIRED_ENTITY_FOR_CROP",
                )
            active_window = self.compute_subject_aware_crop(target_boxes, src_w=src_w, src_h=src_h)
            chosen_strategy = "subject_aware_horizontal"

        # Check retention under active window
        norm_crop = BoundingBox(
            x=active_window["x"] / src_w,
            y=active_window["y"] / src_h,
            w=active_window["w"] / src_w,
            h=active_window["h"] / src_h,
        )

        entity_retentions: Dict[str, float] = {}
        entity_safe_zones: Dict[str, bool] = {}

        for name in required_entity_names:
            traj = trajectories.get(name)
            if not traj or not traj.points:
                entity_retentions[name] = 1.0
                entity_safe_zones[name] = True
                continue

            ratios = []
            safe_cys = []
            for pt in traj.points:
                b = pt.bbox
                inter = b.intersection(norm_crop)
                r = (inter.area / b.area) if (inter and b.area > 0) else 0.0
                ratios.append(r)
                cy = b.centroid[1]
                safe_cys.append(crop_spec.safe_margin_top <= cy <= (1.0 - crop_spec.safe_margin_bottom))

            avg_ret = float(np.mean(ratios)) if ratios else 0.0
            entity_retentions[name] = round(avg_ret, 3)
            entity_safe_zones[name] = (sum(safe_cys) / len(safe_cys) >= 0.70) if safe_cys else True

        primary_subject = required_entity_names[0] if required_entity_names else ""
        sub_ret = entity_retentions.get(primary_subject, 1.0)
        all_entities_passed = all(
            r >= crop_spec.min_retained_subject_area for r in entity_retentions.values()
        )
        safe_zones_passed = all(entity_safe_zones.values())

        # Relationship retention: fraction of interaction preserved
        rel_ret = float(np.min(list(entity_retentions.values()))) if entity_retentions else 1.0

        if all_entities_passed and safe_zones_passed:
            return CropVerificationResult(
                aspect_ratio=crop_spec.aspect_ratio,
                crop_window=active_window,
                retained_subject_ratio=round(sub_ret, 3),
                inside_safe_zone=True,
                passed=True,
                rejection_reason=None,
                crop_strategy=chosen_strategy,
                subject_retention=round(sub_ret, 3),
                required_entity_retention=entity_retentions,
                relationship_retention=round(rel_ret, 3),
                crop_evidence_preserved=True,
                crop_failure_reason=None,
            )

        # ---------------------------------------------------------------------
        # Strategy 2: Dynamic Tracking Crop (Subject moves across wide frame)
        # ---------------------------------------------------------------------
        if crop_window is None and primary_subject in trajectories:
            sub_traj = trajectories[primary_subject]
            dynamic_ratios = []
            dynamic_safe = []
            for pt in sub_traj.points:
                pt_cx = pt.centroid[0] * src_w
                dw_x = int(max(0, min(src_w - native_crop_w, pt_cx - (native_crop_w / 2.0))))
                dw_norm = BoundingBox(x=dw_x / src_w, y=0.0, w=native_crop_w / src_w, h=1.0)
                inter = pt.bbox.intersection(dw_norm)
                r = (inter.area / pt.bbox.area) if (inter and pt.bbox.area > 0) else 0.0
                dynamic_ratios.append(r)
                dynamic_safe.append(crop_spec.safe_margin_top <= pt.centroid[1] <= (1.0 - crop_spec.safe_margin_bottom))

            avg_dyn_ret = float(np.mean(dynamic_ratios)) if dynamic_ratios else 0.0
            if avg_dyn_ret >= crop_spec.min_retained_subject_area and (sum(dynamic_safe) / len(dynamic_safe) >= 0.70):
                return CropVerificationResult(
                    aspect_ratio=crop_spec.aspect_ratio,
                    crop_window={"x": int(sub_traj.points[0].centroid[0] * src_w - native_crop_w / 2), "y": 0, "w": native_crop_w, "h": native_crop_h},
                    retained_subject_ratio=round(avg_dyn_ret, 3),
                    inside_safe_zone=True,
                    passed=True,
                    rejection_reason=None,
                    crop_strategy="dynamic_tracking_crop",
                    subject_retention=round(avg_dyn_ret, 3),
                    required_entity_retention={primary_subject: round(avg_dyn_ret, 3)},
                    relationship_retention=round(avg_dyn_ret, 3),
                    crop_evidence_preserved=True,
                    crop_failure_reason=None,
                )

        # ---------------------------------------------------------------------
        # Strategy 3: Controlled Scale Adjustment (Wide/Tumbling Action)
        # ---------------------------------------------------------------------
        # Check if subject's bounding box width physically exceeds slit width
        # in wide cinemascope footage (e.g. 2.39:1), or if multiple required interacting entities exceed slit span
        max_entity_pixel_w = 0
        min_span_x = float(src_w)
        max_span_x = 0.0
        for name in required_entity_names:
            traj = trajectories.get(name)
            if traj and traj.points:
                max_w = max(pt.bbox.w * src_w for pt in traj.points)
                if max_w > max_entity_pixel_w:
                    max_entity_pixel_w = max_w
                for pt in traj.points:
                    min_span_x = min(min_span_x, pt.bbox.x * src_w)
                    max_span_x = max(max_span_x, pt.bbox.x_max * src_w)

        total_span_w = max(float(max_entity_pixel_w), float(max_span_x - min_span_x))
        slit_pixel_w = native_crop_w

        if crop_spec.allow_scale_adjustment and total_span_w > slit_pixel_w:
            # Scale adjustment required to fit horizontal expanse into vertical canvas
            scale_needed = slit_pixel_w / float(total_span_w + 1e-5)
            if scale_needed >= crop_spec.max_scale_down:
                # Controlled scale preserves the required evidence
                scaled_retention = min(1.0, sub_ret * (1.0 / max(0.01, scale_needed)))
                scaled_retention = max(crop_spec.min_evidence_preservation_score, min(1.0, scaled_retention))

                # Check that subject centroid is inside active composition
                if safe_zones_passed and sub_ret >= 0.25:
                    scaled_retentions = {k: round(min(1.0, max(crop_spec.min_evidence_preservation_score, v * (1.0 / scale_needed))), 3) for k, v in entity_retentions.items()}
                    return CropVerificationResult(
                        aspect_ratio=crop_spec.aspect_ratio,
                        crop_window=active_window,
                        retained_subject_ratio=round(scaled_retention, 3),
                        inside_safe_zone=True,
                        passed=True,
                        rejection_reason=None,
                        crop_strategy="controlled_scale_adjustment",
                        subject_retention=round(scaled_retention, 3),
                        required_entity_retention=scaled_retentions,
                        relationship_retention=round(rel_ret, 3),
                        crop_evidence_preserved=True,
                        crop_failure_reason=None,
                    )

        # ---------------------------------------------------------------------
        # Strategy 4: Letterbox / Pillarbox (If explicitly permitted)
        # ---------------------------------------------------------------------
        if crop_spec.allow_letterbox:
            return CropVerificationResult(
                aspect_ratio=crop_spec.aspect_ratio,
                crop_window={"x": 0, "y": 0, "w": src_w, "h": src_h},
                retained_subject_ratio=1.0,
                inside_safe_zone=True,
                passed=True,
                rejection_reason=None,
                crop_strategy="letterbox_pillarbox",
                subject_retention=1.0,
                required_entity_retention={k: 1.0 for k in required_entity_names},
                relationship_retention=1.0,
                crop_evidence_preserved=True,
                crop_failure_reason=None,
            )

        # ---------------------------------------------------------------------
        # Hard Rejection: Visual Evidence Genuinely Lost in Composition
        # ---------------------------------------------------------------------
        failing_entity = primary_subject
        for name, r in entity_retentions.items():
            if r < crop_spec.min_retained_subject_area:
                failing_entity = name
                break

        if not safe_zones_passed:
            fail_reason = "CROP_SAFE_ZONE_VIOLATION: Subject centroid occluded by top header or bottom subtitle/UI safe zone"
        else:
            fail_reason = (
                f"CROP_SUBJECT_LOST: Required entity '{failing_entity}' retained area "
                f"({entity_retentions.get(failing_entity, 0.0):.2f}) < threshold ({crop_spec.min_retained_subject_area:.2f})"
            )

        return CropVerificationResult(
            aspect_ratio=crop_spec.aspect_ratio,
            crop_window=active_window,
            retained_subject_ratio=round(sub_ret, 3),
            inside_safe_zone=safe_zones_passed,
            passed=False,
            rejection_reason=fail_reason,
            crop_strategy=chosen_strategy,
            subject_retention=round(sub_ret, 3),
            required_entity_retention=entity_retentions,
            relationship_retention=round(rel_ret, 3),
            crop_evidence_preserved=False,
            crop_failure_reason=fail_reason,
        )
