"""
STORY FORGE — Retrieval Foundation Package (Phase 1)
====================================================
Public exports for next-generation multi-stage video retrieval.
"""

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
from engines.retrieval.cascade_engine import RetrievalCascadeEngine

__all__ = [
    "IRetrievalStage",
    "RetrievalQuery",
    "RetrievalCandidate",
    "L1FTS5DialogueStage",
    "L2MovieEventStage",
    "L3OpenCLIPDenseStage",
    "L4QDDETRTemporalStage",
    "CandidateFusionEngine",
    "LanceVectorIndex",
    "OpenCLIPVisualEncoder",
    "RetrievalCascadeEngine",
]
