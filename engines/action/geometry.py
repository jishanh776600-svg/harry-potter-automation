"""
STORY FORGE — Spatio-Temporal Relationship Geometry Engine
===========================================================
Calculates timestamped spatial relationships between entities:
NEAR, TOUCHING, OVERLAPPING, MOVING_TOWARD, MOVING_AWAY, BETWEEN,
INSIDE, ABOVE, BELOW, LEFT_OF, RIGHT_OF.
"""

from __future__ import annotations
import math
from typing import List, Dict, Optional, Tuple, Set
from py_visual_evidence.schema import BoundingBox
from engines.action.models import GeometricRelation, TimestampedRelation


class SpatialGeometryEngine:
    """
    Computes rigorous normalized geometric relationships between bounding boxes.
    """

    def __init__(
        self,
        near_threshold: float = 0.22,
        touch_margin: float = 0.04,
        motion_deriv_threshold: float = 0.08,
    ):
        self.near_threshold = near_threshold
        self.touch_margin = touch_margin
        self.motion_deriv_threshold = motion_deriv_threshold

    @staticmethod
    def euclidean_distance(pt1: Tuple[float, float], pt2: Tuple[float, float]) -> float:
        return math.sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)

    @classmethod
    def bounding_box_distance(cls, box_a: BoundingBox, box_b: BoundingBox) -> float:
        """
        Minimum Euclidean distance between two bounding box perimeters.
        If overlapping or touching, distance is 0.0.
        """
        # Horizontal separation
        if box_a.x_max < box_b.x:
            dx = box_b.x - box_a.x_max
        elif box_b.x_max < box_a.x:
            dx = box_a.x - box_b.x_max
        else:
            dx = 0.0

        # Vertical separation
        if box_a.y_max < box_b.y:
            dy = box_b.y - box_a.y_max
        elif box_b.y_max < box_a.y:
            dy = box_a.y - box_b.y_max
        else:
            dy = 0.0

        return math.sqrt(dx * dx + dy * dy)

    def evaluate_static_relations(
        self,
        box_a: BoundingBox,
        box_b: BoundingBox,
        name_a: str,
        name_b: str,
        timestamp_sec: float,
        frame_idx: int,
    ) -> List[TimestampedRelation]:
        """
        Evaluates frame-level static spatial relations between Box A and Box B.
        """
        relations: List[TimestampedRelation] = []
        iou = box_a.iou(box_b)
        dist = self.bounding_box_distance(box_a, box_b)
        ca = box_a.centroid
        cb = box_b.centroid

        # 1. OVERLAPPING / TOUCHING / NEAR
        if iou > 0.01:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.OVERLAPPING,
                distance=dist,
                iou=iou,
            ))
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.TOUCHING,
                distance=dist,
                iou=iou,
            ))
        elif dist <= self.touch_margin:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.TOUCHING,
                distance=dist,
                iou=iou,
            ))

        if dist <= self.near_threshold:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.NEAR,
                distance=dist,
                iou=iou,
            ))

        # 2. INSIDE
        if (box_a.x >= box_b.x and box_a.y >= box_b.y and 
            box_a.x_max <= box_b.x_max and box_a.y_max <= box_b.y_max):
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.INSIDE,
                distance=dist,
                iou=iou,
            ))

        # 3. Relative cardinal positions (above, below, left_of, right_of)
        # Using centroids
        dx = ca[0] - cb[0]
        dy = ca[1] - cb[1]

        if dx < -0.05:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.LEFT_OF,
                distance=dist,
                iou=iou,
            ))
        elif dx > 0.05:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.RIGHT_OF,
                distance=dist,
                iou=iou,
            ))

        if dy < -0.05:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.ABOVE,
                distance=dist,
                iou=iou,
            ))
        elif dy > 0.05:
            relations.append(TimestampedRelation(
                timestamp_sec=timestamp_sec,
                frame_index=frame_idx,
                entity_a=name_a,
                entity_b=name_b,
                relation=GeometricRelation.BELOW,
                distance=dist,
                iou=iou,
            ))

        return relations

    def evaluate_pairwise_trajectory_relations(
        self,
        traj_a: List[Tuple[float, int, BoundingBox]], # [(ts, frame, bbox)]
        traj_b: List[Tuple[float, int, BoundingBox]],
        name_a: str,
        name_b: str,
    ) -> List[TimestampedRelation]:
        """
        Computes dynamic time-varying relationships (MOVING_TOWARD, MOVING_AWAY)
        and static relations across matched timestamps.
        """
        all_relations: List[TimestampedRelation] = []
        if not traj_a or not traj_b:
            return all_relations

        # Index traj_b by timestamp (with tolerance of 0.05s)
        time_to_b = {round(t[0], 2): (t[1], t[2]) for t in traj_b}

        distances: List[Tuple[float, int, float, BoundingBox, BoundingBox]] = []
        for t_a, f_a, box_a in traj_a:
            t_key = round(t_a, 2)
            if t_key in time_to_b:
                f_b, box_b = time_to_b[t_key]
                d = self.bounding_box_distance(box_a, box_b)
                distances.append((t_a, f_a, d, box_a, box_b))
                # Add static relations
                static_rels = self.evaluate_static_relations(
                    box_a, box_b, name_a, name_b, t_a, f_a
                )
                all_relations.extend(static_rels)

        # Compute derivative of distance to detect approach vs retreat
        if len(distances) >= 2:
            for i in range(1, len(distances)):
                t_prev, f_prev, d_prev, _, _ = distances[i - 1]
                t_curr, f_curr, d_curr, b_a, b_b = distances[i]
                dt = t_curr - t_prev
                if dt > 0.001:
                    # Negative derivative = distance decreasing = moving toward
                    d_deriv = (d_curr - d_prev) / dt
                    rel_vel = abs(d_deriv)
                    if d_deriv < -self.motion_deriv_threshold:
                        all_relations.append(TimestampedRelation(
                            timestamp_sec=t_curr,
                            frame_index=f_curr,
                            entity_a=name_a,
                            entity_b=name_b,
                            relation=GeometricRelation.MOVING_TOWARD,
                            distance=d_curr,
                            relative_velocity=rel_vel,
                        ))
                    elif d_deriv > self.motion_deriv_threshold:
                        all_relations.append(TimestampedRelation(
                            timestamp_sec=t_curr,
                            frame_index=f_curr,
                            entity_a=name_a,
                            entity_b=name_b,
                            relation=GeometricRelation.MOVING_AWAY,
                            distance=d_curr,
                            relative_velocity=rel_vel,
                        ))

        # Sort chronologically
        all_relations.sort(key=lambda r: (r.timestamp_sec, r.relation.value))
        return all_relations

    @classmethod
    def check_between(
        cls,
        box_mid: BoundingBox,
        box_left: BoundingBox,
        box_right: BoundingBox,
    ) -> bool:
        """Determines if box_mid is geometrically between box_left and box_right."""
        cx_mid = box_mid.centroid[0]
        cx_1 = box_left.centroid[0]
        cx_2 = box_right.centroid[0]
        min_x = min(cx_1, cx_2)
        max_x = max(cx_1, cx_2)
        return min_x < cx_mid < max_x
