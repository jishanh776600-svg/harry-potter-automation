"""
py-visual-evidence
Domain-agnostic CPU-native visual evidence verification engine for video automation.
"""

from py_visual_evidence.schema import (
    VisualAssertion,
    EntitySpec,
    StateTransitionSpec,
    CropSpec,
    BoundingBox,
    GroundedEntity,
    EntityTrajectory,
    TrajectoryPoint,
    ActionResult,
    StateTransitionResult,
    CropVerificationResult,
    ObservationEvidence,
    EvidenceVerdict,
)
from py_visual_evidence.video_reader import VideoClip
from py_visual_evidence.shot_detector import ShotBoundaryDetector, ShotAnalysisResult
from py_visual_evidence.grounding import BaseEntityGrounder, DeterministicBenchmarkGrounder, OpenVocabularyGrounder
from py_visual_evidence.tracking import FastSpatioTemporalTracker
from py_visual_evidence.causal_order import CausalOrderValidator
from py_visual_evidence.crop_validator import VerticalCropValidator
from py_visual_evidence.reporter import EvidenceReporter
from py_visual_evidence.engine import VideoEvidenceEngine

__version__ = "0.1.0"

__all__ = [
    "VisualAssertion",
    "EntitySpec",
    "StateTransitionSpec",
    "CropSpec",
    "BoundingBox",
    "GroundedEntity",
    "EntityTrajectory",
    "TrajectoryPoint",
    "ActionResult",
    "StateTransitionResult",
    "CropVerificationResult",
    "ObservationEvidence",
    "EvidenceVerdict",
    "VideoClip",
    "ShotBoundaryDetector",
    "ShotAnalysisResult",
    "BaseEntityGrounder",
    "DeterministicBenchmarkGrounder",
    "OpenVocabularyGrounder",
    "FastSpatioTemporalTracker",
    "CausalOrderValidator",
    "VerticalCropValidator",
    "EvidenceReporter",
    "VideoEvidenceEngine",
]
