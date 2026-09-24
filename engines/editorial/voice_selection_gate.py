"""
STORY FORGE — Voice Selection Hard Gate
================================================================================
CRITICAL PRODUCTION SAFETY GATE:
Enforces that no real Short can ever be produced with a silent default voice
(such as af_bella or Andrew) without explicit user audition and signoff.

Raises VoiceSelectionRequiredError if an attempt is made to bypass user selection.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("VoiceSelectionGate")

APPROVAL_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "voice_approval.json"


class VoiceSelectionRequiredError(RuntimeError):
    """Raised when pipeline attempts real production rendering without user voice approval."""
    pass


class VoiceSelectionGate:
    """
    Enforces that the user must explicitly select, audition, and approve the production voice.
    """
    _selected_voice: Optional[str] = None
    _user_approved: bool = False
    _audition_metadata: Dict[str, Any] = {}

    @classmethod
    def set_approved_voice(cls, voice_id: str, metadata: Optional[Dict[str, Any]] = None, persist: bool = True) -> None:
        """Records explicit user audition and signoff of a production voice."""
        cls._selected_voice = voice_id
        cls._user_approved = True
        cls._audition_metadata = metadata or {}
        if persist:
            try:
                APPROVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
                APPROVAL_FILE.write_text(json.dumps({
                    "approved": True,
                    "voice_id": voice_id,
                    "metadata": cls._audition_metadata
                }, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not persist voice approval file: {e}")
        logger.info("VoiceSelectionGate: User approved voice '%s'. Gate is OPEN.", voice_id)

    @classmethod
    def load_saved_approval(cls) -> bool:
        """Loads persistent user approval from disk if available."""
        if APPROVAL_FILE.exists():
            try:
                data = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
                if data.get("approved") and data.get("voice_id"):
                    cls._selected_voice = data.get("voice_id")
                    cls._user_approved = True
                    cls._audition_metadata = data.get("metadata", {})
                    return True
            except Exception as e:
                logger.warning(f"Could not load voice approval file: {e}")
        return False

    @classmethod
    def reset_gate(cls) -> None:
        """Resets approval to require explicit re-approval."""
        cls._selected_voice = None
        cls._user_approved = False
        cls._audition_metadata = {}

    @classmethod
    def verify_gate(cls) -> None:
        """
        Validates that the voice selection gate has been explicitly cleared by the user.
        Raises VoiceSelectionRequiredError if unapproved.
        """
        if not cls._user_approved or not cls._selected_voice:
            raise VoiceSelectionRequiredError(
                "VOICE_SELECTION_REQUIRED: No production voice has been explicitly approved by the user. "
                "The system must NOT silently default to af_bella or Andrew. "
                "Please request the user to audition and select the production voice."
            )

    @classmethod
    def is_approved(cls) -> bool:
        """Returns True if the user has explicitly approved a voice."""
        return cls._user_approved and cls._selected_voice is not None

    @classmethod
    def get_selected_voice(cls) -> Optional[str]:
        return cls._selected_voice
