"""
STORY FORGE — Movie Event Models (V2)
=====================================
Structured data models for observable movie events, visual storyboard beats,
abstract claim classifications, event search queries, and verification results.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator

VISUAL_OPTIONAL = "VISUAL_OPTIONAL"
DIRECT_VISUAL = "DIRECT"
INSUFFICIENT_VISUAL_COVERAGE = "INSUFFICIENT_VISUAL_COVERAGE"


class ClaimType(str, Enum):
    """Classification of narrative claims against physical visual demonstrability."""
    DIRECTLY_VISUALIZABLE = "DIRECTLY_VISUALIZABLE"
    VISUALLY_REPRESENTABLE_WITH_CONTEXT = "VISUALLY_REPRESENTABLE_WITH_CONTEXT"
    ABSTRACT_NOT_DIRECTLY_VISUALIZABLE = "ABSTRACT_NOT_DIRECTLY_VISUALIZABLE"


class VerificationStatus(str, Enum):
    """Detailed visual verification outcome."""
    VERIFIED = "VERIFIED"
    REJECT_ACTION_MISMATCH = "REJECT_ACTION_MISMATCH"
    REJECT_SUBJECT_MISMATCH = "REJECT_SUBJECT_MISMATCH"
    REJECT_TARGET_MISMATCH = "REJECT_TARGET_MISMATCH"
    REJECT_LOCATION_MISMATCH = "REJECT_LOCATION_MISMATCH"
    REJECT_FORBIDDEN_ELEMENT = "REJECT_FORBIDDEN_ELEMENT"
    REJECT_TEMPORAL_DISCONTINUITY = "REJECT_TEMPORAL_DISCONTINUITY"
    NO_DIRECT_VISUAL_EVENT = "NO_DIRECT_VISUAL_EVENT"


class MovieEvent(BaseModel):
    """
    Representation of an observable physical event in the movie.
    Strictly describes what is VISIBLY occurring on screen.
    Does NOT encode invisible thoughts, intentions, or narrative interpretations as facts.
    """
    event_id: str = Field(..., description="Unique event identifier, e.g. evt_m1_potions_snape_questions_01")
    movie_id: str = Field(..., description="Movie asset identifier, e.g. hp_movie_1")
    movie_number: int = Field(..., ge=1, le=8, description="Canonical movie number (1-8)")
    scene_id: str = Field(..., description="Parent scene identifier")
    start_time: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    end_time: float = Field(..., ge=0.0, description="End timestamp in seconds")
    
    # Character & Subject Details
    characters_present: List[str] = Field(default_factory=list, description="All identifiable characters visible")
    primary_subject: str = Field(..., description="Character or entity initiating or performing the primary action")
    secondary_subjects: List[str] = Field(default_factory=list, description="Other characters actively engaged")
    
    # Observable Physical Action & Interaction
    action: str = Field(..., description="Physical action depicted (e.g. questions, punches, opens, draws)")
    target: Optional[str] = Field(None, description="Direct object or recipient of action (e.g. Harry, Malfoy, Sword, Sink)")
    interaction_type: str = Field("neutral", description="Nature of interaction: confrontation, combat, instruction, dialogue, lone_action")
    location: str = Field(..., description="Physical environment (e.g. Potions classroom, Sundial stone circle, Myrtle bathroom)")
    visible_objects: List[str] = Field(default_factory=list, description="Physical props visible (e.g. quill, wand, Sorting Hat, snake tap)")
    
    # Cinematic & Framing Attributes
    emotional_state: str = Field("neutral", description="Visible emotional demeanor (e.g. stern, defiant, terrified, furious)")
    camera_scale: str = Field("MEDIUM", description="Shot scale: CLOSE_UP, MEDIUM, WIDE, TWO_SHOT")
    camera_motion: Optional[str] = Field(None, description="Camera motion if detectable: static, pan, tracking, zoom, handheld")
    
    # Event Chain Topology
    preceding_event: Optional[str] = Field(None, description="ID of causally/chronologically preceding event")
    following_event: Optional[str] = Field(None, description="ID of causally/chronologically following event")
    
    # Transcript & Evidentiary Support
    dialogue_ref: Optional[str] = Field(None, description="Associated movie dialogue or subtitle transcript excerpt")
    visual_description: str = Field(..., description="Purely observable visual description of what happens on screen")
    observable_claims: List[str] = Field(default_factory=list, description="Facts directly verifiable from the visual frames")
    unsupported_claims: List[str] = Field(default_factory=list, description="Interpretive or book-only claims NOT shown visually")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Extraction / grounding confidence score")

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


class VisualBeat(BaseModel):
    """
    Structured visual requirement generated from a narrative proposition/beat.
    Guarantees strict beat-to-visual correspondence and observable proof contracts.
    """
    beat_id: str = Field(..., description="Unique beat identifier, e.g. beat_01")
    start_time: float = Field(0.0, ge=0.0, description="Timeline start in seconds")
    end_time: float = Field(0.0, ge=0.0, description="Timeline end in seconds")
    narration_start: float = Field(0.0, ge=0.0, description="Spoken narration start timestamp in seconds")
    narration_end: float = Field(0.0, ge=0.0, description="Spoken narration end timestamp in seconds")
    narrative_text: str = Field(..., description="Narration voiceover spoken during this beat")
    narrative_role: str = Field("DEVELOPMENT", description="Role: INTRODUCE_CONFRONTATION, ACTION, REACTION, CLIMAX, PAYOFF, HOOK, LORE_COMPARISON")
    
    # Mandatory Observable Visual Requirements
    required_subjects: List[str] = Field(default_factory=list, description="Entities that MUST appear on screen")
    required_action: str = Field("none", description="Observable action required (e.g. questions, punches, draws, opens, snaps)")
    required_target: Optional[str] = Field(None, description="Target/recipient that must be interacted with")
    required_location: Optional[str] = Field(None, description="Setting required for coherence")
    required_objects: List[str] = Field(default_factory=list, description="Key physical props that must appear")
    required_entities: List[str] = Field(default_factory=list, description="Consolidated list of all required physical entities")
    required_interaction: Optional[str] = Field(None, description="Interaction type required, e.g. teacher -> student")
    visual_state: Optional[str] = Field(None, description="Expected observable physical state (e.g. INTACT, BROKEN, HELD)")
    visual_assertion: Optional[Any] = Field(None, description="Associated VisualAssertion or structured assertion contract")
    
    # Framing & Role Preferences
    preferred_shot_scale: Optional[str] = Field(None, description="Preferred scale, e.g. TWO_SHOT, CLOSE_UP")
    preferred_visual_role: str = Field("CORE_ACTION", description="CORE_ACTION, PRECEDING_CONTEXT, REACTION_PAYOFF")
    forbidden_visuals: List[str] = Field(default_factory=list, description="Visuals strictly disallowed for this beat")
    
    # Evidence Strictness & Coverage Modes
    direct_visual_requirement: bool = Field(True, description="Whether direct physical proof is required")
    coverage_requirement: str = Field("DIRECT", description="DIRECT or VISUAL_OPTIONAL")
    contextual_visual_allowed: bool = Field(False, description="Whether contextual/atmospheric shot is acceptable")
    fallback_strategy: str = Field("STRICT_FAIL", description="STRICT_FAIL, WIDEN_LOCATION, CONTEXT_REACTION")

    @model_validator(mode="after")
    def _sync_fields(self) -> "VisualBeat":
        # Keep start_time / narration_start and end_time / narration_end synchronized
        if self.narration_start == 0.0 and self.start_time > 0.0:
            self.narration_start = self.start_time
        elif self.start_time == 0.0 and self.narration_start > 0.0:
            self.start_time = self.narration_start

        if self.narration_end == 0.0 and self.end_time > 0.0:
            self.narration_end = self.end_time
        elif self.end_time == 0.0 and self.narration_end > 0.0:
            self.end_time = self.narration_end

        # Synchronize direct_visual_requirement and coverage_requirement
        if not self.direct_visual_requirement:
            self.coverage_requirement = VISUAL_OPTIONAL
        elif self.coverage_requirement == VISUAL_OPTIONAL:
            self.direct_visual_requirement = False

        # Populate required_entities if not explicitly provided
        if not self.required_entities:
            all_ents = list(self.required_subjects) + list(self.required_objects)
            if self.required_target and self.required_target not in all_ents:
                all_ents.append(self.required_target)
            self.required_entities = list(dict.fromkeys(all_ents))

        return self

    @property
    def is_visual_optional(self) -> bool:
        """Returns True if this beat does not strictly require physical movie footage."""
        return not self.direct_visual_requirement or self.coverage_requirement == VISUAL_OPTIONAL

    @property
    def requires_direct_proof(self) -> bool:
        """Returns True if the beat strictly requires directly observable visual evidence."""
        return self.direct_visual_requirement and not self.contextual_visual_allowed and not self.is_visual_optional


class VisualStoryboard(BaseModel):
    """Collection of structured VisualBeats representing an entire Short storyboard."""
    storyboard_id: str = Field(..., description="Storyboard identifier")
    title: str = Field(..., description="Title or candidate topic")
    beats: List[VisualBeat] = Field(default_factory=list, description="Sequential visual beats")
    total_duration: float = Field(0.0, description="Total expected duration in seconds")


class MovieEventQuery(BaseModel):
    """
    Structured query for searching the MovieEventIndex.
    Constructed directly from a VisualBeat or test query.
    """
    subject: Optional[str] = Field(None, description="Required or preferred primary character/entity")
    action: Optional[str] = Field(None, description="Required observable action")
    target: Optional[str] = Field(None, description="Required target/object of action")
    interaction: Optional[str] = Field(None, description="Required interaction pattern")
    location: Optional[str] = Field(None, description="Required or preferred setting")
    objects: List[str] = Field(default_factory=list, description="Key required props")
    movie_number: Optional[int] = Field(None, description="Specific movie constraint (1-8), if known")
    visual_role: Optional[str] = Field(None, description="A_CONTEXT, B_ACTION, C_REACTION")
    temporal_context: Optional[str] = Field(None, description="Temporal or narrative placement")
    forbidden_elements: List[str] = Field(default_factory=list, description="Elements that disqualify a candidate")


class ClaimClassification(BaseModel):
    """Result of transforming a narration claim into visual demonstrability."""
    raw_claim: str = Field(..., description="Original narration claim")
    classification: ClaimType = Field(..., description="DIRECT, CONTEXT, or ABSTRACT")
    is_directly_visualizable: bool = Field(..., description="True if physically observable on screen")
    demonstrable_action: Optional[str] = Field(None, description="The concrete physical action to look for")
    abstract_elements: List[str] = Field(default_factory=list, description="Invisible thoughts/feelings in the claim")
    recommended_rewrite: Optional[str] = Field(None, description="Narration rewrite that expresses claim through observable actions")
    rejection_notice: Optional[str] = Field(None, description="Reason if NO_DIRECT_VISUAL_EVENT")


class EventVerificationResult(BaseModel):
    """Detailed visual verification report for a candidate movie event."""
    candidate_event_id: str = Field(..., description="ID of evaluated MovieEvent")
    query_action: str = Field(..., description="Action requested by query/beat")
    event_action: str = Field(..., description="Action present in candidate event")
    status: VerificationStatus = Field(..., description="Verification verdict")
    is_verified: bool = Field(..., description="True if passes verification")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Verification score")
    
    # Dimension Gates
    subject_match: bool = Field(False)
    action_match: bool = Field(False)
    target_match: bool = Field(False)
    location_match: bool = Field(False)
    object_match: bool = Field(False)
    interaction_match: bool = Field(False)
    forbidden_absent: bool = Field(True)
    
    explanation: str = Field(..., description="Human-readable decision explanation")
    rejection_reasons: List[str] = Field(default_factory=list, description="Specific failure reasons if rejected")
