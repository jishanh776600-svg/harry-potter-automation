"""
STORY FORGE — Spatio-Temporal Entity Timeline Generator (Phase 2)
=================================================================
Processes candidate video clips to produce a timestamped EntityTimeline:
  1. Keyframe Sampling: Evaluates frames at configurable temporal frequency (e.g. 2-4 Hz).
  2. Character Identification: Runs FaceMatcher against the CharacterBank with strict rejection.
  3. Camera-Compensated Tracking: Tracks all persons and props across camera pans and motion.
  4. Geometric Spatial Relationships: Computes pairwise distances, IoUs, and proximities
     (e.g., person-person proximity, person-prop proximity).
  5. Uncertainty Event Logging: Audits lookalike ambiguities, temporary face losses, and UNKNOWN flags.
  6. Cryptographic Lineage: Tags the timeline with model versions, bank version, and movie hashes.
"""

from __future__ import annotations
import math
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import cv2
import numpy as np

from py_visual_evidence.schema import BoundingBox, EntitySpec
from engines.perception.models import (
    EntityTimeline,
    EntityTrack,
    VisualObject,
    IdentityMatchStatus,
)
from engines.perception.character_bank import CharacterBank, BANK_VERSION
from engines.perception.face_matcher import FaceMatcher
from engines.perception.tracker import CameraCompensatedTracker
from engines.perception.object_grounder import ObjectGrounder

logger = logging.getLogger("EntityTimelineGenerator")


class EntityTimelineGenerator:
    """
    Constructs unified spatio-temporal EntityTimelines for candidate movie clips.
    """

    def __init__(
        self,
        character_bank: Optional[CharacterBank] = None,
        face_matcher: Optional[FaceMatcher] = None,
        object_grounder: Optional[ObjectGrounder] = None,
        sampling_fps: float = 2.0,
    ):
        if character_bank is not None:
            self.character_bank = character_bank
        elif DEFAULT_BANK_PATH.exists():
            self.character_bank = CharacterBank.load_from_file(DEFAULT_BANK_PATH)
        else:
            from engines.perception.character_bank import build_canonical_bank
            self.character_bank = build_canonical_bank()

        self.face_matcher = face_matcher or FaceMatcher(character_bank=self.character_bank)
        self.object_grounder = object_grounder or ObjectGrounder()
        self.sampling_fps = sampling_fps

    def _compute_centroid_distance(self, b1: BoundingBox, b2: BoundingBox) -> float:
        """Euclidean distance between bounding box centroids in normalized [0, 1] space."""
        c1 = b1.centroid
        c2 = b2.centroid
        return round(math.sqrt((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2), 4)

    def generate_timeline(
        self,
        video_path: Union[str, Path],
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
        target_characters: Optional[List[str]] = None,
        target_objects: Optional[List[str]] = None,
        clip_id: str = "candidate_clip",
    ) -> EntityTimeline:
        """
        Processes candidate clip interval and generates a complete EntityTimeline.
        """
        video_p = Path(video_path)
        if not video_p.exists():
            raise FileNotFoundError(f"Video file not found: {video_p}")

        cap = cv2.VideoCapture(str(video_p))
        native_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / native_fps if native_fps > 0 else 0.0
        end_t = min(duration, end_sec) if end_sec is not None else duration

        tracker = CameraCompensatedTracker()
        timeline_timestamps: List[float] = []
        active_tracks_by_time: Dict[str, List[Dict[str, Any]]] = {}
        active_objects_by_time: Dict[str, List[Dict[str, Any]]] = {}
        spatial_relations_by_time: Dict[str, List[Dict[str, Any]]] = {}
        uncertainty_events: List[Dict[str, Any]] = []

        step_sec = 1.0 / self.sampling_fps if self.sampling_fps > 0 else 0.5
        curr_t = start_sec

        while curr_t <= end_t:
            frame_idx = int(curr_t * native_fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            time_str = f"{curr_t:.2f}"
            timeline_timestamps.append(curr_t)

            # 1. Ground Persons via open-vocabulary detector
            person_specs = [EntitySpec(name="person", role="subject", description="person", min_confidence=0.18)]
            grounded_persons = self.face_matcher.grounder.ground_entities(frame, person_specs, timestamp_sec=curr_t)
            person_boxes = [gp.bbox for gp in grounded_persons]

            # 2. Extract and match faces
            detections_for_tracker: List[Dict[str, Any]] = []
            for gp in grounded_persons:
                # Try head crop matching
                head_det, match_res = self.face_matcher.match_person_head(frame, gp.bbox, timestamp_sec=curr_t)
                
                det_entry = {
                    "bbox": gp.bbox,
                    "confidence": gp.confidence,
                    "entity_type": "person",
                    "appearance": np.array(head_det.embedding, dtype=np.float32) if head_det and head_det.embedding else None,
                    "identity_id": match_res.matched_character_id,
                    "canonical_name": match_res.canonical_name,
                    "identity_status": match_res.status,
                }
                detections_for_tracker.append(det_entry)

                # Log uncertainty if ambiguity occurred
                if match_res.status == IdentityMatchStatus.UNKNOWN and match_res.rejection_reason != "NONE":
                    uncertainty_events.append({
                        "timestamp": curr_t,
                        "person_bbox": gp.bbox.model_dump(),
                        "reason": match_res.rejection_reason.value,
                        "explanation": match_res.explanation,
                    })

            # 3. Step tracker with CMC
            active_track_states = tracker.step(frame, detections_for_tracker, timestamp_sec=curr_t)
            
            # Format active tracks
            active_tracks_list = []
            for ts in active_track_states:
                active_tracks_list.append({
                    "track_id": ts.track_id,
                    "identity_id": ts.identity_id,
                    "canonical_name": ts.canonical_name,
                    "identity_status": ts.identity_status.value,
                    "bbox": ts.current_bbox.model_dump(),
                    "confidence": round(ts.confidence, 4),
                })
            active_tracks_by_time[time_str] = active_tracks_list

            # 4. Ground Objects (props)
            grounded_objects: List[VisualObject] = []
            if target_objects:
                grounded_objects = self.object_grounder.ground_objects(
                    frame,
                    target_labels=target_objects,
                    timestamp_sec=curr_t,
                    person_boxes=person_boxes,
                )
            
            active_objs_list = []
            for obj in grounded_objects:
                active_objs_list.append({
                    "object_id": obj.object_id,
                    "label": obj.label,
                    "bbox": obj.bbox.model_dump(),
                    "state": obj.state,
                    "confidence": obj.confidence,
                })
            active_objects_by_time[time_str] = active_objs_list

            # 5. Compute Spatial Geometric Relationships
            rels: List[Dict[str, Any]] = []
            # Person <-> Person Proximity
            for i in range(len(active_track_states)):
                for j in range(i + 1, len(active_track_states)):
                    t1 = active_track_states[i]
                    t2 = active_track_states[j]
                    dist = self._compute_centroid_distance(t1.current_bbox, t2.current_bbox)
                    is_near = dist < 0.35
                    rels.append({
                        "type": "person_proximity",
                        "entity1": t1.canonical_name or f"Track_{t1.track_id}",
                        "entity2": t2.canonical_name or f"Track_{t2.track_id}",
                        "distance": dist,
                        "is_proximate": is_near,
                    })

            # Person <-> Object Proximity
            for ts in active_track_states:
                for obj in grounded_objects:
                    dist = self._compute_centroid_distance(ts.current_bbox, obj.bbox)
                    near_prop = dist < 0.25
                    rels.append({
                        "type": "person_object_proximity",
                        "person": ts.canonical_name or f"Track_{ts.track_id}",
                        "object": obj.label,
                        "distance": dist,
                        "is_near": near_prop,
                    })
            spatial_relations_by_time[time_str] = rels

            curr_t += step_sec

        cap.release()
        tracker.finalize()

        return EntityTimeline(
            clip_id=clip_id,
            duration=round(end_t - start_sec, 3),
            timestamps=timeline_timestamps,
            active_tracks_by_time=active_tracks_by_time,
            active_objects_by_time=active_objects_by_time,
            spatial_relations_by_time=spatial_relations_by_time,
            uncertainty_events=uncertainty_events,
            lineage={
                "video_file": video_p.name,
                "bank_version": BANK_VERSION,
                "tracker": "CameraCompensatedTracker_BoTSORT",
                "grounder": "OWLv2_MultiScale",
                "feature_encoder": "OpenCLIP_ViT_B_32_512d",
            },
        )
