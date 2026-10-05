"""
Kinematic Motion & Gesture Analyzer (Wave, Swing, Sweep, Punch, Strike)
Distinguishes stationary holding from active movement/waving via localized ROI velocity,
and verifies recipient-directed impact convergence for physical strikes (punches/hits).
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


class KinematicMotionAnalyzer(BaseActionAnalyzer):
    def __init__(self, min_peak_velocity: float = 0.45, min_mean_velocity: float = 0.15):
        # Velocities are normalized screen units per second
        self.min_peak_velocity = min_peak_velocity
        self.min_mean_velocity = min_mean_velocity

    def analyze_action(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
        fps: float = 24.0,
    ) -> ActionResult:
        # Determine target entity to track motion for (evaluate object and subject, selecting the most kinematically active entity)
        candidate_names = []
        if assertion.object and assertion.object.name in trajectories:
            candidate_names.append(assertion.object.name)
        if assertion.subject and assertion.subject.name in trajectories:
            candidate_names.append(assertion.subject.name)

        target_name = assertion.subject.name
        best_p_vel = -1.0
        for c_name in candidate_names:
            c_traj = trajectories.get(c_name)
            if c_traj and c_traj.peak_velocity > best_p_vel:
                best_p_vel = c_traj.peak_velocity
                target_name = c_name

        traj = trajectories.get(target_name)

        if not traj or len(traj.points) < 3:
            return ActionResult(
                action_name=assertion.action,
                detected=False,
                confidence=0.0,
                peak_metric_value=0.0,
                threshold_used=self.min_peak_velocity,
                details={"error": f"No valid trajectory found for target '{target_name}' to analyze motion."},
            )

        # 1. Trajectory Velocity (excluding single boundary frames to avoid cut transition noise)
        int_pts = traj.points[1:-1] if len(traj.points) > 3 else traj.points
        vels = [((p.velocity[0] ** 2) + (p.velocity[1] ** 2)) ** 0.5 for p in int_pts]
        peak_vel = float(np.percentile(vels, 95)) if vels else 0.0
        mean_vel = float(np.mean(vels)) if vels else 0.0

        # 2. Localized Optical Flow inside Target Bounding Box
        roi_flow_peaks = []
        img_h, img_w, _ = frames[0].shape

        for i in range(1, len(frames)):
            f_prev = frames[i - 1]
            f_curr = frames[i]
            pt = traj.points[i]

            px_x, px_y, px_w, px_h = pt.bbox.to_pixels(img_w, img_h)
            # Expand ROI slightly by 20% to capture wand sweep / hand motion
            pad_x = int(px_w * 0.20)
            pad_y = int(px_h * 0.20)
            rx1 = max(0, px_x - pad_x)
            ry1 = max(0, px_y - pad_y)
            rx2 = min(img_w, px_x + px_w + pad_x)
            ry2 = min(img_h, px_y + px_h + pad_y)

            if (rx2 - rx1) > 5 and (ry2 - ry1) > 5:
                roi_prev = cv2.cvtColor(f_prev[ry1:ry2, rx1:rx2], cv2.COLOR_BGR2GRAY)
                roi_curr = cv2.cvtColor(f_curr[ry1:ry2, rx1:rx2], cv2.COLOR_BGR2GRAY)
                flow = cv2.calcOpticalFlowFarneback(roi_prev, roi_curr, None, 0.5, 2, 9, 2, 5, 1.1, 0)
                mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                roi_flow_peaks.append(float(np.percentile(mag, 95)))

        mean_roi_flow = float(np.mean(roi_flow_peaks)) if roi_flow_peaks else 0.0
        peak_roi_flow = float(np.max(roi_flow_peaks)) if roi_flow_peaks else 0.0

        # Base active motion detection
        has_active_motion = (
            (peak_vel >= self.min_peak_velocity and mean_vel >= self.min_mean_velocity)
            or (peak_roi_flow > 4.5 and mean_roi_flow > 1.8)
        )

        # 3. Recipient-Directed Strike / Impact Verification
        # For physical strikes (punch, strike, hit) against a named recipient:
        action_lower = assertion.action.lower()
        is_strike_action = any(w in action_lower for w in ("punch", "strike", "hit", "smash", "slap"))
        rec_name = assertion.recipient.name if assertion.recipient else None
        rec_traj = trajectories.get(rec_name) if rec_name else None

        strike_details = {}
        if is_strike_action and rec_traj and len(rec_traj.points) >= 3:
            num_pts = min(len(traj.points), len(rec_traj.points))
            sub_rec_dists = [
                float(np.linalg.norm(np.array(traj.points[i].centroid) - np.array(rec_traj.points[i].centroid)))
                for i in range(num_pts)
            ]
            start_dist = sub_rec_dists[0]
            min_dist = min(sub_rec_dists)
            dist_delta = start_dist - min_dist

            rec_vels = [((p.velocity[0] ** 2) + (p.velocity[1] ** 2)) ** 0.5 for p in rec_traj.points[1:-1]]
            rec_peak_vel = float(np.percentile(rec_vels, 95)) if rec_vels else 0.0

            strike_details = {
                "strike_distance_delta": round(dist_delta, 3),
                "closest_approach_dist": round(min_dist, 3),
                "recipient_recoil_velocity": round(rec_peak_vel, 3),
            }

            # A physical strike requires:
            # - Rapid closure towards recipient (dist_delta >= 0.045 with strike velocity), OR
            # - Observable recipient recoil (recoil velocity >= min_peak_velocity with contact)
            is_genuine_strike = (
                (dist_delta >= 0.045 and peak_vel >= self.min_peak_velocity)
                or (rec_peak_vel >= self.min_peak_velocity and min_dist <= 0.40)
            )

            # In a static standoff (distance delta < 0.04 and no recipient recoil), reject strike
            if not is_genuine_strike:
                has_active_motion = False

        confidence = 0.0
        if has_active_motion:
            confidence = min(0.98, 0.70 + (peak_vel / (self.min_peak_velocity * 2.0)) * 0.25)
        else:
            confidence = max(0.10, 0.40 * (peak_vel / (self.min_peak_velocity + 1e-5)))

        details = {
            "target_entity": target_name,
            "peak_trajectory_velocity": round(peak_vel, 3),
            "mean_trajectory_velocity": round(mean_vel, 3),
            "peak_roi_flow": round(peak_roi_flow, 2),
            "mean_roi_flow": round(mean_roi_flow, 2),
            "is_stationary": not has_active_motion,
        }
        details.update(strike_details)

        return ActionResult(
            action_name=assertion.action,
            detected=has_active_motion,
            confidence=round(confidence, 3),
            peak_metric_value=round(max(peak_vel, peak_roi_flow / 10.0), 3),
            threshold_used=self.min_peak_velocity,
            details=details,
        )
