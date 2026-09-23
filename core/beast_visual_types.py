"""
STORY FORGE — BEAST Visual Matching Engine Data Models & Contracts
================================================================================
Defines unified contracts for multi-stage video semantic retrieval and temporal verification:
  - BeastVisualRequirement: Structured semantic and compositional query contract
  - MultiFrameSample: 5-frame equidistant temporal sequence (10%, 30%, 50%, 70%, 90%)
  - BeastCandidateShot: Atomic video segment with multi-frame metadata and embeddings
  - BeastVLMVerificationResult: Structured JSON gate response from multimodal VLM
  - BeastScoringBreakdown: Multi-criteria score vector with penalties and decisions
  - BeastScoringWeights: Configurable weights for composite ranking
"""

import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from core.composition_models import ShotScale, NormalizedBBox, ShotCompositionAssessment
from core.storyboard_types import VisualRole, TransitionIntent


class NarrativeEra(str, Enum):
    """Temporal / narrative era within the Harry Potter canon."""
    YEAR_1 = "YEAR_1"       # Sorcerer's Stone (11 years old)
    YEAR_2 = "YEAR_2"       # Chamber of Secrets (12 years old)
    YEAR_3 = "YEAR_3"       # Prisoner of Azkaban (13 years old)
    YEAR_4 = "YEAR_4"       # Goblet of Fire (14 years old)
    YEAR_5 = "YEAR_5"       # Order of the Phoenix (15 years old)
    YEAR_6 = "YEAR_6"       # Half-Blood Prince (16 years old)
    YEAR_7 = "YEAR_7"       # Deathly Hallows Part 1 & 2 (17-18 years old, Battle of Hogwarts)
    FLASHBACK = "FLASHBACK" # Historical lore (Tom Riddle, Marauders, Founders)
    ANY = "ANY"


@dataclass
class MultiFrameSample:
    """
    Equidistant temporal frame sequence sampled across a shot:
    Alpha percentiles: [0.10, 0.30, 0.50, 0.70, 0.90]
    """
    shot_id: str
    source_video_path: str
    timestamps: List[float] = field(default_factory=list)      # Exact seconds in source
    percentiles: List[float] = field(default_factory=list)     # [0.10, 0.30, 0.50, 0.70, 0.90]
    frame_paths: List[str] = field(default_factory=list)       # Local cached frame paths
    frame_embeddings: List[List[float]] = field(default_factory=list)
    motion_scores: List[float] = field(default_factory=list)   # Frame-to-frame optical/pixel deltas

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "source_video_path": self.source_video_path,
            "timestamps": [round(t, 3) for t in self.timestamps],
            "percentiles": self.percentiles,
            "frame_paths": self.frame_paths,
            "motion_scores": [round(m, 3) for m in self.motion_scores],
            "has_embeddings": len(self.frame_embeddings) > 0,
        }


@dataclass
class BeastCandidateShot:
    """
    Atomic video shot from source video with rich multi-frame metadata.
    """
    shot_id: str
    source_video: str
    movie_number: int
    start_seconds: float
    end_seconds: float
    duration: float
    narrative_era: NarrativeEra = NarrativeEra.ANY
    scene_description: str = ""
    characters_present: List[str] = field(default_factory=list)
    detected_faces: int = 0
    primary_character_prominence: float = 0.0                  # 0.0 to 1.0 (relative area of primary face/body)
    objects_present: List[str] = field(default_factory=list)   # Canonical items detected
    actions_depicted: List[str] = field(default_factory=list)  # Atomic actions
    environment: str = ""                                      # Canonical location
    ocr_text: str = ""                                         # On-screen text
    shot_scale: ShotScale = ShotScale.MEDIUM_SHOT
    multi_frame_sample: Optional[MultiFrameSample] = None
    shot_embedding: Optional[List[float]] = None               # Aggregated visual embedding
    composition: Optional[ShotCompositionAssessment] = None
    is_dialogue_shot: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "source_video": self.source_video,
            "movie_number": self.movie_number,
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "duration": round(self.duration, 3),
            "narrative_era": self.narrative_era.value,
            "scene_description": self.scene_description,
            "characters_present": self.characters_present,
            "detected_faces": self.detected_faces,
            "primary_character_prominence": round(self.primary_character_prominence, 3),
            "objects_present": self.objects_present,
            "actions_depicted": self.actions_depicted,
            "environment": self.environment,
            "ocr_text": self.ocr_text,
            "shot_scale": self.shot_scale.value if isinstance(self.shot_scale, ShotScale) else str(self.shot_scale),
            "is_dialogue_shot": self.is_dialogue_shot,
            "composition": self.composition.to_dict() if self.composition else None,
            "multi_frame_sample": self.multi_frame_sample.to_dict() if self.multi_frame_sample else None,
        }


@dataclass
class BeastVisualRequirement:
    """
    Fine-grained semantic and compositional query contract extracted from narration beat.
    """
    beat_id: str
    narration_text: str
    narrative_phase: str = "EVIDENCE"                          # HOOK, EVIDENCE, ANCHOR, PAYOFF
    primary_subject: str = ""                                  # e.g., "Neville Longbottom"
    secondary_subject: Optional[str] = None                    # e.g., "Sorting Hat"
    required_action: str = ""                                  # e.g., "pleading / arguing / requesting"
    required_objects: List[str] = field(default_factory=list)  # e.g., ["Sorting Hat"]
    required_location: Optional[str] = None                   # e.g., "Great Hall"
    interaction_type: str = ""                                 # e.g., "Neville <-> Sorting Hat"
    emotional_state: Optional[str] = None                      # e.g., "desperate / anxious"
    visual_role: VisualRole = VisualRole.DIRECT_EVIDENCE       # DIRECT_EVIDENCE, CONTEXTUAL_ENVIRONMENT, etc.
    preferred_framing: List[ShotScale] = field(default_factory=list)
    forbidden_characters: List[str] = field(default_factory=list)
    negative_constraints: List[str] = field(default_factory=list) # Hard rejection criteria
    temporal_requirement: str = ""                             # e.g., "actual interaction, not merely standing nearby"
    expected_era: NarrativeEra = NarrativeEra.ANY              # Enforces canonical era match
    allow_close_up: bool = False                               # Explicit permission for CLOSE_UP
    confidence_threshold: float = 65.0                         # Minimum final score to accept candidate

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["visual_role"] = self.visual_role.value if isinstance(self.visual_role, VisualRole) else str(self.visual_role)
        d["preferred_framing"] = [s.value if isinstance(s, ShotScale) else str(s) for s in self.preferred_framing]
        d["expected_era"] = self.expected_era.value
        return d


@dataclass
class BeastVLMVerificationResult:
    """
    Structured JSON verdict returned by the Multimodal Vision-Language Model gate.
    """
    match: bool = False
    confidence: float = 0.0                                    # 0 to 100
    subjects_present: List[str] = field(default_factory=list)
    action_present: bool = False
    object_present: bool = False
    location_consistent: bool = False
    interaction_present: bool = False
    contradiction_detected: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BeastScoringWeights:
    """Configurable weights for the multi-stage reranking model."""
    w_semantic: float = 0.20
    w_character: float = 0.15
    w_secondary_character: float = 0.10
    w_action: float = 0.20
    w_object: float = 0.15
    w_location: float = 0.05
    w_temporal: float = 0.05
    w_vlm: float = 0.10
    # Penalty weights (subtracted)
    p_contradiction: float = 100.0                             # Severe disqualification penalty
    p_crop_risk: float = 25.0
    p_repetition: float = 30.0


@dataclass
class BeastScoringBreakdown:
    """
    Detailed audit trail for candidate shot evaluation.
    """
    shot_id: str
    semantic_similarity: float = 0.0                           # 0 - 100
    character_score: float = 0.0                               # 0 - 100
    secondary_character_score: float = 0.0                     # 0 - 100
    action_score: float = 0.0                                  # 0 - 100
    object_score: float = 0.0                                  # 0 - 100
    location_score: float = 0.0                                # 0 - 100
    temporal_coherence: float = 100.0                          # 0 - 100
    vlm_score: float = 0.0                                     # 0 - 100
    framing_score: float = 100.0                               # 0 - 100
    contradiction_penalty: float = 0.0                         # Subtracted
    crop_risk_penalty: float = 0.0                             # Subtracted
    repetition_penalty: float = 0.0                            # Subtracted
    final_score: float = 0.0                                   # 0 - 100 composite score
    is_acceptable: bool = False
    rejection_reasons: List[str] = field(default_factory=list)
    vlm_verdict: Optional[BeastVLMVerificationResult] = None
    extracted_interval: Tuple[float, float] = (0.0, 0.0)       # (start_sec, end_sec)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "semantic_similarity": round(self.semantic_similarity, 2),
            "character_score": round(self.character_score, 2),
            "secondary_character_score": round(self.secondary_character_score, 2),
            "action_score": round(self.action_score, 2),
            "object_score": round(self.object_score, 2),
            "location_score": round(self.location_score, 2),
            "temporal_coherence": round(self.temporal_coherence, 2),
            "vlm_score": round(self.vlm_score, 2),
            "framing_score": round(self.framing_score, 2),
            "contradiction_penalty": round(self.contradiction_penalty, 2),
            "crop_risk_penalty": round(self.crop_risk_penalty, 2),
            "repetition_penalty": round(self.repetition_penalty, 2),
            "final_score": round(self.final_score, 2),
            "is_acceptable": self.is_acceptable,
            "rejection_reasons": self.rejection_reasons,
            "vlm_verdict": self.vlm_verdict.to_dict() if self.vlm_verdict else None,
            "extracted_interval": (round(self.extracted_interval[0], 3), round(self.extracted_interval[1], 3)),
        }
