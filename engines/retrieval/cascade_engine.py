"""
STORY FORGE — Multi-Stage Retrieval Cascade Engine (Phase 1 Master)
===================================================================
Coordinates the full multi-tier retrieval hierarchy:
  L1 — SQLite FTS5 (Dialogue / Subtitles)
  L2 — MovieEvent (Structured Semantic Catalog)
  L3 — OpenCLIP + LanceDB (Dense Visual Similarity)
  L4 — QD-DETR Adapter (Query-Dependent Temporal Moment Proposal)
  FUSION — Reciprocal Rank & Multi-Signal Diversity Filter

Hard Invariant:
  Retrieval NEVER verifies footage. It outputs candidate video intervals for
  the existing Physical Visual Evidence Verifier to prove or reject.
"""

import time
import logging
from typing import List, Dict, Any, Optional

from engines.retrieval.models import (
    IRetrievalStage,
    RetrievalQuery,
    RetrievalCandidate,
)
from engines.retrieval.fts5_stage import L1FTS5DialogueStage
from engines.retrieval.movie_event_stage import L2MovieEventStage
from engines.retrieval.dense_retrieval_stage import L3OpenCLIPDenseStage
from engines.retrieval.temporal_qddetr_stage import L4QDDETRTemporalStage
from engines.retrieval.candidate_fusion import CandidateFusionEngine
from engines.retrieval.vector_index import LanceVectorIndex
from engines.retrieval.clip_encoder import OpenCLIPVisualEncoder

logger = logging.getLogger("RetrievalCascadeEngine")


class RetrievalCascadeEngine:
    """
    Master coordinator for the Story Forge next-generation retrieval cascade.
    """

    def __init__(
        self,
        vector_index: Optional[LanceVectorIndex] = None,
        encoder: Optional[OpenCLIPVisualEncoder] = None,
        enable_l1: bool = True,
        enable_l2: bool = True,
        enable_l3: bool = True,
        enable_l4: bool = True,
    ):
        self.vector_index = vector_index or LanceVectorIndex()
        self.encoder = encoder  # lazy loaded on first dense search if None

        self.stages: Dict[str, IRetrievalStage] = {}
        if enable_l1:
            self.stages["L1_FTS5"] = L1FTS5DialogueStage()
        if enable_l2:
            self.stages["L2_MOVIE_EVENT"] = L2MovieEventStage()
        if enable_l3:
            enc = self.encoder or OpenCLIPVisualEncoder.get_instance()
            self.stages["L3_OPENCLIP"] = L3OpenCLIPDenseStage(vector_index=self.vector_index, encoder=enc)
        if enable_l4:
            enc = self.encoder or OpenCLIPVisualEncoder.get_instance()
            self.stages["L4_QD_DETR"] = L4QDDETRTemporalStage(vector_index=self.vector_index, encoder=enc)

        self.fusion_engine = CandidateFusionEngine()

    def retrieve_candidates(
        self,
        query: RetrievalQuery,
        top_k: int = 5,
        per_stage_k: int = 4,
    ) -> List[RetrievalCandidate]:
        """
        Executes cascade across enabled stages and fuses results into a ranked pool.
        """
        t0 = time.time()
        stage_candidates: Dict[str, List[RetrievalCandidate]] = {}
        stage_latencies: Dict[str, float] = {}

        for name, stage in self.stages.items():
            s_t0 = time.time()
            try:
                cands = stage.retrieve(query, top_k=per_stage_k)
                stage_candidates[name] = cands
                stage_latencies[name] = round((time.time() - s_t0) * 1000, 2)
            except Exception as e:
                logger.warning(f"Retrieval stage {name} raised error: {e}")
                stage_candidates[name] = []
                stage_latencies[name] = round((time.time() - s_t0) * 1000, 2)

        # Fuse candidate pools
        fused = self.fusion_engine.fuse_and_rank(stage_candidates, query, top_k=top_k)
        total_ms = round((time.time() - t0) * 1000, 2)

        # Attach retrieval cascade trace to all candidates
        for c in fused:
            c.retrieval_trace["cascade_total_ms"] = total_ms
            c.retrieval_trace["stage_latencies_ms"] = stage_latencies
            c.retrieval_trace["stages_evaluated"] = list(self.stages.keys())

        logger.info(
            f"Cascade for '{query.assertion_id}': found {len(fused)} candidates across "
            f"{list(self.stages.keys())} in {total_ms}ms"
        )
        return fused

    @staticmethod
    def query_from_beat(beat: Any) -> RetrievalQuery:
        """
        Adapter to construct RetrievalQuery from a VisualBeat object.
        """
        pref_movies = []
        if hasattr(beat, "movie_number") and beat.movie_number:
            pref_movies.append(f"movie_{beat.movie_number}")

        return RetrievalQuery(
            assertion_id=getattr(beat, "beat_id", "beat_query"),
            text_query=getattr(beat, "narrative_text", ""),
            required_subjects=list(getattr(beat, "required_subjects", [])),
            required_objects=list(getattr(beat, "required_objects", [])),
            required_action=getattr(beat, "required_action", None),
            required_target=getattr(beat, "required_target", None),
            required_location=getattr(beat, "required_location", None),
            narration_start=getattr(beat, "narration_start", None),
            narration_end=getattr(beat, "narration_end", None),
            preferred_movie_ids=pref_movies or None,
            forbidden_entities=list(getattr(beat, "forbidden_visuals", [])),
        )
