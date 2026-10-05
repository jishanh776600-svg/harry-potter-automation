"""
Tier 0: Shot Boundary Analysis (PySceneDetect Integration)
Detects cinematic cuts and transitions, ensuring evidence is not conflated across cuts.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from scenedetect import detect, ContentDetector, AdaptiveDetector


class ShotAnalysisResult:
    def __init__(self, scenes: List[Tuple[float, float]], total_duration: float):
        self.scenes = scenes
        self.total_duration = total_duration

    @property
    def shot_count(self) -> int:
        return len(self.scenes) if self.scenes else 1

    @property
    def is_single_shot(self) -> bool:
        return self.shot_count == 1

    @property
    def cut_timestamps(self) -> List[float]:
        # End timestamp of all shots except the last
        if len(self.scenes) <= 1:
            return []
        return [s[1] for s in self.scenes[:-1]]

    def contains_cut_between(self, start_sec: float, end_sec: float) -> bool:
        """Returns True if a camera cut occurs within the specified interval."""
        for cut in self.cut_timestamps:
            if start_sec < cut < end_sec:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_count": self.shot_count,
            "is_single_shot": self.is_single_shot,
            "scenes": [(round(s[0], 3), round(s[1], 3)) for s in self.scenes],
            "cut_timestamps": [round(c, 3) for c in self.cut_timestamps],
            "total_duration": round(self.total_duration, 3),
        }


class ShotBoundaryDetector:
    def __init__(self, threshold: float = 27.0, min_scene_len_sec: float = 0.4):
        self.threshold = threshold
        self.min_scene_len_sec = min_scene_len_sec

    def analyze(self, video_path: str | Path, start_sec: float = 0.0, end_sec: Optional[float] = None) -> ShotAnalysisResult:
        """Analyzes camera shot boundaries across the clip using PySceneDetect ContentDetector."""
        video_p = Path(video_path)
        if not video_p.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_p}")

        try:
            detector = ContentDetector(threshold=self.threshold)
            scene_list = detect(str(video_p), detector)
        except Exception:
            # Fallback if scenedetect encounters format edge cases
            scene_list = []

        if not scene_list:
            # Single continuous shot spanning the entire interval
            if end_sec is not None:
                dur = max(0.0, end_sec - start_sec)
            else:
                import cv2
                cap = cv2.VideoCapture(str(video_p))
                fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                total_sec = total_frames / fps if fps > 0 else 1.0
                cap.release()
                dur = max(0.0, total_sec - start_sec)
            return ShotAnalysisResult(scenes=[(start_sec, start_sec + dur)], total_duration=dur)

        scenes_sec = [
            (
                getattr(s[0], "seconds", s[0].get_seconds()),
                getattr(s[1], "seconds", s[1].get_seconds()),
            )
            for s in scene_list
        ]
        
        # Filter to requested temporal window if specified
        if end_sec is not None:
            filtered = []
            for s_start, s_end in scenes_sec:
                if s_end > start_sec and s_start < end_sec:
                    clamped_start = max(start_sec, s_start)
                    clamped_end = min(end_sec, s_end)
                    if (clamped_end - clamped_start) >= 0.05:
                        filtered.append((clamped_start, clamped_end))
            if filtered:
                scenes_sec = filtered

        total_dur = scenes_sec[-1][1] - scenes_sec[0][0] if scenes_sec else 0.0
        return ShotAnalysisResult(scenes=scenes_sec, total_duration=total_dur)
