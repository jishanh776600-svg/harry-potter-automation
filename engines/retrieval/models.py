"""
STORY FORGE — Retrieval Foundation Data Models & Interfaces (Phase 1A)
======================================================================
Defines the clean abstraction boundary for multi-stage video retrieval.

Core Principles:
  1. Retrieval is NOT verification: Retrieval only proposes candidate moments.
  2. Provenance Preservation: Every candidate carries a rich retrieval_trace
     documenting the exact model, score breakdown, source, and timestamps.
  3. Hard Authority Boundary: `is_verified` defaults to False and cannot be
     asserted by any retrieval component.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class RetrievalQuery:
    """
    Unified query representation across all retrieval tiers (L1-L4).
    Encompasses natural language, structured semantic entities,
    and temporal constraints.
    """
    assertion_id: str
    text_query: str
    required_subjects: List[str] = field(default_factory=list)
    required_objects: List[str] = field(default_factory=list)
    required_action: Optional[str] = None
    required_target: Optional[str] = None
    required_location: Optional[str] = None
    temporal_constraints: Optional[Dict[str, Any]] = None
    narration_start: Optional[float] = None
    narration_end: Optional[float] = None
    preferred_movie_ids: Optional[List[str]] = None
    forbidden_entities: Optional[List[str]] = None
    forbidden_actions: Optional[List[str]] = None

    def build_dense_prompt(self) -> str:
        """
        Synthesizes a rich multimodal prompt combining text_query,
        subjects, objects, and actions for embedding models.
        """
        parts = [self.text_query.strip()]
        if self.required_subjects:
            parts.append(f"featuring {', '.join(self.required_subjects)}")
        if self.required_action:
            parts.append(f"action: {self.required_action}")
        if self.required_objects:
            parts.append(f"with {', '.join(self.required_objects)}")
        if self.required_location:
            parts.append(f"at {self.required_location}")
        return " | ".join(parts)


@dataclass
class RetrievalCandidate:
    """
    Plausible video candidate interval returned by a retrieval stage.
    """
    candidate_id: str
    movie_id: str
    start: float
    end: float
    source: str  # e.g. "L1_FTS5", "L2_MOVIE_EVENT", "L3_OPENCLIP", "L4_QD_DETR", "FUSION"
    retrieval_score: float  # Normalized [0.0, 1.0]
    semantic_score: float = 0.0
    temporal_score: float = 0.0
    structured_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieval_trace: Dict[str, Any] = field(default_factory=dict)
    is_verified: bool = False  # HARD INVARIANT: Always False at retrieval time

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "movie_id": self.movie_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "source": self.source,
            "retrieval_score": round(self.retrieval_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "temporal_score": round(self.temporal_score, 4),
            "structured_score": round(self.structured_score, 4),
            "is_verified": self.is_verified,
            "metadata": self.metadata,
            "retrieval_trace": self.retrieval_trace,
        }


class IRetrievalStage(ABC):
    """
    Interface for individual retrieval stages in the cascade.
    """
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Stage identifier (e.g. L1_FTS5, L2_MOVIE_EVENT)."""
        pass

    @abstractmethod
    def retrieve(
        self,
        query: RetrievalQuery,
        top_k: int = 5,
    ) -> List[RetrievalCandidate]:
        """
        Retrieves top_k candidate video segments matching the query.
        """
        pass
