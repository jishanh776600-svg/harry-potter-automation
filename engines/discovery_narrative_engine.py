"""
Discovery Narrative Engine (Step 1)
================================================================================
Architectural core for Deep Discovery Shorts in Harry Potter STORY FORGE.
Implements:
  - Primary format: DEEP_DISCOVERY (68.0–78.0s, hard ceiling 80.9s, ~240–280 words, 3.4–3.7 wps)
  - Exceptional format: MICRO_DISCOVERY (max ~5% uploads for short high-curiosity topics)
  - Narrative Spine: Thesis -> Evidence -> Contrast/Escalation -> Insider Epiphany -> Payoff
  - Template A (Curated Listicle) & Template B (Myth-Buster / Deep Dive) structures
  - 5 Topic-Aware Hook Archetypes with Anti-Repetition Guard & Zero Throat-Clearing
  - Tri-Partite Evidence Routing (Novel, Movie, BTS) with strict verification
  - 4-Part Topic Scoring Formula (Canon 30%, Movie 30%, Curiosity 20%, Visual 20%)
  - Pacing Model Intent (Step 1)
  - Non-deceptive Curiosity Title Generation
  - 100% Isolation of Novel Story
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Union

from core.discovery_types import (
    DiscoverySubtype,
    DiscoveryTier,
    DiscoveryStoryStructure,
    HookArchetype,
    EvidenceRoute,
    PayoffType,
    TitlePattern,
    PacingPhase,
    DiscoveryRouting,
    EvidencePoint,
    DeepDiscoveryStoryPlan,
)

logger = logging.getLogger(__name__)

# ── Throat-Clearing Opening Patterns (Forbidden in Frame 0) ───────────────────
THROAT_CLEARING_PATTERNS = [
    r"\bin this video\b",
    r"\btoday we('re| are) going to\b",
    r"\blet's talk about\b",
    r"\bdid you know\b",
    r"\bwelcome back\b",
    r"\bwhat if i told you\b",
    r"\bhave you ever wondered\b",
    r"\bin today's short\b",
    r"\bin this short\b",
    r"\bso basically\b",
    r"\bhey guys\b",
    r"\bhi guys\b",
]


class DiscoveryNarrativeEngine:
    """
    Core narrative engine for STORY FORGE Deep Discovery Shorts.
    Enforces argument-driven storytelling with verified evidence provenance.
    """

    # ── Topic Scoring & Routing ────────────────────────────────────────────────

    @staticmethod
    def calculate_topic_score(
        canon_depth: float,
        movie_contrast: float,
        curiosity_factor: float,
        visual_feasibility: float
    ) -> float:
        """
        Calculates canonical topic score using the 4-part weighted formula:
        Topic Score = 0.30 * Canon Depth + 0.30 * Movie Contrast + 0.20 * Curiosity + 0.20 * Visual Feasibility
        Inputs are normalized to 0.0 - 100.0 scale.
        """
        c_depth = max(0.0, min(100.0, float(canon_depth)))
        m_contrast = max(0.0, min(100.0, float(movie_contrast)))
        curiosity = max(0.0, min(100.0, float(curiosity_factor)))
        v_feas = max(0.0, min(100.0, float(visual_feasibility)))

        score = (
            (0.30 * c_depth) +
            (0.30 * m_contrast) +
            (0.20 * curiosity) +
            (0.20 * v_feas)
        )
        return round(score, 2)

    @classmethod
    def route_candidate(
        cls,
        topic_score: float,
        canon_depth: float,
        movie_contrast: float,
        curiosity_factor: float,
        can_sustain_long_form: bool = True
    ) -> DiscoveryRouting:
        """
        Determines the routing pipeline for a topic candidate:
          - Score >= 75: Deep Discovery candidate
          - Score >= 65 with deep novel lore (canon_depth >= 70) but low movie contrast (movie_contrast < 40): Novel Story candidate
          - Score 50–64: Hold/defer for evidence accumulation
          - Score < 50: Reject
          - Exceptional Micro: only when curiosity >= 80 and topic cannot sustain 65–80s without filler.
        """
        # Exceptional Micro routing guard
        if curiosity_factor >= 80.0 and not can_sustain_long_form:
            return DiscoveryRouting.MICRO_DISCOVERY

        if topic_score >= 75.0:
            return DiscoveryRouting.DEEP_DISCOVERY
        
        # Lore-heavy topics with low film comparison belong in Novel Story
        if topic_score >= 65.0 and canon_depth >= 70.0 and movie_contrast < 40.0:
            return DiscoveryRouting.NOVEL_STORY

        if 50.0 <= topic_score < 65.0:
            return DiscoveryRouting.HOLD

        return DiscoveryRouting.REJECT

    # ── Hook Engine ────────────────────────────────────────────────────────────

    @staticmethod
    def validate_hook(hook_text: str) -> Tuple[bool, List[str]]:
        """
        Programmatically validates a Hook concept or opening line.
        Enforces Frame 0 impact:
          - Rejects empty hooks
          - Rejects generic throat-clearing ('In this video...', 'Did you know...', etc.)
        """
        errors = []
        if not hook_text or not hook_text.strip():
            return False, ["Hook text is empty"]

        text_lower = hook_text.strip().lower()

        for pattern in THROAT_CLEARING_PATTERNS:
            if re.search(pattern, text_lower):
                errors.append(f"Forbidden throat-clearing opening detected matching pattern: '{pattern}'")

        is_valid = len(errors) == 0
        return is_valid, errors

    @classmethod
    def select_hook_archetype(
        cls,
        topic_context: Dict[str, Any],
        recent_hooks: Optional[List[Union[HookArchetype, str]]] = None
    ) -> HookArchetype:
        """
        Topic-aware hook selection with anti-repetition window.
        Prevents the same archetype from dominating recent uploads.
        """
        recent_set = set()
        if recent_hooks:
            for h in recent_hooks:
                if isinstance(h, HookArchetype):
                    recent_set.add(h.value)
                else:
                    recent_set.add(str(h))

        # Check topic characteristics to determine archetype priority ranking
        has_dialogue = bool(topic_context.get("quote") or topic_context.get("dialogue_line") or "said" in str(topic_context.get("novel_fact_summary", "")).lower())
        is_comic = any(w in str(topic_context.get("novel_fact_summary", "")).lower() for w in ["peeves", "joke", "prank", "toilet", "howler", "boggart", "weasley", "chaos"])
        is_challenge = any(w in str(topic_context.get("novel_fact_summary", "")).lower() for w in ["sorting hat", "misconception", "wrong", "lie", "secret", "never realized"])
        is_difference = bool("difference" in str(topic_context.get("discovery_type", "")).lower() or topic_context.get("movie_omits_or_changes"))

        # Build candidate priority list based on topic DNA
        priority_list: List[HookArchetype] = []
        if has_dialogue:
            priority_list.append(HookArchetype.DIALOGUE_COLD_OPEN)
        if is_comic:
            priority_list.append(HookArchetype.ABSURD_COMIC_REALITY)
        if is_challenge:
            priority_list.append(HookArchetype.DIRECT_CHALLENGE)
        if is_difference:
            priority_list.append(HookArchetype.COUNTER_INTUITIVE_TRUTH)
            priority_list.append(HookArchetype.INCREDULITY_AWARENESS_TEST)

        # Append all remaining archetypes in deterministic order
        all_archetypes = [
            HookArchetype.COUNTER_INTUITIVE_TRUTH,
            HookArchetype.INCREDULITY_AWARENESS_TEST,
            HookArchetype.DIRECT_CHALLENGE,
            HookArchetype.ABSURD_COMIC_REALITY,
            HookArchetype.DIALOGUE_COLD_OPEN,
        ]
        for arc in all_archetypes:
            if arc not in priority_list:
                priority_list.append(arc)

        # Select first priority archetype not present in recent_set
        for candidate_arc in priority_list:
            if candidate_arc.value not in recent_set:
                return candidate_arc

        # Fallback if all archetypes were used recently
        return priority_list[0]

    # ── Structure Selection ───────────────────────────────────────────────────

    @staticmethod
    def select_structure(
        evidence_points_count: int,
        is_myth_or_deep_dive: bool = False
    ) -> DiscoveryStoryStructure:
        """
        Selects canonical Deep Discovery narrative template:
          - Template A: Curated Multi-Point Listicle (Hook -> Rapid Entry -> Secondary Point -> Anchor Highlight -> Quick-Fire -> Payoff)
          - Template B: Myth-Buster / Single-Topic Deep Dive (Curiosity Hook -> Common Perception -> Canon Contradiction -> Escalating Evidence -> Deeper Truth -> Payoff)
        """
        if is_myth_or_deep_dive or evidence_points_count <= 2:
            return DiscoveryStoryStructure.TEMPLATE_B_MYTH_BUSTER
        return DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE

    # ── Tri-Partite Evidence Routing ──────────────────────────────────────────

    @staticmethod
    def route_evidence(
        claim: str,
        source_type: str,
        source_id: str,
        source_excerpt: str,
        notes: Optional[str] = None
    ) -> EvidencePoint:
        """
        Routes and constructs a verified EvidencePoint.
        Preserves provenance:
          - Novel/Canon claim -> NOVEL_CANON
          - Movie claim -> MOVIE_CANON
          - BTS / Casting / Production claim -> BTS_PRODUCTION
        """
        st_upper = str(source_type).upper()
        if "MOVIE" in st_upper or "FILM" in st_upper or "SRT" in st_upper:
            route = EvidenceRoute.MOVIE_CANON.value
        elif "BTS" in st_upper or "PRODUCTION" in st_upper or "ARCHIVAL" in st_upper or "INTERVIEW" in st_upper:
            route = EvidenceRoute.BTS_PRODUCTION.value
        else:
            route = EvidenceRoute.NOVEL_CANON.value

        is_verified = bool(source_id and str(source_id).strip() and source_excerpt and str(source_excerpt).strip())

        return EvidencePoint(
            claim=claim.strip(),
            evidence_route=route,
            source_id=source_id.strip() if source_id else "",
            source_excerpt=source_excerpt.strip() if source_excerpt else "",
            verified=is_verified,
            notes=notes
        )

    @staticmethod
    def validate_evidence_points(evidence_points: List[EvidencePoint]) -> Tuple[bool, List[str]]:
        """
        Strict QA check: every claim in a finalized Discovery plan must be backed
        by a verified source with source_id and excerpt. No ungrounded claims permitted.
        """
        errors = []
        if not evidence_points:
            return False, ["Zero evidence points provided"]

        for idx, ep in enumerate(evidence_points):
            if not ep.claim:
                errors.append(f"Evidence point {idx} has empty claim")
            if not ep.verified:
                errors.append(f"Evidence point {idx} is unverified: '{ep.claim}'")
            if not ep.source_id:
                errors.append(f"Evidence point {idx} lacks source_id: '{ep.claim}'")
            if not ep.source_excerpt:
                errors.append(f"Evidence point {idx} lacks source_excerpt: '{ep.claim}'")

        return len(errors) == 0, errors

    # ── Timing & Word Count Budget ────────────────────────────────────────────

    @staticmethod
    def calculate_targets(
        tier: DiscoveryTier = DiscoveryTier.DEEP_DISCOVERY,
        custom_duration: Optional[float] = None,
        custom_speech_rate: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates target word counts, duration boundaries, and speech rate for a given tier.
        DEEP_DISCOVERY:
          - Target duration: 68.0–78.0s (hard ceiling 80.9s)
          - Target speech rate: 3.4–3.7 words/second
          - Target word count: ~240–280 words
        MICRO_DISCOVERY:
          - Target duration: 25.0–35.0s
          - Target speech rate: ~2.5 words/second
          - Target word count: ~60–80 words
        """
        if tier == DiscoveryTier.DEEP_DISCOVERY:
            duration = custom_duration if custom_duration is not None else 72.0
            duration = max(65.0, min(80.9, duration))
            speech_rate = custom_speech_rate if custom_speech_rate is not None else 3.55
            speech_rate = max(3.4, min(3.7, speech_rate))
            word_count = int(round(duration * speech_rate))
            return {
                "tier": DiscoveryTier.DEEP_DISCOVERY.value,
                "expected_duration": duration,
                "min_duration": 68.0,
                "max_duration": 78.0,
                "hard_ceiling_duration": 80.9,
                "target_speech_rate": speech_rate,
                "min_speech_rate": 3.4,
                "max_speech_rate": 3.7,
                "target_word_count": word_count,
                "min_word_count": 240,
                "max_word_count": 280,
            }
        else:
            duration = custom_duration if custom_duration is not None else 28.0
            duration = max(20.0, min(35.0, duration))
            speech_rate = custom_speech_rate if custom_speech_rate is not None else 2.5
            word_count = int(round(duration * speech_rate))
            return {
                "tier": DiscoveryTier.MICRO_DISCOVERY.value,
                "expected_duration": duration,
                "min_duration": 25.0,
                "max_duration": 35.0,
                "hard_ceiling_duration": 40.0,
                "target_speech_rate": speech_rate,
                "min_speech_rate": 2.2,
                "max_speech_rate": 2.8,
                "target_word_count": word_count,
                "min_word_count": 60,
                "max_word_count": 80,
            }

    # ── Pacing Model Intent (Step 1 Conceptual Targets) ────────────────────────

    @staticmethod
    def get_pacing_intent(structure: DiscoveryStoryStructure) -> Dict[str, Any]:
        """
        Returns editorial target visual rhythm curves for Step 1 story schemas.
        """
        return {
            "structure": structure.value if isinstance(structure, DiscoveryStoryStructure) else str(structure),
            "phases": {
                PacingPhase.HOOK.value: {"target_cut_seconds": (0.8, 1.2), "description": "High visual rhythm engagement"},
                PacingPhase.SETUP.value: {"target_cut_seconds": (1.2, 1.6), "description": "Rapid exposition"},
                PacingPhase.EVIDENCE.value: {"target_cut_seconds": (1.4, 1.8), "description": "Escalating proof"},
                PacingPhase.ANCHOR.value: {"target_cut_seconds": (2.2, 3.2), "description": "Asymmetric emphasis scene"},
                PacingPhase.PAYOFF.value: {"target_cut_seconds": (1.0, 1.5), "description": "Punchy revelation and finish"},
            }
        }

    # ── Non-Deceptive Curiosity Title Generation ──────────────────────────────

    @staticmethod
    def generate_suggested_title(
        pattern: TitlePattern,
        topic_summary: str,
        entities: Optional[List[str]] = None
    ) -> str:
        """
        Produces curiosity-driven, truthful titles adhering to canonical patterns.
        """
        entity_name = entities[0] if (entities and len(entities) > 0) else "Harry Potter"
        clean_summary = topic_summary.replace("Harry Potter", "").strip(" —-.")

        if pattern == TitlePattern.CURIOSITY_QUESTION:
            return f"Why Did the Harry Potter Movies Change This About {entity_name}?"
        elif pattern == TitlePattern.HIDDEN_DETAIL:
            return f"The Secret {entity_name} Detail Hidden in the Books"
        elif pattern == TitlePattern.COUNTER_INTUITIVE_TRUTH:
            return f"The Movies Made You Think This Happened to {entity_name} — The Books Prove Otherwise"
        elif pattern == TitlePattern.BOOK_VS_MOVIE:
            return f"Book vs Movie: The Crucial Scene Left Out of {entity_name}'s Story"
        elif pattern == TitlePattern.MYSTERY_REVEAL:
            return f"The Real Reason This {entity_name} Scene Was Cut"
        elif pattern == TitlePattern.CHALLENGE:
            return f"Only True Harry Potter Book Readers Know What Really Happened to {entity_name}"
        else:
            return f"Harry Potter Canon: {topic_summary[:60]}"

    # ── High-Level Story Plan Builder ─────────────────────────────────────────

    @classmethod
    def build_deep_discovery_plan(
        cls,
        topic_id: str,
        discovery_type: str,
        thesis: str,
        evidence_points: List[EvidencePoint],
        insider_epiphany: str,
        payoff_type: PayoffType,
        payoff_text: str,
        canon_depth: float,
        movie_contrast: float,
        curiosity_factor: float,
        visual_feasibility: float,
        anchor_point: Optional[EvidencePoint] = None,
        hook_archetype: Optional[HookArchetype] = None,
        recent_hooks: Optional[List[HookArchetype]] = None,
        topic_context: Optional[Dict[str, Any]] = None,
        title_pattern: TitlePattern = TitlePattern.BOOK_VS_MOVIE,
        suggested_title: Optional[str] = None,
        tier: DiscoveryTier = DiscoveryTier.DEEP_DISCOVERY,
        can_sustain_long_form: bool = True
    ) -> DeepDiscoveryStoryPlan:
        """
        Builds, scores, validates, and packages a complete DeepDiscoveryStoryPlan.
        """
        topic_score = cls.calculate_topic_score(
            canon_depth=canon_depth,
            movie_contrast=movie_contrast,
            curiosity_factor=curiosity_factor,
            visual_feasibility=visual_feasibility
        )

        routing_decision = cls.route_candidate(
            topic_score=topic_score,
            canon_depth=canon_depth,
            movie_contrast=movie_contrast,
            curiosity_factor=curiosity_factor,
            can_sustain_long_form=can_sustain_long_form
        )

        # Select hook archetype if not provided
        if hook_archetype is None:
            ctx = topic_context or {
                "novel_fact_summary": thesis,
                "discovery_type": discovery_type
            }
            hook_archetype = cls.select_hook_archetype(ctx, recent_hooks)

        # Select narrative structure
        structure = cls.select_structure(
            evidence_points_count=len(evidence_points),
            is_myth_or_deep_dive=(routing_decision == DiscoveryRouting.MICRO_DISCOVERY or "difference" not in str(discovery_type).lower())
        )

        # Anchor point selection for Template A
        if anchor_point is None and evidence_points:
            anchor_point = evidence_points[0]

        targets = cls.calculate_targets(tier=tier)

        final_title = suggested_title or cls.generate_suggested_title(
            pattern=title_pattern,
            topic_summary=thesis,
            entities=topic_context.get("characters") if topic_context else None
        )

        plan = DeepDiscoveryStoryPlan(
            topic_id=topic_id,
            discovery_type=discovery_type,
            discovery_tier=tier,
            story_structure=structure,
            hook_archetype=hook_archetype,
            evidence_route=evidence_points[0].evidence_route if evidence_points else EvidenceRoute.NOVEL_CANON,
            thesis=thesis,
            evidence_points=evidence_points,
            anchor_point=anchor_point,
            insider_epiphany=insider_epiphany,
            payoff_type=payoff_type,
            payoff_text=payoff_text,
            title_pattern=title_pattern,
            suggested_title=final_title,
            expected_duration=targets["expected_duration"],
            target_word_count=targets["target_word_count"],
            target_speech_rate=targets["target_speech_rate"],
            topic_score=topic_score,
            canon_depth=canon_depth,
            movie_contrast=movie_contrast,
            curiosity_factor=curiosity_factor,
            visual_feasibility=visual_feasibility,
            pacing_intent=cls.get_pacing_intent(structure),
            routing_decision=routing_decision.value,
        )

        plan.validate()
        return plan
