"""
Localized Structural State-Transition Analyzer
Verifies physical state change (e.g. INTACT -> SHATTERED) within the localized object ROI.
Distinguishes 'already broken' from 'actually shatters during this clip'.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import cv2
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    EntityTrajectory,
    StateTransitionResult,
    ActionResult,
)
from py_visual_evidence.action_analyzers.base import BaseActionAnalyzer


class StructuralStateTransitionAnalyzer(BaseActionAnalyzer):
    def __init__(self, min_disruption_ratio: float = 1.35, min_burst_diff: float = 12.0):
        self.min_disruption_ratio = min_disruption_ratio
        self.min_burst_diff = min_burst_diff

    def analyze_action(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
        fps: float = 24.0,
    ) -> ActionResult:
        res = self.evaluate_state_transition(frames, trajectories, assertion)
        return ActionResult(
            action_name=assertion.action,
            detected=res.detected,
            confidence=round(min(0.98, 0.70 + (res.disruption_ratio * 0.15)) if res.detected else 0.15, 3),
            peak_metric_value=round(res.disruption_ratio, 3),
            threshold_used=self.min_disruption_ratio,
            details=res.details,
        )

    def evaluate_state_transition(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
    ) -> StateTransitionResult:
        if len(frames) < 6:
            return StateTransitionResult(
                detected=False,
                initial_state_metric=0.0,
                final_state_metric=0.0,
                disruption_ratio=1.0,
                details={"error": "Clip contains too few frames to evaluate temporal state transition."},
            )

        target_name = assertion.object.name if assertion.object and assertion.object.name in trajectories else assertion.subject.name
        traj = trajectories.get(target_name)

        img_h, img_w, _ = frames[0].shape
        n = len(frames)

        # Determine target bounding box ROI
        if traj and traj.points:
            # Use median bounding box of target object
            mid_pt = traj.points[len(traj.points) // 2]
            px_x, px_y, px_w, px_h = mid_pt.bbox.to_pixels(img_w, img_h)
            pad_x = int(px_w * 0.40)
            pad_y = int(px_h * 0.40)
            rx1 = max(0, px_x - pad_x)
            ry1 = max(0, px_y - pad_y)
            rx2 = min(img_w, px_x + px_w + pad_x)
            ry2 = min(img_h, px_y + px_h + pad_y)
        else:
            # Fallback to dominant center quadrant if object trajectory is not provided
            rx1, ry1, rx2, ry2 = int(img_w * 0.15), int(img_h * 0.20), int(img_w * 0.85), int(img_h * 0.80)

        # Extract localized grayscale ROIs
        rois = []
        for f in frames:
            crop = f[ry1:ry2, rx1:rx2]
            if crop.size > 0:
                rois.append(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))

        if not rois or len(rois) < 6:
            return StateTransitionResult(
                detected=False,
                initial_state_metric=0.0,
                final_state_metric=0.0,
                disruption_ratio=1.0,
                details={"error": "Invalid ROI size for state transition analysis."},
            )

        # Partition into BEFORE (first 20%), DURING (middle 60%), and AFTER (last 20%)
        split_b = max(2, int(n * 0.20))
        split_a = min(n - 2, int(n * 0.80))
        before_rois = rois[:split_b]
        during_rois = rois[split_b:split_a]
        after_rois = rois[split_a:]

        def get_edge_variance(roi_list):
            return [float(cv2.Laplacian(r, cv2.CV_64F).var()) for r in roi_list]

        before_vars = get_edge_variance(before_rois)
        during_vars = get_edge_variance(during_rois)
        after_vars = get_edge_variance(after_rois)

        before_mean = float(np.mean(before_vars))
        during_peak = float(np.max(during_vars))
        after_mean = float(np.mean(after_vars))

        # Peak inter-frame localized difference burst (captures explosive shattered fragments)
        diff_bursts = []
        for i in range(1, len(rois)):
            d = cv2.absdiff(rois[i - 1], rois[i])
            diff_bursts.append(float(np.mean(d)))
        peak_diff = float(np.max(diff_bursts)) if diff_bursts else 0.0

        # Disruption ratio compares the dynamic peak during the event against the initial baseline
        # In a shattering event, either edge variance spikes violently or catastrophic pixel displacement occurs
        var_ratio = during_peak / (before_mean + 1e-5)
        after_ratio = after_mean / (before_mean + 1e-5)

        # A true destruction event requires:
        # 1. High localized inter-frame difference burst (the shatter moment)
        # 2. Structural edge variance shift
        is_destruction = (peak_diff >= self.min_burst_diff) and (var_ratio >= self.min_disruption_ratio or peak_diff >= 22.0)

        # Distinguish 'already broken': if before_mean is already high and peak_diff is low, it was already broken
        is_already_broken = (before_mean > 50.0) and (peak_diff < (self.min_burst_diff * 0.6))
        if is_already_broken:
            is_destruction = False

        effective_ratio = max(var_ratio, peak_diff / 10.0)

        return StateTransitionResult(
            detected=is_destruction,
            initial_state_metric=round(before_mean, 2),
            final_state_metric=round(after_mean, 2),
            disruption_ratio=round(effective_ratio, 3),
            details={
                "target_entity": target_name,
                "before_edge_variance": round(before_mean, 2),
                "during_peak_variance": round(during_peak, 2),
                "after_edge_variance": round(after_mean, 2),
                "peak_frame_difference_burst": round(peak_diff, 2),
                "is_already_broken_at_start": is_already_broken,
                "is_destruction_transition": is_destruction,
            },
        )
