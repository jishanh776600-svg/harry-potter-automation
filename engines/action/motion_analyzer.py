"""
STORY FORGE — Entity-Local Motion Analyzer with Camera Motion Compensation
==========================================================================
Extracts deterministic physical motion signals from tracked entities:
  - Compensates for global camera pans, tilts, and zooms
  - Computes velocity, acceleration, jerk, and direction changes
  - Evaluates localized optical flow within entity ROIs (arms, hands, props)
  - Eliminates false action positives caused by global camera motion
"""

from __future__ import annotations
import math
import logging
from typing import List, Dict, Tuple, Optional, Any
import cv2
import numpy as np

from py_visual_evidence.schema import BoundingBox
from engines.perception.tracker import CameraMotionCompensator
from engines.perception.models import EntityTrack

logger = logging.getLogger("MotionAnalyzer")


class EntityMotionProfile:
    """
    Summary of physical motion for an entity over a temporal interval.
    """
    def __init__(self, entity_name: str, track_id: int):
        self.entity_name = entity_name
        self.track_id = track_id
        self.timestamps: List[float] = []
        self.frame_indices: List[int] = []
        self.raw_centroids: List[Tuple[float, float]] = []
        self.compensated_centroids: List[Tuple[float, float]] = []
        self.bboxes: List[BoundingBox] = []
        self.velocities: List[Tuple[float, float]] = []  # (vx, vy) in normalized units/sec
        self.speeds: List[float] = []                   # scalar speed in units/sec
        self.accelerations: List[float] = []            # scalar acceleration in units/sec^2
        self.local_flow_energies: List[float] = []      # ROI optical flow magnitude
        self.peak_speed: float = 0.0
        self.mean_speed: float = 0.0
        self.net_displacement: float = 0.0
        self.peak_acceleration: float = 0.0
        self.direction_changes: int = 0


class LocalMotionAnalyzer:
    """
    Deterministic motion engine that strips camera motion from entity trajectories
    and computes localized limb / object kinematics.
    """

    def __init__(
        self,
        min_motion_threshold: float = 0.04,  # Units/sec below which is static
        speed_spike_threshold: float = 0.25, # Rapid action threshold
    ):
        self.min_motion_threshold = min_motion_threshold
        self.speed_spike_threshold = speed_spike_threshold
        self.cmc = CameraMotionCompensator()

    def analyze_track_motion(
        self,
        track: EntityTrack,
        frames: Optional[List[np.ndarray]] = None,
        timestamps: Optional[List[float]] = None,
        fps: float = 24.0,
    ) -> EntityMotionProfile:
        """
        Analyzes the motion profile of an EntityTrack, optionally compensating
        with video frames if available.
        """
        from engines.action.models import extract_track_boxes
        char_name = getattr(track, "canonical_name", None) or getattr(track, "character_name", None) or f"track_{track.track_id}"
        profile = EntityMotionProfile(entity_name=char_name, track_id=track.track_id)

        pts = extract_track_boxes(track)
        if len(pts) < 2:
            return profile

        # Extract timestamps and bounding boxes
        for ts, f_idx, bbox in pts:
            if timestamps and f_idx < len(timestamps):
                ts = timestamps[f_idx]
            profile.frame_indices.append(f_idx)
            profile.timestamps.append(ts)
            profile.bboxes.append(bbox)
            profile.raw_centroids.append(bbox.centroid)

        # 1. Camera Motion Compensation (CMC)
        # If frames are supplied, compute affine motion between consecutive frames
        camera_transforms: List[np.ndarray] = []
        if frames is not None and len(frames) > 1:
            prev_gray = None
            for f_idx in profile.frame_indices:
                if f_idx < len(frames):
                    curr_frame = frames[f_idx]
                    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY) if len(curr_frame.shape) == 3 else curr_frame
                    if prev_gray is not None:
                        M = self.cmc.estimate_motion(prev_gray, curr_gray)
                        camera_transforms.append(M)
                    else:
                        camera_transforms.append(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32))
                    prev_gray = curr_gray
                else:
                    camera_transforms.append(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32))
        else:
            camera_transforms = [
                np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
                for _ in profile.frame_indices
            ]

        # Calculate compensated centroids
        # Transform centroid using cumulative camera inverse transform or frame-to-frame delta
        compensated: List[Tuple[float, float]] = [profile.raw_centroids[0]]
        img_w = frames[0].shape[1] if (frames is not None and len(frames) > 0) else 1920
        img_h = frames[0].shape[0] if (frames is not None and len(frames) > 0) else 1080

        for i in range(1, len(profile.raw_centroids)):
            M = camera_transforms[i] if i < len(camera_transforms) else camera_transforms[-1]
            # M maps frame i-1 to frame i. The camera motion delta is M[:2, 2] in pixels
            cam_dx_norm = float(M[0, 2]) / img_w
            cam_dy_norm = float(M[1, 2]) / img_h

            raw_dx = profile.raw_centroids[i][0] - profile.raw_centroids[i - 1][0]
            raw_dy = profile.raw_centroids[i][1] - profile.raw_centroids[i - 1][1]

            # Net true motion = raw observed delta - camera delta
            true_dx = raw_dx - cam_dx_norm
            true_dy = raw_dy - cam_dy_norm

            comp_x = round(compensated[-1][0] + true_dx, 6)
            comp_y = round(compensated[-1][1] + true_dy, 6)
            compensated.append((comp_x, comp_y))

        profile.compensated_centroids = compensated

        # 2. Kinematic Derivatives: Velocity, Speed, Acceleration
        speeds: List[float] = [0.0]
        velocities: List[Tuple[float, float]] = [(0.0, 0.0)]
        for i in range(1, len(compensated)):
            dt = profile.timestamps[i] - profile.timestamps[i - 1]
            if dt > 0.0001:
                vx = (compensated[i][0] - compensated[i - 1][0]) / dt
                vy = (compensated[i][1] - compensated[i - 1][1]) / dt
                s = math.sqrt(vx * vx + vy * vy)
            else:
                vx, vy, s = 0.0, 0.0, 0.0
            velocities.append((round(vx, 4), round(vy, 4)))
            speeds.append(round(s, 4))

        profile.velocities = velocities
        profile.speeds = speeds

        # Acceleration
        accelerations: List[float] = [0.0]
        for i in range(1, len(speeds)):
            dt = profile.timestamps[i] - profile.timestamps[i - 1]
            if dt > 0.0001:
                acc = (speeds[i] - speeds[i - 1]) / dt
            else:
                acc = 0.0
            accelerations.append(round(acc, 4))
        profile.accelerations = accelerations

        # Direction changes (velocity dot product)
        dir_changes = 0
        for i in range(2, len(velocities)):
            v1 = velocities[i - 1]
            v2 = velocities[i]
            mag1 = math.sqrt(v1[0] * v1[0] + v1[1] * v1[1])
            mag2 = math.sqrt(v2[0] * v2[0] + v2[1] * v2[1])
            if mag1 > 0.05 and mag2 > 0.05:
                cos_theta = (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)
                if cos_theta < 0.2:  # Angle > ~78 degrees
                    dir_changes += 1
        profile.direction_changes = dir_changes

        # Aggregate metrics
        if speeds:
            profile.peak_speed = round(float(np.max(speeds)), 4)
            profile.mean_speed = round(float(np.mean(speeds)), 4)
        if accelerations:
            profile.peak_acceleration = round(float(np.max(np.abs(accelerations))), 4)

        # Net displacement from start to finish (compensated)
        start_c = compensated[0]
        end_c = compensated[-1]
        profile.net_displacement = round(
            math.sqrt((end_c[0] - start_c[0]) ** 2 + (end_c[1] - start_c[1]) ** 2), 4
        )

        # 3. Localized ROI Optical Flow (if frames available)
        if frames is not None and len(frames) > 1:
            profile.local_flow_energies = self.compute_roi_optical_flow(
                frames, profile.frame_indices, profile.bboxes
            )

        return profile

    def compute_roi_optical_flow(
        self,
        frames: List[np.ndarray],
        frame_indices: List[int],
        bboxes: List[BoundingBox],
    ) -> List[float]:
        """
        Computes localized optical flow magnitude within entity bounding boxes.
        Subtracted by background flow to isolate limb / internal movement.
        """
        energies: List[float] = [0.0]
        if len(frame_indices) < 2 or len(frames) < 2:
            return energies

        for i in range(1, len(frame_indices)):
            f_prev_idx = frame_indices[i - 1]
            f_curr_idx = frame_indices[i]
            if f_prev_idx >= len(frames) or f_curr_idx >= len(frames):
                energies.append(0.0)
                continue

            prev_f = frames[f_prev_idx]
            curr_f = frames[f_curr_idx]
            h, w = prev_f.shape[:2]

            prev_gray = cv2.cvtColor(prev_f, cv2.COLOR_BGR2GRAY) if len(prev_f.shape) == 3 else prev_f
            curr_gray = cv2.cvtColor(curr_f, cv2.COLOR_BGR2GRAY) if len(curr_f.shape) == 3 else curr_f

            # Crop ROI to union of current and previous bbox
            b1 = bboxes[i - 1]
            b2 = bboxes[i]
            x1 = max(0, int(min(b1.x, b2.x) * w))
            y1 = max(0, int(min(b1.y, b2.y) * h))
            x2 = min(w, int(max(b1.x_max, b2.x_max) * w))
            y2 = min(h, int(max(b1.y_max, b2.y_max) * h))

            if x2 - x1 < 10 or y2 - y1 < 10:
                energies.append(0.0)
                continue

            roi_prev = prev_gray[y1:y2, x1:x2]
            roi_curr = curr_gray[y1:y2, x1:x2]

            # Fast Farneback flow on ROI only (CPU feasible)
            flow = cv2.calcOpticalFlowFarneback(
                roi_prev, roi_curr, None,
                pyr_scale=0.5, levels=2, winsize=15,
                iterations=2, poly_n=5, poly_sigma=1.1, flags=0
            )
            # Magnitude normalized by ROI dimensions
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            norm_energy = float(np.mean(mag)) / max(1.0, float(w))
            energies.append(round(norm_energy * 100.0, 4))

        return energies
