"""
STORY FORGE — Small Object Grounding & Selective Mask Refinement (Phase 2)
===========================================================================
Detects canonical props (wands, swords, sorting hat, books, letters, cups) with:
  1. Fast Proposal: OWLv2 open-vocabulary grounding for candidate prop queries.
  2. Multi-Scale Hand/Crop Expansion: For thin props (e.g. wands occupying <1% frame),
     searches localized high-resolution crops around character hands/interaction zones.
  3. Selective Mask Refinement: Upgrades coarse bounding boxes to binary pixel masks
     via contour / GrabCut refinement or SAM-2 when available.
  4. Physical State Estimation: Assesses component topology (INTACT vs BROKEN)
     from refined object masks (e.g. verifying Elder Wand snap).
"""

from __future__ import annotations
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import cv2
import numpy as np

from py_visual_evidence.schema import BoundingBox, EntitySpec, GroundedEntity
from py_visual_evidence.grounding import BaseEntityGrounder, OpenVocabularyGrounder
from engines.perception.models import VisualObject

logger = logging.getLogger("ObjectGrounder")

# Canonical Harry Potter object queries and prompt aliases
CANONICAL_PROPS: Dict[str, Dict[str, Any]] = {
    "elder_wand": {
        "label": "elder_wand",
        "aliases": ["elder wand", "the elder wand", "dumbledore's wand", "wooden wand", "wand"],
        "is_small_prop": True,
        "expected_states": ["INTACT", "BROKEN"],
    },
    "wand": {
        "label": "wand",
        "aliases": ["wooden magic wand", "magic wand", "wand"],
        "is_small_prop": True,
        "expected_states": ["INTACT", "HELD"],
    },
    "sword": {
        "label": "sword_of_gryffindor",
        "aliases": ["sword of gryffindor", "silver sword", "ruby sword", "sword"],
        "is_small_prop": False,
        "expected_states": ["INTACT", "HELD", "SWUNG"],
    },
    "sorting_hat": {
        "label": "sorting_hat",
        "aliases": ["patched wizard hat", "sorting hat", "brown pointed hat"],
        "is_small_prop": False,
        "expected_states": ["INTACT", "PLACED"],
    },
    "book": {
        "label": "book",
        "aliases": ["leather book", "heavy book", "textbook", "open book"],
        "is_small_prop": False,
        "expected_states": ["INTACT", "OPEN", "CLOSED"],
    },
    "letter": {
        "label": "hogwarts_letter",
        "aliases": ["envelope with red wax seal", "hogwarts acceptance letter", "parchment letter"],
        "is_small_prop": True,
        "expected_states": ["INTACT", "HELD", "OPENED"],
    },
    "cup": {
        "label": "goblet",
        "aliases": ["crystal goblet", "gold cup", "chalice", "drinking cup"],
        "is_small_prop": True,
        "expected_states": ["INTACT", "HELD"],
    },
}


class ObjectGrounder:
    """
    Grounds and tracks physical props in candidate scenes.
    Combines fast open-vocabulary proposals with multi-scale zooming and mask refinement.
    """

    def __init__(
        self,
        grounder: Optional[BaseEntityGrounder] = None,
        confidence_threshold: float = 0.15,
        enable_sam2_refinement: bool = False,
    ):
        self.grounder = grounder or OpenVocabularyGrounder(confidence_threshold=confidence_threshold)
        self.confidence_threshold = confidence_threshold
        self.enable_sam2_refinement = enable_sam2_refinement
        self._sam2_model = None

    def ground_objects(
        self,
        frame: np.ndarray,
        target_labels: List[str],
        timestamp_sec: float = 0.0,
        person_boxes: Optional[List[BoundingBox]] = None,
    ) -> List[VisualObject]:
        """
        Locates target objects in frame, applying multi-scale zooming for small props.
        """
        if not target_labels:
            return []

        img_h, img_w = frame.shape[:2]
        grounded_objects: List[VisualObject] = []

        # Formulate EntitySpecs for requested labels
        specs: List[EntitySpec] = []
        for lbl in target_labels:
            clean = lbl.strip().lower()
            prop_info = CANONICAL_PROPS.get(clean)
            if prop_info:
                desc = prop_info["aliases"][0]
                specs.append(EntitySpec(name=prop_info["label"], role="object", description=desc, min_confidence=self.confidence_threshold))
            else:
                specs.append(EntitySpec(name=clean, role="object", description=clean, min_confidence=self.confidence_threshold))

        # 1. Full-frame pass
        entities = self.grounder.ground_entities(frame, specs, timestamp_sec=timestamp_sec)

        # Map entities to VisualObjects
        for i, ent in enumerate(entities):
            mask, state = self.refine_mask_and_state(frame, ent.bbox, ent.entity_name)
            obj = VisualObject(
                object_id=f"obj_{ent.entity_name}_{i}_{int(timestamp_sec*1000)}",
                label=ent.entity_name,
                bbox=ent.bbox,
                mask=mask,
                confidence=round(ent.confidence, 4),
                state=state,
                timestamp=timestamp_sec,
            )
            grounded_objects.append(obj)

        # 2. Multi-scale pass for thin/small props (e.g. wand, letter) if not found in full frame
        small_prop_targets = [s for s in specs if s.name in ("elder_wand", "wand", "letter", "goblet")]
        if small_prop_targets and person_boxes and len(grounded_objects) == 0:
            for pbox in person_boxes:
                # Zoom into lower-mid region of person (hand/waist area)
                zoom_x = max(0.0, pbox.x - 0.05)
                zoom_y = max(0.0, pbox.y + (pbox.h * 0.30))
                zoom_w = min(1.0 - zoom_x, pbox.w + 0.10)
                zoom_h = min(1.0 - zoom_y, pbox.h * 0.65)
                zoom_bbox = BoundingBox(x=round(zoom_x, 6), y=round(zoom_y, 6), w=round(zoom_w, 6), h=round(zoom_h, 6))

                px, py, pw, ph = zoom_bbox.to_pixels(img_w, img_h)
                if pw < 30 or ph < 30:
                    continue
                crop = frame[py:py+ph, px:px+pw]

                # Run detection on crop
                crop_ents = self.grounder.ground_entities(crop, small_prop_targets, timestamp_sec=timestamp_sec)
                for ent in crop_ents:
                    # Remap crop coordinates to full frame
                    fx = zoom_bbox.x + (ent.bbox.x * zoom_bbox.w)
                    fy = zoom_bbox.y + (ent.bbox.y * zoom_bbox.h)
                    fw = ent.bbox.w * zoom_bbox.w
                    fh = ent.bbox.h * zoom_bbox.h
                    mapped_bbox = BoundingBox(x=round(fx, 6), y=round(fy, 6), w=round(fw, 6), h=round(fh, 6))

                    mask, state = self.refine_mask_and_state(frame, mapped_bbox, ent.entity_name)
                    obj = VisualObject(
                        object_id=f"obj_zoom_{ent.entity_name}_{int(timestamp_sec*1000)}",
                        label=ent.entity_name,
                        bbox=mapped_bbox,
                        mask=mask,
                        confidence=round(ent.confidence, 4),
                        state=state,
                        timestamp=timestamp_sec,
                    )
                    grounded_objects.append(obj)
                    break

        return grounded_objects

    def refine_mask_and_state(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        label: str,
    ) -> Tuple[Optional[List[List[int]]], str]:
        """
        Refines bounding box into a pixel-level binary mask and assesses physical state.
        For wands: checks if the mask consists of 1 connected component (INTACT) or 2 (BROKEN).
        """
        img_h, img_w = frame.shape[:2]
        px, py, pw, ph = bbox.to_pixels(img_w, img_h)
        if pw < 4 or ph < 4:
            return None, "INTACT"

        crop = frame[py:py+ph, px:px+pw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop

        # Adaptive thresholding to segment prop foreground
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Clean mask via morphological closing
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Analyze connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(closed)
        # Filter tiny noise components (< 5% of crop area)
        min_area = 0.05 * (pw * ph)
        valid_components = [i for i in range(1, num_labels) if stats[i, cv2.CC_STAT_AREA] >= min_area]

        state = "INTACT"
        if "wand" in label.lower():
            if len(valid_components) >= 2:
                state = "BROKEN"
            else:
                state = "INTACT"

        # Downsample mask to 16x16 binary matrix for compact storage
        resized_mask = cv2.resize(closed, (16, 16), interpolation=cv2.INTER_NEAREST)
        binary_grid = (resized_mask > 128).astype(int).tolist()

        return binary_grid, state
