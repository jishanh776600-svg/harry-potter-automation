"""
STORY FORGE — Movie Event Visual Matching Engine (V2)
======================================================
Visual Intelligence Layer for movie event representation, visual storyboarding,
event indexing, multi-attribute retrieval, event chaining, visual verification,
and hybrid SRT + MovieEvent visual selection.
"""

from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    VisualStoryboard,
    MovieEventQuery,
    ClaimClassification,
    ClaimType,
    EventVerificationResult,
    VerificationStatus,
)
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator, ClaimTransformer
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.verifier import MovieEventVisualVerifier
from engines.movie_event.hybrid_matcher import (
    SRTTimeWindow,
    CandidateComparisonResult,
    HybridVisualSelectionOutput,
    SRTCoarseLocator,
    HybridVisualSelector,
    MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
)

__all__ = [
    "MovieEvent",
    "VisualBeat",
    "VisualStoryboard",
    "MovieEventQuery",
    "ClaimClassification",
    "ClaimType",
    "EventVerificationResult",
    "VerificationStatus",
    "MovieEventIndex",
    "VisualStoryboardGenerator",
    "ClaimTransformer",
    "MovieEventRetrievalEngine",
    "MovieEventVisualVerifier",
    "SRTTimeWindow",
    "CandidateComparisonResult",
    "HybridVisualSelectionOutput",
    "SRTCoarseLocator",
    "HybridVisualSelector",
    "MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN",
]
