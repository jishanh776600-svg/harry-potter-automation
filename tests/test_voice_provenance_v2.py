"""
STORY FORGE — Voice Profile Integrity & Provenance Focused Test Suite
=====================================================================
FOCUSED TESTS ONLY (Part 13: Tests 12 through 15):
  12. Correct clone profile -> PASS
  13. Wrong voice profile -> FAIL CLOSED
  14. Stale narration generated with old voice -> INVALIDATED
  15. Voice provenance mismatch -> FAIL CLOSED
"""

import pytest
import hashlib
from engines.voice_provenance import (
    VoiceProfile,
    VoiceProvenanceRecord,
    VoiceProfileIntegrityManager,
    VoiceProfileMismatchError,
    VoiceProvenanceMismatchError,
    VoiceSubstitutionBlockedError,
)


@pytest.fixture
def approved_cloned_profile():
    return VoiceProfile(
        voice_profile_id="f5_cloned_narrator_v1",
        display_name="Approved Cloned Storyteller",
        tts_engine="f5_tts",
        model_identifier="F5TTS_v1_Base",
        reference_audio_path="data/voice_reference/cloned_master.wav",
        reference_audio_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        generation_parameters={"speed": 1.05, "nfe_step": 32, "ode_method": "euler"},
        is_approved_clone=True,
    )


# ------------------------------------------------------------------------------
# TEST 12: Correct clone profile -> PASS
# ------------------------------------------------------------------------------
def test_12_correct_clone_profile_passes(approved_cloned_profile):
    manager = VoiceProfileIntegrityManager(active_profile=approved_cloned_profile)

    # Requesting the correct approved clone profile must succeed
    manager.verify_voice_request("f5_cloned_narrator_v1")
    active = manager.get_active_profile()
    assert active.voice_profile_id == "f5_cloned_narrator_v1"
    assert active.tts_engine == "f5_tts"

    # Creating and verifying genuine provenance matching this profile
    dummy_wav_bytes = b"RIFF_AUDIO_DATA_FOR_CLONED_VOICE"
    script = "Harry Potter walked into the Great Hall."
    rec = VoiceProvenanceRecord.create(
        narration_id="narr_001",
        profile=approved_cloned_profile,
        narration_audio_bytes=dummy_wav_bytes,
        script_text=script,
    )

    assert manager.verify_provenance(rec) is True


# ------------------------------------------------------------------------------
# TEST 13: Wrong voice profile -> FAIL CLOSED
# ------------------------------------------------------------------------------
def test_13_wrong_voice_profile_fail_closed(approved_cloned_profile):
    manager = VoiceProfileIntegrityManager(active_profile=approved_cloned_profile)

    # 1. Attempting to substitute banned fallback voice (Bella, Andrew, etc.) must FAIL CLOSED
    with pytest.raises(VoiceSubstitutionBlockedError):
        manager.verify_voice_request("af_bella")

    with pytest.raises(VoiceSubstitutionBlockedError):
        manager.verify_voice_request("en-US-AndrewNeural")

    # 2. Attempting any other unapproved profile must FAIL CLOSED
    with pytest.raises(VoiceProfileMismatchError):
        manager.verify_voice_request("some_random_unapproved_voice")


# ------------------------------------------------------------------------------
# TEST 14: Stale narration generated with old voice -> INVALIDATED
# ------------------------------------------------------------------------------
def test_14_stale_narration_with_old_voice_invalidated(approved_cloned_profile):
    manager = VoiceProfileIntegrityManager(active_profile=approved_cloned_profile)

    old_profile = VoiceProfile(
        voice_profile_id="old_legacy_profile_v0",
        display_name="Old Retired Voice",
        tts_engine="kokoro",
        model_identifier="Kokoro-82M",
        reference_audio_hash=None,
        generation_parameters={"speed": 1.0},
        is_approved_clone=False,
    )
    stale_rec = VoiceProvenanceRecord.create(
        narration_id="narr_stale_001",
        profile=old_profile,
        narration_audio_bytes=b"OLD_WAV_BYTES",
        script_text="Harry Potter walked into the Great Hall.",
    )

    # Cache validation with active cloned profile must reject stale record (INVALIDATED)
    script = "Harry Potter walked into the Great Hall."
    is_valid = manager.validate_cached_narration(script, stale_rec)
    assert is_valid is False

    # Stale cache without provenance must also be INVALIDATED
    assert manager.validate_cached_narration(script, None) is False


# ------------------------------------------------------------------------------
# TEST 15: Voice provenance mismatch -> FAIL CLOSED
# ------------------------------------------------------------------------------
def test_15_voice_provenance_mismatch_fail_closed(approved_cloned_profile):
    manager = VoiceProfileIntegrityManager(active_profile=approved_cloned_profile)

    # Create provenance with tampered reference audio hash
    tampered_rec = VoiceProvenanceRecord(
        narration_id="narr_tampered_002",
        voice_profile_id=approved_cloned_profile.voice_profile_id,
        tts_engine=approved_cloned_profile.tts_engine,
        model_identifier=approved_cloned_profile.model_identifier,
        reference_audio_hash="TAMPERED_OR_WRONG_REFERENCE_HASH_12345",
        generation_parameters=approved_cloned_profile.generation_parameters,
        narration_sha256="abc123audiohash",
        text_sha256="def456texthash",
        config_fingerprint=approved_cloned_profile.fingerprint(),
    )

    # Verification must FAIL CLOSED
    with pytest.raises(VoiceProvenanceMismatchError):
        manager.verify_provenance(tampered_rec)

    # Create provenance with mismatched engine
    tampered_engine_rec = VoiceProvenanceRecord(
        narration_id="narr_tampered_003",
        voice_profile_id=approved_cloned_profile.voice_profile_id,
        tts_engine="edge_tts",  # Unauthorized engine swap
        model_identifier=approved_cloned_profile.model_identifier,
        reference_audio_hash=approved_cloned_profile.reference_audio_hash,
        generation_parameters=approved_cloned_profile.generation_parameters,
        narration_sha256="abc123audiohash",
        text_sha256="def456texthash",
        config_fingerprint=approved_cloned_profile.fingerprint(),
    )

    with pytest.raises(VoiceProvenanceMismatchError):
        manager.verify_provenance(tampered_engine_rec)
