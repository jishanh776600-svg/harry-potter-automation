"""
Optional Ambiguity Resolver Plugin Interface
Reserved for future micro-VLM offline tie-breaking. Disabled by default in production.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import numpy as np

from py_visual_evidence.schema import VisualAssertion, ActionResult


class OptionalAmbiguityResolver(ABC):
    """
    Abstract plugin interface for optional visual ambiguity resolution.
    NOT enabled in the deterministic CPU-native pipeline.
    """

    @abstractmethod
    def is_enabled(self) -> bool:
        """Indicates if the ambiguity resolver is active."""
        return False

    @abstractmethod
    def resolve_ambiguity(
        self,
        frames: List[np.ndarray],
        assertion: VisualAssertion,
        ambiguity_context: Dict[str, Any],
    ) -> Optional[ActionResult]:
        """Optionally resolves ambiguous visual edge cases."""
        pass


class DisabledAmbiguityResolver(OptionalAmbiguityResolver):
    """Default implementation: disabled to ensure zero-cost, deterministic CPU execution."""

    def is_enabled(self) -> bool:
        return False

    def resolve_ambiguity(
        self,
        frames: List[np.ndarray],
        assertion: VisualAssertion,
        ambiguity_context: Dict[str, Any],
    ) -> Optional[ActionResult]:
        return None
