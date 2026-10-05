"""
Handover & Object Transfer Action Analyzer
Evaluates spatial trajectory, multi-signal evidence, and adaptive lighting normalization
between Subject -> Object -> Recipient.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import cv2
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    EntityTrajectory,
    ActionResult,
)
from py_visual_evidence.action_analyzers.base import BaseActionAnalyzer


class HandoverActionAnalyzer(BaseActionAnalyzer):
    def __init__(self, contact_threshold: float = 0.28, min_transfer_delta: float = 0.08):
        self.contact_threshold = contact_threshold
        self.min_transfer_delta = min_transfer_delta

    def analyze_action(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
        fps: float = 24.0,
    ) -> ActionResult:
        sub_name = assertion.subject.name
        obj_name = assertion.object.name if assertion.object else None
        rec_name = assertion.recipient.name if assertion.recipient else None

        if not rec_name or not obj_name:
            return ActionResult(
                action_name="handover",
                detected=False,
                confidence=0.0,
                peak_metric_value=0.0,
                threshold_used=self.contact_threshold,
                details={"error": "Handover requires both an object and a recipient in the assertion."},
            )

        sub_traj = trajectories.get(sub_name)
        obj_traj = trajectories.get(obj_name)
        rec_traj = trajectories.get(rec_name)

        if not sub_traj or not obj_traj or not rec_traj:
            missing = []
            if not sub_traj: missing.append(sub_name)
            if not obj_traj: missing.append(obj_name)
            if not rec_traj: missing.append(rec_name)
            return ActionResult(
                action_name="handover",
                detected=False,
                confidence=0.0,
                peak_metric_value=0.0,
                threshold_used=self.contact_threshold,
                details={"error": f"Missing trajectories for required handover entities: {missing}"},
            )

        num_pts = min(len(sub_traj.points), len(obj_traj.points), len(rec_traj.points))
        if num_pts < 3:
            return ActionResult(
                action_name="handover",
                detected=False,
                confidence=0.0,
                peak_metric_value=0.0,
                threshold_used=self.contact_threshold,
                details={"error": "Insufficient trajectory points to verify handover."},
            )

        # ---------------------------------------------------------------------
        # 1. Lighting Condition & Contrast Assessment
        # ---------------------------------------------------------------------
        lum_samples = []
        if frames:
            step = max(1, len(frames) // 5)
            for f in frames[::step]:
                gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
                lum_samples.append(float(np.mean(gray)))
        avg_lum = float(np.mean(lum_samples)) if lum_samples else 128.0

        if avg_lum < 75.0:
            lighting_condition = "low_light"
        elif avg_lum > 185.0:
            lighting_condition = "high_contrast"
        else:
            lighting_condition = "normal"

        # ---------------------------------------------------------------------
        # 2. Spatio-Temporal Distance Metrics
        # ---------------------------------------------------------------------
        distances_to_recipient = []
        distances_to_subject = []
        for i in range(num_pts):
            p_obj = np.array(obj_traj.points[i].centroid)
            p_rec = np.array(rec_traj.points[i].centroid)
            p_sub = np.array(sub_traj.points[i].centroid)

            d_rec = float(np.linalg.norm(p_obj - p_rec))
            d_sub = float(np.linalg.norm(p_obj - p_sub))
            distances_to_recipient.append(d_rec)
            distances_to_subject.append(d_sub)

        start_dist_rec = distances_to_recipient[0]
        min_dist_rec = min(distances_to_recipient)
        end_dist_rec = min_dist_rec
        min_idx = int(np.argmin(distances_to_recipient))
        transfer_delta = start_dist_rec - min_dist_rec

        start_dist_sub = distances_to_subject[0]
        end_dist_sub = distances_to_subject[min_idx]

        # Monotonic approach ratio up to arrival
        pre_arrival_dists = distances_to_recipient[: min_idx + 1]
        if len(pre_arrival_dists) > 2:
            approach_steps = sum(
                1 for i in range(1, len(pre_arrival_dists))
                if pre_arrival_dists[i] <= pre_arrival_dists[i - 1] + 0.02
            )
            monotonic_ratio = approach_steps / float(len(pre_arrival_dists) - 1)
        else:
            approach_steps = sum(
                1 for i in range(1, len(distances_to_recipient))
                if distances_to_recipient[i] <= distances_to_recipient[i - 1] + 0.015
            )
            monotonic_ratio = approach_steps / float(len(distances_to_recipient) - 1)

        # ---------------------------------------------------------------------
        # 3. Independent Multi-Signal Construction
        # ---------------------------------------------------------------------
        # Signal 1: Motion signal (approach distance & monotonicity)
        motion_signal = max(0.0, transfer_delta)
        norm_factor = 1.25 if lighting_condition == "low_light" else 1.0
        normalized_motion_signal = min(1.0, (motion_signal * norm_factor) + (0.10 if monotonic_ratio >= 0.60 else 0.0))

        # In low-light / cinema framing, wide actor bounding boxes yield centroid offsets
        starts_near_subject = start_dist_sub <= (start_dist_rec + 0.15)
        contact_margin = 0.09 if lighting_condition == "low_light" else 0.07
        reaches_recipient = min_dist_rec <= (self.contact_threshold + contact_margin)
        leaves_subject = (end_dist_sub >= start_dist_sub - 0.06)
        relationship_signal = 1.0 if (starts_near_subject and reaches_recipient and leaves_subject) else 0.0

        # Signal 3: State persistence signal (Object remains with recipient across interaction window)
        post_arrival = distances_to_recipient[min_idx : min(len(distances_to_recipient), min_idx + int(fps * 0.75) + 1)]
        if len(post_arrival) < 3:
            post_arrival = distances_to_recipient[max(0, min_idx - 2) : min(len(distances_to_recipient), min_idx + 3)]
        persisting_frames = sum(
            1 for d in post_arrival if d <= (self.contact_threshold + contact_margin + 0.03)
        )
        state_signal = (persisting_frames / float(len(post_arrival))) if post_arrival else 0.0

        # ---------------------------------------------------------------------
        # 4. Adaptive Handover Verdict
        # ---------------------------------------------------------------------
        # Fast / High-displacement handover
        is_fast_handover = (
            starts_near_subject
            and reaches_recipient
            and transfer_delta >= self.min_transfer_delta
        )

        # Slow / Low-light handover: multi-signal convergence required
        is_slow_handover = (
            starts_near_subject
            and reaches_recipient
            and leaves_subject
            and transfer_delta >= 0.028
            and monotonic_ratio >= 0.60
            and state_signal >= 0.65
        )

        # Hard fail-closed rejection conditions:
        # - Object merely held in place: transfer_delta < 0.02
        # - Object starts at recipient without transfer: start_dist_rec <= 0.15 and transfer_delta < 0.02
        # - Distance to recipient increases (moving away): transfer_delta <= 0.0
        is_merely_held = transfer_delta < 0.025
        is_moving_away = transfer_delta <= 0.0
        no_transfer_occurred = is_merely_held or is_moving_away

        is_handover = (is_fast_handover or is_slow_handover) and not no_transfer_occurred

        # Handover Confidence
        if is_handover:
            handover_confidence = round(
                min(
                    0.98,
                    0.35 * normalized_motion_signal
                    + 0.40 * relationship_signal
                    + 0.25 * state_signal
                    + 0.45,
                ),
                3,
            )
        else:
            handover_confidence = 0.0

        return ActionResult(
            action_name="handover",
            detected=is_handover,
            confidence=handover_confidence,
            peak_metric_value=round(transfer_delta, 3),
            threshold_used=self.min_transfer_delta,
            details={
                "motion_signal": round(motion_signal, 3),
                "relationship_signal": round(relationship_signal, 3),
                "state_signal": round(state_signal, 3),
                "lighting_condition": lighting_condition,
                "normalized_motion_signal": round(normalized_motion_signal, 3),
                "handover_confidence": handover_confidence,
                "start_distance_to_recipient": round(start_dist_rec, 3),
                "end_distance_to_recipient": round(end_dist_rec, 3),
                "transfer_distance_delta": round(transfer_delta, 3),
                "starts_near_subject": starts_near_subject,
                "reaches_recipient": reaches_recipient,
                "monotonic_ratio": round(monotonic_ratio, 3),
                "is_fast_handover": is_fast_handover,
                "is_slow_handover": is_slow_handover,
            },
        )
