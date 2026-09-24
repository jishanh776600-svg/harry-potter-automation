"""
STORY FORGE — Voice Audition V1 Data Types & Contracts
================================================================================
Defines domain models, manifest contracts, and voice candidate representations
for the 60-voice audition lineup (30 male + 30 female).
Strictly decoupled from production voice mutation.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import hashlib
import json


@dataclass
class VoiceCandidate:
    """
    Representation of an individual voice candidate within the audition lineup.
    """
    number: int                        # 1 to 60 (1-30 Male, 31-60 Female)
    label: str                         # "MALE 01" to "MALE 30", "FEMALE 01" to "FEMALE 30"
    category: str                      # "male" or "female"
    voice_id: str                      # Unique provider voice ID
    provider: str                      # "Kokoro-82M ONNX" or "Edge-TTS Neural"
    model: str                         # Underlying engine model
    locale: str                        # "en-US", "en-GB", etc.
    accent: str                        # "American", "British", "Australian", etc.
    start: float = 0.0                 # Start timestamp in combined audio (seconds)
    end: float = 0.0                   # End timestamp in combined audio (seconds)
    duration: float = 0.0              # Duration in combined audio (seconds)
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "label": self.label,
            "category": self.category,
            "voice_id": self.voice_id,
            "provider": self.provider,
            "model": self.model,
            "locale": self.locale,
            "accent": self.accent,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.duration, 2),
            "config": self.config,
        }


@dataclass
class VoiceAuditionManifest:
    """
    Complete manifest for the 60-voice audition session.
    """
    session_id: str
    created_at: str
    script: str
    total_voices: int
    male_count: int
    female_count: int
    combined_audio_filename: str
    total_duration_seconds: float = 0.0
    deterministic_fingerprint: str = ""
    voices: List[VoiceCandidate] = field(default_factory=list)

    def calculate_fingerprint(self) -> str:
        """Calculates a deterministic 16-character SHA-256 fingerprint."""
        raw_repr = (
            f"{self.session_id}:"
            f"{self.script}:"
            f"{self.total_voices}:"
            f"{[v.voice_id for v in self.voices]}"
        )
        return hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "script": self.script,
            "total_voices": self.total_voices,
            "male_count": self.male_count,
            "female_count": self.female_count,
            "combined_audio_filename": self.combined_audio_filename,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "deterministic_fingerprint": self.deterministic_fingerprint or self.calculate_fingerprint(),
            "voices": [v.to_dict() for v in self.voices],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
