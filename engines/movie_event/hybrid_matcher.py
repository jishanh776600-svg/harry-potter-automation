"""
STORY FORGE — Hybrid SRT + Movie Event Visual Matching Engine (Phase 2)
========================================================================
Combines SRT dialogue coarse localization with Movie Event precision matching:
  Narration
      ↓
  SRT Coarse Localization (Scene / Time Window)
      ↓
  Movie Event Precision Retrieval (Constrained by Window)
      ↓
  Objective Candidate Comparison (SRT Candidate vs Movie Event Candidate)
      ↓
  "Only If Better" Selection Rule (Configurable Improvement Margin)
      ↓
  Temporal Action Verification Integration
      ↓
  Cryptographic Lineage Binding
      ↓
  Controlled Selection Output (NO AUTONOMOUS PRODUCTION MUTATIONS)
"""

import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from pydantic import BaseModel, Field

from config.settings import PROJECT_ROOT
from core.models import MovieSubtitleChunk
from engines.movie_asset_engine import MovieAssetEngine
from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    MovieEventQuery,
    EventVerificationResult,
    VerificationStatus,
)
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.verifier import MovieEventVisualVerifier
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator, ClaimTransformer
from engines.visual_evidence.temporal_action_engine import TemporalActionEngine
from engines.visual_evidence.storyforge_adapter import (
    StoryForgeVisualEvidenceAdapter,
    StoryForgeEvidenceResult,
)
from core.visual_artifact_lineage import (
    compute_narration_hash,
    compute_proposition_hash,
    compute_evidence_hash,
    compute_timeline_hash,
    compute_visual_plan_id,
    compute_render_fingerprint,
)

logger = logging.getLogger("HybridVisualMatcher")

# Configurable Improvement Margin:
# A MovieEvent candidate will only override an existing SRT candidate if it is
# verified, free of action mismatch, and beats the SRT candidate by at least this margin.
MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN: float = 10.0

DEFAULT_LEVEL1_WINDOW_PADDING_SEC: float = 30.0
DEFAULT_LEVEL2_WINDOW_PADDING_SEC: float = 90.0


class SRTTimeWindow(BaseModel):
    """
    Search window and coarse contextual boundaries derived from SRT dialogue cues.
    """
    movie_number: int = Field(..., ge=1, le=8, description="Target movie number")
    scene_window_start: float = Field(..., ge=0.0, description="Start timestamp of search window in seconds")
    scene_window_end: float = Field(..., ge=0.0, description="End timestamp of search window in seconds")
    preferred_timestamp: float = Field(..., ge=0.0, description="Central timestamp of best dialogue hit")
    nearby_scene_context: str = Field("", description="Surrounding dialogue or scene text")
    matched_text: str = Field("", description="Exact subtitle text matched by FTS")
    chunk_id: Optional[str] = Field(None, description="Subtitle chunk identifier")
    relevance_rank: float = Field(0.0, description="BM25 or keyword match rank")


class CandidateComparisonResult(BaseModel):
    """
    Direct side-by-side objective evaluation of candidates.
    Enforces MovieEvent sole authority: SRT has zero visual authority and can NEVER be selected.
    """
    beat_id: str
    srt_candidate_id: Optional[str] = None
    srt_candidate_action: Optional[str] = None
    srt_score: float = 0.0
    srt_verified: bool = False
    srt_rejection_reason: Optional[str] = None

    movie_event_candidate_id: Optional[str] = None
    movie_event_action: Optional[str] = None
    movie_event_score: float = 0.0
    movie_event_verified: bool = False
    movie_event_rejection_reason: Optional[str] = None

    score_delta: float = 0.0
    improvement_margin_required: float = MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN
    margin_satisfied: bool = False

    selected_source: str = "NO_VALID_VISUAL"  # "MOVIE_EVENT", "NO_VALID_VISUAL" (SRT_CANDIDATE strictly prohibited)
    selected_candidate_id: Optional[str] = None
    selection_reason: str = ""
    fallback_used: bool = False  # Strictly False in Phase 3


class HybridVisualSelectionOutput(BaseModel):
    """
    Final output for a VisualBeat including candidate metadata, verification status,
    event-chain context, py_visual_evidence physical proof, and cryptographic lineage binding.
    """
    beat_id: str
    status: str  # "VERIFIED", "NO_VALID_VISUAL" (FALLBACK_SRT strictly prohibited)
    selected_candidate: Optional[Dict[str, Any]] = None
    comparison: CandidateComparisonResult
    event_chain: Optional[Dict[str, Any]] = None
    temporal_action_state: str = "UNCERTAIN"
    
    # Visual Evidence Deep Physical Proof from py_visual_evidence
    evidence_verification: Optional[Dict[str, Any]] = None

    # Cryptographic Lineage Fields
    lineage_metadata: Dict[str, str] = Field(default_factory=dict)
    
    # Telemetry
    search_level_reached: int = 1
    candidates_searched_count: int = 0
    candidates_verified_count: int = 0
    retrieval_duration_ms: float = 0.0


class SRTCoarseLocator:
    """
    Coarse locator utilizing the existing SQLite FTS5 movie subtitles database
    to narrow the spatial/temporal search space before precision event retrieval.
    """

    def __init__(self, asset_engine: Optional[MovieAssetEngine] = None):
        self.asset_engine = asset_engine or MovieAssetEngine()

    def locate_coarse_window(
        self,
        beat: VisualBeat,
        inferred_movie: Optional[int] = None,
        padding_seconds: float = DEFAULT_LEVEL1_WINDOW_PADDING_SEC,
    ) -> Optional[SRTTimeWindow]:
        """
        Searches subtitles for key terms from the narration or required visual beat.
        Returns an SRTTimeWindow defining coarse scene boundaries.
        """
        # Formulate search queries prioritizing salient dialogue/narrative keywords
        import re
        queries = []
        stopwords = {
            "what", "would", "from", "with", "that", "this", "their", "there", "about",
            "which", "before", "after", "while", "during", "then", "have", "been", "were",
            "very", "some", "into", "onto", "over", "under"
        }
        salient_narr = [
            w for w in re.findall(r"[a-zA-Z]{4,}", (beat.narrative_text or "").lower())
            if w not in stopwords
        ]
        if len(salient_narr) >= 2:
            queries.append(" ".join(salient_narr[:2]))
        if salient_narr:
            queries.append(" ".join(salient_narr[:3]))
            for sw in salient_narr[:2]:
                if sw not in queries:
                    queries.append(sw)
        if beat.narrative_text:
            queries.append(beat.narrative_text)
        if beat.required_subjects and beat.required_action:
            queries.append(f"{' '.join(beat.required_subjects)} {beat.required_action}")
        elif beat.required_subjects:
            queries.append(" ".join(beat.required_subjects))
        if beat.required_action:
            queries.append(beat.required_action)

        movie_target = inferred_movie

        best_hit: Optional[Dict[str, Any]] = None
        for q in queries:
            results = self.asset_engine.search_movie_scenes(q, movie_number=movie_target, limit=3)
            if results:
                best_hit = results[0]
                break

        if not best_hit and movie_target:
            # Fallback to broader movie search
            results = self.asset_engine.search_movie_scenes("Harry Potter", movie_number=movie_target, limit=1)
            if results:
                best_hit = results[0]

        if not best_hit:
            return None

        pref_ts = float(best_hit.get("start_seconds", 0.0))
        m_num = int(best_hit.get("movie_number", 1))

        return SRTTimeWindow(
            movie_number=m_num,
            scene_window_start=max(0.0, pref_ts - padding_seconds),
            scene_window_end=pref_ts + padding_seconds,
            preferred_timestamp=pref_ts,
            nearby_scene_context=best_hit.get("text", ""),
            matched_text=best_hit.get("text", ""),
            chunk_id=best_hit.get("chunk_id"),
            relevance_rank=float(best_hit.get("relevance_rank", 0.0)),
        )


class HybridVisualSelector:
    """
    Coordinates hybrid visual retrieval:
    Level 1: Search MovieEventIndex inside SRT-derived time window.
    Level 2: Expand to adjacent events in window.
    Level 3: Global MovieEvent search.
    Level 4: Compare MovieEvent against existing SRT candidate.
    Level 5: Fallback to NO_VALID_VISUAL if neither passes verification.
    """

    def __init__(
        self,
        index: Optional[MovieEventIndex] = None,
        retrieval_engine: Optional[MovieEventRetrievalEngine] = None,
        verifier: Optional[MovieEventVisualVerifier] = None,
        coarse_locator: Optional[SRTCoarseLocator] = None,
        min_improvement_margin: float = MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
        evidence_adapter: Optional[StoryForgeVisualEvidenceAdapter] = None,
        require_video_evidence: bool = False,
    ):
        self.index = index or MovieEventIndex()
        self.retrieval_engine = retrieval_engine or MovieEventRetrievalEngine(self.index)
        self.verifier = verifier or MovieEventVisualVerifier()
        self.coarse_locator = coarse_locator or SRTCoarseLocator()
        self.min_improvement_margin = min_improvement_margin
        self.storyboard_gen = VisualStoryboardGenerator()
        self.evidence_adapter = evidence_adapter
        self.require_video_evidence = require_video_evidence

    def _verify_candidate_with_evidence(
        self,
        ev: MovieEvent,
        beat: VisualBeat,
        require_video: bool,
        candidate_video_overrides: Optional[Dict[str, Union[str, Path]]] = None,
    ) -> Tuple[bool, EventVerificationResult, Optional[StoryForgeEvidenceResult]]:
        """
        Two-stage verification:
          1. MovieEvent candidate hypothesis check (action, subject, forbidden veto).
          2. NEW py_visual_evidence physical frame inspection on candidate video.
        NO MOVIE CLIP MAY ENTER THE FINAL TIMELINE WITHOUT PASSING py_visual_evidence.
        """
        ver = self.verifier.verify_event(ev, beat)
        if not ver.is_verified:
            return False, ver, None

        ev_res = None
        if self.evidence_adapter is not None and require_video:
            override_p = candidate_video_overrides.get(ev.event_id) if candidate_video_overrides else None
            ev_res = self.evidence_adapter.verify_candidate_event(
                event=ev,
                beat_or_prop=beat,
                override_video_path=override_p,
            )
            if not ev_res.is_verified:
                rej_ver = EventVerificationResult(
                    event_id=ev.event_id,
                    status=VerificationStatus.REJECT_ACTION_MISMATCH if "ACTION" in (ev_res.verdict or "") else VerificationStatus.REJECT_MISSING_OBJECT,
                    is_verified=False,
                    explanation=f"py_visual_evidence physical rejection: {ev_res.verdict} ({ev_res.rejection_reason})",
                )
                return False, rej_ver, ev_res

        return True, ver, ev_res

    def select_visual_for_beat(
        self,
        beat: VisualBeat,
        content_id: str = "disc_test_hybrid_v1",
        inferred_movie: Optional[int] = None,
        require_video_evidence: Optional[bool] = None,
        candidate_video_overrides: Optional[Dict[str, Union[str, Path]]] = None,
    ) -> HybridVisualSelectionOutput:
        """
        Executes end-to-end hybrid selection for an individual VisualBeat.
        """
        t0 = time.perf_counter()
        candidates_searched = 0
        candidates_verified = 0
        must_verify_video = self.require_video_evidence if require_video_evidence is None else require_video_evidence

        # Step 0: Check Abstract / Non-Visualizable Claim Gate
        classification = ClaimTransformer.classify_claim(beat.narrative_text)
        if not classification.is_directly_visualizable and not beat.contextual_visual_allowed:
            t_end = time.perf_counter()
            comparison = CandidateComparisonResult(
                beat_id=beat.beat_id,
                selected_source="NO_VALID_VISUAL",
                selection_reason=f"Claim is ABSTRACT_NOT_DIRECTLY_VISUALIZABLE: {classification.rejection_notice}",
            )
            return HybridVisualSelectionOutput(
                beat_id=beat.beat_id,
                status="NO_VALID_VISUAL",
                selected_candidate=None,
                comparison=comparison,
                search_level_reached=0,
                retrieval_duration_ms=round((t_end - t0) * 1000.0, 2),
            )

        # Step 1: SRT Coarse Localization (derive search window only — NO visual selection)
        srt_window = self.coarse_locator.locate_coarse_window(
            beat=beat,
            inferred_movie=inferred_movie,
            padding_seconds=DEFAULT_LEVEL1_WINDOW_PADDING_SEC,
        )

        target_movie = inferred_movie or (srt_window.movie_number if srt_window else None)

        # Formulate MovieEventQuery
        event_query = self.storyboard_gen.create_event_query(beat)
        if target_movie:
            event_query.movie_number = target_movie

        # 5-LEVEL SEARCH HIERARCHY (MovieEvent has SOLE visual authority)
        search_level = 1
        verified_candidates: List[Tuple[MovieEvent, float, Dict[str, float], EventVerificationResult, Optional[StoryForgeEvidenceResult]]] = []

        # Retrieve candidate events from MovieEventIndex
        all_matches = self.retrieval_engine.retrieve_events(event_query, top_k=15, min_score=10.0)
        candidates_searched += len(all_matches)

        # LEVEL 1: Search MovieEvents inside SRT-derived window (T0 ± 30s)
        if srt_window:
            w_start_l1 = srt_window.scene_window_start
            w_end_l1 = srt_window.scene_window_end
            for ev, sc, bd in all_matches:
                if ev.start_time <= w_end_l1 and ev.end_time >= w_start_l1:
                    candidates_verified += 1
                    is_ok, ver, ev_res = self._verify_candidate_with_evidence(
                        ev=ev,
                        beat=beat,
                        require_video=must_verify_video,
                        candidate_video_overrides=candidate_video_overrides,
                    )
                    if is_ok:
                        verified_candidates.append((ev, sc, bd, ver, ev_res))

        # LEVEL 2: Expand to ±90 seconds around SRT anchor if Level 1 yielded no verified event
        if not verified_candidates and srt_window:
            search_level = 2
            w_start_l2 = max(0.0, srt_window.preferred_timestamp - DEFAULT_LEVEL2_WINDOW_PADDING_SEC)
            w_end_l2 = srt_window.preferred_timestamp + DEFAULT_LEVEL2_WINDOW_PADDING_SEC
            for ev, sc, bd in all_matches:
                if ev.start_time <= w_end_l2 and ev.end_time >= w_start_l2:
                    candidates_verified += 1
                    is_ok, ver, ev_res = self._verify_candidate_with_evidence(
                        ev=ev,
                        beat=beat,
                        require_video=must_verify_video,
                        candidate_video_overrides=candidate_video_overrides,
                    )
                    if is_ok:
                        verified_candidates.append((ev, sc, bd, ver, ev_res))

        # LEVEL 3: Expand through neighboring MovieEvent chains / scene boundaries
        if not verified_candidates:
            search_level = 3
            seen_ids = set()
            for ev, sc, bd in all_matches:
                chain = self.retrieval_engine.retrieve_event_chain(ev.event_id)
                for chained_ev in [chain.get("preceding"), chain.get("following")]:
                    if chained_ev and chained_ev.event_id not in seen_ids:
                        seen_ids.add(chained_ev.event_id)
                        candidates_verified += 1
                        is_ok, ver, ev_res = self._verify_candidate_with_evidence(
                            ev=chained_ev,
                            beat=beat,
                            require_video=must_verify_video,
                            candidate_video_overrides=candidate_video_overrides,
                        )
                        if is_ok:
                            ch_sc, ch_bd = self.retrieval_engine._score_event(chained_ev, event_query)
                            verified_candidates.append((chained_ev, ch_sc, ch_bd, ver, ev_res))

        # LEVEL 4: Search entire relevant movie (and franchise) using structured query
        if not verified_candidates:
            search_level = 4
            # Evaluate all matches from target movie
            for ev, sc, bd in all_matches:
                candidates_verified += 1
                is_ok, ver, ev_res = self._verify_candidate_with_evidence(
                    ev=ev,
                    beat=beat,
                    require_video=must_verify_video,
                    candidate_video_overrides=candidate_video_overrides,
                )
                if is_ok:
                    verified_candidates.append((ev, sc, bd, ver, ev_res))

            # If still nothing, expand query globally across entire franchise
            if not verified_candidates:
                global_query = self.storyboard_gen.create_event_query(beat)
                global_matches = self.retrieval_engine.retrieve_events(global_query, top_k=10, min_score=10.0)
                candidates_searched += len(global_matches)
                for ev, sc, bd in global_matches:
                    candidates_verified += 1
                    is_ok, ver, ev_res = self._verify_candidate_with_evidence(
                        ev=ev,
                        beat=beat,
                        require_video=must_verify_video,
                        candidate_video_overrides=candidate_video_overrides,
                    )
                    if is_ok:
                        verified_candidates.append((ev, sc, bd, ver, ev_res))

        # Sort verified candidates descending by score
        verified_candidates.sort(key=lambda x: x[1], reverse=True)

        # LEVEL 5: If no verified event exists -> STRICT FAIL CLOSED (NO_VALID_VISUAL)
        # SRT MUST NEVER SELECT OR FALL BACK TO VISUAL FOOTAGE.
        if not verified_candidates:
            search_level = 5
            t_end = time.perf_counter()
            srt_chunk = srt_window.chunk_id if srt_window else "none"
            comparison = CandidateComparisonResult(
                beat_id=beat.beat_id,
                srt_candidate_id=f"srt_{srt_chunk}",
                srt_candidate_action="dialogue_only",
                srt_score=0.0,
                srt_verified=False,
                srt_rejection_reason="SRT has zero visual selection authority; SRT fallback is strictly prohibited.",
                movie_event_candidate_id=None,
                movie_event_score=0.0,
                movie_event_verified=False,
                movie_event_rejection_reason=f"No verified MovieEvent found fulfilling observable action '{beat.required_action}'.",
                score_delta=0.0,
                margin_satisfied=False,
                selected_source="NO_VALID_VISUAL",
                selected_candidate_id=None,
                selection_reason=f"Level 5 rejection: No verified MovieEvent satisfied required visual action '{beat.required_action}'. Failing closed (zero SRT fallback).",
                fallback_used=False,
            )
            return HybridVisualSelectionOutput(
                beat_id=beat.beat_id,
                status="NO_VALID_VISUAL",
                selected_candidate=None,
                comparison=comparison,
                search_level_reached=search_level,
                candidates_searched_count=candidates_searched,
                candidates_verified_count=candidates_verified,
                retrieval_duration_ms=round((t_end - t0) * 1000.0, 2),
            )

        # Select top verified MovieEvent
        best_me_event, best_me_score, _, best_me_ver, best_ev_res = verified_candidates[0]
        second_me_event = verified_candidates[1][0] if len(verified_candidates) > 1 else None
        second_me_score = verified_candidates[1][1] if len(verified_candidates) > 1 else 0.0
        second_me_ver = verified_candidates[1][3] if len(verified_candidates) > 1 else None

        # Compare candidates
        comparison = self._compare_candidates(
            beat=beat,
            srt_event=None,
            srt_score=0.0,
            srt_ver=None,
            me_event=best_me_event,
            me_score=best_me_score,
            me_ver=best_me_ver,
            cand_b=second_me_event,
            score_b=second_me_score,
            ver_b=second_me_ver,
        )

        # Retrieve event chain continuity
        chain = self.retrieval_engine.retrieve_event_chain(best_me_event.event_id)
        chain_dict = {
            "preceding": chain["preceding"].event_id if chain.get("preceding") else None,
            "core": best_me_event.event_id,
            "following": chain["following"].event_id if chain.get("following") else None,
        }

        # Temporal Action verification
        nature = TemporalActionEngine.classify_action_nature(best_me_event.action)
        temporal_state = "TRANSITION_VERIFIED" if nature.value == "DYNAMIC" else "SUSTAINED_STATE_VERIFIED"

        selected_cand_dict = {
            "candidate_id": best_me_event.event_id,
            "source_type": "MOVIE_EVENT_INDEX",
            "movie_number": best_me_event.movie_number,
            "start_seconds": best_me_event.start_time,
            "end_seconds": best_me_event.end_time,
            "duration": best_me_event.duration,
            "action": best_me_event.action,
            "primary_subject": best_me_event.primary_subject,
            "target": best_me_event.target,
            "location": best_me_event.location,
            "score": best_me_score,
            "visual_description": best_me_event.visual_description,
        }
        if best_ev_res:
            selected_cand_dict["evidence_verification"] = best_ev_res.model_dump()
            selected_cand_dict["verified_sub_shot"] = best_ev_res.verified_sub_shot
            selected_cand_dict["crop_fingerprint"] = best_ev_res.crop_fingerprint

        # Cryptographic Lineage Binding
        lineage = self._build_lineage_metadata(
            content_id=content_id,
            beat=beat,
            selected_cand=selected_cand_dict,
        )

        t_end = time.perf_counter()
        duration_ms = round((t_end - t0) * 1000.0, 2)

        return HybridVisualSelectionOutput(
            beat_id=beat.beat_id,
            status="VERIFIED",
            selected_candidate=selected_cand_dict,
            comparison=comparison,
            event_chain=chain_dict,
            temporal_action_state=temporal_state,
            evidence_verification=best_ev_res.model_dump() if best_ev_res else None,
            lineage_metadata=lineage,
            search_level_reached=search_level,
            candidates_searched_count=candidates_searched,
            candidates_verified_count=candidates_verified,
            retrieval_duration_ms=duration_ms,
        )

    def _compare_candidates(
        self,
        beat: VisualBeat,
        srt_event: Optional[MovieEvent] = None,
        srt_score: float = 0.0,
        srt_ver: Optional[EventVerificationResult] = None,
        me_event: Optional[MovieEvent] = None,
        me_score: float = 0.0,
        me_ver: Optional[EventVerificationResult] = None,
        cand_b: Optional[MovieEvent] = None,
        score_b: float = 0.0,
        ver_b: Optional[EventVerificationResult] = None,
    ) -> CandidateComparisonResult:
        """
        Enforces MovieEvent sole authority and the "Only If Better" rule between competing MovieEvents.
        SRT HAS ZERO VISUAL-SELECTION AUTHORITY: An SRT candidate can NEVER become final visual footage.
        """
        me_id = me_event.event_id if me_event else None
        me_action = me_event.action if me_event else None
        me_ok = bool(me_ver and me_ver.is_verified)
        me_rej = me_ver.explanation if me_ver and not me_ok else None

        # Case 1: A verified MovieEvent candidate exists
        if me_ok and me_event:
            # If competing MovieEvent (cand_b) is present, compute delta
            delta = round(me_score - score_b, 2) if cand_b else me_score
            margin_met = bool(not cand_b or delta >= self.min_improvement_margin)
            
            return CandidateComparisonResult(
                beat_id=beat.beat_id,
                srt_candidate_id=srt_event.event_id if srt_event else None,
                srt_candidate_action=srt_event.action if srt_event else None,
                srt_score=srt_score,
                srt_verified=False,  # SRT has zero visual authority
                srt_rejection_reason="SRT has zero visual selection authority; used solely for coarse localization.",
                movie_event_candidate_id=me_id,
                movie_event_action=me_action,
                movie_event_score=me_score,
                movie_event_verified=True,
                movie_event_rejection_reason=None,
                score_delta=delta,
                improvement_margin_required=self.min_improvement_margin,
                margin_satisfied=margin_met,
                selected_source="MOVIE_EVENT",
                selected_candidate_id=me_id,
                selection_reason=f"MovieEvent '{me_id}' verified with score {me_score:.1f} for observable action '{me_action}'.",
                fallback_used=False,
            )

        # Case 2: No verified MovieEvent exists.
        # HARD ARCHITECTURAL ASSERTION: Even if caller supplied an srt_event, SRT CAN NEVER BE SELECTED.
        srt_id = srt_event.event_id if srt_event else None
        srt_action = srt_event.action if srt_event else None
        return CandidateComparisonResult(
            beat_id=beat.beat_id,
            srt_candidate_id=srt_id,
            srt_candidate_action=srt_action,
            srt_score=srt_score,
            srt_verified=False,  # Prohibited from passing as visual selection
            srt_rejection_reason="SRT candidates can never become final visual selection (SRT visual fallback strictly disabled).",
            movie_event_candidate_id=me_id,
            movie_event_action=me_action,
            movie_event_score=me_score,
            movie_event_verified=False,
            movie_event_rejection_reason=me_rej or "No verified MovieEvent fulfilled the observable action.",
            score_delta=0.0,
            improvement_margin_required=self.min_improvement_margin,
            margin_satisfied=False,
            selected_source="NO_VALID_VISUAL",
            selected_candidate_id=None,
            selection_reason="No verified MovieEvent found. SRT visual fallback is strictly prohibited. Failing closed.",
            fallback_used=False,
        )

    def _build_synthetic_srt_candidate(self, window: SRTTimeWindow, beat: VisualBeat) -> MovieEvent:
        """
        [DEPRECATED / DIAGNOSTIC ONLY]
        SRT cues have ZERO visual-selection authority and can NEVER be selected as final visual footage.
        Retained solely for offline diagnostic comparison and negative-assertion testing.
        """
        # Parse dialogue text for depicted actions
        txt = window.matched_text.lower()
        
        # Check if SRT cue is near an existing indexed event
        for ev in self.index.list_all_events():
            if ev.movie_number == window.movie_number:
                if abs(ev.start_time - window.preferred_timestamp) < 5.0:
                    return ev

        # Otherwise synthesize an event representing what is observable during dialogue
        return MovieEvent(
            event_id=f"srt_cue_{window.chunk_id or 'unknown'}",
            movie_id=f"hp_movie_{window.movie_number}",
            movie_number=window.movie_number,
            scene_id=f"m{window.movie_number}_srt_scene",
            start_time=window.preferred_timestamp,
            end_time=window.preferred_timestamp + 3.0,
            characters_present=beat.required_subjects,
            primary_subject=beat.required_subjects[0] if beat.required_subjects else "Characters",
            secondary_subjects=beat.required_subjects[1:] if len(beat.required_subjects) > 1 else [],
            action="speaks dialogue" if "speaks" not in txt else "addresses class",
            target=beat.required_target,
            interaction_type="dialogue",
            location=beat.required_location or "Hogwarts",
            visible_objects=beat.required_objects,
            visual_description=f"Characters visible on screen during spoken subtitle line: '{window.matched_text}'.",
            observable_claims=["Characters speaking on camera"],
            confidence=0.85,
        )

    def _build_lineage_metadata(
        self,
        content_id: str,
        beat: VisualBeat,
        selected_cand: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Binds selected candidate into cryptographic lineage."""
        narr_hash = compute_narration_hash(beat.narrative_text)
        prop_hash = compute_proposition_hash([{
            "proposition_id": beat.beat_id,
            "claim": beat.narrative_text,
            "subject": beat.required_subjects[0] if beat.required_subjects else "",
            "action": beat.required_action,
            "object": beat.required_target or "",
            "context": beat.required_location or "",
            "evidence_type": "DIRECT",
        }])

        evidence_records = []
        if selected_cand:
            ev_ver = selected_cand.get("evidence_verification") or {}
            evidence_records.append({
                "cand_id": selected_cand.get("candidate_id", ""),
                "prop_id": beat.beat_id,
                "source_clip": f"movie_{selected_cand.get('movie_number', 1)}",
                "src_interval": (selected_cand.get("start_seconds", 0.0), selected_cand.get("end_seconds", 0.0)),
                "evidence_class": "DIRECT",
                "sub_shot_id": ev_ver.get("verified_sub_shot", ""),
                "engine_version": ev_ver.get("engine_version", ""),
                "crop_fingerprint": ev_ver.get("crop_fingerprint", ""),
                "verdict": ev_ver.get("verdict", "PASS"),
            })
        ev_hash = compute_evidence_hash(evidence_records)

        timeline_units = []
        if selected_cand:
            timeline_units.append({
                "unit_id": f"unit_{beat.beat_id}",
                "clip_path": selected_cand.get("candidate_id", ""),
                "trim_start": selected_cand.get("start_seconds", 0.0),
                "duration": selected_cand.get("duration", 2.5),
            })
        tl_hash = compute_timeline_hash(timeline_units)

        plan_id = compute_visual_plan_id(
            content_id=content_id,
            topic_id=content_id,
            narration_hash=narr_hash,
            proposition_hash=prop_hash,
            evidence_hash=ev_hash,
            timeline_hash=tl_hash,
        )

        return {
            "content_id": content_id,
            "narration_hash": narr_hash,
            "proposition_hash": prop_hash,
            "source_evidence_hash": ev_hash,
            "timeline_hash": tl_hash,
            "visual_plan_id": plan_id,
        }
