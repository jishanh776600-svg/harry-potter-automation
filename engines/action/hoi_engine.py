"""
STORY FORGE — Human-Object Interaction (HOI) Engine
===================================================
Verifies physical interactions between human characters and visual props:
  - Possession & Grasp: spatial proximity, temporal persistence, kinematic synchronization
  - Handover / Transfer: source possession -> transfer trajectory -> recipient possession
  - Release / Separation: transition from held to detached ballistic trajectory
  - Rejects false positives: two people standing near an object does NOT constitute a handover
"""

from __future__ import annotations
import math
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from py_visual_evidence.schema import BoundingBox
from engines.perception.models import EntityTrack
from engines.action.models import (
    HOIInteractionType,
    HOIState,
)
from engines.action.geometry import SpatialGeometryEngine

logger = logging.getLogger("HOIEngine")


class HOIEngine:
    """
    Authoritative physical human-object interaction verifier.
    """

    def __init__(
        self,
        possession_distance_threshold: float = 0.18,
        min_persistence_ratio: float = 0.40,
        min_velocity_correlation: float = 0.45,
    ):
        self.possession_distance_threshold = possession_distance_threshold
        self.min_persistence_ratio = min_persistence_ratio
        self.min_velocity_correlation = min_velocity_correlation
        self.geom = SpatialGeometryEngine()

    def evaluate_possession(
        self,
        person_track: EntityTrack,
        object_track: EntityTrack,
        timestamps: Optional[List[float]] = None,
        fps: float = 24.0,
    ) -> Dict[str, Any]:
        """
        Determines whether a person possesses/holds an object based on:
          1. Spatial proximity to person bounds / hand region
          2. Persistence across observed frames
          3. Kinematic velocity synchronization (held objects move with the holder)
        """
        from engines.action.models import extract_track_boxes
        p_pts = extract_track_boxes(person_track)
        o_pts = extract_track_boxes(object_track)
        if len(p_pts) < 2 or len(o_pts) < 2:
            return {
                "is_possessed": False,
                "confidence": 0.0,
                "persistence_ratio": 0.0,
                "velocity_correlation": 0.0,
                "mean_distance": 1.0,
                "reason": "Missing track history",
            }

        person_frames = {f: b for _, f, b in p_pts}
        object_frames = {f: b for _, f, b in o_pts}
        common_frames = sorted(set(person_frames.keys()).intersection(object_frames.keys()))

        if len(common_frames) < 2:
            return {
                "is_possessed": False,
                "confidence": 0.0,
                "persistence_ratio": 0.0,
                "velocity_correlation": 0.0,
                "mean_distance": 1.0,
                "reason": "Insufficient overlapping frames",
            }

        distances: List[float] = []
        near_count = 0
        person_displacements: List[Tuple[float, float]] = []
        object_displacements: List[Tuple[float, float]] = []

        for i, f_idx in enumerate(common_frames):
            p_box = person_frames[f_idx]
            o_box = object_frames[f_idx]
            d = self.geom.bounding_box_distance(p_box, o_box)
            distances.append(d)
            if d <= self.possession_distance_threshold:
                near_count += 1

            if i > 0:
                prev_f = common_frames[i - 1]
                prev_p = person_frames[prev_f]
                prev_o = object_frames[prev_f]
                p_disp = (p_box.centroid[0] - prev_p.centroid[0], p_box.centroid[1] - prev_p.centroid[1])
                o_disp = (o_box.centroid[0] - prev_o.centroid[0], o_box.centroid[1] - prev_o.centroid[1])
                person_displacements.append(p_disp)
                object_displacements.append(o_disp)

        persistence_ratio = near_count / float(len(common_frames))
        mean_dist = float(np.mean(distances))

        # Kinematic velocity correlation
        corr = 0.0
        if len(person_displacements) >= 2:
            p_x = [d[0] for d in person_displacements]
            p_y = [d[1] for d in person_displacements]
            o_x = [d[0] for d in object_displacements]
            o_y = [d[1] for d in object_displacements]

            var_p = np.var(p_x) + np.var(p_y)
            var_o = np.var(o_x) + np.var(o_y)

            # If both are essentially stationary while near each other
            if var_p < 1e-5 and var_o < 1e-5 and persistence_ratio >= 0.6:
                corr = 0.85  # Static holding
            elif var_p > 1e-5 and var_o > 1e-5:
                # Cosine similarity of displacement vectors
                dot_prod = sum(px * ox + py * oy for px, py, ox, oy in zip(p_x, p_y, o_x, o_y))
                mag_p = math.sqrt(sum(px * px + py * py for px, py in zip(p_x, p_y)))
                mag_o = math.sqrt(sum(ox * ox + oy * oy for ox, oy in zip(o_x, o_y)))
                if mag_p > 1e-6 and mag_o > 1e-6:
                    corr = max(0.0, dot_prod / (mag_p * mag_o))

        is_possessed = (persistence_ratio >= self.min_persistence_ratio and 
                        (corr >= self.min_velocity_correlation or mean_dist < 0.08))

        conf = round(float((persistence_ratio * 0.5) + (corr * 0.5)), 4)

        return {
            "is_possessed": is_possessed,
            "confidence": conf,
            "persistence_ratio": round(persistence_ratio, 4),
            "velocity_correlation": round(corr, 4),
            "mean_distance": round(mean_dist, 4),
            "reason": "VERIFIED_POSSESSION" if is_possessed else "STATIC_OR_DETACHED_PROXIMITY",
        }

    def evaluate_handover(
        self,
        source_track: EntityTrack,
        recipient_track: EntityTrack,
        object_track: EntityTrack,
        timestamps: Optional[List[float]] = None,
        fps: float = 24.0,
    ) -> Dict[str, Any]:
        """
        Verifies genuine object transfer from Source to Recipient:
          Phase 1: Object possessed by Source (initial segment)
          Phase 2: Object in transit / moving toward Recipient (intermediate)
          Phase 3: Object possessed by Recipient (final segment)
        Rejects static scenes where two people stand near an object on a table.
        """
        from engines.action.models import extract_track_boxes
        src_pts = extract_track_boxes(source_track)
        rec_pts = extract_track_boxes(recipient_track)
        obj_pts = extract_track_boxes(object_track)

        if not src_pts or not rec_pts or not obj_pts:
            return {
                "is_handover": False,
                "confidence": 0.0,
                "rejection_reason": "Missing one or more required track histories",
            }

        # Divide timeline into 3 sequential temporal segments
        all_frames = sorted(list(set(
            [f for _, f, _ in src_pts] +
            [f for _, f, _ in rec_pts] +
            [f for _, f, _ in obj_pts]
        )))

        if len(all_frames) < 6:
            return {
                "is_handover": False,
                "confidence": 0.0,
                "rejection_reason": "INSUFFICIENT_TEMPORAL_DURATION: Too few frames to establish handover sequence",
            }

        n = len(all_frames)
        seg1_frames = set(all_frames[: n // 3])
        seg2_frames = set(all_frames[n // 3 : 2 * n // 3])
        seg3_frames = set(all_frames[2 * n // 3 :])

        def filter_history(pts: List[Tuple[float, int, BoundingBox]], frame_set: set) -> EntityTrack:
            filtered = [{"timestamp": ts, "frame_index": f, "bbox": b} for ts, f, b in pts if f in frame_set]
            return EntityTrack(
                track_id=1,
                bounding_boxes=filtered,
            )

        src_seg1 = filter_history(src_pts, seg1_frames)
        obj_seg1 = filter_history(obj_pts, seg1_frames)

        rec_seg3 = filter_history(rec_pts, seg3_frames)
        obj_seg3 = filter_history(obj_pts, seg3_frames)

        # Check Phase 1: Source possesses object at start
        pos_src = self.evaluate_possession(src_seg1, obj_seg1, timestamps, fps)

        # Check Phase 3: Recipient possesses object at end
        pos_rec = self.evaluate_possession(rec_seg3, obj_seg3, timestamps, fps)

        # Measure distance delta to recipient between start and end of transfer
        obj_frames_dict = {f: b for _, f, b in obj_pts}
        rec_frames_dict = {f: b for _, f, b in rec_pts}
        src_frames_dict = {f: b for _, f, b in src_pts}

        dist_to_rec_start = 1.0
        dist_to_rec_end = 1.0
        dist_to_src_start = 1.0
        dist_to_src_end = 1.0

        if all_frames[0] in obj_frames_dict and all_frames[0] in rec_frames_dict:
            dist_to_rec_start = self.geom.bounding_box_distance(
                obj_frames_dict[all_frames[0]], rec_frames_dict[all_frames[0]]
            )
        if all_frames[-1] in obj_frames_dict and all_frames[-1] in rec_frames_dict:
            dist_to_rec_end = self.geom.bounding_box_distance(
                obj_frames_dict[all_frames[-1]], rec_frames_dict[all_frames[-1]]
            )

        if all_frames[0] in obj_frames_dict and all_frames[0] in src_frames_dict:
            dist_to_src_start = self.geom.bounding_box_distance(
                obj_frames_dict[all_frames[0]], src_frames_dict[all_frames[0]]
            )
        if all_frames[-1] in obj_frames_dict and all_frames[-1] in src_frames_dict:
            dist_to_src_end = self.geom.bounding_box_distance(
                obj_frames_dict[all_frames[-1]], src_frames_dict[all_frames[-1]]
            )

        converged_to_recipient = (dist_to_rec_start - dist_to_rec_end) > 0.05
        separated_from_source = (dist_to_src_end - dist_to_src_start) > 0.05

        # Decision
        if pos_src["is_possessed"] and pos_rec["is_possessed"] and (converged_to_recipient or separated_from_source):
            conf = round(float((pos_src["confidence"] + pos_rec["confidence"]) / 2.0), 4)
            return {
                "is_handover": True,
                "confidence": conf,
                "phase1_source_possession": pos_src,
                "phase3_recipient_possession": pos_rec,
                "distance_to_recipient_start": round(dist_to_rec_start, 4),
                "distance_to_recipient_end": round(dist_to_rec_end, 4),
                "rejection_reason": None,
            }

        # Anti-False-Positive: Static proximity rejection
        if not converged_to_recipient and not separated_from_source:
            return {
                "is_handover": False,
                "confidence": 0.20,
                "phase1_source_possession": pos_src,
                "phase3_recipient_possession": pos_rec,
                "rejection_reason": "STATIC_PROXIMITY_ONLY: Entities are near each other but object was not transferred between them.",
            }

        if not pos_src["is_possessed"]:
            return {
                "is_handover": False,
                "confidence": 0.15,
                "phase1_source_possession": pos_src,
                "phase3_recipient_possession": pos_rec,
                "rejection_reason": "SOURCE_POSSESSION_NOT_CONFIRMED: Source character was not holding the object at onset.",
            }

        return {
            "is_handover": False,
            "confidence": 0.15,
            "phase1_source_possession": pos_src,
            "phase3_recipient_possession": pos_rec,
            "rejection_reason": "RECIPIENT_POSSESSION_NOT_CONFIRMED: Recipient character did not take possession of object at completion.",
        }
