"""
STORY FORGE — Movie Event Visual Verifier (V2)
==============================================
Validates candidate movie events against structured VisualBeat requirements.
Enforces hard action veto: wrong action cannot be excused by character presence,
setting, or semantic proximity.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    MovieEventQuery,
    EventVerificationResult,
    VerificationStatus,
)
from engines.movie_event.retrieval_engine import ACTION_STEMS

logger = logging.getLogger("MovieEventVerifier")


class MovieEventVisualVerifier:
    """
    Proposition-grounded visual verifier evaluating observable physical alignment.
    Enforces fail-closed validation on ACTION, SUBJECT, TARGET, and FORBIDDEN elements.
    """

    def verify_event(
        self,
        event: MovieEvent,
        beat_or_query: Any,  # VisualBeat or MovieEventQuery
    ) -> EventVerificationResult:
        """
        Executes strict verification of candidate event against requirements.
        Returns EventVerificationResult with detailed diagnostic reasons.
        """
        # Extract requirements from either VisualBeat or MovieEventQuery
        if isinstance(beat_or_query, VisualBeat):
            req_subject = beat_or_query.required_subjects[0] if beat_or_query.required_subjects else None
            req_action = beat_or_query.required_action
            req_target = beat_or_query.required_target
            req_location = beat_or_query.required_location
            req_objects = beat_or_query.required_objects
            forbidden = beat_or_query.forbidden_visuals
        elif isinstance(beat_or_query, MovieEventQuery):
            req_subject = beat_or_query.subject
            req_action = beat_or_query.action or ""
            req_target = beat_or_query.target
            req_location = beat_or_query.location
            req_objects = beat_or_query.objects
            forbidden = beat_or_query.forbidden_elements
        else:
            raise TypeError(f"Unsupported beat_or_query type: {type(beat_or_query)}")

        rejection_reasons: List[str] = []

        # 1. Subject Check
        subject_match = True
        if req_subject:
            q_sub = req_subject.lower()
            ev_sub = event.primary_subject.lower()
            ev_sec = [s.lower() for s in event.secondary_subjects]
            all_chars = [c.lower() for c in event.characters_present]

            if not (q_sub in ev_sub or ev_sub in q_sub or any(q_sub in s for s in ev_sec) or any(q_sub in c for c in all_chars)):
                subject_match = False
                rejection_reasons.append(f"SUBJECT MISMATCH: Required '{req_subject}' is not visible in candidate event.")

        # 2. Action Check (PRIMARY VETO)
        action_match = self._verify_action(req_action, event.action)
        if not action_match:
            rejection_reasons.append(
                f"ACTION MISMATCH: Required action '{req_action}' does not match depicted action '{event.action}'."
            )

        # 3. Target Check
        target_match = True
        if req_target:
            q_target = req_target.lower()
            ev_target = (event.target or "").lower()
            ev_objs = [o.lower() for o in event.visible_objects]
            all_chars = [c.lower() for c in event.characters_present]

            if not (q_target in ev_target or ev_target in q_target or any(q_target in o for o in ev_objs) or any(q_target in c for c in all_chars)):
                target_match = False
                rejection_reasons.append(f"TARGET MISMATCH: Required target '{req_target}' missing in event.")

        # 4. Location Check
        location_match = True
        if req_location:
            q_loc = req_location.lower()
            ev_loc = event.location.lower()
            if not (q_loc in ev_loc or ev_loc in q_loc or any(w in ev_loc for w in q_loc.split())):
                location_match = False
                rejection_reasons.append(f"LOCATION MISMATCH: Candidate in '{event.location}', expected '{req_location}'.")

        # 5. Object Check
        object_match = True
        if req_objects:
            ev_objs = [o.lower() for o in event.visible_objects]
            missing = [obj for obj in req_objects if not any(obj.lower() in o or o in obj.lower() for o in ev_objs)]
            if missing and len(missing) == len(req_objects):
                object_match = False
                rejection_reasons.append(f"OBJECT MISMATCH: None of key objects {req_objects} found in {event.visible_objects}.")

        # 6. Forbidden Visuals Check
        forbidden_absent = True
        if forbidden:
            desc_lower = event.visual_description.lower()
            for f in forbidden:
                if f.lower() in desc_lower or f.lower() in event.action.lower():
                    forbidden_absent = False
                    rejection_reasons.append(f"FORBIDDEN VISUAL: Candidate contains disallowed element '{f}'.")

        # Determine overall verification status
        if not action_match:
            status = VerificationStatus.REJECT_ACTION_MISMATCH
            is_verified = False
        elif not subject_match:
            status = VerificationStatus.REJECT_SUBJECT_MISMATCH
            is_verified = False
        elif not target_match:
            status = VerificationStatus.REJECT_TARGET_MISMATCH
            is_verified = False
        elif not forbidden_absent:
            status = VerificationStatus.REJECT_FORBIDDEN_ELEMENT
            is_verified = False
        elif not location_match:
            status = VerificationStatus.REJECT_LOCATION_MISMATCH
            is_verified = False
        else:
            status = VerificationStatus.VERIFIED
            is_verified = True

        confidence = round(
            (0.40 if action_match else 0.0) +
            (0.30 if subject_match else 0.0) +
            (0.15 if target_match else 0.0) +
            (0.10 if location_match else 0.0) +
            (0.05 if object_match else 0.0),
            2
        )

        explanation = (
            f"Candidate event '{event.event_id}' PASSED physical verification: shows {event.primary_subject} {event.action} in {event.location}."
            if is_verified
            else f"Candidate event '{event.event_id}' REJECTED: {'; '.join(rejection_reasons)}"
        )

        return EventVerificationResult(
            candidate_event_id=event.event_id,
            query_action=req_action,
            event_action=event.action,
            status=status,
            is_verified=is_verified,
            confidence=confidence,
            subject_match=subject_match,
            action_match=action_match,
            target_match=target_match,
            location_match=location_match,
            object_match=object_match,
            interaction_match=True,
            forbidden_absent=forbidden_absent,
            explanation=explanation,
            rejection_reasons=rejection_reasons,
        )

    def _verify_action(self, req_action: str, candidate_action: str) -> bool:
        """Evaluates whether candidate action fulfills the required action."""
        if not req_action:
            return True

        req_words = set(re.findall(r"[a-zA-Z]{3,}", req_action.lower()))
        cand_words = set(re.findall(r"[a-zA-Z]{3,}", candidate_action.lower()))

        # Direct lexical overlap
        if req_words.intersection(cand_words):
            return True

        # Cluster stem mapping
        for stem, cluster in ACTION_STEMS.items():
            req_in_cluster = any(w in cluster for w in req_words)
            cand_in_cluster = any(w in cluster for w in cand_words)
            if req_in_cluster and cand_in_cluster:
                return True

        return False
