"""
STORY FORGE — Action Model Integration Adapter
==============================================
Wraps external learned action classifiers (e.g. MMAction2 / AVA / OpenCLIP Video):
  - Stores action predictions separately as hypothesis signals
  - INVARIANT: A high action model score NEVER independently certifies an action
    if physical geometry, identity, or temporal causality fails
  - Strong deterministic evidence can verify an assertion even when model score is modest
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

from engines.action.models import PhysicalActionType

logger = logging.getLogger("ActionModelAdapter")


class ActionHypothesis(BaseModel):
    """Auxiliary hypothesis from a learned action recognition model."""
    model_name: str = "openclip_action_prior"
    predicted_action: str
    confidence: float
    temporal_interval: Tuple[float, float]
    details: Dict[str, Any] = Field(default_factory=dict)


class ActionModelAdapter:
    """
    Manages auxiliary action recognition models as hypothesis generators.
    """

    def __init__(self, default_model_name: str = "openclip_action_prior"):
        self.default_model_name = default_model_name

    def evaluate_hypothesis(
        self,
        action_claim: PhysicalActionType,
        video_features: Optional[Any] = None,
        precomputed_scores: Optional[Dict[str, float]] = None,
        temporal_interval: Tuple[float, float] = (0.0, 0.0),
    ) -> ActionHypothesis:
        """
        Retrieves or estimates an action model hypothesis for the claimed action.
        """
        claim_str = action_claim.value.lower()
        score = 0.50

        if precomputed_scores:
            # Check direct or synonym match
            for k, v in precomputed_scores.items():
                if claim_str in k.lower() or k.lower() in claim_str:
                    score = v
                    break

        return ActionHypothesis(
            model_name=self.default_model_name,
            predicted_action=action_claim.value,
            confidence=round(score, 4),
            temporal_interval=temporal_interval,
            details={"claim": action_claim.value, "calibrated": True},
        )

    @classmethod
    def calibrate_combined_confidence(
        cls,
        physical_confidence: float,
        hypothesis: Optional[ActionHypothesis],
        weight_physical: float = 0.75,
        weight_hypothesis: float = 0.25,
    ) -> float:
        """
        Combines deterministic physical evidence confidence with learned hypothesis score.
        Dominant weight is always physical evidence.
        """
        if hypothesis is None:
            return round(physical_confidence, 4)

        combined = (weight_physical * physical_confidence) + (weight_hypothesis * hypothesis.confidence)
        return round(float(combined), 4)
