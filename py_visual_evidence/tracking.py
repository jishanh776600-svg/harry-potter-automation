"""
Tier 2: Fast Spatio-Temporal Entity Tracking
Propagates sparse keyframe bounding boxes across consecutive frames at 60+ FPS,
producing continuous trajectories P_entity(t) with velocity and distance metrics.
"""

from __future__ import annotations
from typing import List, Dict, Tuple, Optional
import cv2
import numpy as np

from py_visual_evidence.schema import (
    BoundingBox,
    GroundedEntity,
    TrajectoryPoint,
    EntityTrajectory,
)


class FastSpatioTemporalTracker:
    def __init__(self, tracker_type: str = "CSRT", max_tracking_dim: Optional[int] = 640):
        self.tracker_type = tracker_type.upper()
        self.max_tracking_dim = max_tracking_dim

    def _create_tracker(self):
        if self.tracker_type == "KCF":
            return cv2.TrackerKCF_create()
        return cv2.TrackerCSRT_create()

    def track_entities(
        self,
        frames: List[np.ndarray],
        initial_entities: List[GroundedEntity],
        fps: float = 24.0,
        start_sec: float = 0.0,
    ) -> Dict[str, EntityTrajectory]:
        """
        Initializes OpenCV trackers on the first frame for each grounded entity,
        then propagates them across all subsequent frames.
        Frames are scaled to max_tracking_dim for fast tracking while keeping normalized coordinates.
        """
        if not frames or not initial_entities:
            return {}

        img_h, img_w, _ = frames[0].shape
        trajectories: Dict[str, EntityTrajectory] = {}

        # Performance Optimization: downscale tracking frames if exceeding max_tracking_dim
        scale = 1.0
        if self.max_tracking_dim and max(img_w, img_h) > self.max_tracking_dim:
            scale = self.max_tracking_dim / float(max(img_w, img_h))
            track_w = max(16, int(round(img_w * scale)))
            track_h = max(16, int(round(img_h * scale)))
        else:
            track_w, track_h = img_w, img_h

        first_track_frame = (
            cv2.resize(frames[0], (track_w, track_h), interpolation=cv2.INTER_AREA)
            if scale != 1.0
            else frames[0]
        )

        # Set up a tracker per entity
        trackers = {}
        for entity in initial_entities:
            tracker = self._create_tracker()
            px_x, px_y, px_w, px_h = entity.bbox.to_pixels(track_w, track_h)
            
            # Ensure bounding box is valid within image boundaries
            px_x = max(0, min(track_w - 2, px_x))
            px_y = max(0, min(track_h - 2, px_y))
            px_w = max(2, min(track_w - px_x, px_w))
            px_h = max(2, min(track_h - px_y, px_h))

            tracker.init(first_track_frame, (px_x, px_y, px_w, px_h))
            trackers[entity.entity_name] = tracker

            # Create initial trajectory
            init_pt = TrajectoryPoint(
                frame_index=0,
                timestamp_sec=start_sec,
                bbox=entity.bbox,
                centroid=entity.bbox.centroid,
                velocity=(0.0, 0.0),
            )
            trajectories[entity.entity_name] = EntityTrajectory(
                entity_name=entity.entity_name,
                role=entity.role,
                points=[init_pt],
            )

        # Track across consecutive frames
        dt = 1.0 / fps if fps > 0 else 0.0416
        for f_idx in range(1, len(frames)):
            frame = (
                cv2.resize(frames[f_idx], (track_w, track_h), interpolation=cv2.INTER_AREA)
                if scale != 1.0
                else frames[f_idx]
            )
            t_sec = start_sec + (f_idx * dt)

            for entity_name, tracker in trackers.items():
                success, box = tracker.update(frame)
                prev_pt = trajectories[entity_name].points[-1]

                if success:
                    bx, by, bw, bh = box
                    norm_bbox = BoundingBox(
                        x=max(0.0, min(1.0, bx / track_w)),
                        y=max(0.0, min(1.0, by / track_h)),
                        w=max(0.005, min(1.0, bw / track_w)),
                        h=max(0.005, min(1.0, bh / track_h)),
                    )
                    cx, cy = norm_bbox.centroid
                    vx = (cx - prev_pt.centroid[0]) / dt
                    vy = (cy - prev_pt.centroid[1]) / dt
                else:
                    # In case of tracker loss, retain previous position with zero velocity
                    norm_bbox = prev_pt.bbox
                    cx, cy = prev_pt.centroid
                    vx, vy = 0.0, 0.0

                pt = TrajectoryPoint(
                    frame_index=f_idx,
                    timestamp_sec=t_sec,
                    bbox=norm_bbox,
                    centroid=(cx, cy),
                    velocity=(vx, vy),
                )
                trajectories[entity_name].points.append(pt)

        return trajectories
