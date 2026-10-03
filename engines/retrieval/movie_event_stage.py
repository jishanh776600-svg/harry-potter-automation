"""
STORY FORGE — L2 MovieEvent Structured Retrieval Stage (Phase 1B)
=================================================================
Wraps the curated MovieEventIndex and MovieEventRetrievalEngine to retrieve
semantically rich structured movie events.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from engines.retrieval.models import IRetrievalStage, RetrievalQuery, RetrievalCandidate
from engines.movie_event.models import MovieEventQuery, MovieEvent
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.index import MovieEventIndex

logger = logging.getLogger("L2MovieEventStage")


class L2MovieEventStage(IRetrievalStage):
    """
    Retrieves candidates using structured semantic matching on MovieEventIndex.
    """

    def __init__(self, index: Optional[MovieEventIndex] = None):
        self.engine = MovieEventRetrievalEngine(index=index)

    @property
    def stage_name(self) -> str:
        return "L2_MOVIE_EVENT"

    def retrieve(
        self,
        query: RetrievalQuery,
        top_k: int = 5,
    ) -> List[RetrievalCandidate]:
        candidates: List[RetrievalCandidate] = []
        me_query = self._build_movie_event_query(query)

        try:
            results = self.engine.retrieve_events(me_query, top_k=top_k, min_score=20.0)
        except Exception as e:
            logger.warning(f"MovieEvent retrieval failed for query {query.assertion_id}: {e}")
            return []

        for event, score, breakdown in results:
            norm_score = max(0.0, min(1.0, score / 100.0))
            cand = RetrievalCandidate(
                candidate_id=f"event_{event.event_id}",
                movie_id=event.movie_id,
                start=event.start_time,
                end=event.end_time,
                source=self.stage_name,
                retrieval_score=norm_score,
                semantic_score=norm_score * 0.9,
                temporal_score=0.85,
                structured_score=norm_score,
                metadata={
                    "event_id": event.event_id,
                    "movie_number": event.movie_number,
                    "scene_id": event.scene_id,
                    "primary_subject": event.primary_subject,
                    "action": event.action,
                    "target": event.target,
                    "location": event.location,
                    "characters_present": event.characters_present,
                    "visible_objects": event.visible_objects,
                    "description": getattr(event, "visual_description", ""),
                },
                retrieval_trace={
                    "stage": self.stage_name,
                    "raw_score": score,
                    "score_breakdown": breakdown,
                    "event_action": event.action,
                    "event_subject": event.primary_subject,
                },
                is_verified=False,
            )
            candidates.append(cand)

        return candidates

    def _build_movie_event_query(self, query: RetrievalQuery) -> MovieEventQuery:
        subject = query.required_subjects[0] if query.required_subjects else None
        target = query.required_target
        if not target and len(query.required_subjects) > 1:
            target = query.required_subjects[1]

        movie_num: Optional[int] = None
        if query.preferred_movie_ids:
            for mid in query.preferred_movie_ids:
                m = re.search(r"(\d+)", str(mid))
                if m:
                    movie_num = int(m.group(1))
                    break

        return MovieEventQuery(
            subject=subject,
            action=query.required_action,
            target=target,
            location=query.required_location,
            objects=query.required_objects or [],
            movie_number=movie_num,
            forbidden_elements=query.forbidden_entities or [],
        )
