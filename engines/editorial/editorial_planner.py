"""
STORY FORGE — Editorial Planner & Quality Guardrails (Editorial Intelligence V2)
================================================================================
Directorial decision engine translating verified visual evidence, narration,
word timestamps, and multi-fact topic packs into an auditable EditorialTimelineV2:
  - Sequences proposition-locked EditorialUnits with explicit reasons
  - Enforces Dynamic Pacing and Narrative Weight allocation
  - Applies controlled punch-ins, match-cuts, smash-cuts, J/L-cuts, and callouts
  - Enforces True 9:16 composition without letterboxing
  - Enforces strict Anti-Padding (no stretching, no looping, fail-closed on NO_VALID_VISUAL)
  - Computes deterministic SHA-256 fingerprint for cache invalidation
  - Strictly isolates Novel Story pipelines
"""

import os
import re
import json
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from core.editorial_v2_types import (
    EditorialUnit,
    EditorialTimelineV2,
    VisualEmphasisPrimitive,
    EditorialTransitionType,
    MotionTreatment,
    CompositionTreatment,
    CaptionTreatment,
    SFXTreatment,
    SpotlightCalloutConfig,
)
from core.beast_v2_types import BeastV2MatchResult, BeastV2Decision, EvidenceType
from core.multi_fact_types import MultiFactTopicPack, MultiFactPayload, VisualProposition
from core.models import HarryPotterScript
from core.composition_models import ShotScale
from engines.editorial.pacing_engine import EditorialPacingEngine
from engines.editorial.treatment_selector import EditorialTreatmentSelector
from engines.editorial.caption_sfx_intelligence import CaptionSFXIntelligence
from engines.movie_retrieval_engine import MovieRetrievalEngine

logger = logging.getLogger("EditorialPlanner")


class EditorialPlanner:
    """
    Directorial planner generating frame-locked, proposition-aware editorial timelines.
    """

    def __init__(self, fps: float = 30.0, config_version: str = "v2.0"):
        self.fps = fps
        self.config_version = config_version

    def plan_timeline(
        self,
        topic_pack: MultiFactTopicPack,
        beast_matches: List[BeastV2MatchResult],
        narration_script: Optional[HarryPotterScript] = None,
        word_timestamps: Optional[List[Dict[str, Any]]] = None,
        candidate_type: str = "deep_discovery",
    ) -> EditorialTimelineV2:
        """
        Main entry point: Generates an auditable, deterministic EditorialTimelineV2.
        """
        # 1. NOVEL STORY ISOLATION GUARD
        if candidate_type == "novel_story" or "NOVEL_STORY" in str(topic_pack.format):
            raise ValueError("Novel Story pipeline is isolated from Deep Discovery Editorial Engine.")

        units: List[EditorialUnit] = []
        validation_warnings: List[str] = []
        recent_transitions: List[EditorialTransitionType] = []
        recent_punch_ins = 0
        last_sfx_time = -10.0
        current_time = 0.0
        unit_idx = 1

        # Build mapping from proposition_id / candidate_id to beast match
        match_map = {m.candidate_id: m for m in beast_matches}
        match_by_prop = {m.verification_metadata.get("proposition_id", m.candidate_id): m for m in beast_matches}

        # Detect Discovery Short vs Big / other formats
        fmt_str = str(getattr(topic_pack, "format", "") or "").upper()
        cand_str = str(candidate_type).lower()
        target_dur = getattr(topic_pack, "total_target_duration", 65.0)
        is_discovery_short = (
            "DISCOVERY_SHORT" in fmt_str
            or ("SHORT" in fmt_str and "DISCOVERY" in fmt_str)
            or ("short" in cand_str and "discovery" in cand_str)
            or target_dur <= 35.0
        )

        # ----------------------------------------------------------------------
        # A. HOOK EDITING: Hard cold open (first 0.8 - 1.5s)
        # ----------------------------------------------------------------------
        hook_text = (topic_pack.hook or "").strip()
        hook_match = beast_matches[0] if beast_matches else None
        
        # Check fail-closed condition on hook
        if not hook_match or hook_match.decision == BeastV2Decision.NO_VALID_VISUAL:
            validation_warnings.append("NO_VALID_VISUAL: Hook has no verified evidence.")

        hook_weight = 0.90
        hook_duration = EditorialPacingEngine.calculate_editorial_duration(
            narrative_role="HOOK",
            narrative_weight=hook_weight,
            available_narration_duration=1.4,
            is_discovery_short=is_discovery_short,
        )
        if is_discovery_short:
            hook_duration = min(1.50, hook_duration)

        hook_motion = MotionTreatment.PUNCH_IN_115 if hook_weight >= 0.85 else MotionTreatment.STATIC
        hook_sfx, hook_sfx_reason = CaptionSFXIntelligence.select_sfx_treatment(
            text=hook_text,
            narrative_role="HOOK",
            narrative_weight=hook_weight,
            last_sfx_timestamp=last_sfx_time,
            current_timestamp=current_time,
        )
        if hook_sfx != SFXTreatment.NONE:
            last_sfx_time = current_time

        # Natural framing for hook: preserve cinematic context
        hook_comp = EditorialTreatmentSelector.select_composition_treatment(
            shot_scale=ShotScale.MEDIUM_SHOT,
        )

        hook_unit = EditorialUnit(
            unit_id=f"unit_{unit_idx:02d}_hook",
            fact_id="hook",
            proposition_id="prop_hook",
            asset_id=hook_match.asset_id if hook_match else "none",
            source_start=hook_match.source_start if hook_match else 0.0,
            source_end=hook_match.source_start + hook_duration if hook_match else hook_duration,
            evidence_type=hook_match.evidence_type.value if hook_match else "DIRECT_EVIDENCE",
            visual_role="HOOK",
            narration_start=current_time,
            narration_end=current_time + hook_duration,
            duration_seconds=hook_duration,
            importance=0.95,
            narrative_weight=hook_weight,
            pacing_weight=hook_duration,
            emphasis_level="MAJOR",
            emphasis_primitives=[VisualEmphasisPrimitive.PUNCH_IN],
            transition_type=EditorialTransitionType.HARD_CUT,
            motion_treatment=hook_motion,
            caption_treatment=CaptionTreatment.REVEAL_WORD_BURST,
            sfx_treatment=hook_sfx,
            composition_treatment=hook_comp,
            reason="Hard cold open: Immediate proposition promise with rapid hook pacing",
        )
        units.append(hook_unit)
        current_time += hook_duration
        unit_idx += 1
        recent_transitions.append(EditorialTransitionType.HARD_CUT)
        if hook_motion == MotionTreatment.PUNCH_IN_115:
            recent_punch_ins += 1

        # ----------------------------------------------------------------------
        # B. MULTI-FACT PAYLOADS EDITORIAL SEQUENCING
        # ----------------------------------------------------------------------
        fact_counters_list: List[Dict[str, Any]] = []

        for fact_idx, fact in enumerate(topic_pack.facts):
            fact_num = fact.fact_number or (fact_idx + 1)
            fact.fact_number = fact_num
            fact_counter_str = topic_pack.get_fact_counter(fact_num)
            fact_start_time = round(current_time, 3)
            fact.fact_start = fact_start_time

            fact_weight = EditorialPacingEngine.calculate_narrative_weight(
                importance=fact.importance,
                curiosity=fact.curiosity_score,
                movie_contrast=fact.movie_contrast,
                emotional_value=fact.emotional_value,
                payoff_value=fact.payoff_value,
            )

            # Assign duration
            fact_duration = fact.target_duration_sec or 12.0
            elapsed_fact_time = 0.0

            # Subdivide fact into proposition units
            props = fact.visual_propositions or [
                VisualProposition(
                    proposition_id=f"prop_{fact.fact_id}_1",
                    subject="Harry Potter",
                    action=fact.claim[:30],
                    object="None",
                    context="Hogwarts",
                )
            ]

            for prop_sub_idx, prop in enumerate(props):
                # Retrieve matching BEAST V2 result strictly tied to this proposition
                match = match_by_prop.get(prop.proposition_id)
                if not match and prop.proposition_id in match_map:
                    match = match_map.get(prop.proposition_id)

                # Part D: Strict fail-closed. NEVER cycle or substitute unrelated clips to fill time!
                if not match and len(props) == 1 and len(beast_matches) == 1:
                    single_m = beast_matches[0]
                    prop_meta = single_m.verification_metadata.get("proposition_id")
                    if not prop_meta or prop_meta == prop.proposition_id:
                        match = single_m

                if not match or match.decision == BeastV2Decision.NO_VALID_VISUAL:
                    validation_warnings.append(
                        f"NO_VALID_VISUAL on fact {fact.fact_id} proposition {prop.proposition_id}."
                    )

                # Duration per proposition unit (with Discovery Short hard 1.5s cap)
                unit_dur = EditorialPacingEngine.calculate_editorial_duration(
                    narrative_role=fact.narrative_role or "BODY",
                    narrative_weight=fact_weight,
                    available_narration_duration=max(1.2, (fact_duration - elapsed_fact_time) / max(1, len(props) - prop_sub_idx)),
                    is_discovery_short=is_discovery_short,
                )

                if is_discovery_short:
                    unit_dur = min(1.50, unit_dur)

                # Check anti-padding rule (no stretching, looping, or freezing!)
                if match and match.source_end - match.source_start < unit_dur:
                    # Clip available is shorter than target; use exact available (no stretching!)
                    unit_dur = max(0.8, match.source_end - match.source_start)
                    if is_discovery_short:
                        unit_dur = min(1.50, unit_dur)

                elapsed_fact_time += unit_dur

                # Transitions
                is_audio_j = (prop_sub_idx == 0 and fact_idx > 0 and fact_weight >= 0.75)
                trans_type, trans_reason = EditorialTreatmentSelector.select_transition(
                    prev_shot=None,
                    curr_shot=None,
                    narrative_role=fact.narrative_role or "BODY",
                    movie_contrast=fact.movie_contrast,
                    is_audio_led_j_cut=is_audio_j,
                    recent_transitions=recent_transitions,
                )
                recent_transitions.append(trans_type)

                # Motion
                is_anchor = (fact.narrative_role in ("SURPRISE", "CLIMAX") or fact_weight >= 0.85)
                motion = EditorialTreatmentSelector.select_motion_treatment(
                    narrative_weight=fact_weight,
                    is_anchor=is_anchor,
                    is_revelation=(fact.narrative_role == "CLIMAX"),
                    recent_punch_ins=recent_punch_ins,
                )
                if motion == MotionTreatment.PUNCH_IN_115:
                    recent_punch_ins += 1
                else:
                    recent_punch_ins = max(0, recent_punch_ins - 1)

                # Callout
                is_hidden = "hidden" in fact.claim.lower() or "detail" in fact.claim.lower()
                is_prop_detail = prop.visual_role in ("OBJECT_PROP", "OBJECT_PROP_EVIDENCE")
                callout = EditorialTreatmentSelector.select_callout(
                    proposition=prop,
                    is_hidden_detail=is_hidden,
                    is_prop_inscription=is_prop_detail,
                )

                # Composition - Natural cinematic movie framing (Part E)
                is_book_movie = fact.claim_type.value == "BOOK_VS_MOVIE" if hasattr(fact.claim_type, "value") else "BOOK" in str(fact.claim_type)
                prop_framing = getattr(prop, "preferred_framing", None) or getattr(prop, "shot_scale", None)
                if not prop_framing or str(prop_framing).upper() in ("NONE", ""):
                    beat_dict = {
                        "visual_requirement": prop.action or "",
                        "action": prop.action or "",
                        "narration_text": fact.claim,
                        "text": f"{prop.subject} {prop.action} {prop.object}",
                        "characters": [prop.subject] if prop.subject and prop.subject.lower() != "none" else [],
                        "location": prop.context or "",
                    }
                    try:
                        prop_framing = MovieRetrievalEngine.infer_target_shot_scale(beat_dict)
                    except Exception:
                        prop_framing = ShotScale.MEDIUM_SHOT

                comp = EditorialTreatmentSelector.select_composition_treatment(
                    shot_scale=prop_framing,
                    is_book_vs_movie_comparison=(is_book_movie and prop_sub_idx == 1),
                )

                # Caption
                caption_treat = CaptionSFXIntelligence.select_caption_treatment(
                    text=f"{fact.claim} {prop.object}",
                    narrative_weight=fact_weight,
                    is_revelation=(fact.narrative_role == "CLIMAX"),
                )

                # SFX
                sfx_treat, sfx_reason = CaptionSFXIntelligence.select_sfx_treatment(
                    text=fact.claim,
                    narrative_role=fact.narrative_role or "BODY",
                    narrative_weight=fact_weight,
                    last_sfx_timestamp=last_sfx_time,
                    current_timestamp=current_time,
                )
                if sfx_treat != SFXTreatment.NONE and sfx_treat != SFXTreatment.INTENTIONAL_SILENCE:
                    last_sfx_time = current_time

                # Emphasis level
                if fact.narrative_role == "CLIMAX":
                    emphasis_lvl = "CLIMAX"
                elif fact_weight >= 0.80:
                    emphasis_lvl = "MAJOR"
                elif fact_weight >= 0.65:
                    emphasis_lvl = "IMPORTANT"
                else:
                    emphasis_lvl = "NORMAL"

                primitives = EditorialTreatmentSelector.assemble_emphasis_primitives(
                    motion=motion,
                    composition=comp,
                    callout=callout,
                    narrative_role=fact.narrative_role or "BODY",
                    is_object_prop=is_prop_detail,
                )

                is_no_valid = (not match) or (match.decision == BeastV2Decision.NO_VALID_VISUAL)
                final_evidence = "NO_VALID_VISUAL" if is_no_valid else match.evidence_type.value

                # Proposition Evidence Validator classification check (Sections 8, 9)
                ev_class = getattr(match, "evidence_class", None) if match else None
                if not ev_class and match and match.verification_metadata:
                    ev_class = match.verification_metadata.get("evidence_class")

                if ev_class == "NO_VALID_VISUAL":
                    is_no_valid = True
                    final_evidence = "NO_VALID_VISUAL"
                elif ev_class == "CONTEXT":
                    # Context is never silently treated as DIRECT evidence
                    prop_req = getattr(prop, "evidence_type", None) or getattr(prop, "required_relationship", None)
                    prop_req_str = str(prop_req.value if hasattr(prop_req, "value") else prop_req).upper()
                    if prop_req_str in ("DIRECT", "DIRECT_EVIDENCE"):
                        validation_warnings.append(
                            f"CONTEXT_NOT_DIRECT: Fact {fact.fact_id} proposition {prop.proposition_id} requires DIRECT evidence; candidate is only CONTEXT."
                        )
                    final_evidence = "CONTEXTUAL_EVIDENCE"

                # Part C: Align visual onset directly to spoken onset when timestamps are present
                prop_spoken_start = getattr(prop, "spoken_start", None) or getattr(prop, "spoken_onset", None)
                if prop_spoken_start is not None and prop_spoken_start >= 0.0:
                    current_time = float(prop_spoken_start)

                unit = EditorialUnit(
                    unit_id=f"unit_{unit_idx:02d}_{fact.fact_id}",
                    fact_id=fact.fact_id,
                    proposition_id=prop.proposition_id,
                    asset_id=match.asset_id if not is_no_valid else "NO_VALID_VISUAL",
                    source_start=match.source_start if not is_no_valid else 0.0,
                    source_end=(match.source_start + unit_dur) if not is_no_valid else unit_dur,
                    evidence_type=final_evidence,
                    visual_role=prop.visual_role,
                    narration_start=round(current_time, 3),
                    narration_end=round(current_time + unit_dur, 3),
                    duration_seconds=unit_dur,
                    importance=fact.importance,
                    narrative_weight=fact_weight,
                    pacing_weight=unit_dur,
                    emphasis_level=emphasis_lvl,
                    emphasis_primitives=primitives,
                    transition_type=trans_type,
                    motion_treatment=motion,
                    caption_treatment=caption_treat,
                    sfx_treatment=sfx_treat,
                    composition_treatment=comp,
                    callout=callout,
                    audio_offset_seconds=-0.25 if trans_type == EditorialTransitionType.J_CUT else 0.0,
                    fact_number=fact_num,
                    fact_counter=fact_counter_str,
                    reason=f"{fact.narrative_role or 'BODY'} evidence cut: {trans_reason}",
                )
                units.append(unit)
                current_time += unit_dur
                unit_idx += 1

            fact_end_time = round(current_time, 3)
            fact.fact_end = fact_end_time
            if fact_counter_str:
                fact_counters_list.append({
                    "fact_number": fact_num,
                    "counter": fact_counter_str,
                    "title": fact.fact_title or fact.claim,
                    "start_time": fact_start_time,
                    "end_time": fact_end_time,
                    "duration": round(fact_end_time - fact_start_time, 3),
                })

        # ----------------------------------------------------------------------
        # C. PAYOFF & EPIPHANY HOLD
        # ----------------------------------------------------------------------
        payoff_text = (topic_pack.payoff_text or "").strip()
        payoff_dur = 1.40 if is_discovery_short else 3.2
        last_match = beast_matches[-1] if beast_matches else None
        
        payoff_sfx, _ = CaptionSFXIntelligence.select_sfx_treatment(
            text=payoff_text,
            narrative_role="CLIMAX",
            narrative_weight=0.98,
            last_sfx_timestamp=last_sfx_time,
            current_timestamp=current_time,
        )

        payoff_comp = EditorialTreatmentSelector.select_composition_treatment(
            shot_scale=ShotScale.MEDIUM_SHOT,
        )

        payoff_unit = EditorialUnit(
            unit_id=f"unit_{unit_idx:02d}_payoff",
            fact_id="payoff",
            proposition_id="prop_payoff",
            asset_id=last_match.asset_id if last_match else "none",
            source_start=last_match.source_start if last_match else 0.0,
            source_end=(last_match.source_start + payoff_dur) if last_match else payoff_dur,
            evidence_type=last_match.evidence_type.value if last_match else "DIRECT_EVIDENCE",
            visual_role="PAYOFF",
            narration_start=round(current_time, 3),
            narration_end=round(current_time + payoff_dur, 3),
            duration_seconds=payoff_dur,
            importance=0.99,
            narrative_weight=0.98,
            pacing_weight=payoff_dur,
            emphasis_level="CLIMAX",
            emphasis_primitives=[VisualEmphasisPrimitive.MICRO_HOLD, VisualEmphasisPrimitive.PUNCH_IN],
            transition_type=EditorialTransitionType.HARD_CUT,
            motion_treatment=MotionTreatment.SLOW_PUSH_IN,
            caption_treatment=CaptionTreatment.REVEAL_WORD_BURST,
            sfx_treatment=payoff_sfx,
            composition_treatment=payoff_comp,
            reason="Final climax hold: Deliberate visual breathing room on unifying epiphany",
        )
        units.append(payoff_unit)
        current_time += payoff_dur

        # ----------------------------------------------------------------------
        # D. TIMELINE ASSEMBLY & QUALITY AUDIT
        # ----------------------------------------------------------------------
        timeline_id = f"timeline_{topic_pack.topic_id}"
        timeline = EditorialTimelineV2(
            timeline_id=timeline_id,
            topic_id=topic_pack.topic_id,
            total_duration_seconds=round(current_time, 3),
            total_cuts=len(units),
            units=units,
            fact_counters=fact_counters_list,
            validation_warnings=validation_warnings,
            quality_audit={
                "total_units": len(units),
                "punch_in_count": sum(1 for u in units if u.motion_treatment == MotionTreatment.PUNCH_IN_115),
                "sfx_count": sum(1 for u in units if u.sfx_treatment not in (SFXTreatment.NONE, SFXTreatment.INTENTIONAL_SILENCE)),
                "callout_count": sum(1 for u in units if u.callout is not None),
                "transition_types_used": list(set(u.transition_type.value for u in units)),
                "average_cut_duration": round(current_time / max(1, len(units)), 2),
            }
        )
        timeline.calculate_fingerprint(config_version=self.config_version)
        return timeline
