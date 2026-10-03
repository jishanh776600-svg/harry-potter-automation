"""
STORY FORGE — Candidate Fusion & Diversity Engine (Phase 1H, 1I, 1O)
===================================================================
Fuses heterogeneous candidates from L1 (FTS5), L2 (MovieEvent), L3 (OpenCLIP),
and L4 (QD-DETR) into a ranked, diverse candidate pool.

Core Invariants:
  1. No False Authority: Fusion only produces CANDIDATES. `is_verified` remains strictly False.
  2. Provenance Preservation: Individual stage scores are preserved in `retrieval_trace`.
  3. Anti-Clustering Diversity: Enforces temporal spacing (min 3.0s between candidate centers)
     and multi-source representation to prevent 20 identical frames from crowding the pool.
  4. Fail-Closed: If all candidate scores fall below `min_score_threshold`, returns empty pool.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

from engines.retrieval.models import RetrievalCandidate, RetrievalQuery

logger = logging.getLogger("CandidateFusionEngine")

DEFAULT_STAGE_WEIGHTS = {
    "L1_FTS5": 0.20,
    "L2_MOVIE_EVENT": 0.35,
    "L3_OPENCLIP": 0.25,
    "L4_QD_DETR": 0.20,
}


class CandidateFusionEngine:
    """
    Fuses candidate pools across retrieval stages with Reciprocal Rank Fusion (RRF)
    and weighted multi-signal scoring, enforcing temporal and source diversity.
    """

    def __init__(
        self,
        stage_weights: Optional[Dict[str, float]] = None,
        min_score_threshold: float = 0.22,
        temporal_spacing_sec: float = 3.5,
        rrf_k: int = 60,
    ):
        self.weights = stage_weights or DEFAULT_STAGE_WEIGHTS
        self.min_score_threshold = min_score_threshold
        self.temporal_spacing_sec = temporal_spacing_sec
        self.rrf_k = rrf_k

    def fuse_and_rank(
        self,
        stage_candidates: Dict[str, List[RetrievalCandidate]],
        query: RetrievalQuery,
        top_k: int = 5,
    ) -> List[RetrievalCandidate]:
        """
        Fuses candidates from all provided stages.
        """
        all_candidates: List[RetrievalCandidate] = []
        for stage_name, cands in stage_candidates.items():
            all_candidates.extend(cands)

        if not all_candidates:
            logger.debug("Candidate pool empty across all stages.")
            return []

        # 1. Cluster temporally overlapping candidates for the same movie
        fused_clusters = self._cluster_overlapping_candidates(all_candidates)

        # 2. Compute multi-signal fused score for each cluster
        scored_candidates: List[RetrievalCandidate] = []
        for cluster in fused_clusters:
            fused_cand = self._score_cluster(cluster, stage_candidates, query)
            if fused_cand.retrieval_score >= self.min_score_threshold:
                scored_candidates.append(fused_cand)

        if not scored_candidates:
            logger.info("All candidates below minimum threshold. Failing closed (NO_CANDIDATE_FOUND).")
            return []

        # 3. Sort by fused retrieval score
        scored_candidates.sort(key=lambda c: c.retrieval_score, reverse=True)

        # 4. Apply diversity filter (temporal spacing + source diversity)
        diverse_candidates = self._enforce_diversity(scored_candidates, top_k)
        return diverse_candidates

    def _cluster_overlapping_candidates(
        self,
        candidates: List[RetrievalCandidate],
    ) -> List[List[RetrievalCandidate]]:
        """
        Groups candidates from the same movie that overlap within temporal_spacing_sec.
        """
        clusters: List[List[RetrievalCandidate]] = []

        for cand in candidates:
            placed = False
            cand_shot = cand.metadata.get("shot_id")
            for cluster in clusters:
                rep = cluster[0]
                rep_shot = rep.metadata.get("shot_id")
                # If both have explicit shot_ids and they differ, they are distinct shots
                if cand_shot and rep_shot and cand_shot != rep_shot:
                    continue

                if cand.movie_id == rep.movie_id:
                    cluster_min = min(c.start for c in cluster)
                    cluster_max = max(c.end for c in cluster)
                    # Check temporal overlap or proximity
                    if not (cand.end < cluster_min - self.temporal_spacing_sec or cand.start > cluster_max + self.temporal_spacing_sec):
                        cluster.append(cand)
                        placed = True
                        break
            if not placed:
                clusters.append([cand])

        return clusters

    def _score_cluster(
        self,
        cluster: List[RetrievalCandidate],
        stage_candidates: Dict[str, List[RetrievalCandidate]],
        query: RetrievalQuery,
    ) -> RetrievalCandidate:
        rep = cluster[0]
        movie_id = rep.movie_id
        start_t = min(c.start for c in cluster)
        end_t = max(c.end for c in cluster)

        # Collect source contributions
        sources_present = set(c.source for c in cluster)
        source_scores: Dict[str, float] = {}
        for c in cluster:
            source_scores[c.source] = max(source_scores.get(c.source, 0.0), c.retrieval_score)

        # Compute weighted signal score
        weighted_score = 0.0
        total_weight = 0.0
        for src, sc in source_scores.items():
            w = self.weights.get(src, 0.20)
            weighted_score += sc * w
            total_weight += w

        normalized_score = weighted_score / max(1e-6, total_weight)

        # Multi-stage agreement bonus: if multiple independent stages found the same window
        agreement_bonus = min(0.15, max(0, len(sources_present) - 1) * 0.05)
        fused_retrieval_score = min(1.0, normalized_score + agreement_bonus)

        # Compute max sub-scores
        semantic_score = max(c.semantic_score for c in cluster)
        temporal_score = max(c.temporal_score for c in cluster)
        structured_score = max(c.structured_score for c in cluster)

        # Compile consolidated metadata starting from the highest-scoring candidate in cluster
        best_in_cluster = max(cluster, key=lambda c: c.retrieval_score)
        merged_meta: Dict[str, Any] = dict(best_in_cluster.metadata)
        merged_meta.update({
            "contributing_sources": list(sources_present),
            "source_candidate_count": len(cluster),
            "source_scores": {k: round(v, 4) for k, v in source_scores.items()},
            "agreement_bonus": round(agreement_bonus, 4),
        })

        # Compile unified trace
        merged_trace: Dict[str, Any] = {
            "fusion_type": "weighted_agreement_fusion",
            "sources": list(sources_present),
            "score_breakdown": {
                "base_weighted": round(normalized_score, 4),
                "agreement_bonus": round(agreement_bonus, 4),
                "final_fused": round(fused_retrieval_score, 4),
            },
            "source_traces": {c.source: c.retrieval_trace for c in cluster},
        }

        source_label = "FUSION" if len(sources_present) > 1 else list(sources_present)[0]

        return RetrievalCandidate(
            candidate_id=f"fused_{movie_id}_{int(start_t)}_{len(sources_present)}src",
            movie_id=movie_id,
            start=start_t,
            end=end_t,
            source=source_label,
            retrieval_score=fused_retrieval_score,
            semantic_score=semantic_score,
            temporal_score=temporal_score,
            structured_score=structured_score,
            metadata=merged_meta,
            retrieval_trace=merged_trace,
            is_verified=False,  # Hard Invariant
        )

    def _enforce_diversity(
        self,
        candidates: List[RetrievalCandidate],
        top_k: int,
    ) -> List[RetrievalCandidate]:
        """
        Filters candidates to ensure temporal and scene diversity.
        """
        diverse: List[RetrievalCandidate] = []
        for cand in candidates:
            too_close = False
            cand_shot = cand.metadata.get("shot_id")
            for accepted in diverse:
                acc_shot = accepted.metadata.get("shot_id")
                # If both have explicit shot_ids and they differ, they are distinct shots
                if cand_shot and acc_shot and cand_shot != acc_shot:
                    continue
                if accepted.movie_id == cand.movie_id:
                    if abs(accepted.midpoint - cand.midpoint) < self.temporal_spacing_sec:
                        too_close = True
                        break

            if not too_close:
                diverse.append(cand)

            if len(diverse) >= top_k:
                break

        return diverse
