"""
STORY FORGE — BEAST Shot Boundary Detector & Multi-Frame Sampler (Phase 2 & 3)
================================================================================
Implements deterministic video segmentation and temporal sequence sampling:
  1. Detects atomic shot boundaries using PySceneDetect (AdaptiveDetector).
  2. Preserves exact source video timestamps (start, end, duration).
  3. Caches shot catalogs to avoid expensive re-processing.
  4. Extracts 5 equidistant frames per shot (10%, 30%, 50%, 70%, 90%).
  5. Computes temporal motion scores across consecutive sample frames.
"""

import os
import json
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import cv2
import numpy as np
from scenedetect import detect, ContentDetector, AdaptiveDetector

from core.beast_visual_types import BeastCandidateShot, MultiFrameSample, NarrativeEra
from core.composition_models import ShotScale, ShotCompositionAssessment

logger = logging.getLogger("BeastShotDetector")

SAMPLE_PERCENTILES = [0.10, 0.30, 0.50, 0.70, 0.90]


class BeastShotDetector:
    """
    Shot detection and multi-frame sampling engine for movie archives.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        frames_dir: Optional[Path] = None,
        min_shot_duration: float = 1.0,
        max_shot_duration: float = 15.0,
    ):
        self.cache_dir = Path(cache_dir or "data/cache/beast_shots")
        self.frames_dir = Path(frames_dir or "data/cache/beast_frames")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.min_shot_duration = min_shot_duration
        self.max_shot_duration = max_shot_duration

    def _compute_file_fingerprint(self, video_path: Path) -> str:
        """Computes a deterministic fingerprint based on file size and partial content."""
        if not video_path.exists():
            return "missing_file"
        st = video_path.stat()
        file_size = st.st_size
        mtime = st.st_mtime
        # Read 64KB from beginning and middle
        h = hashlib.sha256()
        h.update(f"{video_path.name}:{file_size}:{mtime}".encode("utf-8"))
        try:
            with open(video_path, "rb") as f:
                h.update(f.read(65536))
                if file_size > 131072:
                    f.seek(file_size // 2)
                    h.update(f.read(65536))
        except Exception:
            pass
        return h.hexdigest()[:16]

    def detect_shots(
        self,
        video_path: Path,
        movie_number: int = 1,
        narrative_era: NarrativeEra = NarrativeEra.ANY,
        max_shots: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[BeastCandidateShot]:
        """
        Detects atomic shot boundaries in video file using PySceneDetect.
        Returns list of BeastCandidateShot with exact source timestamps.
        """
        v_path = Path(video_path)
        if not v_path.exists():
            logger.warning("Video file not found: %s", v_path)
            return []

        fp = self._compute_file_fingerprint(v_path)
        cache_file = self.cache_dir / f"shots_{v_path.stem}_{fp}.json"

        if use_cache and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                shots = []
                for item in cached_data:
                    shot = BeastCandidateShot(
                        shot_id=item["shot_id"],
                        source_video=item["source_video"],
                        movie_number=item["movie_number"],
                        start_seconds=item["start_seconds"],
                        end_seconds=item["end_seconds"],
                        duration=item["duration"],
                        narrative_era=NarrativeEra(item.get("narrative_era", "ANY")),
                        scene_description=item.get("scene_description", ""),
                        characters_present=item.get("characters_present", []),
                        objects_present=item.get("objects_present", []),
                        actions_depicted=item.get("actions_depicted", []),
                        environment=item.get("environment", ""),
                        shot_scale=ShotScale(item.get("shot_scale", "medium")),
                    )
                    shots.append(shot)
                logger.info("Loaded %d shots from cache for %s", len(shots), v_path.name)
                return shots[:max_shots] if max_shots else shots
            except Exception as e:
                logger.warning("Failed to load cached shots (%s). Re-detecting...", e)

        logger.info("Running PySceneDetect AdaptiveDetector on %s...", v_path.name)
        try:
            # Run PySceneDetect with adaptive detector
            scene_list = detect(str(v_path), AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=24))
        except Exception as e:
            logger.error("PySceneDetect error: %s. Falling back to ContentDetector.", e)
            try:
                scene_list = detect(str(v_path), ContentDetector(threshold=27.0))
            except Exception as e2:
                logger.error("ContentDetector error: %s", e2)
                return []

        candidate_shots: List[BeastCandidateShot] = []
        for idx, (start_time, end_time) in enumerate(scene_list, 1):
            t_start = start_time.get_seconds()
            t_end = end_time.get_seconds()
            dur = t_end - t_start

            if dur < self.min_shot_duration:
                continue

            shot_id = f"shot_m{movie_number}_{idx:04d}_{int(t_start*1000)}"
            shot = BeastCandidateShot(
                shot_id=shot_id,
                source_video=str(v_path),
                movie_number=movie_number,
                start_seconds=t_start,
                end_seconds=t_end,
                duration=dur,
                narrative_era=narrative_era,
                scene_description=f"Movie {movie_number} scene at {t_start:.1f}s - {t_end:.1f}s",
            )
            candidate_shots.append(shot)
            if max_shots and len(candidate_shots) >= max_shots:
                break

        # Save cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in candidate_shots], f, indent=2)
            logger.info("Cached %d detected shots to %s", len(candidate_shots), cache_file)
        except Exception as e:
            logger.warning("Failed to write shot cache: %s", e)

        return candidate_shots

    def extract_multi_frame_sample(
        self,
        shot: BeastCandidateShot,
        extract_images: bool = True,
    ) -> MultiFrameSample:
        """
        Extracts 5 equidistant frames (10%, 30%, 50%, 70%, 90%) across the temporal interval.
        Computes inter-frame motion scores using mean absolute pixel differences.
        """
        t_start = shot.start_seconds
        t_end = shot.end_seconds
        dur = shot.duration
        v_path = Path(shot.source_video)

        timestamps = [round(t_start + p * dur, 3) for p in SAMPLE_PERCENTILES]
        frame_paths = []
        motion_scores = []
        extracted_frames_np = []

        if extract_images and v_path.exists():
            shot_dir = self.frames_dir / shot.shot_id
            shot_dir.mkdir(parents=True, exist_ok=True)

            for idx, (p, ts) in enumerate(zip(SAMPLE_PERCENTILES, timestamps)):
                out_path = shot_dir / f"f_{int(p*100):02d}_{ts:.2f}s.jpg"
                if not out_path.exists():
                    cmd = [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-ss", f"{ts:.3f}",
                        "-i", str(v_path),
                        "-vframes", "1",
                        "-q:v", "3",
                        str(out_path)
                    ]
                    subprocess.run(cmd, capture_output=True)

                if out_path.exists():
                    frame_paths.append(str(out_path))
                    img = cv2.imread(str(out_path))
                    if img is not None:
                        extracted_frames_np.append(img)
                else:
                    frame_paths.append("")

            # Compute motion scores between consecutive frames
            for i in range(len(extracted_frames_np) - 1):
                f1 = extracted_frames_np[i]
                f2 = extracted_frames_np[i + 1]
                if f1.shape == f2.shape:
                    diff = cv2.absdiff(f1, f2)
                    motion = float(np.mean(diff))
                    motion_scores.append(round(motion, 2))
                else:
                    motion_scores.append(0.0)
            if not motion_scores:
                motion_scores = [0.0] * 4

        sample = MultiFrameSample(
            shot_id=shot.shot_id,
            source_video_path=str(v_path),
            timestamps=timestamps,
            percentiles=SAMPLE_PERCENTILES,
            frame_paths=frame_paths,
            motion_scores=motion_scores,
        )
        shot.multi_frame_sample = sample
        return sample
