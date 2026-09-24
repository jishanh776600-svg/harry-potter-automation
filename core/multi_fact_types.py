"""
STORY FORGE — Multi-Fact & Discovery Domain Models V2
======================================================
Defines strongly-typed schemas for STORY FORGE Content Architecture V2:
  - MultiFactFormat: DISCOVERY_BIG (60–70s), DISCOVERY_SHORT (25–30s), NOVEL_STORY
  - MultiFactPayload: Explicit fact boundaries (fact_number, fact_title, fact_start, fact_end,
                      narration_segments, visual_propositions, evidence requirements, visual_status)
  - VisualProposition: Semantic unit of visual communication <Subject, Action, Object, Context, Relationship>
  - VisualRelationship: DIRECT_EVIDENCE, CONTRAST, CONTEXT, OBJECT_DETAIL, NO_VALID_VISUAL
  - MultiFactTopicPack: Enforces Content Quality -> Structure -> Fact Count (NO fixed fact count)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from core.discovery_types import HookArchetype, TitlePattern


class FactType(str, Enum):
    """Categorization of canonical fact payloads."""
    BOOK_VS_MOVIE = "BOOK_VS_MOVIE"
    OMITTED_SCENE = "OMITTED_SCENE"
    CHARACTER_DETAIL = "CHARACTER_DETAIL"
    CHARACTER_PSYCHOLOGY = "CHARACTER_PSYCHOLOGY"
    HIDDEN_MOTIVE = "HIDDEN_MOTIVE"
    PLOT_DETAIL = "PLOT_DETAIL"
    CANON_CONNECTION = "CANON_CONNECTION"
    PROP_DETAIL = "PROP_DETAIL"
    LORE = "LORE"
    FORESHADOWING = "FORESHADOWING"
    HIDDEN_SYMMETRY = "HIDDEN_SYMMETRY"
    CASTING_BTS = "CASTING_BTS"
    PRODUCTION_CHANGE = "PRODUCTION_CHANGE"
    DIALOGUE_DETAIL = "DIALOGUE_DETAIL"
    VISUAL_DETAIL = "VISUAL_DETAIL"


class RequiredEvidenceType(str, Enum):
    """Visual evidence requirements for grounding facts."""
    DIRECT_FILM_EVIDENCE = "DIRECT_FILM_EVIDENCE"
    OBJECT_PROP_EVIDENCE = "OBJECT_PROP_EVIDENCE"
    BOOK_EVIDENCE = "BOOK_EVIDENCE"
    BTS_EVIDENCE = "BTS_EVIDENCE"
    ARCHIVAL_EVIDENCE = "ARCHIVAL_EVIDENCE"
    ORIENTATION_BRIDGE = "ORIENTATION_BRIDGE"
    CONTEXTUAL_EVIDENCE = "CONTEXTUAL_EVIDENCE"
    MIXED_EVIDENCE = "MIXED_EVIDENCE"


class VisualRelationship(str, Enum):
    """
    Formal visual-proposition evidence relationships:
    - DIRECT_EVIDENCE: Video literally demonstrates the narrated event/action/object.
    - CONTRAST: Video explicitly represents the movie reality contrasted against book/canon.
    - CONTEXT: Orientation only; brief; not presented as proof.
    - OBJECT_DETAIL: The relevant object/detail is visibly present in the video.
    - NO_VALID_VISUAL: No suitable video exists.
    """
    DIRECT_EVIDENCE = "DIRECT_EVIDENCE"
    CONTRAST = "CONTRAST"
    CONTEXT = "CONTEXT"
    OBJECT_DETAIL = "OBJECT_DETAIL"
    NO_VALID_VISUAL = "NO_VALID_VISUAL"


class MultiFactFormat(str, Enum):
    """
    Content architecture format:
    - DISCOVERY_BIG: 60–70 seconds. Naturally contains 5–7 facts or 1 deep topic. No fixed fact count.
    - DISCOVERY_SHORT: 25–30 seconds. Naturally contains 1 strong fact or compact facts. No fixed fact count.
    - NOVEL_STORY: 45–60 seconds. Deep novel lore narrative.
    """
    DISCOVERY_BIG = "DISCOVERY_BIG"
    DISCOVERY_SHORT = "DISCOVERY_SHORT"
    NOVEL_STORY = "NOVEL_STORY"
    
    # Backwards-compatible aliases
    MULTI_FACT_DISCOVERY = "MULTI_FACT_DISCOVERY"
    SINGLE_TOPIC_DEEP_DIVE = "SINGLE_TOPIC_DEEP_DIVE"


@dataclass
class VisualProposition:
    """
    The fundamental unit of visual communication.
    Represents <Subject, Action, Object, Context, Required Relationship>.
    Being the same character, location, movie, era, or scene is NOT enough.
    If the exact event was never filmed, required_relationship MUST be NO_VALID_VISUAL.
    """
    proposition_id: str
    subject: str
    action: str
    object: str
    context: str
    visual_role: str = "DIRECT_EVIDENCE"               # DIRECT_EVIDENCE, OBJECT_PROP, ORIENTATION_BRIDGE, IRONIC_CONTRAST
    required_relationship: VisualRelationship = VisualRelationship.DIRECT_EVIDENCE
    narrative_era: Optional[str] = None                # YEAR_1 ... YEAR_7, MARAUDERS, POST_WAR
    preferred_framing: Optional[str] = None            # CLOSE_UP, MEDIUM_SHOT, WIDE_SHOT, DETAIL
    estimated_duration_sec: float = 2.0                # Typically 1.5s - 3.0s

    def __post_init__(self):
        # Normalize relationship from visual_role if given
        if isinstance(self.required_relationship, str):
            try:
                self.required_relationship = VisualRelationship(self.required_relationship)
            except ValueError:
                if self.required_relationship in ("IRONIC_CONTRAST", "CONTRAST"):
                    self.required_relationship = VisualRelationship.CONTRAST
                elif self.required_relationship in ("CONTEXTUAL_EVIDENCE", "ORIENTATION_BRIDGE", "CONTEXT"):
                    self.required_relationship = VisualRelationship.CONTEXT
                elif self.required_relationship in ("OBJECT_PROP", "OBJECT_PROP_EVIDENCE", "OBJECT_DETAIL"):
                    self.required_relationship = VisualRelationship.OBJECT_DETAIL
                else:
                    self.required_relationship = VisualRelationship.DIRECT_EVIDENCE

    @property
    def primary_subject(self) -> str:
        return self.subject

    @property
    def required_action(self) -> str:
        return self.action

    @property
    def required_objects(self) -> List[str]:
        return [self.object] if self.object and self.object.lower() != "none" else []

    @property
    def required_location(self) -> Optional[str]:
        return self.context if self.context and self.context.lower() != "none" else None

    def to_beast_requirement(self, beat_id: str = "") -> Dict[str, Any]:
        """Translates the proposition into a BEAST-compatible visual requirement dict."""
        return {
            "beat_id": beat_id or self.proposition_id,
            "primary_subject": self.subject,
            "secondary_subject": None,
            "required_action": self.action,
            "required_objects": [self.object] if self.object and self.object.lower() != "none" else [],
            "required_location": self.context if self.context and self.context.lower() != "none" else None,
            "visual_role": self.visual_role,
            "required_relationship": self.required_relationship.value,
            "narrative_era": self.narrative_era,
            "preferred_framing": self.preferred_framing or "MEDIUM_SHOT",
            "estimated_duration": self.estimated_duration_sec,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "subject": self.subject,
            "action": self.action,
            "object": self.object,
            "context": self.context,
            "visual_role": self.visual_role,
            "required_relationship": self.required_relationship.value if isinstance(self.required_relationship, VisualRelationship) else str(self.required_relationship),
            "narrative_era": self.narrative_era,
            "preferred_framing": self.preferred_framing,
            "estimated_duration_sec": self.estimated_duration_sec,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualProposition":
        rel = data.get("required_relationship", data.get("visual_role", "DIRECT_EVIDENCE"))
        return cls(
            proposition_id=data.get("proposition_id", ""),
            subject=data.get("subject", ""),
            action=data.get("action", ""),
            object=data.get("object", ""),
            context=data.get("context", ""),
            visual_role=data.get("visual_role", "DIRECT_EVIDENCE"),
            required_relationship=rel,
            narrative_era=data.get("narrative_era"),
            preferred_framing=data.get("preferred_framing"),
            estimated_duration_sec=float(data.get("estimated_duration_sec", 2.0)),
        )


@dataclass
class MultiFactPayload:
    """
    A single, verified factual payload with explicit fact boundaries.
    One fact != one shot. A fact may contain multiple sentences and multiple visual propositions.
    """
    fact_id: str
    theme: str
    claim: str
    claim_type: FactType
    canon_source: str                          # e.g., "HP Book 1, Chapter 7"
    canon_evidence: str                        # Raw excerpt / factual text
    
    # Explicit Fact Boundaries (Architecture V2)
    fact_number: int = 1                       # 1-indexed deterministic counter (1, 2, 3...)
    fact_title: str = ""                       # Short human-readable title
    fact_start: float = 0.0                    # Frame-accurate or second-accurate start
    fact_end: float = 0.0                      # Frame-accurate or second-accurate end
    narration_segments: List[str] = field(default_factory=list)  # Short conversational sentences
    visual_status: str = "PENDING"             # GROUNDED, NO_VALID_VISUAL, CONTRAST_GROUNDED
    
    importance: float = 0.8                    # 0.0 - 1.0 (weight in story)
    curiosity_score: float = 0.8               # 0.0 - 1.0 (intrigue / counter-intuitiveness)
    emotional_value: float = 0.5               # 0.0 - 1.0 (heartbreak, humor, shock)
    movie_contrast: float = 0.5                # 0.0 - 1.0 (divergence from movie depiction)
    visual_feasibility: float = 0.8            # 0.0 - 1.0 (can it be shown on screen?)
    required_evidence_type: RequiredEvidenceType = RequiredEvidenceType.DIRECT_FILM_EVIDENCE
    required_visual_evidence: List[str] = field(default_factory=list)
    fallback_visual_evidence: List[str] = field(default_factory=list)
    visual_propositions: List[VisualProposition] = field(default_factory=list)
    supporting_details: List[str] = field(default_factory=list)
    payoff_value: float = 0.5                  # 0.0 - 1.0 (punchline / reveal strength)
    source_provenance: Dict[str, Any] = field(default_factory=dict)
    
    # Book-vs-Movie Evidence Chain
    book_difference: Optional[str] = None
    movie_difference: Optional[str] = None
    why_it_matters: Optional[str] = None

    # Editorial Budgeting & Sequencing
    target_duration_sec: float = 12.0          # Estimated time budget
    target_word_count: int = 42                # Estimated word budget
    spoken_transition: Optional[str] = None    # Contextual spoken bridge before this fact
    narrative_role: str = "BODY"               # ENTRY, DEEPENING, SURPRISE, EMOTION, CLIMAX

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "theme": self.theme,
            "claim": self.claim,
            "claim_type": self.claim_type.value if isinstance(self.claim_type, FactType) else str(self.claim_type),
            "canon_source": self.canon_source,
            "canon_evidence": self.canon_evidence,
            "fact_number": self.fact_number,
            "fact_title": self.fact_title or self.fact_id.replace("_", " ").title(),
            "fact_start": self.fact_start,
            "fact_end": self.fact_end,
            "narration_segments": self.narration_segments,
            "visual_status": self.visual_status,
            "importance": self.importance,
            "curiosity_score": self.curiosity_score,
            "emotional_value": self.emotional_value,
            "movie_contrast": self.movie_contrast,
            "visual_feasibility": self.visual_feasibility,
            "required_evidence_type": self.required_evidence_type.value if isinstance(self.required_evidence_type, RequiredEvidenceType) else str(self.required_evidence_type),
            "required_visual_evidence": self.required_visual_evidence,
            "fallback_visual_evidence": self.fallback_visual_evidence,
            "visual_propositions": [vp.to_dict() for vp in self.visual_propositions],
            "supporting_details": self.supporting_details,
            "payoff_value": self.payoff_value,
            "source_provenance": self.source_provenance,
            "book_difference": self.book_difference,
            "movie_difference": self.movie_difference,
            "why_it_matters": self.why_it_matters,
            "target_duration_sec": self.target_duration_sec,
            "target_word_count": self.target_word_count,
            "spoken_transition": self.spoken_transition,
            "narrative_role": self.narrative_role,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiFactPayload":
        vps = [VisualProposition.from_dict(p) for p in data.get("visual_propositions", [])]
        ct = data.get("claim_type", FactType.BOOK_VS_MOVIE.value)
        if isinstance(ct, str):
            ct = FactType(ct)
        ret = data.get("required_evidence_type", RequiredEvidenceType.DIRECT_FILM_EVIDENCE.value)
        if isinstance(ret, str):
            ret = RequiredEvidenceType(ret)

        return cls(
            fact_id=data.get("fact_id", ""),
            theme=data.get("theme", ""),
            claim=data.get("claim", ""),
            claim_type=ct,
            canon_source=data.get("canon_source", ""),
            canon_evidence=data.get("canon_evidence", ""),
            fact_number=int(data.get("fact_number", 1)),
            fact_title=data.get("fact_title", ""),
            fact_start=float(data.get("fact_start", 0.0)),
            fact_end=float(data.get("fact_end", 0.0)),
            narration_segments=data.get("narration_segments", []),
            visual_status=data.get("visual_status", "PENDING"),
            importance=float(data.get("importance", 0.8)),
            curiosity_score=float(data.get("curiosity_score", 0.8)),
            emotional_value=float(data.get("emotional_value", 0.5)),
            movie_contrast=float(data.get("movie_contrast", 0.5)),
            visual_feasibility=float(data.get("visual_feasibility", 0.8)),
            required_evidence_type=ret,
            required_visual_evidence=data.get("required_visual_evidence", []),
            fallback_visual_evidence=data.get("fallback_visual_evidence", []),
            visual_propositions=vps,
            supporting_details=data.get("supporting_details", []),
            payoff_value=float(data.get("payoff_value", 0.5)),
            source_provenance=data.get("source_provenance", {}),
            book_difference=data.get("book_difference"),
            movie_difference=data.get("movie_difference"),
            why_it_matters=data.get("why_it_matters"),
            target_duration_sec=float(data.get("target_duration_sec", 12.0)),
            target_word_count=int(data.get("target_word_count", 42)),
            spoken_transition=data.get("spoken_transition"),
            narrative_role=data.get("narrative_role", "BODY"),
        )


@dataclass
class MultiFactTopicPack:
    """
    Authoritative Discovery Topic Package (Architecture V2).
    Enforces Content Quality -> Structure -> Fact Count.
    NO fixed fact-count requirement:
      - DISCOVERY_BIG (60–70s): Can naturally contain 5–7 facts OR 1 deep fact when stronger.
      - DISCOVERY_SHORT (25–30s): Can naturally contain 1 strong difference or compact facts.
    """
    topic_id: str
    theme: str
    hook: str
    hook_archetype: HookArchetype = HookArchetype.COUNTER_INTUITIVE_TRUTH
    facts: List[MultiFactPayload] = field(default_factory=list)
    total_target_duration: float = 65.0        # Default midpoint for DISCOVERY_BIG
    total_target_words: int = 230              # Midpoint based on ~3.5 wps
    target_speech_rate: float = 3.55           # 3.4 - 3.7 words/second
    format: MultiFactFormat = MultiFactFormat.DISCOVERY_BIG
    theme_score: float = 85.0
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    visual_feasibility_summary: float = 85.0
    expected_fact_count: int = 5
    payoff_strategy: str = "FINAL_CLIMAX_REVEAL"
    payoff_text: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    title_pattern: TitlePattern = TitlePattern.BOOK_VS_MOVIE
    suggested_title: str = ""
    validation_errors: List[str] = field(default_factory=list)
    is_valid: bool = True

    def __post_init__(self):
        # Auto-sequence fact numbers 1..N deterministically
        for idx, fact in enumerate(self.facts, 1):
            if not getattr(fact, "fact_number", None) or fact.fact_number <= 0:
                fact.fact_number = idx

    def get_fact_counter(self, fact_number: int) -> Optional[str]:
        """
        Multi-Fact Numbering rule:
        - For every Discovery Short containing MULTIPLE facts (len(facts) > 1), return formatted counter.
        - For a single-fact Discovery (len(facts) == 1), return None (counter absent).
        - For Novel Story, return None (counter absent).
        """
        fmt_str = str(self.format).upper()
        if "NOVEL_STORY" in fmt_str:
            return None
        if len(self.facts) <= 1:
            return None
        return f"FACT {fact_number:02d}"

    def validate(self) -> bool:
        """Enforces quality gates, duration boundaries, and thematic coherence."""
        errors: List[str] = []

        if not self.topic_id:
            errors.append("topic_id is required")
        if not self.theme or not self.theme.strip():
            errors.append("theme must be a non-empty statement")
        if not self.hook or not self.hook.strip():
            errors.append("hook must introduce the overarching premise")

        fmt_val = self.format.value if hasattr(self.format, "value") else str(self.format).upper()
        num_facts = len(self.facts)

        # ── DISCOVERY_BIG Validation (60–70s, ceiling 80.9s for legacy) ─────────────
        if "DISCOVERY_BIG" in fmt_val or "MULTI_FACT" in fmt_val:
            # Target 60-70s (with grace tolerance up to 80.9s for legacy compatibility)
            if self.total_target_duration < 58.0:
                errors.append(f"DISCOVERY_BIG target_duration {self.total_target_duration}s below minimum 60.0s (bounds: 60.0–70.0s)")
            elif self.total_target_duration > 80.9:
                errors.append(f"DISCOVERY_BIG target_duration {self.total_target_duration}s exceeds maximum 70.0s (ceiling 80.9s)")
            if num_facts < 1:
                errors.append("DISCOVERY_BIG must contain at least 1 verified factual payload")
            # Note: No fixed minimum 4/5 facts required; 1 deep fact or 5-7 facts are both valid!

        # ── DISCOVERY_SHORT Validation (25–30s) ──────────────────────────────────
        elif "DISCOVERY_SHORT" in fmt_val:
            if self.total_target_duration < 24.0:
                errors.append(f"DISCOVERY_SHORT target_duration {self.total_target_duration}s below minimum 25.0s (bounds: 25.0–30.0s)")
            elif self.total_target_duration > 32.0:
                errors.append(f"DISCOVERY_SHORT target_duration {self.total_target_duration}s exceeds maximum 30.0s (bounds: 25.0–30.0s)")
            if num_facts < 1:
                errors.append("DISCOVERY_SHORT must contain at least 1 verified factual payload")
            # Note: No fixed fact-count requirement; 1 strong difference or compact facts valid!

        # ── NOVEL_STORY Validation (45–60s) ─────────────────────────────────────
        elif "NOVEL_STORY" in fmt_val:
            if self.total_target_duration < 44.0:
                errors.append(f"NOVEL_STORY target_duration {self.total_target_duration}s below minimum 45.0s (bounds: 45.0–60.0s)")
            elif self.total_target_duration > 62.0:
                errors.append(f"NOVEL_STORY target_duration {self.total_target_duration}s exceeds maximum 60.0s (bounds: 45.0–60.0s)")

        # Fact validity & proposition check
        seen_claims = set()
        for idx, fact in enumerate(self.facts, 1):
            fact.fact_number = idx
            if not fact.claim or not fact.claim.strip():
                errors.append(f"fact[{idx}] has empty claim")
            norm_claim = fact.claim.lower().strip()
            if norm_claim in seen_claims:
                errors.append(f"Duplicate fact claim detected at index {idx}: '{fact.claim}'")
            seen_claims.add(norm_claim)

            if not fact.canon_evidence or not fact.canon_evidence.strip():
                errors.append(f"fact[{idx}] ({fact.fact_id}) lacks canon_evidence provenance")
            if not fact.visual_propositions:
                errors.append(f"fact[{idx}] ({fact.fact_id}) must have at least one VisualProposition")

        self.validation_errors = errors
        self.is_valid = (len(errors) == 0)
        return self.is_valid

    def validate_content_architecture(self) -> Tuple[bool, List[str]]:
        """
        Explicit Content Architecture V2 validation helper:
        Returns (is_valid, validation_errors).
        """
        valid = self.validate()
        return valid, list(self.validation_errors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "theme": self.theme,
            "hook": self.hook,
            "hook_archetype": self.hook_archetype.value if isinstance(self.hook_archetype, HookArchetype) else str(self.hook_archetype),
            "facts": [f.to_dict() for f in self.facts],
            "total_target_duration": self.total_target_duration,
            "total_target_words": self.total_target_words,
            "target_speech_rate": self.target_speech_rate,
            "format": self.format.value if isinstance(self.format, MultiFactFormat) else str(self.format),
            "theme_score": self.theme_score,
            "evidence_summary": self.evidence_summary,
            "visual_feasibility_summary": self.visual_feasibility_summary,
            "expected_fact_count": self.expected_fact_count,
            "payoff_strategy": self.payoff_strategy,
            "payoff_text": self.payoff_text,
            "provenance": self.provenance,
            "title_pattern": self.title_pattern.value if isinstance(self.title_pattern, TitlePattern) else str(self.title_pattern),
            "suggested_title": self.suggested_title,
            "validation_errors": self.validation_errors,
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiFactTopicPack":
        facts = [MultiFactPayload.from_dict(f) for f in data.get("facts", [])]
        hook_arch = data.get("hook_archetype", HookArchetype.COUNTER_INTUITIVE_TRUTH.value)
        if isinstance(hook_arch, str):
            hook_arch = HookArchetype(hook_arch)
        fmt = data.get("format", MultiFactFormat.DISCOVERY_BIG.value)
        if isinstance(fmt, str):
            try:
                fmt = MultiFactFormat(fmt)
            except ValueError:
                fmt = MultiFactFormat.DISCOVERY_BIG
        tp = data.get("title_pattern", TitlePattern.BOOK_VS_MOVIE.value)
        if isinstance(tp, str):
            tp = TitlePattern(tp)

        pack = cls(
            topic_id=data.get("topic_id", ""),
            theme=data.get("theme", ""),
            hook=data.get("hook", ""),
            hook_archetype=hook_arch,
            facts=facts,
            total_target_duration=float(data.get("total_target_duration", 65.0)),
            total_target_words=int(data.get("total_target_words", 230)),
            target_speech_rate=float(data.get("target_speech_rate", 3.55)),
            format=fmt,
            theme_score=float(data.get("theme_score", 85.0)),
            evidence_summary=data.get("evidence_summary", {}),
            visual_feasibility_summary=float(data.get("visual_feasibility_summary", 85.0)),
            expected_fact_count=int(data.get("expected_fact_count", len(facts))),
            payoff_strategy=data.get("payoff_strategy", "FINAL_CLIMAX_REVEAL"),
            payoff_text=data.get("payoff_text", ""),
            provenance=data.get("provenance", {}),
            title_pattern=tp,
            suggested_title=data.get("suggested_title", ""),
            validation_errors=data.get("validation_errors", []),
            is_valid=data.get("is_valid", True),
        )
        return pack
