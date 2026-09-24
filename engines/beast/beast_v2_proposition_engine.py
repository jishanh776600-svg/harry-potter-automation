"""
STORY FORGE — BEAST V2 Proposition-Aware Visual Evidence Engine
================================================================================
Upgrades BEAST V1 from "footage related to narration" to
"does this visual communicate the exact VISUAL PROPOSITION required?".

Implements:
  1. Gated proposition alignment (Subject, Action, Object, Context, Era, Source)
  2. Multi-evidence classification:
     - ACCEPT_DIRECT
     - ACCEPT_OBJECT (object-centric proposition; character absence is NOT disqualifying)
     - ACCEPT_ORIENTATION (strict <= 2.0s duration limit)
     - ACCEPT_CONTEXT (context != proof)
     - ACCEPT_CONTRAST (ironic / book-vs-movie contrast)
     - NO_VALID_VISUAL (fail-closed guarantee)
  3. Source-evidence separation:
     - Movie footage cannot prove a book-only proposition
     - Regular movie scene cannot prove a behind-the-scenes proposition
  4. Temporal micro-interval grounding & multi-frame temporal inspection
  5. Asset Acquisition Engine fallback when movie archive lacks evidence
  6. Anti-repetition sliding window
  7. Fact-level visual coverage tracking (Short -> Fact -> Proposition -> Visual)
"""

from collections import deque
import logging
import re
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_v2_types import (
    EvidenceType,
    SourceEvidenceType,
    ActionCategory,
    BeastV2Decision,
    TemporalMicroInterval,
    PropositionAlignmentBreakdown,
    BeastV2MatchResult,
    FactPropositionCoverage,
)
from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    NarrativeEra,
)
from core.multi_fact_types import VisualProposition, RequiredEvidenceType
from core.storyboard_types import VisualRole
from engines.beast.beast_entity_verifiers import BeastEntityVerifiers, CHARACTER_ALIASES, OBJECT_ALIASES
from engines.beast.beast_contradiction_guard import BeastContradictionGuard
from engines.beast.beast_v2_action_verifier import BeastV2ActionVerifier
from engines.beast.beast_v2_temporal_grounding import BeastV2TemporalGrounder

logger = logging.getLogger("BeastV2PropositionEngine")

# Canonical Object-centric items where object alone can be primary evidence
OBJECT_CENTRIC_ENTITIES = {
    "sword of gryffindor", "sword", "sorting hat", "mirror of erised",
    "daily prophet", "marauder's map", "marauders map", "map", "horcrux",
    "diadem", "locket", "cup", "ring", "diary", "tombstone", "elder wand",
    "wand", "invisibility cloak", "cloak", "remembrall", "letter",
    "newspaper", "photograph", "prop inscription", "black family tree",
}


class BeastV2PropositionEngine:
    """
    Proposition-Aware Visual Evidence Engine (BEAST V2).
    """

    def __init__(
        self,
        min_confidence_threshold: float = 65.0,
        repetition_window_size: int = 4,
        asset_acquisition_engine: Optional[Any] = None,
    ):
        self.min_confidence_threshold = min_confidence_threshold
        self.repetition_window_size = repetition_window_size
        self.asset_acquisition_engine = asset_acquisition_engine
        self._recently_used_queue: deque = deque(maxlen=repetition_window_size)
        self._recently_used_assets: Set[str] = set()

    # ==========================================================================
    # 1. PROPOSITION PREPARATION & ENHANCEMENT
    # ==========================================================================

    @classmethod
    def is_object_centric_proposition(cls, proposition: VisualProposition) -> bool:
        """
        Determines if the proposition is fundamentally about an object/prop:
        - Explicit visual_role in ('OBJECT_PROP', 'OBJECT_PROP_EVIDENCE')
        - OR subject is None/absent/ambient and an object is specified.
        """
        if (proposition.visual_role or "").upper() in ("OBJECT_PROP", "OBJECT_PROP_EVIDENCE"):
            return True
        prop_subj = (proposition.subject or "").strip().lower()
        if prop_subj in ("none", "", "ambient", "environment") and proposition.object and proposition.object.lower() not in ("none", ""):
            return True
        return False

    @classmethod
    def resolve_source_evidence_type(cls, evidence_str: Optional[str]) -> SourceEvidenceType:
        """Maps freeform or enum string to SourceEvidenceType."""
        if not evidence_str:
            return SourceEvidenceType.FILM
        ev_upper = evidence_str.upper()
        if "BOOK" in ev_upper or "TEXT" in ev_upper:
            return SourceEvidenceType.BOOK_TEXT
        if "BTS" in ev_upper or "BEHIND" in ev_upper:
            return SourceEvidenceType.BTS
        if "INTERVIEW" in ev_upper:
            return SourceEvidenceType.INTERVIEW
        if "ARCHIVAL" in ev_upper:
            return SourceEvidenceType.ARCHIVAL
        if "ARTWORK" in ev_upper or "ILLUSTRATION" in ev_upper:
            return SourceEvidenceType.ARTWORK
        if "PHOTO" in ev_upper:
            return SourceEvidenceType.PHOTOGRAPH
        if "DOCUMENT" in ev_upper:
            return SourceEvidenceType.DOCUMENT
        return SourceEvidenceType.FILM

    # ==========================================================================
    # 2. PROPOSITION ALIGNMENT & EVIDENCE VERIFICATION
    # ==========================================================================

    def verify_candidate_against_proposition(
        self,
        proposition: VisualProposition,
        shot: BeastCandidateShot,
        target_duration: float = 2.0,
        candidate_interval: Optional[Tuple[float, float]] = None,
        source_evidence_type: SourceEvidenceType = SourceEvidenceType.FILM,
        is_book_only_claim: bool = False,
        is_bts_claim: bool = False,
    ) -> BeastV2MatchResult:
        """
        Evaluates a candidate visual asset against an exact VisualProposition.
        Enforces strict gating across entities, actions, objects, contexts, eras, and sources.
        """
        contradictions: List[str] = []
        gating_failures: List[str] = []

        prop_subject = (proposition.subject or "").strip()
        prop_action = (proposition.action or "").strip()
        prop_object = (proposition.object or "").strip()
        prop_context = (proposition.context or "").strip()
        is_obj_centric = self.is_object_centric_proposition(proposition)
        role_upper = (proposition.visual_role or "").upper()

        # ----------------------------------------------------------------------
        # A. SOURCE-AWARE EVIDENCE SEPARATION
        # ----------------------------------------------------------------------
        source_compatibility = 100.0
        if is_book_only_claim and source_evidence_type == SourceEvidenceType.FILM:
            msg = "Source Incompatibility: Claim is Book-only canon, but candidate is Movie footage. Movie footage cannot prove book-only events."
            gating_failures.append(msg)
            source_compatibility = 0.0

        if is_bts_claim and source_evidence_type == SourceEvidenceType.FILM:
            msg = "Source Incompatibility: BTS proposition requires behind-the-scenes/interview evidence, not in-universe movie fiction."
            gating_failures.append(msg)
            source_compatibility = 0.0

        if source_evidence_type == SourceEvidenceType.ARTWORK and role_upper == "DIRECT_EVIDENCE":
            msg = "Source Incompatibility: Artwork/illustration cannot serve as DIRECT_FILM_EVIDENCE for movie reality."
            gating_failures.append(msg)
            source_compatibility = 20.0

        # ----------------------------------------------------------------------
        # B. TEMPORAL MICRO-INTERVAL & WRONG-INTERVAL CHECK
        # ----------------------------------------------------------------------
        action_cat = BeastV2ActionVerifier.classify_action(prop_action)
        interval, interval_valid, interval_reason = BeastV2TemporalGrounder.ground_action_interval(
            shot=shot,
            action_category=action_cat,
            target_duration=target_duration,
            candidate_interval=candidate_interval,
        )

        if not interval_valid:
            gating_failures.append(interval_reason or "Temporal Interval Mismatch")
            contradictions.append(interval_reason or "Temporal Interval Mismatch")

        # ----------------------------------------------------------------------
        # C. CONTRADICTION & ERA GUARD
        # ----------------------------------------------------------------------
        if proposition.narrative_era:
            prop_era_str = proposition.narrative_era.upper()
            shot_era_str = shot.narrative_era.value if hasattr(shot.narrative_era, "value") else str(shot.narrative_era)
            if prop_era_str != "ANY" and shot_era_str != "ANY":
                if ("YEAR_1" in prop_era_str and "YEAR_7" in shot_era_str) or \
                   ("YEAR_7" in prop_era_str and "YEAR_1" in shot_era_str):
                    contra_msg = f"Narrative Era Contradiction: Proposition is {prop_era_str} but shot is {shot_era_str}."
                    contradictions.append(contra_msg)
                    gating_failures.append(contra_msg)

        # ----------------------------------------------------------------------
        # D. SUBJECT ALIGNMENT
        # ----------------------------------------------------------------------
        subject_alignment = 0.0
        if not prop_subject or prop_subject.lower() in ("none", "", "ambient", "environment"):
            subject_alignment = 100.0
        else:
            shot_chars = [c.lower() for c in shot.characters_present]
            desc_lower = shot.scene_description.lower()
            norm_prop = BeastEntityVerifiers._normalize_name(prop_subject)

            match_found = False
            for canonical, aliases in CHARACTER_ALIASES.items():
                if norm_prop == canonical:
                    if any(a in " ".join(shot_chars) for a in aliases) or any(re.search(rf"\b{re.escape(a)}\b", desc_lower) for a in aliases):
                        match_found = True
                        break

            if match_found:
                subject_alignment = 100.0
            else:
                if is_obj_centric:
                    subject_alignment = 50.0
                else:
                    subject_alignment = 0.0
                    contra_msg = f"Wrong Character: Narration requires '{prop_subject}' but character is absent from shot."
                    contradictions.append(contra_msg)
                    gating_failures.append(contra_msg)

        # ----------------------------------------------------------------------
        # E. ACTION ALIGNMENT & TEMPORAL PHASES
        # ----------------------------------------------------------------------
        action_alignment = 100.0
        skip_action_check = (
            role_upper in ("ORIENTATION_BRIDGE", "CONTEXTUAL_EVIDENCE", "OBJECT_PROP", "OBJECT_PROP_EVIDENCE")
            or prop_action.lower() in ("none", "", "static", "presence", "ambient", "establishing")
        )

        if not skip_action_check and prop_action:
            action_score, req_cat, cand_cat, act_contras = BeastV2ActionVerifier.verify_action_alignment(
                required_action=prop_action,
                candidate_actions=shot.actions_depicted,
                candidate_description=shot.scene_description,
            )
            action_alignment = action_score
            if act_contras:
                contradictions.extend(act_contras)
                if action_score < 40.0:
                    gating_failures.extend(act_contras)

        # ----------------------------------------------------------------------
        # F. OBJECT ALIGNMENT
        # ----------------------------------------------------------------------
        object_alignment = 100.0
        if prop_object and prop_object.lower() not in ("none", "", "environment"):
            obj_lower = prop_object.lower()
            shot_objs = [o.lower() for o in shot.objects_present]
            desc_lower = shot.scene_description.lower()

            obj_match = any(obj_lower in o for o in shot_objs) or (obj_lower in desc_lower)
            if not obj_match:
                for canonical, aliases in OBJECT_ALIASES.items():
                    if obj_lower in aliases:
                        if any(a in " ".join(shot_objs) for a in aliases) or any(a in desc_lower for a in aliases):
                            obj_match = True
                            break

            if obj_match:
                object_alignment = 100.0
            else:
                if is_obj_centric:
                    object_alignment = 0.0
                    contra_msg = f"Missing Object: Proposition requires '{prop_object}' but object is absent."
                    contradictions.append(contra_msg)
                    gating_failures.append(contra_msg)
                else:
                    object_alignment = 40.0

        # ----------------------------------------------------------------------
        # G. CONTEXT / LOCATION ALIGNMENT
        # ----------------------------------------------------------------------
        context_alignment = 100.0
        if prop_context and prop_context.lower() not in ("none", ""):
            ctx_lower = prop_context.lower()
            shot_env = (shot.environment or "").lower()
            desc_lower = shot.scene_description.lower()
            if ctx_lower in shot_env or ctx_lower in desc_lower:
                context_alignment = 100.0
            else:
                context_alignment = 65.0

        # ----------------------------------------------------------------------
        # H. COMPOSITE SCORING & GATING
        # ----------------------------------------------------------------------
        contra_penalty = 100.0 if contradictions else 0.0

        composite = (
            (subject_alignment * 0.25)
            + (action_alignment * 0.25)
            + (object_alignment * 0.20)
            + (context_alignment * 0.10)
            + (source_compatibility * 0.10)
            + (100.0 if interval_valid else 0.0) * 0.10
        )
        final_score = max(0.0, composite - contra_penalty)
        gating_passed = len(gating_failures) == 0 and final_score >= self.min_confidence_threshold

        alignment_breakdown = PropositionAlignmentBreakdown(
            subject_alignment=subject_alignment,
            action_alignment=action_alignment,
            object_alignment=object_alignment,
            context_alignment=context_alignment,
            temporal_alignment=100.0 if interval_valid else 0.0,
            visual_role_alignment=100.0,
            source_evidence_compatibility=source_compatibility,
            contradiction_penalty=contra_penalty,
            composite_score=round(final_score, 2),
            gating_passed=gating_passed,
            gating_failures=gating_failures,
        )

        # ----------------------------------------------------------------------
        # I. DECISION CATEGORIZATION
        # ----------------------------------------------------------------------
        if not gating_passed:
            decision = BeastV2Decision.NO_VALID_VISUAL
            reason = f"Gating failed: {'; '.join(gating_failures)}"
            evidence_type = EvidenceType.DIRECT_EVIDENCE
        else:
            if role_upper == "IRONIC_CONTRAST":
                decision = BeastV2Decision.ACCEPT_CONTRAST
                evidence_type = EvidenceType.IRONIC_CONTRAST
                reason = "Deliberate ironic contrast verified."
            elif role_upper == "ORIENTATION_BRIDGE":
                # Check orientation bridge constraint: duration MUST be <= 2.0s
                is_valid_bridge, bridge_err = BeastV2TemporalGrounder.validate_orientation_bridge(interval.duration)
                if not is_valid_bridge:
                    decision = BeastV2Decision.NO_VALID_VISUAL
                    reason = bridge_err or "Orientation bridge exceeds 2.0s."
                    evidence_type = EvidenceType.ORIENTATION_BRIDGE
                else:
                    decision = BeastV2Decision.ACCEPT_ORIENTATION
                    evidence_type = EvidenceType.ORIENTATION_BRIDGE
                    reason = f"Orientation bridge accepted ({interval.duration:.1f}s <= 2.0s ceiling)."
            elif role_upper == "CONTEXTUAL_EVIDENCE":
                decision = BeastV2Decision.ACCEPT_CONTEXT
                evidence_type = EvidenceType.CONTEXTUAL_EVIDENCE
                reason = "Contextual environment verified (context preserved as background, not proof)."
            elif is_obj_centric:
                decision = BeastV2Decision.ACCEPT_OBJECT
                evidence_type = EvidenceType.OBJECT_PROP_EVIDENCE
                reason = "Object/prop evidence directly verified without requiring character action."
            else:
                decision = BeastV2Decision.ACCEPT_DIRECT
                evidence_type = EvidenceType.DIRECT_EVIDENCE
                reason = "Direct evidence: Subject, Action, Object, and Context verified."

        return BeastV2MatchResult(
            candidate_id=shot.shot_id,
            asset_id=shot.shot_id,
            source="MOVIE_ARCHIVE" if source_evidence_type == SourceEvidenceType.FILM else "ASSET_ACQUISITION",
            source_start=interval.source_start,
            source_end=interval.source_end,
            action_start=interval.action_start,
            action_peak=interval.action_peak,
            action_end=interval.action_end,
            evidence_type=evidence_type,
            source_evidence_type=source_evidence_type,
            visual_role=VisualRole(proposition.visual_role) if hasattr(VisualRole, proposition.visual_role) else VisualRole.DIRECT_EVIDENCE,
            decision=decision,
            alignment_scores=alignment_breakdown,
            contradictions=contradictions,
            confidence=round(final_score, 2),
            verification_metadata={
                "is_object_centric": is_obj_centric,
                "interval_duration": interval.duration,
                "action_category": action_cat.value if action_cat else None,
            },
            reason=reason,
        )

    # ==========================================================================
    # 3. MULTI-CANDIDATE RANKING & ASSET ACQUISITION FALLBACK
    # ==========================================================================

    def find_best_proposition_match(
        self,
        proposition: VisualProposition,
        candidates: List[BeastCandidateShot],
        target_duration: float = 2.0,
        is_book_only_claim: bool = False,
        is_bts_claim: bool = False,
        allow_acquisition_fallback: bool = True,
    ) -> BeastV2MatchResult:
        """
        Ranks multiple candidate shots, executes proposition verification,
        and falls back to Asset Acquisition if existing archive lacks evidence.
        """
        evaluated_results: List[BeastV2MatchResult] = []

        for shot in candidates:
            # Check repetition penalty
            is_recent = shot.shot_id in self._recently_used_assets
            result = self.verify_candidate_against_proposition(
                proposition=proposition,
                shot=shot,
                target_duration=target_duration,
                source_evidence_type=SourceEvidenceType.FILM,
                is_book_only_claim=is_book_only_claim,
                is_bts_claim=is_bts_claim,
            )
            if is_recent:
                result.confidence = max(0.0, result.confidence - 25.0)
                result.reason += " (Repetition Penalty applied)"

            evaluated_results.append(result)

        # Filter only accepted decisions
        valid_matches = [
            r for r in evaluated_results
            if r.decision != BeastV2Decision.NO_VALID_VISUAL
        ]

        if valid_matches:
            # Sort valid matches by confidence descending
            valid_matches.sort(key=lambda r: r.confidence, reverse=True)
            best_match = valid_matches[0]
            self._recently_used_queue.append(best_match.asset_id)
            self._recently_used_assets = set(self._recently_used_queue)
            return best_match

        # Fallback to Asset Acquisition Engine if archive fails
        if allow_acquisition_fallback and self.asset_acquisition_engine:
            logger.info("Movie Archive produced NO_VALID_VISUAL. Triggering Asset Acquisition fallback...")
            try:
                from engines.acquisition.query_generator import AcquisitionQueryGenerator
                from core.acquisition_types import AssetAcquisitionRequest, MediaCategory
                queries = AcquisitionQueryGenerator.generate_queries(proposition, MediaCategory.IMAGE)
                if queries:
                    acq_res = self.asset_acquisition_engine.acquire_asset(
                        AssetAcquisitionRequest(
                            query=queries[0],
                            beat_id=proposition.proposition_id,
                            primary_entity=proposition.subject,
                            action_descriptor=proposition.action,
                        )
                    )
                    if acq_res.success and acq_res.asset_records:
                        rec = acq_res.asset_records[0]
                        # Create synthetic acquired candidate shot
                        acquired_shot = BeastCandidateShot(
                            shot_id=f"acq_{rec.asset_id[:12]}",
                            source_video=rec.local_cached_path or rec.cloud_path or "acquired_asset.jpg",
                            movie_number=1,
                            start_seconds=0.0,
                            end_seconds=target_duration,
                            duration=target_duration,
                            narrative_era=NarrativeEra.ANY,
                            scene_description=rec.filename,
                            characters_present=[proposition.subject] if proposition.subject else [],
                            objects_present=[proposition.object] if proposition.object else [],
                            actions_depicted=[proposition.action] if proposition.action else [],
                            environment=proposition.context,
                        )
                        # Re-verify acquired asset with appropriate source type
                        source_type = SourceEvidenceType.BTS if is_bts_claim else (
                            SourceEvidenceType.BOOK_TEXT if is_book_only_claim else SourceEvidenceType.PHOTOGRAPH
                        )
                        acq_match = self.verify_candidate_against_proposition(
                            proposition=proposition,
                            shot=acquired_shot,
                            target_duration=target_duration,
                            source_evidence_type=source_type,
                            is_book_only_claim=False,  # Now provided by acquired archival/book source
                            is_bts_claim=False,       # Now provided by acquired BTS source
                        )
                        if acq_match.decision != BeastV2Decision.NO_VALID_VISUAL:
                            acq_match.source = "ASSET_ACQUISITION"
                            return acq_match
            except Exception as e:
                logger.warning("Asset Acquisition fallback failed: %s", str(e))

        # Absolute fail-closed guarantee
        return BeastV2MatchResult(
            candidate_id="none",
            asset_id="none",
            source="NONE",
            source_start=0.0,
            source_end=0.0,
            evidence_type=EvidenceType.DIRECT_EVIDENCE,
            source_evidence_type=SourceEvidenceType.FILM,
            visual_role=VisualRole.DIRECT_EVIDENCE,
            decision=BeastV2Decision.NO_VALID_VISUAL,
            alignment_scores=None,
            contradictions=["NO_VALID_CANDIDATE_FOUND"],
            confidence=0.0,
            verification_metadata={},
            reason="Fail-Closed: No candidate asset satisfied the visual proposition.",
        )

    # ==========================================================================
    # 4. FACT-LEVEL VISUAL COVERAGE TRACKER
    # ==========================================================================

    @classmethod
    def evaluate_fact_coverage(
        cls,
        short_id: str,
        fact_id: str,
        propositions: List[VisualProposition],
        match_results: List[BeastV2MatchResult],
    ) -> List[FactPropositionCoverage]:
        """
        Tracks coverage at: Short -> Fact -> Proposition -> Visual Segment.
        """
        coverages: List[FactPropositionCoverage] = []
        for prop in propositions:
            # Find matching result
            matching = next((m for m in match_results if m.candidate_id != "none" and m.decision != BeastV2Decision.NO_VALID_VISUAL), None)
            if matching:
                cov = FactPropositionCoverage(
                    short_id=short_id,
                    fact_id=fact_id,
                    proposition_id=prop.proposition_id,
                    covered=True,
                    decision=matching.decision,
                    match_result=matching,
                )
            else:
                cov = FactPropositionCoverage(
                    short_id=short_id,
                    fact_id=fact_id,
                    proposition_id=prop.proposition_id,
                    covered=False,
                    decision=BeastV2Decision.NO_VALID_VISUAL,
                    match_result=None,
                )
            coverages.append(cov)

        return coverages

    def clear_session(self) -> None:
        """Resets sliding window state."""
        self._recently_used_queue.clear()
        self._recently_used_assets.clear()
