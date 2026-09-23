"""
STORY FORGE Anchor-Grounded Hybrid Storyboard Planner (Step 2)
================================================================================
Implements the timeline-locked storyboard planner sitting between Deep Discovery
narrative planning (Step 1) and downstream rendering:

    Canon thesis/evidence -> visual feasibility audit -> anchor selection ->
    bidirectional visual routing -> timeline-locked storyboard contracts

Key Capabilities & Strict Rules:
1. Novel Story Isolation:
   - Deep Discovery Storyboard Planner strictly isolates Deep Discovery / Curated Listicle
     / Myth-Buster formats from Novel Story (Type A).
2. Four Explicit Visual Roles:
   - DIRECT_EVIDENCE: Visuals directly depict the specific claim, action, or object.
   - CONTEXTUAL_ENVIRONMENT: Authentic setting or world atmosphere providing spatial grounding.
   - CHARACTER_REACTION: Emotional expression or response reflecting the revelation.
   - IRONIC_CONTRAST: Visual explicitly contradicts voiceover (e.g. film omitted or changed scene).
3. Hybrid Visual Hierarchy:
   - 1. MOVIE_DIRECT (canonical Movies 1-8).
   - 2. FAN_ART / OFFICIAL_ARTWORK (cleared, authentic illustrations).
   - 3. NO_VALID_VISUAL (truthful fallback; never generic stock, never AI images).
4. Asymmetric Anchor Duration & Dynamic Pacing:
   - HOOK: 0.8s - 1.2s (target ~1.0s)
   - SETUP: 1.2s - 1.6s (target ~1.4s)
   - EVIDENCE: 1.4s - 1.8s (target ~1.6s)
   - ANCHOR: 2.2s - 3.2s (target ~2.7s) (asymmetric screen-time emphasis)
   - PAYOFF: 1.0s - 1.5s (target ~1.2s)
5. Bidirectional Feasibility Audit:
   - Audits visual availability against canonical movie database & artwork registry.
   - Assigns 0.0 - 100.0 score per beat and overall short.
   - Rejects unsupported / misleading pairings.
6. Commit 37b1463 Framing Intent Preservation:
   - Enforces Natural Cinematic Framing (ShotScale): CLOSE_UP, TWO_SHOT, WIDE_SHOT,
     MEDIUM_WIDE, MEDIUM_SHOT.
7. Anti-Repetition & Visual Diversity:
   - Prevents repetitive shot scales and identical movie timestamp loops.
8. Deterministic Generation:
   - Reproducible beat contracts and timeline-locked start/end timestamps.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config.settings import PROJECT_ROOT, DB_PATH
from core.hybrid_visual_models import (
    VisualSourceType,
    ArtistLicenseStatus,
    CommercialClearanceStatus,
    RightsStatus,
    ApprovalStatus,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.discovery_types import (
    DiscoveryTier,
    DiscoveryStoryStructure,
    PacingPhase,
    EvidenceRoute,
    EvidencePoint,
    DeepDiscoveryStoryPlan,
)
from core.storyboard_types import (
    VisualRole,
    TransitionIntent,
    FallbackStrategy,
    StoryboardBeatContract,
    StoryboardPlan,
)
from engines.movie_retrieval_engine import MovieRetrievalEngine, ShotScale, KNOWN_CHARACTERS
from engines.fan_art_retrieval_engine import FanArtRetrievalEngine
from engines.hybrid_visual_engine import HybridVisualEngine

logger = logging.getLogger(__name__)

# Canonical locations for contextual fallback detection
COMMON_LOCATIONS = [
    "great hall", "gryffindor common room", "slytherin common room", "dungeons",
    "potions classroom", "defense against the dark arts", "library", "forbidden forest",
    "quidditch pitch", "hagrid's hut", "astronomy tower", "headmaster's office",
    "dumbledore's office", "ministry of magic", "diagon alley", "platform 9 3/4",
    "privet drive", "shrieking shack", "hogsmeade", "chamber of secrets",
    "room of requirement", "graveyard", "department of mysteries"
]

# Canonical characters for reaction fallback detection
KEY_REACTION_CHARACTERS = [
    "harry", "ron", "hermione", "dumbledore", "snape", "voldemort",
    "neville", "draco", "mcgonagall", "hagrid", "sirius", "lupin"
]


class StoryboardPlanner:
    """
    Anchor-Grounded Hybrid Storyboard Planner.
    Generates deterministic, timeline-locked storyboard beat contracts.
    """

    def __init__(
        self,
        movie_engine: Optional[MovieRetrievalEngine] = None,
        fan_art_engine: Optional[FanArtRetrievalEngine] = None,
        hybrid_engine: Optional[HybridVisualEngine] = None,
        db_path: Optional[Path] = None,
    ):
        self.db_path = db_path or DB_PATH
        self.movie_engine = movie_engine or MovieRetrievalEngine(db_path=self.db_path)
        self.fan_art_engine = fan_art_engine or FanArtRetrievalEngine()
        self.hybrid_engine = hybrid_engine or HybridVisualEngine(
            db_path=self.db_path,
            fan_art_engine=self.fan_art_engine,
            movie_engine=self.movie_engine,
        )

    def plan_storyboard(
        self,
        plan: Union[DeepDiscoveryStoryPlan, Dict[str, Any], Any],
        candidate_type: str = "deep_discovery",
        target_total_duration: Optional[float] = None,
    ) -> StoryboardPlan:
        """
        Main entry point: Generates a complete, validated StoryboardPlan.
        Strictly isolates Novel Story pipelines.
        """
        # 1. NOVEL STORY ISOLATION GUARD
        if candidate_type == "novel_story":
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Storyboard Planner."
            )

        if isinstance(plan, DeepDiscoveryStoryPlan):
            if hasattr(plan, "discovery_tier") and str(plan.discovery_tier).upper() in ("NOVEL_STORY", "NOVEL_STORY_CANDIDATE"):
                raise ValueError(
                    "Novel Story pipeline is isolated from Deep Discovery Storyboard Planner."
                )
        elif isinstance(plan, dict):
            if (
                plan.get("content_type") == "novel_story"
                or str(plan.get("discovery_tier", "")).upper() in ("NOVEL_STORY", "NOVEL_STORY_CANDIDATE")
            ):
                raise ValueError(
                    "Novel Story pipeline is isolated from Deep Discovery Storyboard Planner."
                )
        elif hasattr(plan, "content_type") and getattr(plan, "content_type") == "novel_story":
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Storyboard Planner."
            )

        # 2. EXTRACT NARRATIVE DATA
        topic_id, tier, structure, thesis, evidence_points, anchor_pt, epiphany, payoff_text, expected_dur = (
            self._extract_plan_components(plan)
        )

        expected_total_duration = target_total_duration or expected_dur or 72.0
        storyboard_id = f"sb_{topic_id}"

        # 3. IDENTIFY ANCHOR POINT
        anchor_point_id = None
        if anchor_pt:
            anchor_point_id = anchor_pt.source_id or anchor_pt.claim
        elif evidence_points:
            # Deterministic selection: find first novel-only or book-vs-movie difference, or first point
            for ep in evidence_points:
                route = ep.evidence_route.upper() if isinstance(ep.evidence_route, str) else ep.evidence_route.value
                if "NOVEL" in route or "BOOK" in route or "DIFFERENCE" in route:
                    anchor_point_id = ep.source_id or ep.claim
                    break
            if not anchor_point_id and evidence_points:
                anchor_point_id = evidence_points[0].source_id or evidence_points[0].claim

        # 4. GENERATE BEAT CONTRACTS ACROSS 5 PACING PHASES
        beats: List[StoryboardBeatContract] = []
        used_movie_intervals: List[Tuple[int, float, float]] = []
        recent_shot_scales: List[ShotScale] = []

        # Phase A: HOOK (0.8s - 1.2s, target 1.0s)
        hook_beat = self._build_hook_beat(
            topic_id=topic_id,
            thesis=thesis,
            recent_scales=recent_shot_scales,
            used_intervals=used_movie_intervals,
        )
        beats.append(hook_beat)
        recent_shot_scales.append(hook_beat.framing_intent)

        # Phase B: SETUP (1.2s - 1.6s, target 1.4s)
        setup_beat = self._build_setup_beat(
            topic_id=topic_id,
            thesis=thesis,
            recent_scales=recent_shot_scales,
            used_intervals=used_movie_intervals,
        )
        beats.append(setup_beat)
        recent_shot_scales.append(setup_beat.framing_intent)

        # Phase C: EVIDENCE & ANCHOR BEATS
        anchor_beat_ids: List[str] = []
        for idx, ev in enumerate(evidence_points, start=1):
            is_anchor = (
                (anchor_point_id is not None and (ev.source_id == anchor_point_id or ev.claim == anchor_point_id))
                or (anchor_pt is not None and ev.claim == anchor_pt.claim)
            )

            beat = self._build_evidence_beat(
                topic_id=topic_id,
                ev=ev,
                idx=idx,
                is_anchor=is_anchor,
                recent_scales=recent_shot_scales,
                used_intervals=used_movie_intervals,
            )
            beats.append(beat)
            recent_shot_scales.append(beat.framing_intent)
            if beat.is_anchor:
                anchor_beat_ids.append(beat.beat_id)

        # Ensure at least one beat is designated anchor
        if not anchor_beat_ids and len(beats) > 2:
            # Promote the most detailed evidence beat to anchor
            target_b = beats[2]
            target_b.is_anchor = True
            target_b.target_duration = 2.7
            target_b.narrative_phase = PacingPhase.ANCHOR.value
            target_b.motion_intent = "SLOW_PUSH_IN"
            anchor_beat_ids.append(target_b.beat_id)

        # Phase D: PAYOFF (1.0s - 1.5s, target 1.2s)
        payoff_beat = self._build_payoff_beat(
            topic_id=topic_id,
            epiphany=epiphany,
            payoff_text=payoff_text,
            recent_scales=recent_shot_scales,
            used_intervals=used_movie_intervals,
        )
        beats.append(payoff_beat)
        recent_shot_scales.append(payoff_beat.framing_intent)

        # 5. CONTINUOUS TIMELINE LOCKING
        current_time = 0.0
        for b in beats:
            b.start_seconds = round(current_time, 2)
            b.end_seconds = round(current_time + b.target_duration, 2)
            current_time = b.end_seconds

        total_duration = round(current_time, 2)

        # 6. OVERALL FEASIBILITY & ADAPTATION SUGGESTIONS
        beat_feasibility_scores = [b.visual_feasibility_score for b in beats]
        overall_feasibility = (
            round(sum(beat_feasibility_scores) / len(beat_feasibility_scores), 1)
            if beat_feasibility_scores
            else 0.0
        )

        narrative_adjustments: List[str] = []
        is_production_feasible = True

        for b in beats:
            if b.is_anchor and b.visual_source_type == VisualSourceType.NO_VALID_VISUAL:
                is_production_feasible = False
                narrative_adjustments.append(
                    f"Anchor beat '{b.beat_id}' has NO_VALID_VISUAL. Suggest reframing anchor claim to filmed scene or clearing fan art."
                )
            elif b.visual_feasibility_score < 40.0:
                narrative_adjustments.append(
                    f"Beat '{b.beat_id}' has low visual feasibility ({b.visual_feasibility_score:.1f}). Suggest acquiring illustration or utilizing contextual setting."
                )

        if overall_feasibility < 60.0:
            is_production_feasible = False
            narrative_adjustments.append(
                f"Overall visual feasibility ({overall_feasibility:.1f}) is below production threshold (60.0). Recommend movie-contrast refocus."
            )

        storyboard_plan = StoryboardPlan(
            storyboard_id=storyboard_id,
            topic_id=topic_id,
            discovery_tier=tier,
            story_structure=structure,
            total_target_duration=total_duration,
            beats=beats,
            anchor_beat_ids=anchor_beat_ids,
            overall_visual_feasibility_score=overall_feasibility,
            is_production_feasible=is_production_feasible,
            narrative_adjustments_suggested=narrative_adjustments,
            metadata={
                "candidate_type": candidate_type,
                "anchor_point_id": anchor_point_id,
                "beat_count": len(beats),
            },
        )

        # Validate
        is_valid, validation_errors = storyboard_plan.validate()
        if not is_valid:
            logger.warning(f"[StoryboardPlanner] Validation warnings for {storyboard_id}: {validation_errors}")
            storyboard_plan.metadata["validation_errors"] = validation_errors

        return storyboard_plan

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS: PHASE BEAT BUILDERS
    # --------------------------------------------------------------------------

    def _build_hook_beat(
        self,
        topic_id: str,
        thesis: str,
        recent_scales: List[ShotScale],
        used_intervals: List[Tuple[int, float, float]],
    ) -> StoryboardBeatContract:
        """Builds high-impact HOOK beat (0.8s - 1.2s, target 1.0s)."""
        beat_id = f"{topic_id}_beat_01_hook"
        duration = 1.0  # Strict range 0.8 - 1.2s

        beat_dict = {
            "beat_id": beat_id,
            "narration_text": thesis,
            "action": "facial reaction or dramatic revelation",
            "emotional_context": "shock disbelief discovery",
        }
        framing = self._infer_framing_with_diversity(beat_dict, recent_scales)

        # Audit visual
        v_role, v_source, score, fallback, clip_ref = self._audit_feasibility_for_text(
            text=thesis,
            role_hint=VisualRole.DIRECT_EVIDENCE,
            used_intervals=used_intervals,
        )

        return StoryboardBeatContract(
            beat_id=beat_id,
            narrative_phase=PacingPhase.HOOK.value,
            target_duration=duration,
            narration_intent=f"Hook: {thesis[:100]}",
            evidence_point_id=None,
            visual_role=v_role,
            visual_source_type=v_source,
            preferred_movie_number=clip_ref.get("movie_number"),
            scene_reference=clip_ref.get("scene_reference"),
            clip_start_seconds=clip_ref.get("start_seconds"),
            clip_end_seconds=clip_ref.get("end_seconds"),
            framing_intent=framing,
            is_anchor=False,
            visual_feasibility_score=score,
            fallback_strategy=fallback,
            transition_intent=TransitionIntent.HARD_CUT,
            motion_intent="RAPID_CUT",
            caption_intent="HOOK_KEYWORD_HIGHLIGHT",
        )

    def _build_setup_beat(
        self,
        topic_id: str,
        thesis: str,
        recent_scales: List[ShotScale],
        used_intervals: List[Tuple[int, float, float]],
    ) -> StoryboardBeatContract:
        """Builds SETUP beat establishing context/setting (1.2s - 1.6s, target 1.4s)."""
        beat_id = f"{topic_id}_beat_02_setup"
        duration = 1.4  # Strict range 1.2 - 1.6s

        beat_dict = {
            "beat_id": beat_id,
            "narration_text": thesis,
            "visual_requirement": "Hogwarts setting or baseline situation",
            "location": "Hogwarts Castle or setting",
        }
        framing = self._infer_framing_with_diversity(beat_dict, recent_scales, default=ShotScale.MEDIUM_WIDE)

        v_role, v_source, score, fallback, clip_ref = self._audit_feasibility_for_text(
            text=f"Hogwarts setting {thesis}",
            role_hint=VisualRole.CONTEXTUAL_ENVIRONMENT,
            used_intervals=used_intervals,
        )

        return StoryboardBeatContract(
            beat_id=beat_id,
            narrative_phase=PacingPhase.SETUP.value,
            target_duration=duration,
            narration_intent=f"Setup: Context for {thesis[:80]}",
            evidence_point_id=None,
            visual_role=v_role,
            visual_source_type=v_source,
            preferred_movie_number=clip_ref.get("movie_number"),
            scene_reference=clip_ref.get("scene_reference"),
            clip_start_seconds=clip_ref.get("start_seconds"),
            clip_end_seconds=clip_ref.get("end_seconds"),
            framing_intent=framing,
            is_anchor=False,
            visual_feasibility_score=score,
            fallback_strategy=fallback,
            transition_intent=TransitionIntent.HARD_CUT,
            motion_intent="SUBTLE_PAN",
        )

    def _build_evidence_beat(
        self,
        topic_id: str,
        ev: EvidencePoint,
        idx: int,
        is_anchor: bool,
        recent_scales: List[ShotScale],
        used_intervals: List[Tuple[int, float, float]],
    ) -> StoryboardBeatContract:
        """
        Builds an EVIDENCE or ANCHOR beat linked directly to an EvidencePoint.
        Anchor beats receive asymmetric duration (2.2s - 3.2s, target ~2.7s).
        Regular evidence beats receive (1.4s - 1.8s, target ~1.6s).
        """
        phase_str = PacingPhase.ANCHOR.value if is_anchor else PacingPhase.EVIDENCE.value
        beat_id = f"{topic_id}_beat_{idx+2:02d}_{'anchor' if is_anchor else 'ev'}"
        duration = 2.7 if is_anchor else 1.6  # Asymmetric anchor emphasis

        # Extract entities from evidence claim
        route_str = ev.evidence_route.upper() if isinstance(ev.evidence_route, str) else ev.evidence_route.value
        claim = ev.claim
        is_novel_only = "NOVEL" in route_str and "MOVIE" not in route_str
        is_difference = "DIFFERENCE" in route_str or "VS" in route_str or "BOOK_VS_MOVIE" in route_str

        # Framing determination (Commit 37b1463 policy)
        beat_dict = {
            "beat_id": beat_id,
            "narration_text": claim,
            "visual_requirement": claim,
            "action": claim,
        }
        framing = self._infer_framing_with_diversity(beat_dict, recent_scales)

        # Bidirectional Feasibility Audit
        v_role, v_source, score, fallback, clip_ref, provenance = self._audit_evidence_feasibility(
            claim=claim,
            route=route_str,
            source_id=ev.source_id,
            is_novel_only=is_novel_only,
            is_difference=is_difference,
            used_intervals=used_intervals,
        )

        motion = "SLOW_PUSH_IN" if is_anchor else "RAPID_CUT"
        trans = TransitionIntent.MATCH_CUT if is_anchor else TransitionIntent.HARD_CUT

        return StoryboardBeatContract(
            beat_id=beat_id,
            narrative_phase=phase_str,
            target_duration=duration,
            narration_intent=f"Evidence: {claim}",
            evidence_point_id=ev.source_id or f"ep_{idx}",
            visual_role=v_role,
            visual_source_type=v_source,
            preferred_movie_number=clip_ref.get("movie_number"),
            scene_reference=clip_ref.get("scene_reference"),
            clip_start_seconds=clip_ref.get("start_seconds"),
            clip_end_seconds=clip_ref.get("end_seconds"),
            required_characters=clip_ref.get("characters", []),
            required_actions=clip_ref.get("actions", []),
            required_objects=clip_ref.get("objects", []),
            framing_intent=framing,
            is_anchor=is_anchor,
            visual_feasibility_score=score,
            fallback_strategy=fallback,
            source_provenance=provenance,
            transition_intent=trans,
            motion_intent=motion,
            caption_intent="ANCHOR_KEYWORD" if is_anchor else None,
            adaptation_notes=ev.notes,
        )

    def _build_payoff_beat(
        self,
        topic_id: str,
        epiphany: str,
        payoff_text: str,
        recent_scales: List[ShotScale],
        used_intervals: List[Tuple[int, float, float]],
    ) -> StoryboardBeatContract:
        """Builds PAYOFF beat (1.0s - 1.5s, target 1.2s)."""
        beat_id = f"{topic_id}_beat_last_payoff"
        duration = 1.2  # Strict range 1.0 - 1.5s
        payoff_narr = payoff_text or epiphany or "The hidden canon reality revealed."

        beat_dict = {
            "beat_id": beat_id,
            "narration_text": payoff_narr,
            "emotional_context": "realization epiphany knowing smile",
        }
        framing = self._infer_framing_with_diversity(beat_dict, recent_scales, default=ShotScale.CLOSE_UP)

        v_role, v_source, score, fallback, clip_ref = self._audit_feasibility_for_text(
            text=payoff_narr,
            role_hint=VisualRole.CHARACTER_REACTION,
            used_intervals=used_intervals,
        )

        return StoryboardBeatContract(
            beat_id=beat_id,
            narrative_phase=PacingPhase.PAYOFF.value,
            target_duration=duration,
            narration_intent=f"Payoff: {payoff_narr[:100]}",
            evidence_point_id=None,
            visual_role=v_role,
            visual_source_type=v_source,
            preferred_movie_number=clip_ref.get("movie_number"),
            scene_reference=clip_ref.get("scene_reference"),
            clip_start_seconds=clip_ref.get("start_seconds"),
            clip_end_seconds=clip_ref.get("end_seconds"),
            framing_intent=framing,
            is_anchor=False,
            visual_feasibility_score=score,
            fallback_strategy=fallback,
            transition_intent=TransitionIntent.SMASH_CUT,
            motion_intent="HOLD",
            caption_intent="FINAL_PUNCHLINE",
        )

    # --------------------------------------------------------------------------
    # BIDIRECTIONAL FEASIBILITY AUDIT ENGINE
    # --------------------------------------------------------------------------

    def _audit_evidence_feasibility(
        self,
        claim: str,
        route: str,
        source_id: str,
        is_novel_only: bool,
        is_difference: bool,
        used_intervals: List[Tuple[int, float, float]],
    ) -> Tuple[VisualRole, VisualSourceType, float, Optional[FallbackStrategy], Dict[str, Any], Dict[str, Any]]:
        """
        Core bidirectional feasibility audit.
        Evaluates visual availability and assigns visual role truthfully:
        1. MOVIE_DIRECT
        2. FAN_ART / OFFICIAL_ARTWORK
        3. CONTEXTUAL_ENVIRONMENT / CHARACTER_REACTION Fallbacks
        4. NO_VALID_VISUAL
        """
        provenance = {
            "source_id": source_id,
            "route": route,
            "claim": claim,
            "evaluated_at": "storyboard_planner_step2",
        }

        # Check for forbidden sources in claim text
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in claim.lower():
                raise ValueError(
                    f"FORBIDDEN VISUAL SOURCE: Evidence '{claim}' requested '{forbidden}'. Stock is permanently disabled."
                )

        # ----------------------------------------------------------------------
        # A. BOOK VS MOVIE DIFFERENCE -> IRONIC_CONTRAST
        # ----------------------------------------------------------------------
        if is_difference:
            # Check if movie scene exists showing what the movie did instead
            movie_cand = self._search_movie_direct(claim, used_intervals)
            if movie_cand and movie_cand.get("retrieval_score", 0.0) >= 60.0:
                clip_ref = self._candidate_to_clip_ref(movie_cand)
                used_intervals.append((movie_cand["movie_number"], movie_cand["start_seconds"], movie_cand["end_seconds"]))
                provenance["movie_contrast_chunk_id"] = movie_cand.get("chunk_id")
                return (
                    VisualRole.IRONIC_CONTRAST,
                    VisualSourceType.MOVIE_DIRECT,
                    min(95.0, movie_cand["retrieval_score"] + 5.0),
                    None,
                    clip_ref,
                    provenance,
                )

        # ----------------------------------------------------------------------
        # B. MOVIE FOOTAGE FIRST (if not novel-only)
        # ----------------------------------------------------------------------
        if not is_novel_only:
            movie_cand = self._search_movie_direct(claim, used_intervals)
            if movie_cand and movie_cand.get("retrieval_score", 0.0) >= 65.0:
                clip_ref = self._candidate_to_clip_ref(movie_cand)
                used_intervals.append((movie_cand["movie_number"], movie_cand["start_seconds"], movie_cand["end_seconds"]))
                provenance["movie_chunk_id"] = movie_cand.get("chunk_id")
                return (
                    VisualRole.DIRECT_EVIDENCE,
                    VisualSourceType.MOVIE_DIRECT,
                    min(95.0, movie_cand["retrieval_score"]),
                    None,
                    clip_ref,
                    provenance,
                )

        # ----------------------------------------------------------------------
        # C. FAN ART / OFFICIAL ARTWORK (For Novel-Only or Unfilmed details)
        # ----------------------------------------------------------------------
        art_cand = self._search_cleared_artwork(claim)
        if art_cand and art_cand.get("is_cleared", False):
            provenance["artwork_asset_id"] = art_cand.get("asset_id")
            provenance["artist"] = art_cand.get("creator")
            provenance["license"] = art_cand.get("license")
            provenance["source_url"] = art_cand.get("source_url")
            clip_ref = {
                "scene_reference": f"FanArt: {art_cand.get('title', 'Illustration')}",
                "characters": art_cand.get("characters", []),
                "actions": art_cand.get("actions", []),
                "objects": art_cand.get("objects", []),
            }
            vst = VisualSourceType.OFFICIAL_ARTWORK if art_cand.get("is_official") else VisualSourceType.FAN_ART
            return (
                VisualRole.DIRECT_EVIDENCE,
                vst,
                88.0,
                None,
                clip_ref,
                provenance,
            )

        # ----------------------------------------------------------------------
        # D. TRUTHFUL FALLBACK: CONTEXTUAL_ENVIRONMENT
        # ----------------------------------------------------------------------
        # Detect if claim specifies a recognizable location
        loc = self._detect_location(claim)
        if loc:
            loc_cand = self._search_movie_direct(f"{loc} castle interior", used_intervals)
            if loc_cand:
                clip_ref = self._candidate_to_clip_ref(loc_cand)
                provenance["fallback_location"] = loc
                return (
                    VisualRole.CONTEXTUAL_ENVIRONMENT,
                    VisualSourceType.MOVIE_DIRECT,
                    68.0,
                    FallbackStrategy.CONTEXTUAL_FALLBACK,
                    clip_ref,
                    provenance,
                )

        # ----------------------------------------------------------------------
        # E. TRUTHFUL FALLBACK: CHARACTER_REACTION
        # ----------------------------------------------------------------------
        # Detect if claim features a character whose reaction provides authentic grounding
        char = self._detect_character(claim)
        if char:
            react_cand = self._search_movie_direct(f"{char} looking listening reaction", used_intervals)
            if react_cand:
                clip_ref = self._candidate_to_clip_ref(react_cand)
                provenance["fallback_character"] = char
                return (
                    VisualRole.CHARACTER_REACTION,
                    VisualSourceType.MOVIE_DIRECT,
                    62.0,
                    FallbackStrategy.REACTION_FALLBACK,
                    clip_ref,
                    provenance,
                )

        # ----------------------------------------------------------------------
        # F. NO_VALID_VISUAL (Truthful Rejection - Never Stock / AI Images)
        # ----------------------------------------------------------------------
        logger.info(
            f"[StoryboardPlanner] No verified visual found for claim: '{claim[:60]}'. Flagging NO_VALID_VISUAL."
        )
        provenance["unfulfilled_claim"] = claim
        return (
            VisualRole.DIRECT_EVIDENCE,
            VisualSourceType.NO_VALID_VISUAL,
            20.0,
            FallbackStrategy.REVISION_REQUIRED,
            {},
            provenance,
        )

    def _audit_feasibility_for_text(
        self,
        text: str,
        role_hint: VisualRole,
        used_intervals: List[Tuple[int, float, float]],
    ) -> Tuple[VisualRole, VisualSourceType, float, Optional[FallbackStrategy], Dict[str, Any]]:
        """Audits feasibility for general text (hook, setup, payoff)."""
        cand = self._search_movie_direct(text, used_intervals)
        if cand and cand.get("retrieval_score", 0.0) >= 55.0:
            clip_ref = self._candidate_to_clip_ref(cand)
            used_intervals.append((cand["movie_number"], cand["start_seconds"], cand["end_seconds"]))
            return role_hint, VisualSourceType.MOVIE_DIRECT, min(92.0, cand["retrieval_score"]), None, clip_ref
        
        # Fallback to general Hogwarts ambience
        env_cand = self._search_movie_direct("Hogwarts students Great Hall castle", used_intervals)
        if env_cand:
            clip_ref = self._candidate_to_clip_ref(env_cand)
            return VisualRole.CONTEXTUAL_ENVIRONMENT, VisualSourceType.MOVIE_DIRECT, 70.0, FallbackStrategy.CONTEXTUAL_FALLBACK, clip_ref

        return role_hint, VisualSourceType.MOVIE_DIRECT, 60.0, None, {}

    # --------------------------------------------------------------------------
    # RETRIEVAL ADAPTERS & QUERY HELPERS
    # --------------------------------------------------------------------------

    def _search_movie_direct(
        self,
        query_text: str,
        used_intervals: List[Tuple[int, float, float]],
    ) -> Optional[Dict[str, Any]]:
        """Searches MovieRetrievalEngine candidates without rendering or downloading."""
        try:
            # Build mock beat dict for candidate searching
            chars = [c for c in KNOWN_CHARACTERS if re.search(r"\b" + re.escape(c) + r"\b", query_text, re.IGNORECASE)]
            beat = {
                "narration_text": query_text,
                "text": query_text,
                "characters": chars,
                "action": query_text,
            }
            cands = self.movie_engine.search_candidates_for_beat(beat)
            if not cands:
                return None

            for c in cands:
                self.movie_engine.expand_candidate_context(c)

            # Convert used_intervals from (movie, start, end) to format expected by rerank
            ranked = self.movie_engine.rerank_candidates(beat, cands, used_intervals=used_intervals)
            if ranked:
                top = ranked[0]
                # Synthesize retrieval_score if missing
                if "retrieval_score" not in top:
                    top["retrieval_score"] = top.get("total_score", top.get("score", 70.0))
                return top
        except Exception as e:
            logger.debug(f"[StoryboardPlanner] Movie search error for '{query_text[:40]}': {e}")
        return None

    def _search_cleared_artwork(self, claim: str) -> Optional[Dict[str, Any]]:
        """
        Checks FanArtRetrievalEngine / Vault for cleared illustrations.
        Requires both ARTIST_LICENSE_VERIFIED and COMMERCIAL_PRODUCTION_CLEARED.
        """
        try:
            # Check approved artwork registry directory if available
            app_dir = PROJECT_ROOT / "data" / "artworks" / "approved"
            if app_dir.exists():
                for art_file in app_dir.glob("*.json"):
                    try:
                        with open(art_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            # Check keyword overlap with claim
                            meta_text = f"{meta.get('title', '')} {meta.get('description', '')} {' '.join(meta.get('tags', []))}".lower()
                            claim_words = set(re.findall(r"[a-zA-Z]{4,}", claim.lower())) - {"harry", "potter", "scene", "novel"}
                            if claim_words and any(w in meta_text for w in claim_words):
                                if (
                                    meta.get("artist_license_status") == ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED.value
                                    and meta.get("commercial_clearance") == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_CLEARED.value
                                ):
                                    return {
                                        "is_cleared": True,
                                        "asset_id": meta.get("candidate_id", art_file.stem),
                                        "title": meta.get("title", ""),
                                        "creator": meta.get("creator", "Verified Artist"),
                                        "license": meta.get("license_name", "Public Domain / CC0"),
                                        "source_url": meta.get("source_url", ""),
                                        "is_official": meta.get("is_official", False),
                                        "characters": meta.get("characters", []),
                                        "actions": meta.get("actions", []),
                                        "objects": meta.get("objects", []),
                                    }
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"[StoryboardPlanner] Artwork search check failed: {e}")
        return None

    def _infer_framing_with_diversity(
        self,
        beat_dict: Dict[str, Any],
        recent_scales: List[ShotScale],
        default: ShotScale = ShotScale.MEDIUM_SHOT,
    ) -> ShotScale:
        """
        Infers natural shot scale preserving commit 37b1463 policy,
        while preventing repetitive loops (e.g. 3 consecutive CLOSE_UPs).
        """
        inferred = self.movie_engine.infer_target_shot_scale(beat_dict)
        if not inferred:
            inferred = default

        # Anti-repetition check: do not repeat CLOSE_UP 2+ times in a row unless explicitly forced
        if inferred == ShotScale.CLOSE_UP and len(recent_scales) >= 1 and recent_scales[-1] == ShotScale.CLOSE_UP:
            # Check if text specifically commands close-up
            text = str(beat_dict.get("narration_text", "")).lower()
            if not any(k in text for k in ("tears", "eyes widen", "shocked face", "look of horror")):
                inferred = ShotScale.MEDIUM_SHOT

        # Do not repeat identical shot scales 3 times in a row
        if len(recent_scales) >= 2 and recent_scales[-1] == inferred and recent_scales[-2] == inferred:
            if inferred == ShotScale.MEDIUM_SHOT:
                inferred = ShotScale.MEDIUM_WIDE
            elif inferred == ShotScale.MEDIUM_WIDE:
                inferred = ShotScale.MEDIUM_SHOT
            elif inferred == ShotScale.WIDE_SHOT:
                inferred = ShotScale.MEDIUM_WIDE

        return inferred

    def _candidate_to_clip_ref(self, cand: Dict[str, Any]) -> Dict[str, Any]:
        """Formats candidate movie match into clean clip reference."""
        m_num = cand.get("movie_number", 1)
        st = float(cand.get("start_seconds", 0.0))
        end = float(cand.get("end_seconds", st + 2.5))
        return {
            "movie_number": m_num,
            "scene_reference": f"Movie {m_num} @ {st:.1f}s-{end:.1f}s [{cand.get('text', '')[:40]}]",
            "start_seconds": st,
            "end_seconds": end,
            "characters": cand.get("characters", []),
            "actions": cand.get("actions", []),
            "objects": cand.get("objects", []),
        }

    def _detect_location(self, text: str) -> Optional[str]:
        t = text.lower()
        for loc in COMMON_LOCATIONS:
            if loc in t:
                return loc
        return None

    def _detect_character(self, text: str) -> Optional[str]:
        t = text.lower()
        for char in KEY_REACTION_CHARACTERS:
            if re.search(r"\b" + re.escape(char) + r"\b", t):
                return char
        return None

    def _extract_plan_components(
        self,
        plan: Union[DeepDiscoveryStoryPlan, Dict[str, Any], Any]
    ) -> Tuple[str, DiscoveryTier, DiscoveryStoryStructure, str, List[EvidencePoint], Optional[EvidencePoint], str, str, float]:
        """Extracts and normalizes narrative components from diverse input types."""
        if isinstance(plan, DeepDiscoveryStoryPlan):
            return (
                plan.topic_id or "disc_topic",
                plan.discovery_tier,
                plan.story_structure,
                plan.thesis,
                plan.evidence_points,
                plan.anchor_point,
                plan.insider_epiphany,
                plan.payoff_text,
                plan.expected_duration,
            )

        if isinstance(plan, dict):
            topic_id = plan.get("topic_id") or plan.get("id") or "disc_topic"
            tier_val = plan.get("discovery_tier", DiscoveryTier.DEEP_DISCOVERY.value)
            tier = DiscoveryTier(tier_val) if isinstance(tier_val, str) else tier_val
            struct_val = plan.get("story_structure", DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE.value)
            struct = DiscoveryStoryStructure(struct_val) if isinstance(struct_val, str) else struct_val
            thesis = plan.get("thesis") or plan.get("hook") or ""
            epiphany = plan.get("insider_epiphany") or ""
            payoff_text = plan.get("payoff_text") or plan.get("payoff") or ""
            expected_dur = float(plan.get("expected_duration") or plan.get("estimated_duration_sec") or 72.0)

            # Evidence points extraction
            ev_list: List[EvidencePoint] = []
            raw_ev = plan.get("evidence_points") or plan.get("evidence_points_json")
            if isinstance(raw_ev, str):
                try:
                    raw_ev = json.loads(raw_ev)
                except Exception:
                    raw_ev = []
            if isinstance(raw_ev, list):
                for item in raw_ev:
                    if isinstance(item, EvidencePoint):
                        ev_list.append(item)
                    elif isinstance(item, dict):
                        ev_list.append(EvidencePoint.from_dict(item))
                    elif isinstance(item, str):
                        ev_list.append(EvidencePoint(claim=item, evidence_route=EvidenceRoute.NOVEL_CANON.value, source_id="ev_raw", source_excerpt=""))

            # Fallback if no evidence points: create from claims or development
            if not ev_list:
                dev_text = plan.get("development") or plan.get("novel_fact_summary") or ""
                if dev_text:
                    sentences = [s.strip() for s in re.split(r"[.!?]", dev_text) if len(s.strip()) > 15]
                    for s_idx, s in enumerate(sentences[:4], start=1):
                        ev_list.append(EvidencePoint(
                            claim=s,
                            evidence_route=EvidenceRoute.NOVEL_CANON.value,
                            source_id=f"{topic_id}_claim_{s_idx}",
                            source_excerpt=s,
                        ))

            anchor_pt = None
            raw_anchor = plan.get("anchor_point") or plan.get("anchor_point_json")
            if isinstance(raw_anchor, str):
                try:
                    raw_anchor = json.loads(raw_anchor)
                except Exception:
                    raw_anchor = None
            if isinstance(raw_anchor, dict):
                anchor_pt = EvidencePoint.from_dict(raw_anchor)
            elif isinstance(raw_anchor, EvidencePoint):
                anchor_pt = raw_anchor

            return topic_id, tier, struct, thesis, ev_list, anchor_pt, epiphany, payoff_text, expected_dur

        # Generic object / HarryPotterScript / DiscoveryCandidate
        topic_id = getattr(plan, "id", None) or getattr(plan, "candidate_id", "disc_topic")
        thesis = getattr(plan, "thesis", None) or getattr(plan, "hook", "")
        epiphany = getattr(plan, "insider_epiphany", "")
        payoff_text = getattr(plan, "payoff", "") or getattr(plan, "payoff_text", "")
        expected_dur = float(getattr(plan, "expected_duration", 72.0) or 72.0)
        
        ev_list = []
        raw_ev = getattr(plan, "evidence_points_json", None)
        if raw_ev:
            try:
                items = json.loads(raw_ev)
                for it in items:
                    ev_list.append(EvidencePoint.from_dict(it))
            except Exception:
                pass

        if not ev_list:
            dev = getattr(plan, "development", "") or getattr(plan, "novel_fact_summary", "")
            if dev:
                for s_idx, s in enumerate([s.strip() for s in re.split(r"[.!?]", dev) if len(s.strip()) > 15][:4], start=1):
                    ev_list.append(EvidencePoint(
                        claim=s,
                        evidence_route=EvidenceRoute.NOVEL_CANON.value,
                        source_id=f"{topic_id}_claim_{s_idx}",
                        source_excerpt=s,
                    ))

        return topic_id, DiscoveryTier.DEEP_DISCOVERY, DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE, thesis, ev_list, None, epiphany, payoff_text, expected_dur
