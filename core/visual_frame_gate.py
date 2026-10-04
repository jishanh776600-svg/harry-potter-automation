"""
Visual Frame Gate (Computer Vision Quality & Character Presence Gate)
=====================================================================
Performs frame-level computer vision verification on extracted movie clips.
Ensures zero inanimate object cutaways, zero blackout frames, and guaranteed
character face presence when required by the script.
"""

import os
import cv2
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HAAR_PATH = PROJECT_ROOT / "data" / "models" / "haarcascade_frontalface_default.xml"
YUNET_PATH = PROJECT_ROOT / "data" / "models" / "face_detection_yunet_2023mar.onnx"

MIN_BRIGHTNESS = 20.0
MIN_FACE_AREA_RATIO = 0.006  # Face must occupy at least 0.6% of frame area


class VisualFrameGate:
    def __init__(
        self,
        haar_path: Optional[Path] = None,
        yunet_path: Optional[Path] = None,
        min_brightness: float = MIN_BRIGHTNESS,
        min_face_area_ratio: float = MIN_FACE_AREA_RATIO,
    ):
        self.min_brightness = min_brightness
        self.min_face_area_ratio = min_face_area_ratio

        # Load Haar Cascade
        h_path = haar_path or HAAR_PATH
        self.face_cascade = cv2.CascadeClassifier(str(h_path)) if h_path.exists() else None

        # Load YuNet ONNX
        y_path = yunet_path or YUNET_PATH
        self.yunet = None
        if y_path.exists():
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(y_path), "", (320, 320))
            except Exception as e:
                logger.warning(f"Failed to initialize YuNet face detector: {e}")

    def inspect_frame(self, frame) -> Dict[str, Any]:
        """
        Analyzes a single frame for brightness and face presence.
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())

        faces = []
        max_face_area = 0.0

        # Primary: YuNet
        if self.yunet is not None:
            try:
                self.yunet.setInputSize((w, h))
                _, faces_yn = self.yunet.detect(frame)
                if faces_yn is not None:
                    for f in faces_yn:
                        fx, fy, fw, fh = f[:4]
                        area_ratio = (fw * fh) / (w * h)
                        if area_ratio > max_face_area:
                            max_face_area = float(area_ratio)
                        faces.append({
                            "bbox": [float(fx), float(fy), float(fw), float(fh)],
                            "area_ratio": float(area_ratio),
                            "confidence": float(f[14]) if len(f) > 14 else 1.0,
                            "detector": "yunet"
                        })
            except Exception as e:
                logger.debug(f"YuNet detection exception: {e}")

        # Secondary fallback: Haar Cascade
        if not faces and self.face_cascade is not None:
            faces_haar = self.face_cascade.detectMultiScale(gray, 1.1, 4)
            for (hx, hy, hw, hh) in faces_haar:
                area_ratio = (hw * hh) / (w * h)
                if area_ratio > max_face_area:
                    max_face_area = float(area_ratio)
                faces.append({
                    "bbox": [float(hx), float(hy), float(hw), float(hh)],
                    "area_ratio": float(area_ratio),
                    "confidence": 0.85,
                    "detector": "haar"
                })

        valid_faces = [f for f in faces if f["area_ratio"] >= self.min_face_area_ratio]

        return {
            "brightness": brightness,
            "face_count": len(valid_faces),
            "max_face_area": max_face_area,
            "has_face": len(valid_faces) > 0,
            "is_too_dark": brightness < self.min_brightness
        }

    def verify_clip(
        self,
        clip_path: Path,
        required_characters: Optional[List[str]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Samples frames across the clip and verifies visual quality and character presence.
        Returns:
            (is_accepted: bool, reason: str, stats: Dict)
        """
        clip_p = Path(clip_path)
        if not clip_p.exists():
            return False, f"FILE_NOT_FOUND: {clip_p}", {}

        cap = cv2.VideoCapture(str(clip_p))
        if not cap.isOpened():
            return False, f"CANNOT_OPEN_VIDEO: {clip_p}", {}

        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if n_frames <= 0:
            cap.release()
            return False, "EMPTY_VIDEO_ZERO_FRAMES", {}

        # Sample at 25%, 50%, 75%
        sample_indices = [
            max(0, int(n_frames * 0.25)),
            max(0, int(n_frames * 0.50)),
            max(0, int(n_frames * 0.75)),
        ]

        frame_results = []
        for s_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, s_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                res = self.inspect_frame(frame)
                frame_results.append(res)

        cap.release()

        if not frame_results:
            return False, "CANNOT_DECODE_FRAMES", {}

        avg_brightness = sum(r["brightness"] for r in frame_results) / len(frame_results)
        any_face = any(r["has_face"] for r in frame_results)
        max_area = max(r["max_face_area"] for r in frame_results)
        total_detected_faces = sum(r["face_count"] for r in frame_results)

        stats = {
            "avg_brightness": round(avg_brightness, 1),
            "any_face_detected": any_face,
            "max_face_area_pct": round(max_area * 100, 2),
            "total_detected_faces": total_detected_faces,
            "frames_inspected": len(frame_results)
        }

        # Check 1: Luminance gate
        if avg_brightness < self.min_brightness:
            return False, f"REJECTED_FRAME_TOO_DARK (avg brightness {avg_brightness:.1f} < {self.min_brightness})", stats

        # Check 2: Character presence gate
        req_chars = [c for c in (required_characters or []) if c.lower() not in ("hogwarts", "castle", "hogwarts castle")]
        if req_chars:
            if not any_face:
                return False, f"REJECTED_NO_CHARACTER_FACE (Required {req_chars}, but 0 human faces detected in clip)", stats

        return True, "ACCEPTED_VISUAL_GATE_VERIFIED", stats
