"""
STORY FORGE SFX Data Models & Timeline Contracts (Step 5)
================================================================================
Defines canonical contracts for the Intelligent Beat-Aware SFX Pipeline:
  - SFXCategory: CLICK, SHORT_TRANSITION, WHOOSH_TRANSITION, REVELATION
  - SFXAssetRecord: Deterministic catalog record for closed 4-file library
  - SFXCue: Frame-locked SFX cue mapped to editorial beat & speech safe-zones
  - SFXPlan: Complete SFX soundtrack container for Remotion composition
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


class SFXCategory(str, Enum):
    """Semantic acoustic and editorial classification for sound effects."""
    CLICK = "CLICK"                         # Subtle tactile accent, caption emphasis, micro cut
    SHORT_TRANSITION = "SHORT_TRANSITION"   # Evidence shifts, structural cuts, quick reveals
    WHOOSH_TRANSITION = "WHOOSH_TRANSITION" # Anchor entrance, major visual transition, escalation
    REVELATION = "REVELATION"               # Major canon realization, magical epiphany, bell accent


@dataclass
class SFXAssetRecord:
    """
    Deterministic registry entry for an authorized source SFX audio file.
    Represents an immutable record within the closed 4-file SFX universe.
    """
    asset_id: str
    filename: str
    local_path: str
    duration_seconds: float
    sample_rate: int
    channels: int
    file_format: str
    sha256: str
    category: SFXCategory
    intensity: float                        # Relative perceptual impact (0.0 to 1.0)
    target_level_db: float                  # Target mix level relative to full scale (e.g. -20 dB)
    measured_max_db: float                  # Measured maximum peak volume in dB
    measured_mean_db: float                 # Measured mean volume in dB
    base_gain_db: float                     # Calibrated gain offset to hit target mix level
    suitable_beat_types: List[str]          # Editorial/visual roles where this asset is suitable
    cooldown_seconds: float                 # Minimum time before reusing this exact asset
    max_uses_per_short: int                 # Hard ceiling for single Short composition
    cooldown_group: str                     # Logical cooldown bucket

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value if isinstance(self.category, SFXCategory) else str(self.category)
        return d


@dataclass
class SFXCue:
    """
    Frame-synchronized sound effect placement unit.
    Traceable to a specific Step 4 editorial beat with acoustic gain and timing safety.
    """
    cue_id: str
    source_sfx_id: str
    beat_id: str
    start_time: float                       # Start time in seconds
    start_frame: int                        # Start frame locked to composition FPS
    duration: float                         # Playback duration in seconds
    duration_frames: int                    # Playback duration in frames
    category: str                           # Semantic category
    intensity: float                        # Cue intensity (0.0 to 1.0)
    gain_db: float                          # Playback volume gain in dB
    fade_in: float = 0.01                   # Fade-in duration in seconds
    fade_out: float = 0.05                  # Fade-out duration in seconds
    semantic_reason: str = ""               # Narrative/editorial rationale for placement
    editorial_role: str = ""                # Visual role or emphasis of triggering beat
    confidence: float = 1.0                 # Placement confidence score (0.0 to 1.0)
    cooldown_group: str = ""                # Asset cooldown grouping
    deterministic_selection_key: str = ""   # Deterministic hash key used for selection
    file_path: Optional[str] = None         # Absolute path to audio file

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_remotion_props(self) -> Dict[str, Any]:
        """Converts cue into props format for Remotion composition."""
        return {
            "cueId": self.cue_id,
            "sourceSfxId": self.source_sfx_id,
            "beatId": self.beat_id,
            "startTime": round(self.start_time, 3),
            "startFrame": self.start_frame,
            "duration": round(self.duration, 3),
            "durationFrames": self.duration_frames,
            "category": self.category,
            "intensity": round(self.intensity, 2),
            "gainDb": round(self.gain_db, 2),
            "volumeLinear": round(10.0 ** (self.gain_db / 20.0), 3),
            "fadeInSec": self.fade_in,
            "fadeOutSec": self.fade_out,
            "semanticReason": self.semantic_reason,
            "editorialRole": self.editorial_role,
            "confidence": round(self.confidence, 2),
            "filePath": self.file_path or "",
        }


@dataclass
class SFXPlan:
    """
    Complete directorial SFX soundtrack plan for a Remotion composition.
    Deterministic, auditable, and strictly validated against the 4-file library.
    """
    composition_id: str
    cues: List[SFXCue] = field(default_factory=list)
    sfx_fingerprint: str = ""
    total_cues: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "cues": [c.to_dict() for c in self.cues],
            "sfx_fingerprint": self.sfx_fingerprint,
            "total_cues": self.total_cues,
            "metadata": self.metadata,
        }

    def to_remotion_props(self) -> List[Dict[str, Any]]:
        return [c.to_remotion_props() for c in self.cues]
