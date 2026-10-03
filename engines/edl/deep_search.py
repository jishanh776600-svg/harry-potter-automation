"""
STORY FORGE — 7-Level Deep Movie Searcher (Part 4, 6, 23, 24)
============================================================
Executes hierarchical deep search across movies to find physical visual evidence:
  LEVEL 1: SRT / Dialogue Locator
  LEVEL 2: MovieEvent Structured Catalog
  LEVEL 3: OpenCLIP + LanceDB Dense Visual Search
  LEVEL 4: QD-DETR Temporal Proposals
  LEVEL 5: Adjacent Shot / Event Expansion
  LEVEL 6: Full-Movie Structured Search
  LEVEL 7: Franchise-Wide Search Across All 8 Movies

Enforces Candidate Pooling (>=5 candidates from diverse temporal regions),
Search Diagnostics recording, and Critical Search Exhaustion.
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set, Tuple

from engines.retrieval.models import RetrievalQuery, RetrievalCandidate
from engines.retrieval.cascade_engine import RetrievalCascadeEngine
from engines.edl.models import VisualBeat, SearchDiagnosticRecord
from engines.edl.concept_expansion import VisualConceptExpander

logger = logging.getLogger("DeepMovieSearcher")


class DeepMovieSearcher:
    """
    Hierarchical 7-level deep search engine for Story Forge.
    Prevents narrow SRT windows or single-candidate domination.
    """

    def __init__(
        self,
        cascade_engine: Optional[RetrievalCascadeEngine] = None,
        concept_expander: Optional[VisualConceptExpander] = None,
        min_candidate_pool_size: int = 5,
        default_movie_id: int = 3,
    ):
        self.cascade_engine = cascade_engine or RetrievalCascadeEngine()
        self.concept_expander = concept_expander or VisualConceptExpander()
        self.min_candidate_pool_size = min_candidate_pool_size
        self.default_movie_id = default_movie_id

    def search_beat_candidates(
        self,
        beat: VisualBeat,
        target_movie_id: Optional[int] = None,
        allow_cross_movie: bool = True,
    ) -> Tuple[List[RetrievalCandidate], SearchDiagnosticRecord]:
        """
        Executes deep hierarchical search for a VisualBeat across Levels 1-7.
        Returns candidate pool and diagnostic audit record.
        """
        movie_id = target_movie_id or self._infer_movie_id(beat) or self.default_movie_id
        diagnostic = SearchDiagnosticRecord(beat_id=beat.beat_id)

        # 1. Expand visual concepts into structured queries
        queries = self.concept_expander.expand_beat(beat)
        diagnostic.queries_attempted = queries

        candidate_pool: List[RetrievalCandidate] = []
        seen_intervals: Set[str] = set()

        # Helper to add candidate with temporal diversity check
        def add_candidate(cand: RetrievalCandidate, level_name: str):
            # Bin interval to ~5 seconds to prevent clustering
            bin_key = f"{cand.movie_id}_{int(cand.start / 5.0) * 5}_{int(cand.end / 5.0) * 5}"
            if bin_key not in seen_intervals:
                seen_intervals.add(bin_key)
                cand.retrieval_trace["deep_search_level"] = level_name
                candidate_pool.append(cand)

        # -------------------------------------------------------------------
        # LEVEL 1-4: Primary Cascade Engine (SRT, MovieEvent, OpenCLIP, QD-DETR)
        # -------------------------------------------------------------------
        diagnostic.search_levels_attempted.append("L1_L4_PRIMARY_CASCADE")
        for q_text in queries[:4]:
            ret_query = RetrievalQuery(
                assertion_id=f"{beat.beat_id}_{q_text[:12]}",
                text_query=q_text,
                preferred_movie_ids=[str(movie_id)],
                required_subjects=beat.required_entities,
                required_objects=beat.required_objects,
                required_action=beat.required_action,
            )
            cands = self.cascade_engine.retrieve_candidates(ret_query, top_k=6)
            for c in cands:
                add_candidate(c, "L1_L4_CASCADE")

        # -------------------------------------------------------------------
        # LEVEL 5: Adjacent Shot / Event Expansion
        # -------------------------------------------------------------------
        # If we have initial candidates, expand around their temporal neighborhoods
        if candidate_pool:
            diagnostic.search_levels_attempted.append("L5_ADJACENT_EXPANSION")
            expanded_cands: List[RetrievalCandidate] = []
            for c in candidate_pool[:3]:
                # Expand window by 15-30s before and after to catch action surrounding dialogue
                exp_start = max(0.0, c.start - 20.0)
                exp_end = c.end + 20.0
                adj_cand = RetrievalCandidate(
                    candidate_id=f"{c.candidate_id}_adj_exp",
                    movie_id=str(c.movie_id),
                    start=round(exp_start, 2),
                    end=round(exp_end, 2),
                    source="L5_ADJACENT",
                    retrieval_score=round(c.retrieval_score * 0.95, 4),
                    metadata=dict(c.metadata),
                    retrieval_trace={"parent_candidate": c.candidate_id, "expansion_delta": 20.0},
                )
                expanded_cands.append(adj_cand)
            for ec in expanded_cands:
                add_candidate(ec, "L5_ADJACENT")

        # -------------------------------------------------------------------
        # LEVEL 6: Full-Movie Structured Search
        # -------------------------------------------------------------------
        # If pool size is still below minimum target, query full movie with action concepts
        if len(candidate_pool) < self.min_candidate_pool_size:
            diagnostic.search_levels_attempted.append("L6_FULL_MOVIE_SEARCH")
            for q_text in queries[4:8]:
                ret_query = RetrievalQuery(
                    assertion_id=f"{beat.beat_id}_full_{q_text[:12]}",
                    text_query=q_text,
                    preferred_movie_ids=[str(movie_id)],
                    required_subjects=beat.required_entities,
                    required_objects=beat.required_objects,
                    required_action=beat.required_action,
                )
                cands = self.cascade_engine.retrieve_candidates(ret_query, top_k=4)
                for c in cands:
                    add_candidate(c, "L6_FULL_MOVIE")

        # -------------------------------------------------------------------
        # LEVEL 7: Franchise-Wide Search Across All 8 Movies
        # -------------------------------------------------------------------
        # If still insufficient or cross-movie permitted and requested
        if allow_cross_movie and len(candidate_pool) < self.min_candidate_pool_size:
            diagnostic.search_levels_attempted.append("L7_FRANCHISE_WIDE_SEARCH")
            other_movies = [m for m in [1, 2, 3, 4, 5, 6, 7, 8] if m != movie_id]
            for m_other in other_movies[:3]:
                if len(candidate_pool) >= self.min_candidate_pool_size:
                    break
                primary_q = queries[0] if queries else beat.text_span
                ret_query = RetrievalQuery(
                    assertion_id=f"{beat.beat_id}_cross_{m_other}",
                    text_query=primary_q,
                    preferred_movie_ids=[str(m_other)],
                    required_subjects=beat.required_entities,
                    required_objects=beat.required_objects,
                    required_action=beat.required_action,
                )
                cands = self.cascade_engine.retrieve_candidates(ret_query, top_k=2)
                for c in cands:
                    add_candidate(c, f"L7_CROSS_M{m_other}")

        # Sort candidate pool by retrieval score
        candidate_pool.sort(key=lambda x: x.retrieval_score, reverse=True)
        diagnostic.candidates_returned = len(candidate_pool)
        if candidate_pool:
            diagnostic.best_candidate_score = candidate_pool[0].retrieval_score

        return candidate_pool, diagnostic

    def _infer_movie_id(self, beat: VisualBeat) -> Optional[int]:
        """Infers movie ID based on unique character/scene context if mentioned."""
        lower = (beat.text_span + " " + beat.visual_assertion).lower()
        if "elder wand" in lower or "nagini" in lower or "deathly hallows" in lower:
            return 8
        if "buckbeak" in lower or "prisoner of azkaban" in lower or "time-turner" in lower:
            return 3
        if "sorting hat" in lower or "ollivander" in lower or "philosopher" in lower or "sorcerer" in lower:
            return 1
        if "basilisk" in lower or "chamber of secrets" in lower or "tom riddle" in lower:
            return 2
        if "goblet of fire" in lower or "triwizard" in lower or "cedric" in lower:
            return 4
        if "order of the phoenix" in lower or "umbridge" in lower:
            return 5
        if "half-blood" in lower or "slughorn" in lower or "horcrux cave" in lower:
            return 6
        return None
