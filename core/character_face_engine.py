"""
Character Face Engine (Face Recognition & Character Verification Addon)
========================================================================
Reference Face Bank & Deep Learning Face Verification for Harry Potter Automation.

Key Principles:
1. PURELY AN INSPECTION & VERIFICATION GATE:
   - Does NOT dictate clip discovery or force specific scenes.
   - Merely verifies whether a proposed video frame actually depicts the intended character.
2. PRE-COMPUTED EMBEDDINGS (OpenCV SFace 128-d cosine similarity):
   - Ultra-fast (sub-millisecond comparison).
   - Major characters: 50-60 diverse reference faces across movies.
   - Minor characters: 15-20 diverse reference faces.
"""

import os
import cv2
import json
import logging
import requests
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "data" / "models"
FACES_DIR = PROJECT_ROOT / "data" / "reference_faces"
EMBEDDINGS_CACHE_FILE = FACES_DIR / "character_embeddings.npz"

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# Cosine similarity threshold for SFace (OpenCV official recommended: >= 0.363)
MATCH_THRESHOLD = 0.363

# Major Characters (Target: 50-60 reference faces)
MAJOR_CHARACTERS = {
    "Harry Potter": 50,
    "Hermione Granger": 50,
    "Ron Weasley": 50,
    "Albus Dumbledore": 50,
    "Severus Snape": 50,
    "Draco Malfoy": 50,
    "Lord Voldemort": 50,
    "Neville Longbottom": 50,
    "Ginny Weasley": 50,
    "Minerva McGonagall": 50,
    "Rubeus Hagrid": 50,
    "Sirius Black": 50,
}

# Secondary & Minor Characters (Target: 15-20 reference faces)
SECONDARY_CHARACTERS = {
    "Vernon Dursley": 20,
    "Petunia Dursley": 20,
    "Dudley Dursley": 20,
    "Remus Lupin": 20,
    "Bellatrix Lestrange": 20,
    "Lucius Malfoy": 20,
    "Fred Weasley": 20,
    "George Weasley": 20,
    "Molly Weasley": 20,
    "Arthur Weasley": 20,
    "Percy Weasley": 20,
    "Luna Lovegood": 20,
    "Cedric Diggory": 20,
    "Cho Chang": 20,
    "Dolores Umbridge": 20,
    "Alastor Moody": 20,
    "Barty Crouch Jr.": 20,
    "Peter Pettigrew": 20,
    "Argus Filch": 20,
    "Gilderoy Lockhart": 20,
    "Quirinus Quirrell": 20,
    "Sybill Trelawney": 20,
    "Horace Slughorn": 20,
    "Cornelius Fudge": 20,
    "Kingsley Shacklebolt": 20,
    "Nymphadora Tonks": 20,
    "Narcissa Malfoy": 20,
    "James Potter": 20,
    "Lily Potter": 20,
    "Moaning Myrtle": 20,
    "Oliver Wood": 20,
    "Seamus Finnigan": 20,
    "Dean Thomas": 20,
    "Lavender Brown": 20,
    "Parvati Patil": 20,
    "Padma Patil": 20,
    "Gregory Goyle": 20,
    "Vincent Crabbe": 20,
    "Colin Creevey": 20,
    "Filius Flitwick": 20,
    "Pomona Sprout": 20,
    "Madam Pomfrey": 20,
    "Madam Hooch": 20,
    "Garrick Ollivander": 20,
    "Xenophilius Lovegood": 20,
    "Aberforth Dumbledore": 20,
    "Gellert Grindelwald": 20,
    "Tom Riddle": 20,
    "Rufus Scrimgeour": 20,
    "Rita Skeeter": 20,
    "Viktor Krum": 20,
    "Fleur Delacour": 20,
    "Igor Karkaroff": 20,
    "Madame Maxime": 20,
    "Frank Bryce": 20,
    "Charity Burbage": 20,
    "Mundungus Fletcher": 20,
    "Aunt Marge": 20,
    "Stan Shunpike": 20,
    "Griphook": 20,
    "Kreacher": 20,
    "Dobby": 20,
    "Fenrir Greyback": 20,
    "Scabior": 20,
    "Alecto Carrow": 20,
    "Amycus Carrow": 20,
    "Regulus Black": 20,
    "Amos Diggory": 20,
    "Barty Crouch Sr.": 20,
}

ALL_CHARACTER_TARGETS = {**MAJOR_CHARACTERS, **SECONDARY_CHARACTERS}


def slugify_name(name: str) -> str:
    """Converts 'Albus Dumbledore' -> 'albus_dumbledore'."""
    return name.lower().replace(".", "").replace("'", "").replace("-", "_").replace(" ", "_")


class CharacterFaceEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CharacterFaceEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        FACES_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        self.yunet = None
        self.sface = None
        self._init_models()

        self.embeddings: Dict[str, np.ndarray] = {}  # slug -> np.ndarray of shape (N, 128)
        self.load_cached_embeddings()
        self._initialized = True

    def _init_models(self):
        """Initializes OpenCV YuNet detector and SFace recognizer."""
        if YUNET_PATH.exists():
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (320, 320), score_threshold=0.6)
            except Exception as e:
                logger.error(f"Error initializing YuNet: {e}")

        if SFACE_PATH.exists():
            try:
                self.sface = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
            except Exception as e:
                logger.error(f"Error initializing SFace: {e}")

    def load_cached_embeddings(self):
        """Loads precomputed 128-d face embeddings from .npz cache."""
        if EMBEDDINGS_CACHE_FILE.exists():
            try:
                data = np.load(str(EMBEDDINGS_CACHE_FILE))
                for key in data.files:
                    self.embeddings[key] = data[key]
                logger.info(f"Loaded {len(self.embeddings)} character embedding clusters from cache.")
            except Exception as e:
                logger.warning(f"Could not load cached embeddings: {e}")

    def save_cached_embeddings(self):
        """Saves current embeddings dictionary to .npz file."""
        if self.embeddings:
            np.savez_compressed(str(EMBEDDINGS_CACHE_FILE), **self.embeddings)
            logger.info(f"Saved {len(self.embeddings)} character embedding clusters to {EMBEDDINGS_CACHE_FILE.name}.")

    def extract_face_embeddings_from_image(self, img: np.ndarray) -> List[np.ndarray]:
        """
        Detects faces in an image, crops/aligns them, and computes 128-d SFace embeddings.
        """
        if self.yunet is None or self.sface is None or img is None:
            return []

        h, w = img.shape[:2]
        self.yunet.setInputSize((w, h))
        _, faces = self.yunet.detect(img)
        if faces is None or len(faces) == 0:
            return []

        embeddings = []
        for face in faces:
            try:
                aligned = self.sface.alignCrop(img, face)
                feat = self.sface.feature(aligned)
                embeddings.append(feat)
            except Exception:
                pass
        return embeddings

    def match_face_to_character(
        self,
        face_feature: np.ndarray,
        character_slug: str,
        threshold: float = MATCH_THRESHOLD
    ) -> Tuple[bool, float]:
        """
        Matches a single face feature vector against a character's reference cluster.
        Returns (is_match, best_similarity).
        """
        if self.sface is None:
            return False, 0.0

        ref_feats = self.embeddings.get(character_slug)
        if ref_feats is None or len(ref_feats) == 0:
            return False, 0.0

        best_score = -1.0
        for ref in ref_feats:
            ref_vec = ref.reshape(1, 128)
            cand_vec = face_feature.reshape(1, 128)
            score = float(self.sface.match(cand_vec, ref_vec, cv2.FaceRecognizerSF_FR_COSINE))
            if score > best_score:
                best_score = score

        return (best_score >= threshold), best_score

    def verify_character_in_frame(
        self,
        frame: np.ndarray,
        character_name: str,
        threshold: float = MATCH_THRESHOLD
    ) -> Dict[str, Any]:
        """
        Inspects an extracted video frame and checks if the given character is visible.
        Returns:
            {
                "is_present": bool,
                "character": character_name,
                "best_score": float,
                "faces_in_frame": int,
                "status": "PASS" | "FAIL_CHARACTER_MISMATCH" | "FAIL_NO_FACES"
            }
        """
        slug = slugify_name(character_name)
        if slug not in self.embeddings:
            # If character has alternative name alias (e.g. Dumbledore -> albus_dumbledore)
            for k in self.embeddings:
                if slug in k or k in slug:
                    slug = k
                    break

        if slug not in self.embeddings or len(self.embeddings[slug]) == 0:
            return {
                "is_present": True,  # Non-blocking if character has no reference cluster yet
                "character": character_name,
                "best_score": 0.0,
                "faces_in_frame": 0,
                "status": "UNINDEXED_CHARACTER_BYPASS"
            }

        cand_features = self.extract_face_embeddings_from_image(frame)
        if not cand_features:
            return {
                "is_present": False,
                "character": character_name,
                "best_score": 0.0,
                "faces_in_frame": 0,
                "status": "FAIL_NO_FACES"
            }

        overall_best = -1.0
        for feat in cand_features:
            matched, score = self.match_face_to_character(feat, slug, threshold)
            if score > overall_best:
                overall_best = score
            if matched:
                return {
                    "is_present": True,
                    "character": character_name,
                    "best_score": score,
                    "faces_in_frame": len(cand_features),
                    "status": "PASS"
                }

        return {
            "is_present": False,
            "character": character_name,
            "best_score": overall_best,
            "faces_in_frame": len(cand_features),
            "status": "FAIL_CHARACTER_MISMATCH"
        }
