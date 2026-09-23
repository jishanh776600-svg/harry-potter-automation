"""
STORY FORGE Storyboard Data Models & Beat Contracts (Step 2)
================================================================================
Defines canonical contracts for the Anchor-Grounded Hybrid Storyboard Planner:
  - 4 Visual Roles: DIRECT_EVIDENCE, CONTEXTUAL_ENVIRONMENT, CHARACTER_REACTION, IRONIC_CONTRAST
  - Visual Source Types: MOVIE_DIRECT, FAN_ART, OFFICIAL_ARTWORK, NO_VALID_VISUAL
  - Framing Intent: ShotScale (Commit 37b1463 natural medium framing policy)
  - Pacing Phases: HOOK, SETUP, EVIDENCE, ANCHOR, PAYOFF
  - Timeline-Locked Storyboard Beat Contracts
  - Complete StoryboardPlan with provenance linkage and bidirectional feasibility audit
"""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from core.hybrid_visual_models import (
    VisualSourceType,
    ArtistLicenseStatus,
    CommercialClearanceStatus,
    RightsStatus,
    ApprovalStatus,
    VisualProvenance,
    FORBIDDEN_SOURCE_PROVIDERS
)
from core.discovery_types import (
    DiscoveryTier,
    DiscoveryStoryStructure,
    PacingPhase,
    EvidenceRoute,
    EvidencePoint
)
from engines.movie_retrieval_engine import ShotScale


class VisualRole(str, Enum):
    """
    Explicit visual role of footage relative to the voiceover claim.
    DIRECT_EVIDENCE: Footage directly depicts the specific claim, action, or object.
    CONTEXTUAL_ENVIRONMENT: Authentic setting or world atmosphere providing spatial grounding.
    CHARACTER_REACTION: Emotional expression or response reflecting the revelation.
    IRONIC_CONTRAST: Visual explicitly contradicts voiceover (e.g. showing what the movie changed).
    """
    DIRECT_EVIDENCE = "DIRECT_EVIDENCE"
    CONTEXTUAL_ENVIRONMENT = "CONTEXTUAL_ENVIRONMENT"
    CHARACTER_REACTION = "CHARACTER_REACTION"
    IRONIC_CONTRAST = "IRONIC_CONTRAST"


class TransitionIntent(str, Enum):
    """Transition styling between visual beats."""
    HARD_CUT = "HARD_CUT"
    J_CUT = "J_CUT"
    MATCH_CUT = "MATCH_CUT"
    CROSSFADE = "CROSSFADE"
    SMASH_CUT = "SMASH_CUT"


class FallbackStrategy(str, Enum):
    """Fallback options when primary visual evidence is constrained."""
    CONTEXTUAL_FALLBACK = "CONTEXTUAL_FALLBACK"
    REACTION_FALLBACK = "REACTION_FALLBACK"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    NO_VISUAL_FLAG = "NO_VISUAL_FLAG"


@dataclass
class StoryboardBeatContract:
    """
    Timeline-locked beat contract between narration, evidence, and visuals.
    Preserves full provenance, framing intent, and visual role.
    """
    beat_id: str
    narrative_phase: str                               # HOOK, SETUP, EVIDENCE, ANCHOR, PAYOFF
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    target_duration: float = 2.0
    narration_intent: str = ""                         # What is being spoken / explained
    evidence_point_id: Optional[str] = None            # Link to Step 1 EvidencePoint
    visual_role: VisualRole = VisualRole.DIRECT_EVIDENCE
    visual_source_type: VisualSourceType = VisualSourceType.MOVIE_DIRECT
    preferred_movie_number: Optional[int] = None
    scene_reference: Optional[str] = None
    clip_start_seconds: Optional[float] = None
    clip_end_seconds: Optional[float] = None
    required_characters: List[str] = field(default_factory=list)
    required_actions: List[str] = field(default_factory=list)
    required_objects: List[str] = field(default_factory=list)
    framing_intent: ShotScale = ShotScale.MEDIUM_SHOT  # Commit 37b1463 policy
    is_anchor: bool = False                            # Anchor beat (asymmetric emphasis)
    visual_feasibility_score: float = 0.0              # 0.0 - 100.0
    fallback_strategy: Optional[FallbackStrategy] = None
    source_provenance: Optional[Dict[str, Any]] = None  # Provenance dictionary
    transition_intent: TransitionIntent = TransitionIntent.HARD_CUT
    motion_intent: Optional[str] = None                # Camera motion / subtle zoom
    caption_intent: Optional[str] = None               # Caption highlight cue
    adaptation_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["visual_role"] = self.visual_role.value if isinstance(self.visual_role, VisualRole) else str(self.visual_role)
        d["visual_source_type"] = self.visual_source_type.value if isinstance(self.visual_source_type, VisualSourceType) else str(self.visual_source_type)
        d["framing_intent"] = self.framing_intent.value if isinstance(self.framing_intent, ShotScale) else str(self.framing_intent)
        d["transition_intent"] = self.transition_intent.value if isinstance(self.transition_intent, TransitionIntent) else str(self.transition_intent)
        if self.fallback_strategy:
            d["fallback_strategy"] = self.fallback_strategy.value if isinstance(self.fallback_strategy, FallbackStrategy) else str(self.fallback_strategy)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryboardBeatContract":
        vr = data.get("visual_role", VisualRole.DIRECT_EVIDENCE.value)
        if isinstance(vr, str):
            vr = VisualRole(vr)

        vst = data.get("visual_source_type", VisualSourceType.MOVIE_DIRECT.value)
        if isinstance(vst, str):
            vst = VisualSourceType(vst)

        fi = data.get("framing_intent", ShotScale.MEDIUM_SHOT.value)
        if isinstance(fi, str):
            fi = ShotScale(fi)

        ti = data.get("transition_intent", TransitionIntent.HARD_CUT.value)
        if isinstance(ti, str):
            ti = TransitionIntent(ti)

        fb = data.get("fallback_strategy")
        if fb and isinstance(fb, str):
            fb = FallbackStrategy(fb)

        return cls(
            beat_id=data.get("beat_id", ""),
            narrative_phase=data.get("narrative_phase", PacingPhase.EVIDENCE.value),
            start_seconds=data.get("start_seconds", 0.0),
            end_seconds=data.get("end_seconds", 0.0),
            target_duration=data.get("target_duration", 2.0),
            narration_intent=data.get("narration_intent", ""),
            evidence_point_id=data.get("evidence_point_id"),
            visual_role=vr,
            visual_source_type=vst,
            preferred_movie_number=data.get("preferred_movie_number"),
            scene_reference=data.get("scene_reference"),
            clip_start_seconds=data.get("clip_start_seconds"),
            clip_end_seconds=data.get("clip_end_seconds"),
            required_characters=data.get("required_characters", []),
            required_actions=data.get("required_actions", []),
            required_objects=data.get("required_objects", []),
            framing_intent=fi,
            is_anchor=data.get("is_anchor", False),
            visual_feasibility_score=data.get("visual_feasibility_score", 0.0),
            fallback_strategy=fb,
            source_provenance=data.get("source_provenance"),
            transition_intent=ti,
            motion_intent=data.get("motion_intent"),
            caption_intent=data.get("caption_intent"),
            adaptation_notes=data.get("adaptation_notes"),
        )


@dataclass
class StoryboardPlan:
    """
    Complete timeline-locked storyboard plan for a Deep Discovery Short.
    Contains sequence of beat contracts, anchor assignments, and feasibility score.
    """
    storyboard_id: str
    topic_id: str
    discovery_tier: DiscoveryTier = DiscoveryTier.DEEP_DISCOVERY
    story_structure: DiscoveryStoryStructure = DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE
    total_target_duration: float = 72.0
    beats: List[StoryboardBeatContract] = field(default_factory=list)
    anchor_beat_ids: List[str] = field(default_factory=list)
    overall_visual_feasibility_score: float = 0.0
    is_production_feasible: bool = True
    narrative_adjustments_suggested: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Tuple[bool, List[str]]:
        """Validates all storyboard contract rules."""
        errors = []
        if not self.storyboard_id:
            errors.append("storyboard_id is required")
        if not self.beats:
            errors.append("Storyboard must contain at least one beat")

        # Visual role check: every beat must have an explicit visual role
        for b in self.beats:
            if not b.visual_role or not isinstance(b.visual_role, VisualRole):
                errors.append(f"Beat '{b.beat_id}' lacks valid VisualRole")

            # Check forbidden stock providers
            b_dump = json.dumps(b.to_dict()).lower()
            for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
                if forbidden in b_dump:
                    errors.append(f"Beat '{b.beat_id}' requested forbidden source: {forbidden}")

        # Anchor check: must have at least one anchor beat
        has_anchor = any(b.is_anchor for b in self.beats)
        if not has_anchor:
            errors.append("Storyboard must contain at least one designated anchor beat")

        # Pacing / timeline continuity check
        for i in range(len(self.beats) - 1):
            curr_b = self.beats[i]
            next_b = self.beats[i + 1]
            if curr_b.end_seconds > next_b.start_seconds + 0.01:
                errors.append(f"Timeline overlap detected between beat '{curr_b.beat_id}' and '{next_b.beat_id}'")

        is_valid = len(errors) == 0
        return is_valid, errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "storyboard_id": self.storyboard_id,
            "topic_id": self.topic_id,
            "discovery_tier": self.discovery_tier.value if isinstance(self.discovery_tier, DiscoveryTier) else str(self.discovery_tier),
            "story_structure": self.story_structure.value if isinstance(self.story_structure, DiscoveryStoryStructure) else str(self.story_structure),
            "total_target_duration": self.total_target_duration,
            "beats": [b.to_dict() for b in self.beats],
            "anchor_beat_ids": self.anchor_beat_ids,
            "overall_visual_feasibility_score": self.overall_visual_feasibility_score,
            "is_production_feasible": self.is_production_feasible,
            "narrative_adjustments_suggested": self.narrative_adjustments_suggested,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryboardPlan":
        beats = [StoryboardBeatContract.from_dict(b) for b in data.get("beats", [])]

        tier = data.get("discovery_tier", DiscoveryTier.DEEP_DISCOVERY.value)
        if isinstance(tier, str):
            tier = DiscoveryTier(tier)

        struct = data.get("story_structure", DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE.value)
        if isinstance(struct, str):
            struct = DiscoveryStoryStructure(struct)

        return cls(
            storyboard_id=data.get("storyboard_id", ""),
            topic_id=data.get("topic_id", ""),
            discovery_tier=tier,
            story_structure=struct,
            total_target_duration=data.get("total_target_duration", 72.0),
            beats=beats,
            anchor_beat_ids=data.get("anchor_beat_ids", []),
            overall_visual_feasibility_score=data.get("overall_visual_feasibility_score", 0.0),
            is_production_feasible=data.get("is_production_feasible", True),
            narrative_adjustments_suggested=data.get("narrative_adjustments_suggested", []),
            metadata=data.get("metadata", {}),
        )
