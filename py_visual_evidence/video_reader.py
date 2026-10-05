"""
Video Reader and Frame Slicing Primitives
Supports local file iteration, downsampling, and sub-clip temporal extraction.
"""

from __future__ import annotations
from pathlib import Path
from typing import Generator, Tuple, Optional, List
import cv2
import numpy as np


class VideoClip:
    def __init__(self, video_path: str | Path, start_sec: float = 0.0, end_sec: Optional[float] = None):
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.video_path}")
        
        self.start_sec = max(0.0, start_sec)
        self.end_sec = end_sec
        self._meta = self._probe()

    def _probe(self) -> dict:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {self.video_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_sec = total_frames / fps if fps > 0 else 0.0
        cap.release()

        effective_end = min(total_sec, self.end_sec) if self.end_sec is not None else total_sec
        effective_dur = max(0.0, effective_end - self.start_sec)

        return {
            "fps": fps,
            "width": w,
            "height": h,
            "total_frames": total_frames,
            "total_sec": total_sec,
            "effective_start": self.start_sec,
            "effective_end": effective_end,
            "effective_duration": effective_dur,
        }

    @property
    def fps(self) -> float:
        return self._meta["fps"]

    @property
    def width(self) -> int:
        return self._meta["width"]

    @property
    def height(self) -> int:
        return self._meta["height"]

    @property
    def duration(self) -> float:
        return self._meta["effective_duration"]

    def read_all_frames(self, max_height: Optional[int] = None) -> List[np.ndarray]:
        """Reads all frames within the clip interval, optionally resizing."""
        frames = []
        for _, frame in self.iter_frames(max_height=max_height):
            frames.append(frame)
        return frames

    def iter_frames(
        self, max_height: Optional[int] = None, step: int = 1
    ) -> Generator[Tuple[float, np.ndarray], None, None]:
        """Yields (timestamp_sec, frame_bgr) for frames within the target interval."""
        cap = cv2.VideoCapture(str(self.video_path))
        fps = self.fps
        
        # Seek to start
        start_frame = int(self.start_sec * fps)
        end_frame = int(self._meta["effective_end"] * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        current_frame = start_frame
        try:
            while current_frame <= end_frame:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if (current_frame - start_frame) % step == 0:
                    t_sec = current_frame / fps
                    if max_height and frame.shape[0] > max_height:
                        scale = max_height / frame.shape[0]
                        new_w = int(frame.shape[1] * scale)
                        frame = cv2.resize(frame, (new_w, max_height))
                    yield t_sec, frame
                    
                current_frame += 1
        finally:
            cap.release()

    def get_keyframe(self, position_ratio: float = 0.0) -> Tuple[float, np.ndarray]:
        """Fetches a single keyframe at a given fractional offset [0.0 to 1.0]."""
        cap = cv2.VideoCapture(str(self.video_path))
        target_sec = self.start_sec + (self.duration * min(1.0, max(0.0, position_ratio)))
        target_frame = int(target_sec * self.fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Could not read keyframe at {target_sec:.2f}s from {self.video_path}")
        return target_sec, frame
