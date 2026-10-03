"""
STORY FORGE — Phase 4: Visual EDL & Candidate Arbitration Data Models
======================================================================
Contracts and schemas for Locked Narration, Visual Beats, Candidate Evaluation,
Candidate Arbitration, 9:16 Crop Feasibility, and the Canonical Visual EDL.
"""

from enum import Enum
import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class CoverageRequirement(str, Enum):
    """Visual coverage requirement for a narrative beat."""
    DIRECT = "DIRECT"                      # Mandatory physical/visual evidence required
    VISUAL_OPTIONAL = "VISUAL_OPTIONAL"    # Abstract, contextual, comparative, or book-vs-movie claim


class CoverageState(str, Enum):
    """Explicit fulfillment status for an EDL entry."""
    VERIFIED_DIRECT = "VERIFIED_DIRECT"    # Physical evidence independently proven
    VERIFIED_CONTEXT = "VERIFIED_CONTEXT"  # Environmental / contextual evidence proven
    VISUAL_OPTIONAL = "VISUAL_OPTIONAL"    # Non-visual beat fulfilled with contextual imagery
    UNFULFILLED = "UNFULFILLED"            # Direct beat missing verified footage (causes fail-closed)


class CropFeasibility(str, Enum):
    """9:16 vertical re-framing feasibility level."""
    FIT = "FIT"                            # Direct fit within 9:16 safe zone
    FIT_WITH_TRACKING = "FIT_WITH_TRACKING"# Preserved via subject-aware pan/tracking crop
    FIT_WITH_SCALE = "FIT_WITH_SCALE"      # Preserved with scale adjustment
    IMPOSSIBLE = "IMPOSSIBLE"              # Required entities clipped or split; candidate rejected


class WordTimestamp(BaseModel):
    """Exact word-level timing from locked narration tts."""
    word: str
    start_sec: float
    end_sec: float
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


class SentenceBoundary(BaseModel):
    """Sentence boundary with word index span."""
    sentence_index: int
    text: str
    start_sec: float
    end_sec: float
    word_start_idx: int
    word_end_idx: int


class LockedNarrationInput(BaseModel):
    """
    Locked narration input contract. Fail closed if any required field is missing.
    """
    content_id: str
    script_hash: str
    narration_hash: str
    exact_narration_duration: float
    word_timestamps: List[WordTimestamp]
    sentence_boundaries: List[SentenceBoundary]
    narration_text: str
    editorial_beat_boundaries: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("exact_narration_duration")
    @classmethod
    def validate_duration(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("exact_narration_duration must be strictly positive")
        return v

    @field_validator("word_timestamps")
    @classmethod
    def validate_word_timestamps(cls, v: List[WordTimestamp]) -> List[WordTimestamp]:
        if not v:
            raise ValueError("word_timestamps cannot be empty in LockedNarrationInput")
        return v

    def compute_lock_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.content_id.encode())
        h.update(self.script_hash.encode())
        h.update(self.narration_hash.encode())
        h.update(str(round(self.exact_narration_duration, 4)).encode())
        h.update(str(len(self.word_timestamps)).encode())
        return h.hexdigest()


class VisualBeat(BaseModel):
    """
    Compiled visual proposition mapped to exact narration timestamps.
    """
    beat_id: str
    narration_start: float
    narration_end: float
    text_span: str
    narrative_role: str = "core_fact"

    visual_assertion: str
    required_entities: List[str] = Field(default_factory=list)
    required_objects: List[str] = Field(default_factory=list)
    required_action: Optional[str] = None
    required_state: Optional[str] = None
    required_relationship: Optional[str] = None
    required_location: Optional[str] = None

    direct_visual_requirement: bool = True
    coverage_requirement: CoverageRequirement = CoverageRequirement.DIRECT

    @property
    def duration(self) -> float:
        return max(0.0, self.narration_end - self.narration_start)

    def compute_beat_hash(self) -> str:
        payload = f"{self.beat_id}:{self.narration_start}:{self.narration_end}:{self.visual_assertion}:{self.coverage_requirement.value}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class SearchDiagnosticRecord(BaseModel):
    """Records audit details of queries and fallback levels attempted for a beat."""
    beat_id: str
    queries_attempted: List[str] = Field(default_factory=list)
    search_levels_attempted: List[str] = Field(default_factory=list)
    candidates_returned: int = 0
    candidates_rejected: int = 0
    rejection_reasons: List[str] = Field(default_factory=list)
    best_candidate_score: float = 0.0
    physical_evidence_failure: Optional[str] = None
    crop_failure: Optional[str] = None
    duration_failure: Optional[str] = None
    is_exhausted: bool = False


class EvaluatedCandidate(BaseModel):
    """
    A single candidate video interval evaluated through Phase 2 perception,
    Phase 3 physical evidence, and 9:16 crop feasibility.
    """
    candidate_id: str
    beat_id: str
    source_movie_id: int
    source_video: str
    source_interval: Tuple[float, float]
    verified_sub_interval: Tuple[float, float]

    semantic_score: float = 0.0
    perception_confidence: float = 0.0
    physical_evidence_confidence: float = 0.0
    overall_arbitration_score: float = 0.0

    is_perception_verified: bool = False
    is_physical_verified: bool = False
    crop_feasibility: CropFeasibility = CropFeasibility.FIT
    crop_window: Optional[Dict[str, Any]] = None

    verified_entities: List[str] = Field(default_factory=list)
    verified_action: Optional[str] = None
    verified_state: Optional[str] = None

    semantic_relevance_score: float = 1.0
    is_semantically_verified: bool = True
    relevance_rejection_reasons: List[str] = Field(default_factory=list)

    evidence_hash: str = ""
    rejection_reason: Optional[str] = None
    is_rejected: bool = False
    retrieval_level: str = "L1"

    @property
    def verified_duration(self) -> float:
        return max(0.0, self.verified_sub_interval[1] - self.verified_sub_interval[0])


class EDLEntry(BaseModel):
    """
    Canonical Entry in the Story Forge Visual Edit Decision List (EDL).
    """
    beat_id: str
    narration_start: float
    narration_end: float

    source_movie_id: int
    source_video: str
    source_clip_start: float
    source_clip_end: float

    evidence_id: str
    evidence_class: str

    required_entities: List[str] = Field(default_factory=list)
    verified_entities: List[str] = Field(default_factory=list)

    required_action: Optional[str] = None
    verified_action: Optional[str] = None

    crop_requirements: Dict[str, Any] = Field(default_factory=dict)
    crop_feasibility: CropFeasibility = CropFeasibility.FIT

    confidence: float = 0.0
    evidence_hash: str = ""
    lineage_hash: str = ""

    reuse_group: Optional[str] = None
    candidate_rank: int = 1
    coverage_state: CoverageState = CoverageState.VERIFIED_DIRECT

    @property
    def narration_duration(self) -> float:
        return max(0.0, self.narration_end - self.narration_start)

    @property
    def clip_duration(self) -> float:
        return max(0.0, self.source_clip_end - self.source_clip_start)


class EDLLineage(BaseModel):
    """
    Cryptographic lineage binding all pipeline inputs and decisions into the EDL.
    """
    content_id: str
    script_hash: str
    narration_hash: str
    beat_hash: str
    candidate_hash: str
    perception_hash: str
    evidence_hash: str
    crop_feasibility_hash: str
    arbitration_hash: str
    edl_hash: str

    def is_valid(self) -> bool:
        return bool(self.edl_hash and len(self.edl_hash) == 64)


class AntiLoopAuditResult(BaseModel):
    """
    Audits the complete visual EDL for loops, repeated footage, or invalid reuse.
    """
    passed: bool
    total_entries: int
    unique_footage_intervals: int
    repeated_source_count: int = 0
    repeated_evidence_hashes: List[str] = Field(default_factory=list)
    stream_loops_detected: int = 0
    rejections: List[str] = Field(default_factory=list)
    explanation: str = ""


class VisualEDL(BaseModel):
    """
    Complete, verified, and arbitrated Visual Edit Decision List for a Short.
    Produced before any video rendering begins.
    """
    edl_id: str
    content_id: str
    total_narration_duration: float
    directly_covered_duration: float
    optional_duration: float
    unfulfilled_duration: float
    coverage_percentage: float

    entries: List[EDLEntry] = Field(default_factory=list)
    anti_loop_audit: AntiLoopAuditResult
    diagnostics: List[SearchDiagnosticRecord] = Field(default_factory=list)
    lineage: EDLLineage
    is_complete: bool = False
    failure_reason: Optional[str] = None

    def compute_summary_table(self) -> str:
        lines = [
            f"=== VISUAL EDL TIMELINE SUMMARY: {self.edl_id} ===",
            f"Content ID: {self.content_id} | Total Duration: {self.total_narration_duration:.2f}s",
            f"Direct Coverage: {self.directly_covered_duration:.2f}s | Coverage: {self.coverage_percentage * 100:.1f}%",
            f"Anti-Loop Audit: {'PASSED' if self.anti_loop_audit.passed else 'FAILED'}",
            "-" * 80,
            f"{'INTERVAL':<14} | {'BEAT ID':<10} | {'MOVIE':<6} | {'CLIP WINDOW':<16} | {'STATUS':<16} | {'ACTION / ENTITY'}",
            "-" * 80,
        ]
        for e in self.entries:
            interval_str = f"{e.narration_start:.2f}–{e.narration_end:.2f}s"
            clip_str = f"{e.source_clip_start:.2f}–{e.source_clip_end:.2f}s"
            desc = e.verified_action or ", ".join(e.verified_entities) or "Context"
            lines.append(
                f"{interval_str:<14} | {e.beat_id:<10} | HP{e.source_movie_id:<4} | {clip_str:<16} | {e.coverage_state.value:<16} | {desc}"
            )
        lines.append("-" * 80)
        return "\n".join(lines)
