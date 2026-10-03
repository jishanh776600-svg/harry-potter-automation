"""
STORY FORGE — L1 SQLite FTS5 Dialogue Retrieval Stage (Phase 1B)
================================================================
Wraps the movie subtitle FTS5 index to locate dialogue-anchored candidate moments.
Preserves existing SRTCoarseLocator capabilities behind the clean IRetrievalStage interface.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from engines.retrieval.models import IRetrievalStage, RetrievalQuery, RetrievalCandidate
from engines.movie_asset_engine import MovieAssetEngine

logger = logging.getLogger("L1FTS5DialogueStage")

STOPWORDS = {
    "what", "would", "from", "with", "that", "this", "their", "there", "about",
    "which", "before", "after", "while", "during", "then", "have", "been", "were",
    "very", "some", "into", "onto", "over", "under", "will", "shall", "does", "done"
}


class L1FTS5DialogueStage(IRetrievalStage):
    """
    Retrieves candidates using SQLite FTS5 full-text dialogue matching.
    """

    def __init__(self, asset_engine: Optional[MovieAssetEngine] = None, window_padding_sec: float = 12.0):
        self.asset_engine = asset_engine or MovieAssetEngine()
        self.window_padding_sec = window_padding_sec

    @property
    def stage_name(self) -> str:
        return "L1_FTS5"

    def retrieve(
        self,
        query: RetrievalQuery,
        top_k: int = 5,
    ) -> List[RetrievalCandidate]:
        candidates: List[RetrievalCandidate] = []
        search_terms = self._generate_search_terms(query)
        if not search_terms:
            return []

        # Movie filtering: determine which movie numbers to target
        target_movie_numbers: Optional[List[int]] = None
        if query.preferred_movie_ids:
            target_movie_numbers = []
            for mid in query.preferred_movie_ids:
                m = re.search(r"(\d+)", str(mid))
                if m:
                    target_movie_numbers.append(int(m.group(1)))

        seen_chunks = set()
        for term in search_terms:
            if target_movie_numbers:
                for m_num in target_movie_numbers:
                    hits = self.asset_engine.search_movie_scenes(term, movie_number=m_num, limit=top_k)
                    self._collect_hits(hits, query, term, candidates, seen_chunks, top_k)
            else:
                hits = self.asset_engine.search_movie_scenes(term, limit=top_k)
                self._collect_hits(hits, query, term, candidates, seen_chunks, top_k)

            if len(candidates) >= top_k:
                break

        return candidates[:top_k]

    def _generate_search_terms(self, query: RetrievalQuery) -> List[str]:
        terms = []
        raw_text = query.text_query.lower()
        salient_words = [
            w for w in re.findall(r"[a-zA-Z]{4,}", raw_text)
            if w not in STOPWORDS
        ]
        if len(salient_words) >= 2:
            terms.append(" ".join(salient_words[:2]))
        if salient_words:
            terms.append(salient_words[0])

        # Add character names if present
        for sub in query.required_subjects:
            terms.append(sub)

        # Combined subject + action query
        if query.required_subjects and query.required_action:
            terms.append(f"{query.required_subjects[0]} {query.required_action}")

        # Unique terms preserved in order
        deduped = []
        for t in terms:
            t_clean = t.strip()
            if t_clean and t_clean not in deduped:
                deduped.append(t_clean)
        return deduped

    def _collect_hits(
        self,
        hits: List[Dict[str, Any]],
        query: RetrievalQuery,
        search_term: str,
        candidates: List[RetrievalCandidate],
        seen_chunks: set,
        top_k: int,
    ):
        for hit in hits:
            chunk_id = hit.get("chunk_id", f"{hit.get('movie_number')}_{hit.get('start_seconds')}")
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            start_sec = max(0.0, float(hit.get("start_seconds", 0.0)) - self.window_padding_sec)
            end_sec = float(hit.get("end_seconds", start_sec + 2.0)) + self.window_padding_sec
            raw_rank = float(hit.get("relevance_rank", -1.0))
            # Rank in SQLite FTS5 bm25 is negative (lower = better), normalize to [0.0, 1.0]
            norm_score = max(0.2, min(0.95, 1.0 / (1.0 + abs(raw_rank) * 0.1)))

            movie_num = int(hit.get("movie_number", 1))
            cand = RetrievalCandidate(
                candidate_id=f"fts5_m{movie_num}_{int(start_sec)}_{len(candidates)}",
                movie_id=f"movie_{movie_num}",
                start=start_sec,
                end=end_sec,
                source=self.stage_name,
                retrieval_score=norm_score,
                semantic_score=norm_score * 0.8,
                temporal_score=0.7,
                structured_score=0.5,
                metadata={
                    "matched_text": hit.get("text", ""),
                    "movie_title": hit.get("movie_title", ""),
                    "chunk_id": chunk_id,
                },
                retrieval_trace={
                    "stage": self.stage_name,
                    "search_term": search_term,
                    "raw_rank": raw_rank,
                    "dialogue_snippet": hit.get("text", "")[:120],
                },
                is_verified=False,
            )
            candidates.append(cand)
            if len(candidates) >= top_k:
                break
