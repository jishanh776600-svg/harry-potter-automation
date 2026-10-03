"""
STORY FORGE — Pose & Body Kinematics Analyzer
=============================================
Extracts anatomical keypoints (shoulders, elbows, wrists, hips) and derives
physical kinematic metrics:
  - Elbow extension angle during punches/strikes
  - Wrist velocity towards target entity
  - Wrist-to-target distance trajectory
  - Graceful degradation under occlusion, side angles, and motion blur
"""

from __future__ import annotations
import math
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from py_visual_evidence.schema import BoundingBox
from engines.action.models import (
    Keypoint,
    PoseKeypoints,
    LimbKinematics,
)

logger = logging.getLogger("PoseKinematics")


class PoseKinematicsAnalyzer:
    """
    Computes body kinematics from detected anatomical keypoints.
    Designed for movie footage with occlusions, rapid motion, and partial bodies.
    """

    def __init__(self, min_keypoint_confidence: float = 0.30):
        self.min_keypoint_confidence = min_keypoint_confidence

    @staticmethod
    def calculate_angle(p1: Keypoint, p2: Keypoint, p3: Keypoint) -> float:
        """
        Calculates the angle (in degrees) at joint p2 formed by (p1 -> p2) and (p3 -> p2).
        For example: p1=shoulder, p2=elbow, p3=wrist -> elbow extension angle.
        """
        v1 = (p1.x - p2.x, p1.y - p2.y)
        v2 = (p3.x - p2.x, p3.y - p2.y)
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
        mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
        if mag1 < 1e-6 or mag2 < 1e-6:
            return 180.0
        cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.degrees(math.acos(cos_angle))

    def derive_arm_kinematics(
        self,
        pose_sequence: List[PoseKeypoints],
        target_centroids: Optional[List[Tuple[float, float]]] = None,
        timestamps: Optional[List[float]] = None,
        side: str = "right",  # "right" or "left"
    ) -> List[LimbKinematics]:
        """
        Derives frame-by-frame limb kinematics for an arm (elbow extension, wrist velocity,
        and velocity directed toward a target).
        """
        results: List[LimbKinematics] = []
        if not pose_sequence:
            return results

        n = len(pose_sequence)
        for i in range(n):
            pose = pose_sequence[i]
            ts = timestamps[i] if (timestamps and i < len(timestamps)) else pose.timestamp_sec

            if side == "right":
                shoulder = pose.right_shoulder
                elbow = pose.right_elbow
                wrist = pose.right_wrist
            else:
                shoulder = pose.left_shoulder
                elbow = pose.left_elbow
                wrist = pose.left_wrist

            # 1. Elbow extension angle
            extension_angle = 120.0  # neutral default
            if shoulder and elbow and wrist:
                if (shoulder.confidence >= self.min_keypoint_confidence and
                    elbow.confidence >= self.min_keypoint_confidence and
                    wrist.confidence >= self.min_keypoint_confidence):
                    extension_angle = self.calculate_angle(shoulder, elbow, wrist)

            # 2. Wrist velocity
            vx, vy = 0.0, 0.0
            speed = 0.0
            if i > 0 and wrist:
                prev_pose = pose_sequence[i - 1]
                prev_wrist = prev_pose.right_wrist if side == "right" else prev_pose.left_wrist
                if prev_wrist and prev_wrist.confidence >= self.min_keypoint_confidence:
                    prev_ts = timestamps[i - 1] if (timestamps and (i - 1) < len(timestamps)) else prev_pose.timestamp_sec
                    dt = ts - prev_ts
                    if dt > 0.001:
                        vx = (wrist.x - prev_wrist.x) / dt
                        vy = (wrist.y - prev_wrist.y) / dt
                        speed = math.sqrt(vx * vx + vy * vy)

            # 3. Distance and velocity toward target
            v_toward = 0.0
            dist_to_target = None
            if target_centroids and i < len(target_centroids) and wrist:
                target_c = target_centroids[i]
                dx = target_c[0] - wrist.x
                dy = target_c[1] - wrist.y
                dist_to_target = math.sqrt(dx * dx + dy * dy)

                if dist_to_target > 1e-4 and speed > 0.0:
                    # Unit vector toward target
                    ux = dx / dist_to_target
                    uy = dy / dist_to_target
                    # Dot product of velocity with direction toward target
                    v_toward = vx * ux + vy * uy

            results.append(LimbKinematics(
                limb_name=f"{side}_arm",
                extension_angle_deg=round(extension_angle, 2),
                wrist_velocity=(round(vx, 4), round(vy, 4)),
                wrist_speed=round(speed, 4),
                velocity_toward_target=round(v_toward, 4),
                distance_to_target=round(dist_to_target, 4) if dist_to_target is not None else None,
            ))

        return results

    @classmethod
    def evaluate_punch_kinematics(
        cls,
        right_kinematics: List[LimbKinematics],
        left_kinematics: List[LimbKinematics],
    ) -> Dict[str, Any]:
        """
        Checks whether either arm exhibited punch kinematics:
          - Peak velocity directed towards target (> 0.20 units/sec)
          - Elbow extension (angle increases toward 150-180 deg)
          - Wrist distance decreasing to minimum proximity
        """
        for side, kin_list in [("right", right_kinematics), ("left", left_kinematics)]:
            if not kin_list:
                continue

            v_towards = [k.velocity_toward_target for k in kin_list]
            angles = [k.extension_angle_deg for k in kin_list]
            distances = [k.distance_to_target for k in kin_list if k.distance_to_target is not None]

            max_v_toward = max(v_towards) if v_towards else 0.0
            max_angle = max(angles) if angles else 0.0

            # Distance decrease
            dist_decreased = False
            if len(distances) >= 2:
                initial_d = distances[0]
                min_d = min(distances)
                if initial_d - min_d > 0.05:
                    dist_decreased = True

            if max_v_toward > 0.20 and (dist_decreased or max_angle > 140.0):
                return {
                    "is_strike_kinematics": True,
                    "active_limb": f"{side}_arm",
                    "peak_velocity_toward_target": round(max_v_toward, 4),
                    "peak_extension_angle": round(max_angle, 2),
                    "distance_converged": dist_decreased,
                }

        return {
            "is_strike_kinematics": False,
            "active_limb": None,
            "peak_velocity_toward_target": 0.0,
            "peak_extension_angle": 0.0,
            "distance_converged": False,
        }
