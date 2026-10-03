"""
STORY FORGE — Voice Profile Integrity & Cryptographic Provenance V2
===================================================================
Enforces that the selected approved voice profile (e.g. cloned voice)
is strictly used for all narration synthesis without silent fallback or
unauthorized substitution.

STRICT INVARIANTS:
1. No silent substitution (Bella, Andrew Edge-TTS, Kokoro generic, etc.).
2. Cloned profile provenance must match reference audio hash and config fingerprint.
3. If requested profile != active approved profile: FAIL CLOSED.
4. If generated provenance != active profile: FAIL CLOSED.
5. Cached narration from older or different voice profiles is INVALIDATED.
"""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("VoiceProvenanceV2")

# Banned / unapproved substitute voices when a cloned profile is locked
BANNED_SUBSTITUTE_VOICES = frozenset([
    "af_bella", "bella", "af_sarah", "sarah",
    "en-us-andrewneural", "andrew", "andrew_edge",
    "en-gb-ryanneural", "ryan",
    "kokoro_generic", "system_tts", "pyttsx3",
])


class VoiceIntegrityError(RuntimeError):
    """Base exception for voice integrity violations."""
    pass


class VoiceProfileMismatchError(VoiceIntegrityError):
    """Raised when an unapproved or mismatched voice profile is requested."""
    pass


class VoiceProvenanceMismatchError(VoiceIntegrityError):
    """Raised when generated audio provenance does not match the active voice profile."""
    pass


class VoiceSubstitutionBlockedError(VoiceIntegrityError):
    """Raised when a silent fallback/substitution to an unapproved voice is attempted."""
    pass


class StaleNarrationError(VoiceIntegrityError):
    """Raised when stale narration generated under a previous voice profile is detected."""
    pass


@dataclass
class VoiceProfile:
    """Canonical specification of an approved voice profile."""
    voice_profile_id: str
    display_name: str
    tts_engine: str  # e.g. "f5_tts", "kokoro"
    model_identifier: str  # e.g. "F5TTS_v1_Base", "Kokoro-82M"
    reference_audio_path: Optional[str] = None
    reference_audio_hash: Optional[str] = None  # SHA-256 of reference audio
    generation_parameters: Dict[str, Any] = field(default_factory=dict)
    is_approved_clone: bool = True

    def fingerprint(self) -> str:
        """Computes a deterministic cryptographic fingerprint of the voice profile configuration."""
        canonical_dict = {
            "voice_profile_id": self.voice_profile_id,
            "tts_engine": self.tts_engine,
            "model_identifier": self.model_identifier,
            "reference_audio_hash": self.reference_audio_hash or "",
            "generation_parameters": dict(sorted(self.generation_parameters.items())),
            "is_approved_clone": self.is_approved_clone,
        }
        serialized = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["config_fingerprint"] = self.fingerprint()
        return d


@dataclass
class VoiceProvenanceRecord:
    """Cryptographic provenance record bound to a generated narration artifact."""
    narration_id: str
    voice_profile_id: str
    tts_engine: str
    model_identifier: str
    reference_audio_hash: Optional[str]
    generation_parameters: Dict[str, Any]
    narration_sha256: str
    text_sha256: str
    config_fingerprint: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        narration_id: str,
        profile: VoiceProfile,
        narration_audio_bytes: bytes,
        script_text: str,
    ) -> VoiceProvenanceRecord:
        narration_sha = hashlib.sha256(narration_audio_bytes).hexdigest()
        text_sha = hashlib.sha256(script_text.strip().encode("utf-8")).hexdigest()
        return cls(
            narration_id=narration_id,
            voice_profile_id=profile.voice_profile_id,
            tts_engine=profile.tts_engine,
            model_identifier=profile.model_identifier,
            reference_audio_hash=profile.reference_audio_hash,
            generation_parameters=profile.generation_parameters,
            narration_sha256=narration_sha,
            text_sha256=text_sha,
            config_fingerprint=profile.fingerprint(),
        )


class VoiceProfileIntegrityManager:
    """
    Authoritative manager enforcing voice profile integrity, provenance verification,
    and automatic cache invalidation for narration artifacts.
    """

    def __init__(self, active_profile: Optional[VoiceProfile] = None):
        self._active_profile: Optional[VoiceProfile] = active_profile
        self._approved_registry: Dict[str, VoiceProfile] = {}
        if active_profile:
            self._approved_registry[active_profile.voice_profile_id] = active_profile

    def register_approved_profile(self, profile: VoiceProfile) -> None:
        self._approved_registry[profile.voice_profile_id] = profile

    def set_active_profile(self, profile: VoiceProfile) -> None:
        self._active_profile = profile
        self._approved_registry[profile.voice_profile_id] = profile
        logger.info(
            "VoiceProfileIntegrityManager: Active profile set to '%s' (engine=%s, model=%s)",
            profile.voice_profile_id, profile.tts_engine, profile.model_identifier
        )

    def get_active_profile(self) -> VoiceProfile:
        if self._active_profile is None:
            raise VoiceIntegrityError(
                "FAIL_CLOSED: No active voice profile has been configured or approved."
            )
        return self._active_profile

    def verify_voice_request(self, requested_profile_id: str) -> None:
        """
        Validates a requested voice against the active approved profile.
        Fails closed on any unauthorized substitution or mismatch.
        """
        active = self.get_active_profile()
        req_norm = requested_profile_id.lower().strip()

        # Check for banned substitute attempts
        if req_norm in BANNED_SUBSTITUTE_VOICES:
            raise VoiceSubstitutionBlockedError(
                f"FAIL_CLOSED: Unauthorized substitute voice '{requested_profile_id}' is BLOCKED. "
                f"Active locked profile is '{active.voice_profile_id}'."
            )

        if requested_profile_id != active.voice_profile_id:
            raise VoiceProfileMismatchError(
                f"FAIL_CLOSED: Requested voice profile '{requested_profile_id}' does not match "
                f"active locked profile '{active.voice_profile_id}'."
            )

    def verify_provenance(self, record: VoiceProvenanceRecord) -> bool:
        """
        Cryptographically verifies that the generated narration provenance
        strictly matches the active profile.
        Raises VoiceProvenanceMismatchError if invalid (FAIL CLOSED).
        """
        active = self.get_active_profile()

        if record.voice_profile_id != active.voice_profile_id:
            raise VoiceProvenanceMismatchError(
                f"FAIL_CLOSED: Provenance voice_profile_id '{record.voice_profile_id}' "
                f"does not match active profile '{active.voice_profile_id}'."
            )

        if record.tts_engine != active.tts_engine:
            raise VoiceProvenanceMismatchError(
                f"FAIL_CLOSED: Provenance TTS engine '{record.tts_engine}' "
                f"does not match active profile engine '{active.tts_engine}'."
            )

        if record.model_identifier != active.model_identifier:
            raise VoiceProvenanceMismatchError(
                f"FAIL_CLOSED: Provenance model identifier '{record.model_identifier}' "
                f"does not match active profile model '{active.model_identifier}'."
            )

        if active.is_approved_clone:
            if record.reference_audio_hash != active.reference_audio_hash:
                raise VoiceProvenanceMismatchError(
                    f"FAIL_CLOSED: Provenance reference audio hash '{record.reference_audio_hash}' "
                    f"does not match active clone reference hash '{active.reference_audio_hash}'."
                )

        if record.config_fingerprint != active.fingerprint():
            raise VoiceProvenanceMismatchError(
                f"FAIL_CLOSED: Provenance config fingerprint '{record.config_fingerprint}' "
                f"does not match active profile fingerprint '{active.fingerprint()}'."
            )

        return True

    def validate_cached_narration(
        self,
        script_text: str,
        provenance: Optional[VoiceProvenanceRecord],
        audio_sha256: Optional[str] = None,
    ) -> bool:
        """
        Validates cached narration against the active voice profile and script.
        Returns False (INVALIDATED) if stale, generated with an old voice, or mismatched.
        """
        if provenance is None:
            logger.warning("Cache invalidated: No voice provenance record found.")
            return False

        try:
            active = self.get_active_profile()
        except VoiceIntegrityError:
            return False

        # Check profile ID match
        if provenance.voice_profile_id != active.voice_profile_id:
            logger.warning(
                "Cache invalidated: Provenance profile '%s' != active profile '%s'.",
                provenance.voice_profile_id, active.voice_profile_id
            )
            return False

        # Check config fingerprint match
        if provenance.config_fingerprint != active.fingerprint():
            logger.warning("Cache invalidated: Voice configuration fingerprint changed.")
            return False

        # Check reference audio hash for cloned voices
        if active.is_approved_clone and provenance.reference_audio_hash != active.reference_audio_hash:
            logger.warning("Cache invalidated: Cloned voice reference audio hash changed.")
            return False

        # Check text match
        expected_text_sha = hashlib.sha256(script_text.strip().encode("utf-8")).hexdigest()
        if provenance.text_sha256 != expected_text_sha:
            logger.warning("Cache invalidated: Script text changed.")
            return False

        # Check audio hash match if audio bytes available
        if audio_sha256 and provenance.narration_sha256 != audio_sha256:
            logger.warning("Cache invalidated: Audio file hash mismatch.")
            return False

        return True
