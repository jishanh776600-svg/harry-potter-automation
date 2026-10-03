"""
STORY FORGE — Camera-Motion-Compensated Entity Tracker (BoT-SORT / ByteTrack)
=============================================================================
Provides robust multi-entity tracking with:
  1. Camera Motion Compensation (CMC): Affine warping of prior track states
     via sparse optical flow (PyrLK) and RANSAC affine estimation.
  2. Two-Stage Association (ByteTrack): Separate matching for high-confidence
     and low-confidence detections to prevent fragmentation during blur/occlusion.
  3. Appearance & Re-ID Integration: Cosine distance matching of OpenCLIP
     appearance vectors to prevent identity swaps.
  4. Temporal Identity Persistence & Degradation: Maintains confirmed character
     identities across temporary face loss (TRACKED_FROM_PRIOR), while cleanly
     dropping to UNKNOWN when tracks degrade or terminate.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import cv2
import numpy as np

from py_visual_evidence.schema import BoundingBox
from engines.perception.models import (
    EntityTrack,
    IdentityMatchStatus,
    IdentityMatchResult,
)

logger = logging.getLogger("BoTSORTTracker")


class CameraMotionCompensator:
    """
    Estimates camera pan, tilt, and zoom between consecutive frames using
    sparse Lucas-Kanade optical flow and partial affine RANSAC.
    """

    def __init__(self, max_corners: int = 200, quality_level: float = 0.01, min_distance: int = 25):
        self.max_corners = max_corners
        self.quality_level = quality_level
        self.min_distance = min_distance

    def estimate_motion(self, prev_gray: np.ndarray, curr_gray: np.ndarray) -> np.ndarray:
        """
        Estimates 2x3 affine matrix M mapping points from prev_gray to curr_gray.
        Returns identity matrix [[1, 0, 0], [0, 1, 0]] if motion cannot be estimated reliably.
        """
        identity_m = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
        if prev_gray is None or curr_gray is None:
            return identity_m

        pts_prev = cv2.goodFeaturesToTrack(
            prev_gray,
            maxCorners=self.max_corners,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
        )
        if pts_prev is None or len(pts_prev) < 8:
            return identity_m

        pts_curr, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, pts_prev, None)
        if pts_curr is None or status is None:
            return identity_m

        good_prev = pts_prev[status == 1]
        good_curr = pts_curr[status == 1]

        if len(good_prev) < 6:
            return identity_m

        M, inliers = cv2.estimateAffinePartial2D(
            good_prev,
            good_curr,
            method=cv2.RANSAC,
            ransacReprojThreshold=3.0,
            maxIters=500,
        )
        if M is None:
            return identity_m
        return M.astype(np.float32)

    def compensate_bbox(
        self,
        bbox: BoundingBox,
        M: np.ndarray,
        img_w: int,
        img_h: int,
    ) -> BoundingBox:
        """
        Transforms bounding box coordinates using the camera motion matrix M.
        """
        px, py, pw, ph = bbox.to_pixels(img_w, img_h)
        # Transform 4 box corners
        corners = np.array([
            [px, py, 1.0],
            [px + pw, py, 1.0],
            [px, py + ph, 1.0],
            [px + pw, py + ph, 1.0],
        ], dtype=np.float32).T  # 3x4

        warped = np.dot(M, corners)  # 2x4
        wx_min = float(np.min(warped[0]))
        wx_max = float(np.max(warped[0]))
        wy_min = float(np.min(warped[1]))
        wy_max = float(np.max(warped[1]))

        # Normalize back to [0, 1]
        nx = max(0.0, min(1.0, wx_min / img_w))
        ny = max(0.0, min(1.0, wy_min / img_h))
        nw = max(0.005, min(1.0 - nx, (wx_max - wx_min) / img_w))
        nh = max(0.005, min(1.0 - ny, (wy_max - wy_min) / img_h))

        return BoundingBox(x=round(nx, 6), y=round(ny, 6), w=round(nw, 6), h=round(nh, 6))


class TrackState:
    """Internal state representation for an individual tracked object/person."""

    def __init__(
        self,
        track_id: int,
        initial_bbox: BoundingBox,
        confidence: float,
        timestamp: float,
        entity_type: str = "person",
        identity_id: Optional[str] = None,
        canonical_name: Optional[str] = None,
        identity_status: IdentityMatchStatus = IdentityMatchStatus.UNKNOWN,
        appearance: Optional[np.ndarray] = None,
    ):
        self.track_id = track_id
        self.entity_type = entity_type
        self.current_bbox = initial_bbox
        self.confidence = confidence
        self.start_time = timestamp
        self.last_seen_time = timestamp
        self.hits = 1
        self.age = 1
        self.time_since_update = 0
        self.identity_id = identity_id
        self.canonical_name = canonical_name
        self.identity_status = identity_status
        self.appearance = appearance
        self.history: List[Dict[str, Any]] = [
            {"timestamp": timestamp, "bbox": initial_bbox, "confidence": confidence}
        ]
        self.identity_audits: List[Dict[str, Any]] = []

    def update(
        self,
        bbox: BoundingBox,
        confidence: float,
        timestamp: float,
        appearance: Optional[np.ndarray] = None,
    ):
        self.current_bbox = bbox
        self.confidence = confidence
        self.last_seen_time = timestamp
        self.hits += 1
        self.age += 1
        self.time_since_update = 0
        if appearance is not None:
            # Running EMA update of appearance embedding
            if self.appearance is not None:
                self.appearance = 0.8 * self.appearance + 0.2 * appearance
                norm = np.linalg.norm(self.appearance)
                if norm > 0:
                    self.appearance = self.appearance / norm
            else:
                self.appearance = appearance
        self.history.append({"timestamp": timestamp, "bbox": bbox, "confidence": confidence})

    def mark_missed(self, timestamp: float):
        self.age += 1
        self.time_since_update += 1


class CameraCompensatedTracker:
    """
    BoT-SORT / ByteTrack style tracker with optical flow Camera Motion Compensation (CMC),
    two-stage IoU/appearance association, and persistent identity management.
    """

    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 2,
        high_conf_threshold: float = 0.50,
        low_conf_threshold: float = 0.20,
        iou_threshold: float = 0.25,
        appearance_weight: float = 0.30,
    ):
        self.max_age = max_age
        self.min_hits = min_hits
        self.high_conf_threshold = high_conf_threshold
        self.low_conf_threshold = low_conf_threshold
        self.iou_threshold = iou_threshold
        self.appearance_weight = appearance_weight

        self.cmc = CameraMotionCompensator()
        self.active_tracks: Dict[int, TrackState] = {}
        self.finished_tracks: List[EntityTrack] = []
        self._next_id = 1
        self.prev_gray: Optional[np.ndarray] = None

    def _compute_iou(self, b1: BoundingBox, b2: BoundingBox) -> float:
        inter = b1.intersection(b2)
        if inter is None or inter.area <= 0:
            return 0.0
        union_area = b1.area + b2.area - inter.area
        return inter.area / union_area if union_area > 0 else 0.0

    def step(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        timestamp_sec: float,
    ) -> List[TrackState]:
        """
        Updates tracks for a single frame.
        detections: List of dicts with keys:
          - 'bbox': BoundingBox
          - 'confidence': float
          - 'entity_type': str
          - 'appearance': Optional[np.ndarray]
          - 'identity_id': Optional[str]
          - 'canonical_name': Optional[str]
          - 'identity_status': IdentityMatchStatus
        """
        img_h, img_w = frame.shape[:2]
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

        # 1. Camera Motion Compensation
        M = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
        if self.prev_gray is not None:
            M = self.cmc.estimate_motion(self.prev_gray, curr_gray)
            for track in self.active_tracks.values():
                track.current_bbox = self.cmc.compensate_bbox(track.current_bbox, M, img_w, img_h)
        self.prev_gray = curr_gray.copy()

        # 2. Split detections into high and low confidence
        high_dets = [d for d in detections if d.get("confidence", 0.0) >= self.high_conf_threshold]
        low_dets = [
            d for d in detections
            if self.low_conf_threshold <= d.get("confidence", 0.0) < self.high_conf_threshold
        ]

        active_track_ids = list(self.active_tracks.keys())
        unmatched_tracks = set(active_track_ids)
        unmatched_high_dets = set(range(len(high_dets)))

        # 3. First Association: High-confidence detections with active tracks (IoU + Appearance)
        matched_pairs_1 = []
        for det_idx in list(unmatched_high_dets):
            det = high_dets[det_idx]
            best_track_id = None
            best_score = -1.0

            for tid in unmatched_tracks:
                track = self.active_tracks[tid]
                iou = self._compute_iou(track.current_bbox, det["bbox"])
                score = iou

                # If appearance embeddings available, incorporate cosine similarity
                if (
                    self.appearance_weight > 0
                    and track.appearance is not None
                    and det.get("appearance") is not None
                ):
                    cos_sim = float(np.dot(track.appearance, det["appearance"]))
                    score = (1.0 - self.appearance_weight) * iou + self.appearance_weight * max(0.0, cos_sim)

                if score > self.iou_threshold and score > best_score:
                    best_score = score
                    best_track_id = tid

            if best_track_id is not None:
                matched_pairs_1.append((best_track_id, det_idx))
                unmatched_tracks.remove(best_track_id)
                unmatched_high_dets.remove(det_idx)

        # Update matched tracks from stage 1
        for tid, det_idx in matched_pairs_1:
            det = high_dets[det_idx]
            track = self.active_tracks[tid]
            track.update(
                bbox=det["bbox"],
                confidence=det["confidence"],
                timestamp=timestamp_sec,
                appearance=det.get("appearance"),
            )
            # Update identity if fresh confident identity arrives
            fresh_status = det.get("identity_status", IdentityMatchStatus.UNKNOWN)
            if fresh_status in (IdentityMatchStatus.FACE_CONFIRMED, IdentityMatchStatus.FACE_PARTIAL):
                track.identity_id = det.get("identity_id")
                track.canonical_name = det.get("canonical_name")
                track.identity_status = fresh_status
            elif track.identity_status in (IdentityMatchStatus.FACE_CONFIRMED, IdentityMatchStatus.FACE_PARTIAL):
                # Smoothly transition to TRACKED_FROM_PRIOR to preserve continuity during face angle changes
                track.identity_status = IdentityMatchStatus.TRACKED_FROM_PRIOR

        # 4. Second Association: Remaining tracks with low-confidence detections (pure IoU)
        matched_pairs_2 = []
        for det_idx, det in enumerate(low_dets):
            best_track_id = None
            best_iou = -1.0
            for tid in unmatched_tracks:
                track = self.active_tracks[tid]
                iou = self._compute_iou(track.current_bbox, det["bbox"])
                if iou > self.iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_track_id = tid

            if best_track_id is not None:
                matched_pairs_2.append((best_track_id, det_idx))
                unmatched_tracks.remove(best_track_id)

        # Update matched tracks from stage 2
        for tid, det_idx in matched_pairs_2:
            det = low_dets[det_idx]
            track = self.active_tracks[tid]
            track.update(
                bbox=det["bbox"],
                confidence=det["confidence"],
                timestamp=timestamp_sec,
                appearance=det.get("appearance"),
            )
            if track.identity_status in (IdentityMatchStatus.FACE_CONFIRMED, IdentityMatchStatus.FACE_PARTIAL):
                track.identity_status = IdentityMatchStatus.TRACKED_FROM_PRIOR

        # 5. Initialize new tracks from unmatched high-confidence detections
        for det_idx in unmatched_high_dets:
            det = high_dets[det_idx]
            new_track = TrackState(
                track_id=self._next_id,
                initial_bbox=det["bbox"],
                confidence=det["confidence"],
                timestamp=timestamp_sec,
                entity_type=det.get("entity_type", "person"),
                identity_id=det.get("identity_id"),
                canonical_name=det.get("canonical_name"),
                identity_status=det.get("identity_status", IdentityMatchStatus.UNKNOWN),
                appearance=det.get("appearance"),
            )
            self.active_tracks[self._next_id] = new_track
            self._next_id += 1

        # 6. Mark missed for remaining unmatched tracks
        stale_tids = []
        for tid in unmatched_tracks:
            track = self.active_tracks[tid]
            track.mark_missed(timestamp_sec)
            # If missed for too long, drop identity to UNKNOWN before terminating
            if track.time_since_update > 5:
                track.identity_status = IdentityMatchStatus.UNKNOWN
            if track.time_since_update > self.max_age:
                stale_tids.append(tid)

        # 7. Retire expired tracks
        for tid in stale_tids:
            retired = self.active_tracks.pop(tid)
            if retired.hits >= self.min_hits:
                self.finished_tracks.append(self._to_entity_track(retired))

        # Return currently active confirmed tracks
        return [t for t in self.active_tracks.values() if t.time_since_update == 0]

    def _to_entity_track(self, state: TrackState) -> EntityTrack:
        vis = state.hits / max(1.0, float(state.age))
        return EntityTrack(
            track_id=state.track_id,
            entity_type=state.entity_type,
            identity_id=state.identity_id,
            canonical_name=state.canonical_name,
            identity_status=state.identity_status,
            start_time=state.start_time,
            end_time=state.last_seen_time,
            bounding_boxes=state.history,
            confidence=round(state.confidence, 4),
            visibility=round(vis, 4),
            identity_history=state.identity_audits,
        )

    def finalize(self) -> List[EntityTrack]:
        """Flushes all remaining active tracks and returns completed track list."""
        for state in self.active_tracks.values():
            if state.hits >= self.min_hits:
                self.finished_tracks.append(self._to_entity_track(state))
        self.active_tracks.clear()
        return self.finished_tracks
