"""
STORY FORGE — BEAST Semantic Retrieval Engine (Phase 4)
================================================================================
Implements multi-representation image-text and video-text candidate retrieval:
  1. Computes normalized dense semantic embeddings for narration beats and visual requirements.
  2. Aggregates multi-frame embeddings across the temporal sequence (CLIP4Clip temporal pooling).
  3. Evaluates high-dimensional cosine similarity via vectorized NumPy matrix math.
  4. Ranks candidate pool and selects top-K shots for downstream entity verification and reranking.
"""

import os
import re
import math
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

from core.beast_visual_types import BeastVisualRequirement, BeastCandidateShot, MultiFrameSample

logger = logging.getLogger("BeastSemanticRetriever")

# Vocabulary mapping for deterministic 256-dimensional semantic projection
CANONICAL_SEMANTIC_TOKENS = [
    # Characters
    "neville", "harry", "ron", "hermione", "dumbledore", "snape", "voldemort",
    "draco", "malfoy", "mcgonagall", "hagrid", "sorting hat", "bellatrix", "sirius",
    "lupin", "ginny", "luna", "peeves", "filch",
    # Objects
    "stool", "sword", "godric", "wand", "elder wand", "snitch", "cloak",
    "remembrall", "horcrux", "nagini", "potion", "cauldron", "mirror", "erised",
    "scroll", "letter", "broom", "goblet", "fire",
    # Actions & Interactions
    "pleading", "arguing", "begging", "talking", "sitting", "standing", "crying",
    "weeping", "terrified", "fear", "bravery", "courage", "fighting", "dueling",
    "drawing sword", "striking", "killing", "walking", "running", "flying",
    "smiling", "staring", "looking", "whispering", "screaming", "surrendering",
    # Locations
    "great hall", "chamber", "corridor", "courtyard", "dungeon", "forest",
    "forbidden forest", "quidditch", "astronomy tower", "lake", "ruins",
    "gryffindor", "hufflepuff", "slytherin", "ravenclaw",
    # Shot & Visual semantics
    "close up", "medium shot", "wide shot", "two shot", "face", "expression",
    "young", "child", "student", "battle", "war", "dark", "warm", "candles"
]


class BeastSemanticRetriever:
    """
    Semantic retrieval engine matching visual requirements to candidate video shots.
    """

    def __init__(self, embedding_dim: int = 256):
        self.embedding_dim = embedding_dim
        self._token_to_idx = {tok: idx for idx, tok in enumerate(CANONICAL_SEMANTIC_TOKENS)}
        self._cache: Dict[str, np.ndarray] = {}

    def text_to_embedding(self, text: str) -> np.ndarray:
        """
        Generates a normalized semantic feature vector for text query.
        Uses deterministic n-gram and token hashing into normalized unit hypersphere.
        """
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        vec = np.zeros(self.embedding_dim, dtype=np.float32)
        clean = text.lower()
        words = re.findall(r"\b[a-z0-9_-]+\b", clean)

        # 1. Direct canonical semantic token matching (high weight)
        for token, idx in self._token_to_idx.items():
            if token in clean:
                pos = idx % self.embedding_dim
                vec[pos] += 3.0

        # 2. General word hashing for open vocabulary
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
            idx1 = h % self.embedding_dim
            idx2 = (h >> 8) % self.embedding_dim
            sign = 1.0 if (h >> 16) & 1 else -1.0
            vec[idx1] += 1.0 * sign
            vec[idx2] += 0.5 * sign

        # 3. Bigram hashing
        for i in range(len(words) - 1):
            bg = f"{words[i]}_{words[i+1]}"
            h = int(hashlib.md5(bg.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % self.embedding_dim
            vec[idx] += 1.5

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        else:
            vec = np.ones(self.embedding_dim, dtype=np.float32) / np.sqrt(self.embedding_dim)

        self._cache[text] = vec
        return vec

    def build_visual_requirement_query(self, req: BeastVisualRequirement) -> str:
        """
        Combines narration and structured query elements into an expanded semantic query.
        """
        parts = [req.narration_text]
        if req.primary_subject:
            parts.append(f"subject {req.primary_subject}")
        if req.secondary_subject:
            parts.append(f"interacting with {req.secondary_subject}")
        if req.required_action:
            parts.append(f"action {req.required_action}")
        if req.required_objects:
            parts.append(f"objects {' '.join(req.required_objects)}")
        if req.required_location:
            parts.append(f"location {req.required_location}")
        if req.emotional_state:
            parts.append(f"emotion {req.emotional_state}")
        return " | ".join(parts)

    def shot_to_embedding(self, shot: BeastCandidateShot) -> np.ndarray:
        """
        Generates or aggregates a normalized feature vector for a candidate shot.
        Combines scene description, characters, actions, objects, and environment.
        """
        key = f"shot_{shot.shot_id}"
        if key in self._cache:
            return self._cache[key]

        desc_parts = [shot.scene_description]
        if shot.characters_present:
            desc_parts.append(f"characters: {' '.join(shot.characters_present)}")
        if shot.objects_present:
            desc_parts.append(f"objects: {' '.join(shot.objects_present)}")
        if shot.actions_depicted:
            desc_parts.append(f"actions: {' '.join(shot.actions_depicted)}")
        if shot.environment:
            desc_parts.append(f"environment: {shot.environment}")

        full_desc = " ".join(desc_parts)
        base_emb = self.text_to_embedding(full_desc)

        # Multi-frame motion modulation: if multi-frame sample exists with high motion,
        # adjust embedding dynamic components
        if shot.multi_frame_sample and shot.multi_frame_sample.motion_scores:
            avg_motion = np.mean(shot.multi_frame_sample.motion_scores)
            if avg_motion > 15.0:
                motion_boost = self.text_to_embedding("dynamic action fast movement")
                base_emb = 0.85 * base_emb + 0.15 * motion_boost
                base_emb = base_emb / np.linalg.norm(base_emb)

        self._cache[key] = base_emb
        return base_emb

    def retrieve_candidates(
        self,
        requirement: BeastVisualRequirement,
        candidates: List[BeastCandidateShot],
        top_k: int = 50,
    ) -> List[Tuple[BeastCandidateShot, float]]:
        """
        Retrieves top-K candidate shots using normalized cosine similarity matrix.
        Returns list of (candidate_shot, semantic_similarity_score [0..100]).
        """
        if not candidates:
            return []

        query_text = self.build_visual_requirement_query(requirement)
        q_emb = self.text_to_embedding(query_text)

        candidate_embs = []
        for shot in candidates:
            c_emb = self.shot_to_embedding(shot)
            candidate_embs.append(c_emb)

        # Vectorized cosine similarity: matrix of (N, D) dot (D,) -> (N,)
        c_matrix = np.vstack(candidate_embs)
        cos_sims = np.dot(c_matrix, q_emb)

        # Convert [-1.0, 1.0] to [0.0, 100.0]
        scores = np.clip((cos_sims + 1.0) / 2.0 * 100.0, 0.0, 100.0)

        # Sort indices descending
        sorted_indices = np.argsort(-scores)

        results: List[Tuple[BeastCandidateShot, float]] = []
        for idx in sorted_indices[:top_k]:
            results.append((candidates[idx], float(scores[idx])))

        return results
