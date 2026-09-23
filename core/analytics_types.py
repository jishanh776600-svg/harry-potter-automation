"""
STORY FORGE Autonomous Analytics & Learning Loop Data Models (Step 7)
================================================================================
Defines canonical contracts for performance telemetry, learning signals,
BPS scoring, cadence arbitration, and winning pattern propagation.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple


class MaturationState(str, Enum):
    """Analytics observation maturation status."""
    TOO_EARLY = "TOO_EARLY"                   # Less than observation window (6h) or tiny sample (<100 views)
    MATURE = "MATURE"                         # Fully observed across valid observation window
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"   # Missing essential metrics (no fake zeros permitted)


class CadenceDecisionType(str, Enum):
    """Autonomous publishing cadence decision."""
    FATIGUE_PAUSE = "FATIGUE_PAUSE"           # Immediate 12-hour pause due to channel fatigue
    CADENCE_INCREASE = "CADENCE_INCREASE"     # Surge to 4–5 Shorts/day (performance velocity > 2x)
    CADENCE_NORMAL = "CADENCE_NORMAL"         # Standard 3 Shorts/day cadence


class PerformanceScaleDecision(str, Enum):
    """Performance index relative to cohort baseline."""
    SCALE = "SCALE"                           # Performance index >= 1.25
    THROTTLE = "THROTTLE"                     # Performance index < 0.80
    NORMAL = "NORMAL"                         # 0.80 <= Performance index < 1.25


class LearningSignalType(str, Enum):
    """Deterministic learning signal categories."""
    STRONG_HOOK = "STRONG_HOOK"
    WEAK_HOOK = "WEAK_HOOK"
    STRONG_CONVERSION = "STRONG_CONVERSION"
    WEAK_CONVERSION = "WEAK_CONVERSION"
    STRONG_RETENTION = "STRONG_RETENTION"
    WEAK_RETENTION = "WEAK_RETENTION"
    STRONG_COMMENTS = "STRONG_COMMENTS"
    WINNING_PATTERN = "WINNING_PATTERN"
    FATIGUE = "FATIGUE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class OrthogonalAxis(str, Enum):
    """The single variation axis required when cloning winning structural patterns."""
    SUBJECT = "SUBJECT"                       # Change character/entity (e.g., Neville -> Harry -> Sirius)
    DYNAMIC = "DYNAMIC"                       # Change conflict/mechanism (e.g., Hatstall -> Wand loyalty)
    PERSPECTIVE = "PERSPECTIVE"               # Change narrative stance (e.g., Book vs Movie discrepancy)


@dataclass
class AnalyticsSnapshot:
    """
    Per-Short empirical performance snapshot.
    Preserves exact metrics; NEVER substitutes fabricated zeros for missing metrics.
    """
    candidate_id: str
    youtube_video_id: Optional[str] = None
    publish_timestamp: str = ""
    views: Optional[int] = None
    viewed_vs_swiped_away: Optional[float] = None     # VSA (percentage viewed, e.g., 78.5)
    average_percentage_viewed: Optional[float] = None # APV (e.g., 92.0)
    subscriber_gain: Optional[int] = None
    subscriber_conversion_rate: Optional[float] = None# SCR (subs / 1000 views)
    comments: Optional[int] = None
    shares: Optional[int] = None
    likes: Optional[int] = None
    duration_seconds: float = 72.0
    format_template: str = "TEMPLATE_A_CURATED_LISTICLE"
    hook_archetype: str = "COUNTER_INTUITIVE_TRUTH"
    topic_category: str = "DISCOVERY_BOOK_MOVIE_DIFFERENCE"
    lead_character: str = "Neville"
    content_mix_category: str = "deep_discovery"      # "deep_discovery" or "novel_story"
    visual_density: float = 0.58                      # cuts / second
    sfx_density: float = 8.0                          # cues / minute
    bps: Optional[float] = None                       # Calculated BPS score
    baseline_used: Optional[str] = None
    analytics_timestamp: str = ""
    data_freshness: str = "6h_poll"
    observation_window_hours: float = 6.0
    maturation_state: MaturationState = MaturationState.MATURE

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["maturation_state"] = self.maturation_state.value if isinstance(self.maturation_state, MaturationState) else str(self.maturation_state)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalyticsSnapshot":
        ms = data.get("maturation_state", MaturationState.MATURE.value)
        if isinstance(ms, str):
            try:
                ms = MaturationState(ms)
            except ValueError:
                ms = MaturationState.MATURE
        data_clean = dict(data)
        data_clean["maturation_state"] = ms
        return cls(**data_clean)


@dataclass
class LearningSignal:
    """Actionable feedback signal generated from mature observation."""
    signal_type: LearningSignalType
    source_video_id: str
    threshold_used: str
    measured_value: Any
    confidence: float
    timestamp: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type.value if isinstance(self.signal_type, LearningSignalType) else str(self.signal_type),
            "source_video_id": self.source_video_id,
            "threshold_used": self.threshold_used,
            "measured_value": self.measured_value,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "explanation": self.explanation,
        }


@dataclass
class WinningPattern:
    """Discovered structural formula exceeding 3x cohort baseline."""
    source_video_id: str
    format_template: str
    hook_archetype: str
    topic_category: str
    lead_character: str
    performance_index: float
    orthogonal_axis_options: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CadenceDecision:
    """
    Arbitrated publication cadence and scheduling directive.
    Deterministic, auditable, and strictly uncoupled from actual YouTube publishing.
    """
    decision_type: CadenceDecisionType
    recommended_daily_cadence: int                    # 3 (normal) or 4–5 (surge) or 0 (paused)
    recommended_slots: List[str]                      # UTC slots (e.g. ["13:00 UTC", "17:00 UTC", "21:00 UTC"])
    pause_duration_hours: Optional[float] = None      # 12.0 hours if FATIGUE_PAUSE
    bps: Optional[float] = None
    performance_index: Optional[float] = None
    baseline_bps: Optional[float] = None
    learning_signals: List[LearningSignal] = field(default_factory=list)
    winning_patterns: List[WinningPattern] = field(default_factory=list)
    hook_weight_adjustments: Dict[str, float] = field(default_factory=dict)
    supporting_video_ids: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    data_sufficiency: str = "SUFFICIENT"
    timestamp: str = ""
    decision_fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_type": self.decision_type.value if isinstance(self.decision_type, CadenceDecisionType) else str(self.decision_type),
            "recommended_daily_cadence": self.recommended_daily_cadence,
            "recommended_slots": self.recommended_slots,
            "pause_duration_hours": self.pause_duration_hours,
            "bps": self.bps,
            "performance_index": self.performance_index,
            "baseline_bps": self.baseline_bps,
            "learning_signals": [s.to_dict() for s in self.learning_signals],
            "winning_patterns": [w.to_dict() for w in self.winning_patterns],
            "hook_weight_adjustments": self.hook_weight_adjustments,
            "supporting_video_ids": self.supporting_video_ids,
            "reason_codes": self.reason_codes,
            "data_sufficiency": self.data_sufficiency,
            "timestamp": self.timestamp,
            "decision_fingerprint": self.decision_fingerprint,
        }
