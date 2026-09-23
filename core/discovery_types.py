"""
Discovery Content Types and Information Architecture
===================================================
Defines canonical Discovery subtypes, visual classifications, and 
the 11-point Discovery Quality Gate for Harry Potter Shorts.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


class DiscoverySubtype(str, Enum):
    """Explicit Discovery subtypes governing script format and structure."""
    DISCOVERY_FACT = "DISCOVERY_FACT"
    DISCOVERY_BOOK_MOVIE_DIFFERENCE = "DISCOVERY_BOOK_MOVIE_DIFFERENCE"
    DISCOVERY_OMITTED_SCENE = "DISCOVERY_OMITTED_SCENE"
    DISCOVERY_NOVEL_ONLY_DETAIL = "DISCOVERY_NOVEL_ONLY_DETAIL"
    DISCOVERY_CHARACTER_DETAIL = "DISCOVERY_CHARACTER_DETAIL"
    DISCOVERY_BEHIND_THE_SCENES = "DISCOVERY_BEHIND_THE_SCENES"
    DISCOVERY_MOVIE_DETAIL = "DISCOVERY_MOVIE_DETAIL"
    DISCOVERY_TRIVIA = "DISCOVERY_TRIVIA"


class DiscoveryTier(str, Enum):
    """
    Discovery format tier.
    DEEP_DISCOVERY: Primary format (68.0–78.0s, hard ceiling 80.9s, ~240–280 words, 3.4–3.7 wps).
    MICRO_DISCOVERY: Exceptional experimental format (max ~5% uploads, ~25–35s, ~60–80 words).
    """
    DEEP_DISCOVERY = "DEEP_DISCOVERY"
    MICRO_DISCOVERY = "MICRO_DISCOVERY"


class DiscoveryStoryStructure(str, Enum):
    """
    Canonical narrative structures for Deep Discovery Shorts.
    TEMPLATE_A_CURATED_LISTICLE: Hook -> Rapid Entry -> Secondary Point -> Anchor Highlight -> Quick-Fire Points -> Payoff -> Engagement.
    TEMPLATE_B_MYTH_BUSTER: Curiosity Hook -> Common Perception -> Canon Contradiction -> Escalating Evidence -> Deeper Truth / Climax -> Payoff -> Engagement.
    """
    TEMPLATE_A_CURATED_LISTICLE = "TEMPLATE_A_CURATED_LISTICLE"
    TEMPLATE_B_MYTH_BUSTER = "TEMPLATE_B_MYTH_BUSTER"


class HookArchetype(str, Enum):
    """
    Topic-aware hook archetypes. Frame 0 immediate narrative/audio engagement with zero throat-clearing.
    """
    INCREDULITY_AWARENESS_TEST = "INCREDULITY_AWARENESS_TEST"
    COUNTER_INTUITIVE_TRUTH = "COUNTER_INTUITIVE_TRUTH"
    ABSURD_COMIC_REALITY = "ABSURD_COMIC_REALITY"
    DIRECT_CHALLENGE = "DIRECT_CHALLENGE"
    DIALOGUE_COLD_OPEN = "DIALOGUE_COLD_OPEN"


class EvidenceRoute(str, Enum):
    """
    Tri-partite evidence routing:
    NOVEL_CANON: Grounded in ingested novel FTS/corpus.
    MOVIE_CANON: Grounded in movie SRT/timestamps/scene index.
    BTS_PRODUCTION: Grounded in verified production/archival source.
    """
    NOVEL_CANON = "NOVEL_CANON"
    MOVIE_CANON = "MOVIE_CANON"
    BTS_PRODUCTION = "BTS_PRODUCTION"


class PayoffType(str, Enum):
    """Deep discovery payoff and epiphany classifications."""
    REVEAL = "REVEAL"
    REFRAME = "REFRAME"
    IRONY = "IRONY"
    COMEDIC_PUNCHLINE = "COMEDIC_PUNCHLINE"
    CANON_CLARIFICATION = "CANON_CLARIFICATION"
    BOOK_MOVIE_REALIZATION = "BOOK_MOVIE_REALIZATION"
    DEBATE_QUESTION = "DEBATE_QUESTION"


class TitlePattern(str, Enum):
    """Curiosity-driven, non-deceptive title formula patterns."""
    CURIOSITY_QUESTION = "CURIOSITY_QUESTION"
    HIDDEN_DETAIL = "HIDDEN_DETAIL"
    COUNTER_INTUITIVE_TRUTH = "COUNTER_INTUITIVE_TRUTH"
    BOOK_VS_MOVIE = "BOOK_VS_MOVIE"
    MYSTERY_REVEAL = "MYSTERY_REVEAL"
    CHALLENGE = "CHALLENGE"


class PacingPhase(str, Enum):
    """Editorial target pacing phases for visual rhythm (Step 1 intent)."""
    HOOK = "HOOK"          # 0.8 - 1.2s visual rhythm
    SETUP = "SETUP"        # 1.2 - 1.6s
    EVIDENCE = "EVIDENCE"  # 1.4 - 1.8s
    ANCHOR = "ANCHOR"      # 2.2 - 3.2s (asymmetric emphasis)
    PAYOFF = "PAYOFF"      # 1.0 - 1.5s


class DiscoveryRouting(str, Enum):
    """Candidate routing decision."""
    DEEP_DISCOVERY = "DEEP_DISCOVERY"
    NOVEL_STORY = "NOVEL_STORY"
    HOLD = "HOLD"
    REJECT = "REJECT"
    MICRO_DISCOVERY = "MICRO_DISCOVERY"


class VisualClassification(str, Enum):
    """
    Visual-to-Script relationship classification.
    DIRECT: Footage directly depicts the fact/object/action.
    CONTEXTUAL: Footage provides authentic scene/character context for external factual voiceover.
    UNSUPPORTED: Visuals have no meaningful relation to the topic (rejected).
    """
    DIRECT = "DIRECT"
    CONTEXTUAL = "CONTEXTUAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class EvidencePoint:
    """A single factual claim with strict provenance routing."""
    claim: str
    evidence_route: str          # NOVEL_CANON, MOVIE_CANON, BTS_PRODUCTION
    source_id: str               # chunk_id, movie_timestamp/chunk, or bts_citation
    source_excerpt: str          # Raw canon or archival excerpt
    verified: bool = True
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "evidence_route": self.evidence_route,
            "source_id": self.source_id,
            "source_excerpt": self.source_excerpt,
            "verified": self.verified,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidencePoint":
        return cls(
            claim=data.get("claim", ""),
            evidence_route=data.get("evidence_route", EvidenceRoute.NOVEL_CANON.value),
            source_id=data.get("source_id", ""),
            source_excerpt=data.get("source_excerpt", ""),
            verified=data.get("verified", True),
            notes=data.get("notes"),
        )


@dataclass
class DeepDiscoveryStoryPlan:
    """
    Architectural plan for a Deep Discovery Short.
    Enforces the Thesis -> Evidence -> Contrast -> Epiphany -> Payoff narrative spine.
    """
    topic_id: str
    discovery_type: str
    discovery_tier: DiscoveryTier = DiscoveryTier.DEEP_DISCOVERY
    story_structure: DiscoveryStoryStructure = DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE
    hook_archetype: HookArchetype = HookArchetype.COUNTER_INTUITIVE_TRUTH
    evidence_route: EvidenceRoute = EvidenceRoute.NOVEL_CANON
    thesis: str = ""
    evidence_points: List[EvidencePoint] = field(default_factory=list)
    anchor_point: Optional[EvidencePoint] = None
    insider_epiphany: str = ""
    payoff_type: PayoffType = PayoffType.BOOK_MOVIE_REALIZATION
    payoff_text: str = ""
    title_pattern: TitlePattern = TitlePattern.BOOK_VS_MOVIE
    suggested_title: str = ""
    expected_duration: float = 72.0        # 68.0–78.0s (hard ceiling 80.9s)
    target_word_count: int = 255           # ~240–280 words
    target_speech_rate: float = 3.55       # 3.4–3.7 words/sec
    topic_score: float = 0.0
    canon_depth: float = 0.0
    movie_contrast: float = 0.0
    curiosity_factor: float = 0.0
    visual_feasibility: float = 0.0
    pacing_intent: Optional[Dict[str, Any]] = None
    routing_decision: str = "DEEP_DISCOVERY"
    validation_errors: List[str] = field(default_factory=list)
    is_valid: bool = True

    def validate(self) -> bool:
        """Validates all architectural constraints and invariants for Deep Discovery."""
        errors = []
        if not self.topic_id:
            errors.append("topic_id is required")
        if not self.thesis or not self.thesis.strip():
            errors.append("thesis must be a non-empty statement")

        # Tier bounds
        if self.discovery_tier == DiscoveryTier.DEEP_DISCOVERY:
            if not (65.0 <= self.expected_duration <= 80.9):
                errors.append(f"expected_duration {self.expected_duration}s exceeds Deep Discovery bounds (65.0-80.9s)")
            if not (220 <= self.target_word_count <= 300):
                errors.append(f"target_word_count {self.target_word_count} exceeds Deep Discovery bounds (220-300 words)")
            if not (3.2 <= self.target_speech_rate <= 3.9):
                errors.append(f"target_speech_rate {self.target_speech_rate} wps out of bounds (3.2-3.9 wps)")

        # Evidence validation: all claims must have verified provenance
        if not self.evidence_points:
            errors.append("evidence_points must contain at least 1 verified evidence point")
        for idx, ep in enumerate(self.evidence_points):
            if not ep.verified:
                errors.append(f"evidence_point[{idx}] is unverified: {ep.claim}")
            if not ep.source_id or not ep.source_id.strip():
                errors.append(f"evidence_point[{idx}] lacks valid source_id: {ep.claim}")
            if not ep.source_excerpt or not ep.source_excerpt.strip():
                errors.append(f"evidence_point[{idx}] lacks supporting source_excerpt: {ep.claim}")

        # Structure-specific validation
        if self.story_structure == DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE:
            if len(self.evidence_points) < 2:
                errors.append("Template A (Curated Listicle) requires at least 2 distinct evidence points")
            if self.anchor_point is None:
                errors.append("Template A requires an anchor_point for asymmetric emphasis")

        self.validation_errors = errors
        self.is_valid = len(errors) == 0
        return self.is_valid

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "discovery_type": str(self.discovery_type),
            "discovery_tier": self.discovery_tier.value if isinstance(self.discovery_tier, DiscoveryTier) else str(self.discovery_tier),
            "story_structure": self.story_structure.value if isinstance(self.story_structure, DiscoveryStoryStructure) else str(self.story_structure),
            "hook_archetype": self.hook_archetype.value if isinstance(self.hook_archetype, HookArchetype) else str(self.hook_archetype),
            "evidence_route": self.evidence_route.value if isinstance(self.evidence_route, EvidenceRoute) else str(self.evidence_route),
            "thesis": self.thesis,
            "evidence_points": [ep.to_dict() for ep in self.evidence_points],
            "anchor_point": self.anchor_point.to_dict() if self.anchor_point else None,
            "insider_epiphany": self.insider_epiphany,
            "payoff_type": self.payoff_type.value if isinstance(self.payoff_type, PayoffType) else str(self.payoff_type),
            "payoff_text": self.payoff_text,
            "title_pattern": self.title_pattern.value if isinstance(self.title_pattern, TitlePattern) else str(self.title_pattern),
            "suggested_title": self.suggested_title,
            "expected_duration": self.expected_duration,
            "target_word_count": self.target_word_count,
            "target_speech_rate": self.target_speech_rate,
            "topic_score": self.topic_score,
            "canon_depth": self.canon_depth,
            "movie_contrast": self.movie_contrast,
            "curiosity_factor": self.curiosity_factor,
            "visual_feasibility": self.visual_feasibility,
            "pacing_intent": self.pacing_intent,
            "routing_decision": self.routing_decision,
            "validation_errors": self.validation_errors,
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeepDiscoveryStoryPlan":
        eps = [EvidencePoint.from_dict(ep) for ep in data.get("evidence_points", [])]
        anchor = EvidencePoint.from_dict(data["anchor_point"]) if data.get("anchor_point") else None
        
        tier = data.get("discovery_tier", DiscoveryTier.DEEP_DISCOVERY.value)
        if isinstance(tier, str):
            tier = DiscoveryTier(tier)
            
        struct = data.get("story_structure", DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE.value)
        if isinstance(struct, str):
            struct = DiscoveryStoryStructure(struct)
            
        hook = data.get("hook_archetype", HookArchetype.COUNTER_INTUITIVE_TRUTH.value)
        if isinstance(hook, str):
            hook = HookArchetype(hook)
            
        ev_route = data.get("evidence_route", EvidenceRoute.NOVEL_CANON.value)
        if isinstance(ev_route, str):
            ev_route = EvidenceRoute(ev_route)
            
        payoff_t = data.get("payoff_type", PayoffType.BOOK_MOVIE_REALIZATION.value)
        if isinstance(payoff_t, str):
            payoff_t = PayoffType(payoff_t)
            
        title_p = data.get("title_pattern", TitlePattern.BOOK_VS_MOVIE.value)
        if isinstance(title_p, str):
            title_p = TitlePattern(title_p)

        plan = cls(
            topic_id=data.get("topic_id", ""),
            discovery_type=data.get("discovery_type", DiscoverySubtype.DISCOVERY_FACT.value),
            discovery_tier=tier,
            story_structure=struct,
            hook_archetype=hook,
            evidence_route=ev_route,
            thesis=data.get("thesis", ""),
            evidence_points=eps,
            anchor_point=anchor,
            insider_epiphany=data.get("insider_epiphany", ""),
            payoff_type=payoff_t,
            payoff_text=data.get("payoff_text", ""),
            title_pattern=title_p,
            suggested_title=data.get("suggested_title", ""),
            expected_duration=data.get("expected_duration", 72.0),
            target_word_count=data.get("target_word_count", 255),
            target_speech_rate=data.get("target_speech_rate", 3.55),
            topic_score=data.get("topic_score", 0.0),
            canon_depth=data.get("canon_depth", 0.0),
            movie_contrast=data.get("movie_contrast", 0.0),
            curiosity_factor=data.get("curiosity_factor", 0.0),
            visual_feasibility=data.get("visual_feasibility", 0.0),
            pacing_intent=data.get("pacing_intent"),
            routing_decision=data.get("routing_decision", "DEEP_DISCOVERY"),
            validation_errors=data.get("validation_errors", []),
            is_valid=data.get("is_valid", True),
        )
        return plan


@dataclass
class DiscoveryQAResult:
    """Detailed evaluation from the 11-Point Discovery Quality Gate."""
    passed: bool
    subtype: str
    fact_identifiable: bool            # Check A
    fact_explicitly_stated: bool       # Check B
    subject_in_first_5s: bool          # Check C
    feels_like_information: bool       # Check D
    subtype_structure_valid: bool      # Check E
    book_movie_both_stated: bool       # Check F (if BOOK_MOVIE_DIFFERENCE)
    omission_explicitly_stated: bool   # Check G (if OMITTED_SCENE)
    production_fact_stated: bool       # Check H (if BEHIND_THE_SCENES)
    avoids_chronological_story: bool   # Check I
    is_standalone: bool                # Check J
    no_part_markers: bool              # Check K
    no_throat_clearing: bool = True
    duration_within_tier_bounds: bool = True
    word_count_within_tier_bounds: bool = True
    failure_reasons: List[str] = field(default_factory=list)

