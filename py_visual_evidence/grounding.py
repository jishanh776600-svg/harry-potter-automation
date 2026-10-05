"""
Tier 1: Sparse Keyframe Entity Grounding
Locates open-vocabulary subjects, objects, and recipients on strategic keyframes.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

from py_visual_evidence.schema import EntitySpec, GroundedEntity, BoundingBox


class BaseEntityGrounder(ABC):
    """Abstract interface for sparse open-vocabulary entity grounding."""

    @abstractmethod
    def ground_entities(
        self,
        frame: np.ndarray,
        entity_specs: List[EntitySpec],
        timestamp_sec: float = 0.0,
        frame_index: int = 0
    ) -> List[GroundedEntity]:
        """Locates the requested entity specifications on a single frame."""
        pass


class OpenVocabularyGrounder(BaseEntityGrounder):
    """
    Open-vocabulary grounder utilizing lightweight CPU-native models or
    HuggingFace transformers (e.g. OWLv2, YOLO-World).
    """

    def __init__(
        self,
        model_name: str = "google/owlv2-base-patch16-ensemble",
        device: str = "cpu",
        confidence_threshold: float = 0.15,
        lazy_load: bool = True
    ):
        self.model_name = model_name
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.lazy_load = lazy_load
        self._processor = None
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            try:
                from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
                try:
                    self._processor = AutoProcessor.from_pretrained(self.model_name, local_files_only=True)
                    self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_name, local_files_only=True).to(self.device)
                except Exception:
                    self._processor = AutoProcessor.from_pretrained(self.model_name)
                    self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_name).to(self.device)
                self._model.eval()
            except Exception as e:
                # Keep as None; fallback will activate
                self._model = None

    def ground_entities(
        self,
        frame: np.ndarray,
        entity_specs: List[EntitySpec],
        timestamp_sec: float = 0.0,
        frame_index: int = 0
    ) -> List[GroundedEntity]:
        if not entity_specs:
            return []

        self._ensure_loaded()
        img_h, img_w, _ = frame.shape
        grounded = []

        if self._model is not None and self._processor is not None:
            import torch
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            queries = [[spec.description or spec.name for spec in entity_specs]]
            
            inputs = self._processor(text=queries, images=pil_img, padding=True, truncation=True, max_length=16, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self._model(**inputs)

            target_sizes = torch.Tensor([[img_h, img_w]]).to(self.device)
            results = self._processor.post_process_grounded_object_detection(
                outputs=outputs, target_sizes=target_sizes, threshold=self.confidence_threshold, text_labels=queries
            )

            res = results[0]
            boxes, scores, labels = res["boxes"].cpu(), res["scores"].cpu(), res["labels"]

            # Map detections back to requested specs
            for box, score, label in zip(boxes, scores, labels):
                spec_idx = int(label.item()) if hasattr(label, "item") else (int(label) if isinstance(label, (int, np.integer)) or str(label).isdigit() else 0)
                if 0 <= spec_idx < len(entity_specs):
                    target_spec = entity_specs[spec_idx]
                    px_x1, px_y1, px_x2, px_y2 = box.tolist()
                    norm_bbox = BoundingBox(
                        x=max(0.0, min(1.0, px_x1 / img_w)),
                        y=max(0.0, min(1.0, px_y1 / img_h)),
                        w=max(0.01, min(1.0, (px_x2 - px_x1) / img_w)),
                        h=max(0.01, min(1.0, (px_y2 - px_y1) / img_h)),
                    )
                    grounded.append(
                        GroundedEntity(
                            entity_name=target_spec.name,
                            role=target_spec.role,
                            bbox=norm_bbox,
                            confidence=float(score),
                            frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                        )
                    )
        return grounded


class DeterministicBenchmarkGrounder(BaseEntityGrounder):
    """
    Deterministic rule-based grounder for fast CI, unit testing, and controlled benchmarks.
    Simulates grounded bounding boxes based on canonical visual properties.
    """

    def __init__(self, ground_truth_map: Optional[Dict[str, List[BoundingBox]]] = None, strict: bool = False):
        self.ground_truth_map = ground_truth_map or {}
        self.strict = strict

    def register_ground_truth(self, entity_name: str, bbox: BoundingBox):
        if entity_name not in self.ground_truth_map:
            self.ground_truth_map[entity_name] = []
        self.ground_truth_map[entity_name].append(bbox)

    def ground_entities(
        self,
        frame: np.ndarray,
        entity_specs: List[EntitySpec],
        timestamp_sec: float = 0.0,
        frame_index: int = 0
    ) -> List[GroundedEntity]:
        grounded = []
        img_h, img_w, _ = frame.shape

        for spec in entity_specs:
            # Check explicit map
            if spec.name in self.ground_truth_map:
                for bbox in self.ground_truth_map[spec.name]:
                    grounded.append(
                        GroundedEntity(
                            entity_name=spec.name,
                            role=spec.role,
                            bbox=bbox,
                            confidence=0.95,
                            frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                        )
                    )
            elif not self.strict:
                # Default canonical bounding boxes only when no explicit ground truth map was provided
                if "subject" in spec.role:
                    grounded.append(
                        GroundedEntity(
                            entity_name=spec.name,
                            role=spec.role,
                            bbox=BoundingBox(x=0.25, y=0.15, w=0.25, h=0.70),
                            confidence=0.92,
                            frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                        )
                    )
                elif "object" in spec.role:
                    grounded.append(
                        GroundedEntity(
                            entity_name=spec.name,
                            role=spec.role,
                            bbox=BoundingBox(x=0.45, y=0.35, w=0.12, h=0.25),
                            confidence=0.88,
                            frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                        )
                    )
                elif "recipient" in spec.role:
                    grounded.append(
                        GroundedEntity(
                            entity_name=spec.name,
                            role=spec.role,
                            bbox=BoundingBox(x=0.60, y=0.15, w=0.25, h=0.70),
                            confidence=0.90,
                            frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                        )
                    )
        return grounded
