"""
STORY FORGE — ArcFace / Feature Hypersphere Face Matcher (Phase 2)
==================================================================
Extracts face/head candidates from video frames, generates unit-normalized
multimodal embeddings, and matches against the CharacterBank.

Key Capabilities:
  1. Multi-Tier Face Extraction: Detects explicit faces via OWLv2/open-vocabulary
     or upper-body head region proposals from tracked person bounding boxes.
  2. Crop Quality Assessment: Computes Laplacian variance (sharpness) and
     resolution metric to reject blurry or sub-pixel face crops.
  3. ArcFace-Style Hypersphere Matching: Evaluates cosine similarities against
     all exemplars for every bank identity.
  4. Fail-Closed Uncertainty: Returns UNKNOWN whenever confidence is below
     threshold or margin over runner-up is ambiguous.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image

from py_visual_evidence.schema import BoundingBox, EntitySpec, GroundedEntity
from py_visual_evidence.grounding import BaseEntityGrounder, OpenVocabularyGrounder
from engines.retrieval.clip_encoder import OpenCLIPVisualEncoder
from engines.perception.models import (
    FaceDetection,
    IdentityMatchResult,
    IdentityMatchStatus,
    IdentityRejectionReason,
)
from engines.perception.character_bank import CharacterBank

logger = logging.getLogger("FaceMatcher")


class FaceMatcher:
    """
    Performs face localization, crop quality filtering, embedding extraction,
    and character bank matching.
    """

    def __init__(
        self,
        character_bank: CharacterBank,
        encoder: Optional[OpenCLIPVisualEncoder] = None,
        grounder: Optional[BaseEntityGrounder] = None,
        threshold_confirm: float = 0.80,
        threshold_partial: float = 0.72,
        margin_threshold: float = 0.04,
        min_crop_resolution: int = 32,
    ):
        self.character_bank = character_bank
        self.encoder = encoder or OpenCLIPVisualEncoder.get_instance()
        self.grounder = grounder or OpenVocabularyGrounder(confidence_threshold=0.15)
        self.threshold_confirm = threshold_confirm
        self.threshold_partial = threshold_partial
        self.margin_threshold = margin_threshold
        self.min_crop_resolution = min_crop_resolution

    def compute_crop_quality(self, crop: np.ndarray) -> float:
        """
        Estimates visual quality of face crop based on resolution and Laplacian sharpness.
        Returns a score in [0.0, 1.0].
        """
        if crop is None or crop.size == 0:
            return 0.0
        h, w = crop.shape[:2]
        if h < self.min_crop_resolution or w < self.min_crop_resolution:
            return 0.2

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if laplacian_var < 5.0:
            return 0.05
        # Normalization: variance > 250 is very sharp
        sharpness_score = min(1.0, laplacian_var / 250.0)
        res_score = min(1.0, (w * h) / (120.0 * 120.0))
        return round(0.5 * sharpness_score + 0.5 * res_score, 3)

    def extract_crop(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        padding: float = 0.15,
    ) -> Tuple[np.ndarray, float]:
        """
        Crops the bounding box region with symmetric margin padding, clipped to frame bounds.
        Returns (cropped_bgr, quality_score).
        """
        img_h, img_w = frame.shape[:2]
        px_x, px_y, px_w, px_h = bbox.to_pixels(img_w, img_h)

        pad_w = int(px_w * padding)
        pad_h = int(px_h * padding)

        x1 = max(0, px_x - pad_w)
        y1 = max(0, px_y - pad_h)
        x2 = min(img_w, px_x + px_w + pad_w)
        y2 = min(img_h, px_y + px_h + pad_h)

        if x2 <= x1 or y2 <= y1:
            return np.zeros((16, 16, 3), dtype=np.uint8), 0.0

        crop = frame[y1:y2, x1:x2]
        quality = self.compute_crop_quality(crop)
        return crop, quality

    def detect_and_match_faces(
        self,
        frame: np.ndarray,
        timestamp_sec: float = 0.0,
    ) -> List[Tuple[FaceDetection, IdentityMatchResult]]:
        """
        Detects all faces in frame and matches each against the Character Bank.
        Returns list of (FaceDetection, IdentityMatchResult).
        """
        # Ground face entities
        specs = [
            EntitySpec(name="face", role="subject", description="face of a person", min_confidence=0.18),
            EntitySpec(name="head", role="subject", description="head of a person", min_confidence=0.18),
        ]
        entities = self.grounder.ground_entities(frame, specs, timestamp_sec=timestamp_sec)

        results = []
        for i, ent in enumerate(entities):
            crop, quality = self.extract_crop(frame, ent.bbox, padding=0.15)
            if quality < 0.20:
                # Blurry or microscopic crop -> reject early
                detection = FaceDetection(
                    face_id=f"face_{i}_{int(timestamp_sec*1000)}",
                    bbox=ent.bbox,
                    confidence=ent.confidence,
                    crop_quality=quality,
                )
                match_res = IdentityMatchResult(
                    status=IdentityMatchStatus.UNKNOWN,
                    rejection_reason=IdentityRejectionReason.LOW_DETECTION_CONFIDENCE,
                    explanation=f"Face crop quality too low ({quality:.2f} < 0.20).",
                )
                results.append((detection, match_res))
                continue

            # Compute normalized embedding
            emb = self.encoder.encode_image(crop)
            detection = FaceDetection(
                face_id=f"face_{i}_{int(timestamp_sec*1000)}",
                bbox=ent.bbox,
                confidence=ent.confidence,
                crop_quality=quality,
                embedding=emb.tolist(),
            )

            # Match against Character Bank
            match_res = self.character_bank.match_embedding(
                emb,
                threshold_confirm=self.threshold_confirm,
                threshold_partial=self.threshold_partial,
                margin_threshold=self.margin_threshold,
            )
            results.append((detection, match_res))

        return results

    def match_person_head(
        self,
        frame: np.ndarray,
        person_bbox: BoundingBox,
        timestamp_sec: float = 0.0,
    ) -> Tuple[Optional[FaceDetection], IdentityMatchResult]:
        """
        Extracts the upper head region of a detected person bbox and matches identity.
        Useful when face detector missed but person is tracked.
        """
        # Propose head sub-box: upper 35% height, center 70% width
        head_x = person_bbox.x + (person_bbox.w * 0.15)
        head_y = person_bbox.y
        head_w = person_bbox.w * 0.70
        head_h = person_bbox.h * 0.35

        head_bbox = BoundingBox(
            x=max(0.0, min(1.0, head_x)),
            y=max(0.0, min(1.0, head_y)),
            w=max(0.01, min(1.0 - head_x, head_w)),
            h=max(0.01, min(1.0 - head_y, head_h)),
        )

        crop, quality = self.extract_crop(frame, head_bbox, padding=0.10)
        if quality < 0.20:
            return None, IdentityMatchResult(
                status=IdentityMatchStatus.UNKNOWN,
                rejection_reason=IdentityRejectionReason.HEAVILY_OCCLUDED_OR_BACK_FACING,
                explanation="Head region crop quality is too degraded or occluded.",
            )

        emb = self.encoder.encode_image(crop)
        detection = FaceDetection(
            face_id=f"head_{int(timestamp_sec*1000)}",
            bbox=head_bbox,
            confidence=0.85,
            crop_quality=quality,
            embedding=emb.tolist(),
        )

        match_res = self.character_bank.match_embedding(
            emb,
            threshold_confirm=self.threshold_confirm,
            threshold_partial=self.threshold_partial,
            margin_threshold=self.margin_threshold,
        )
        return detection, match_res
