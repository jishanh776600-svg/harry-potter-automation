"""
STORY FORGE — L3 Dense Visual Retrieval Stage (Phase 1D & 1E)
=============================================================
Leverages OpenCLIP multi-modal embeddings and LanceDB vector search to find
plausible video candidates across full movie footage without relying on dialogue.

Capabilities:
  1. Full-Movie Search: Directly searches continuous visual feature embeddings.
  2. Silent Scene Discovery: Locates visual moments (e.g. wand snap, sword draw)
     where spoken dialogue is completely absent.
  3. Multi-Frame Temporal Windowing: Aggregates multi-observation keyframe hits
     into coherent continuous candidate intervals.
  4. Non-Proof Invariant: Returns candidates ONLY; leaves physical proof to downstream verifier.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from engines.retrieval.models import IRetrievalStage, RetrievalQuery, RetrievalCandidate
from engines.retrieval.vector_index import LanceVectorIndex
from engines.retrieval.clip_encoder import OpenCLIPVisualEncoder

logger = logging.getLogger("L3OpenCLIPDenseStage")


class L3OpenCLIPDenseStage(IRetrievalStage):
    """
    Retrieves candidates using dense vector similarity search in LanceDB.
    """

    def __init__(
        self,
        vector_index: Optional[LanceVectorIndex] = None,
        encoder: Optional[OpenCLIPVisualEncoder] = None,
        candidate_window_sec: float = 6.0,
    ):
        self.index = vector_index or LanceVectorIndex()
        self.encoder = encoder or OpenCLIPVisualEncoder.get_instance()
        self.candidate_window_sec = candidate_window_sec

    @property
    def stage_name(self) -> str:
        return "L3_OPENCLIP"

    def retrieve(
        self,
        query: RetrievalQuery,
        top_k: int = 5,
    ) -> List[RetrievalCandidate]:
        if self.index.table.count_rows() == 0:
            logger.debug("LanceDB index is empty; skipping dense visual retrieval.")
            return []

        # 1. Build prompt and encode query
        prompt = query.build_dense_prompt()
        query_vec = self.encoder.encode_text(prompt)

        # 2. Movie filter if requested
        movie_filter: Optional[str] = None
        if query.preferred_movie_ids and len(query.preferred_movie_ids) == 1:
            movie_filter = query.preferred_movie_ids[0]

        # Search top_k * 4 to allow aggregation of multi-frame observations
        raw_hits = self.index.search_vectors(query_vec, top_k=top_k * 4, movie_id=movie_filter)
        if not raw_hits:
            return []

        # 3. Aggregate temporally adjacent keyframe hits into coherent shot candidates
        aggregated_candidates = self._aggregate_frame_hits(raw_hits, query, prompt, top_k)
        return aggregated_candidates[:top_k]

    def _aggregate_frame_hits(
        self,
        raw_hits: List[Dict[str, Any]],
        query: RetrievalQuery,
        prompt: str,
        top_k: int,
    ) -> List[RetrievalCandidate]:
        # Group hits by (movie_id, approximate time cluster)
        clusters: List[Dict[str, Any]] = []

        for hit in raw_hits:
            m_id = hit["movie_id"]
            ts = float(hit["timestamp"])
            sim = float(hit["similarity_score"])

            # Check if hit belongs to an existing cluster within 4 seconds
            merged = False
            for cluster in clusters:
                if cluster["movie_id"] == m_id and abs(cluster["center_ts"] - ts) <= 4.0:
                    cluster["hits"].append(hit)
                    cluster["min_ts"] = min(cluster["min_ts"], ts)
                    cluster["max_ts"] = max(cluster["max_ts"], ts)
                    # Multi-observation reinforcement: boosted slightly if multiple frames match
                    cluster["max_sim"] = max(cluster["max_sim"], sim)
                    cluster["avg_sim"] = sum(h["similarity_score"] for h in cluster["hits"]) / len(cluster["hits"])
                    merged = True
                    break

            if not merged:
                clusters.append({
                    "movie_id": m_id,
                    "center_ts": ts,
                    "min_ts": ts,
                    "max_ts": ts,
                    "max_sim": sim,
                    "avg_sim": sim,
                    "hits": [hit],
                    "shot_id": hit.get("shot_id", "shot_0"),
                })

        # Rank clusters by combined score (max similarity + multi-frame observation bonus)
        for cluster in clusters:
            obs_count = len(cluster["hits"])
            obs_bonus = min(0.08, (obs_count - 1) * 0.025)
            # Calibrate OpenCLIP raw cosine sim [0.15, 0.40] -> [0.0, 1.0]
            raw_sim = cluster["max_sim"]
            calibrated_sim = min(1.0, max(0.0, (raw_sim - 0.15) / 0.25))
            cluster["final_score"] = min(1.0, calibrated_sim + obs_bonus)

        clusters.sort(key=lambda c: c["final_score"], reverse=True)

        candidates: List[RetrievalCandidate] = []
        for i, cl in enumerate(clusters[:top_k]):
            half_win = self.candidate_window_sec / 2.0
            start_t = max(0.0, cl["center_ts"] - half_win)
            end_t = cl["center_ts"] + half_win

            cand = RetrievalCandidate(
                candidate_id=f"clip_{cl['movie_id']}_{int(cl['center_ts'])}_{i}",
                movie_id=cl["movie_id"],
                start=start_t,
                end=end_t,
                source=self.stage_name,
                retrieval_score=cl["final_score"],
                semantic_score=cl["final_score"],
                temporal_score=0.8,
                structured_score=0.4,
                metadata={
                    "center_timestamp": cl["center_ts"],
                    "observation_count": len(cl["hits"]),
                    "hit_timestamps": [round(h["timestamp"], 2) for h in cl["hits"]],
                    "shot_id": cl["shot_id"],
                },
                retrieval_trace={
                    "stage": self.stage_name,
                    "prompt": prompt,
                    "max_similarity": round(cl["max_sim"], 4),
                    "model_fingerprint": cl["hits"][0].get("model_fingerprint", ""),
                    "source_frame_count": len(cl["hits"]),
                },
                is_verified=False,
            )
            candidates.append(cand)

        return candidates
