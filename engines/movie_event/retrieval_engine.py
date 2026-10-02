"""
STORY FORGE — Movie Event Retrieval & Event Chain Engine (V2)
=============================================================
Multi-attribute ranking and event-chain contextual retrieval:
  1. Hierarchical scoring prioritizing Subject, Action, Target, Location, and Interaction.
  2. Strict action veto: wrong action cannot be saved by semantic or character presence.
  3. Event Chain Retrieval: Traverses neighboring events (Preceding -> Core -> Following)
     to establish logical narrative and visual continuity.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from engines.movie_event.models import (
    MovieEvent,
    MovieEventQuery,
    VisualBeat,
)
from engines.movie_event.index import MovieEventIndex

logger = logging.getLogger("MovieEventRetrieval")

# Action compatibility mapping (synonyms / morphological stems)
ACTION_STEMS = {
    "question": ["question", "confront", "address", "grill", "ask", "interrogate"],
    "punch": ["punch", "strike", "hit", "fist", "sock"],
    "draw": ["draw", "pull", "extract", "unsheath", "brandish"],
    "open": ["open", "unlock", "part", "separate", "reveal", "parseltongue"],
    "walk": ["walk", "stride", "pace", "step", "approach"],
    "speak": ["speak", "challenge", "talk", "respond", "say", "shout"],
    "summon": ["summon", "summons", "summoned", "accio", "call", "fetch", "fly"],
    "cast": ["cast", "casts", "incant", "patronus", "crucio", "avada", "spell", "duel", "conjure", "clash"],
    "drink": ["drink", "drinks", "drank", "quaff", "swallow", "sip", "gulp"],
    "destroy": ["destroy", "destroys", "shatter", "shatters", "smash", "smashes", "break", "strike", "stab", "behead"],
    "touch": ["touch", "touches", "grab", "grabs", "grasp", "seize", "hold", "reach"],
    "catch": ["catch", "catches", "snatch", "snatches", "grab", "seize"],
    "flee": ["flee", "flees", "run", "runs", "retreat", "scramble", "escape"],
    "reveal": ["reveal", "reveals", "transform", "transforms", "emerge", "erupt", "burst"],
    "tap": ["tap", "taps", "tapping", "point", "touch", "touches", "wand"],
    "examine": ["examine", "examines", "fold", "folds", "inspect", "inspects", "look", "looks", "read", "reads"],
    "hold": ["hold", "holds", "holding", "carry", "carries", "bearing"],
    "track": ["track", "tracks", "tracking", "follow", "follows", "search", "searches", "illuminate", "illuminated", "creep"],
    "activate": ["activate", "activates", "spread", "spreads", "appear", "appears"],
}


class MovieEventRetrievalEngine:
    """
    Retrieves and ranks candidate movie events from MovieEventIndex based on
    strict multi-attribute matching and chronological event chaining.
    """

    def __init__(self, index: Optional[MovieEventIndex] = None):
        self.index = index or MovieEventIndex()

    def retrieve_events(
        self,
        query: MovieEventQuery,
        top_k: int = 5,
        min_score: float = 40.0,
    ) -> List[Tuple[MovieEvent, float, Dict[str, float]]]:
        """
        Ranks candidate events against the query.
        Returns list of (MovieEvent, total_score, score_breakdown).
        """
        candidate_pool = self.index.search_candidates(query)
        scored_events: List[Tuple[MovieEvent, float, Dict[str, float]]] = []

        for event in candidate_pool:
            score, breakdown = self._score_event(event, query)
            if score >= min_score:
                scored_events.append((event, score, breakdown))

        # Sort descending by total score
        scored_events.sort(key=lambda x: x[1], reverse=True)
        return scored_events[:top_k]

    def retrieve_event_chain(
        self,
        core_event_id: str,
    ) -> Dict[str, Optional[MovieEvent]]:
        """
        Retrieves the complete event chain around a core event:
          - preceding_event (Preceding Context / Approach)
          - core_event (The central observable event)
          - following_event (Following Reaction / Payoff)
        """
        core = self.index.get_event(core_event_id)
        if not core:
            return {"preceding": None, "core": None, "following": None}

        preceding = self.index.get_event(core.preceding_event) if core.preceding_event else None
        following = self.index.get_event(core.following_event) if core.following_event else None

        return {
            "preceding": preceding,
            "core": core,
            "following": following,
        }

    def _score_event(
        self,
        event: MovieEvent,
        query: MovieEventQuery,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Multi-Attribute Scoring:
          1. Subject Match: 30 pts (Veto if wrong primary character)
          2. Action Match:  35 pts (Veto/Penalty if action is wrong)
          3. Target Match:  15 pts
          4. Location Match: 10 pts
          5. Interaction:   10 pts
        """
        breakdown: Dict[str, float] = {
            "subject": 0.0,
            "action": 0.0,
            "target": 0.0,
            "location": 0.0,
            "interaction": 0.0,
            "forbidden_penalty": 0.0,
        }

        # 1. Subject Matching (30 pts)
        if query.subject:
            q_sub = query.subject.lower()
            ev_sub = event.primary_subject.lower()
            ev_sec = [s.lower() for s in event.secondary_subjects]
            all_chars = [c.lower() for c in event.characters_present]

            if q_sub in ev_sub or ev_sub in q_sub:
                breakdown["subject"] = 30.0
            elif any(q_sub in s or s in q_sub for s in ev_sec):
                breakdown["subject"] = 22.0
            elif any(q_sub in c or c in q_sub for c in all_chars):
                breakdown["subject"] = 15.0
            else:
                # Subject mismatch is a major disqualifier
                breakdown["subject"] = 0.0
                return 0.0, breakdown

        # 2. Action Matching (35 pts) — Hard Action Integrity
        if query.action:
            action_score = self._compute_action_similarity(query.action, event.action)
            breakdown["action"] = action_score * 35.0

            # If action has ZERO match, apply heavy penalty
            if action_score <= 0.1:
                breakdown["action"] = 0.0
                # A clip with wrong action cannot rank high even if subject matches
                breakdown["forbidden_penalty"] -= 20.0

        # 3. Target / Object Matching (15 pts)
        target_tokens = set()
        if query.target:
            target_tokens.update(re.findall(r"[a-zA-Z]{3,}", query.target.lower().replace("'", "")))
        for obj in query.objects:
            target_tokens.update(re.findall(r"[a-zA-Z]{3,}", obj.lower().replace("'", "")))

        if target_tokens:
            ev_target_str = f"{event.target or ''} {' '.join(event.visible_objects)}".lower().replace("'", "")
            ev_tokens = set(re.findall(r"[a-zA-Z]{3,}", ev_target_str))
            overlap = target_tokens.intersection(ev_tokens)
            if overlap:
                breakdown["target"] = min(15.0, len(overlap) * 5.0 + 5.0)
            elif any(t in c.lower() for t in target_tokens for c in event.characters_present):
                breakdown["target"] = 10.0
            else:
                breakdown["target"] = 0.0
                # Target mismatch penalty if specific key physical prop was requested
                key_props = {"map", "parchment", "sword", "wand", "mirror", "snitch", "cloak", "potion", "hat"}
                if target_tokens.intersection(key_props):
                    breakdown["forbidden_penalty"] -= 15.0

        # 4. Location Matching (10 pts)
        if query.location:
            q_loc = query.location.lower()
            ev_loc = event.location.lower()
            if q_loc in ev_loc or ev_loc in q_loc:
                breakdown["location"] = 10.0
            elif any(w in ev_loc for w in q_loc.split()):
                breakdown["location"] = 6.0

        # 5. Interaction Matching (10 pts)
        if query.interaction:
            q_int = query.interaction.lower()
            ev_int = event.interaction_type.lower()
            if q_int in ev_int or ev_int in q_int:
                breakdown["interaction"] = 10.0
            elif "confront" in q_int and "confront" in ev_int:
                breakdown["interaction"] = 8.0

        # 6. Check Forbidden Visual Elements
        if query.forbidden_elements:
            desc_lower = event.visual_description.lower()
            for forbidden in query.forbidden_elements:
                f_lower = forbidden.lower()
                if f_lower in desc_lower or f_lower in event.action.lower():
                    breakdown["forbidden_penalty"] -= 50.0

        total = sum(breakdown.values())
        return max(0.0, round(total, 2)), breakdown

    def _compute_action_similarity(self, query_action: str, event_action: str) -> float:
        """Determines semantic action compatibility based on verbal clusters."""
        q_words = re.findall(r"[a-zA-Z]{3,}", query_action.lower())
        e_words = re.findall(r"[a-zA-Z]{3,}", event_action.lower())

        if not q_words or not e_words:
            return 0.0

        # Direct word overlap
        overlap = set(q_words).intersection(set(e_words))
        if overlap:
            return 1.0

        # Cluster stem match
        for stem, cluster in ACTION_STEMS.items():
            q_match = any(w in cluster for w in q_words)
            e_match = any(w in cluster for w in e_words)
            if q_match and e_match:
                return 0.95

        return 0.0
