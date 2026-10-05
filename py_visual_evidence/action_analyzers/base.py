"""
Base Action Analyzer Interface
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    EntityTrajectory,
    ActionResult,
)


class BaseActionAnalyzer(ABC):
    """Abstract base class for domain-agnostic action and event analyzers."""

    @abstractmethod
    def analyze_action(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
        fps: float = 24.0,
    ) -> ActionResult:
        """Evaluates localized visual evidence to determine if assertion action occurred."""
        pass
