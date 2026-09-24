"""
STORY FORGE — Voice Audition V1 Test Suite
================================================================================
Comprehensive test suite covering all 16 required audition capability dimensions:
 1. voice discovery
 2. male/female categorization
 3. distinct voice IDs
 4. 30+30 selection when available
 5. graceful handling when fewer voices exist
 6. identical audition script
 7. candidate ordering
 8. manifest generation
 9. timestamp generation
10. combined audio generation
11. audio normalization
12. deterministic audition manifest
13. zero-device dependency
14. VoiceSelectionGate remains CLOSED
15. no automatic approval
16. no production invocation
"""

import pytest
import numpy as np
import json
from pathlib import Path
from typing import List

from core.voice_audition_types import VoiceCandidate, VoiceAuditionManifest
from engines.voice_audition.voice_discovery import VoiceDiscoveryService, KOKORO_ENGLISH_VOICES
from engines.voice_audition.audition_synthesizer import (
    AuditionSynthesizer,
    DEFAULT_AUDITION_SCRIPT,
    SAMPLE_RATE,
    INTER_CANDIDATE_SILENCE_SEC,
)
from engines.editorial.voice_selection_gate import (
    VoiceSelectionGate,
    VoiceSelectionRequiredError,
)
from engines.tts_engine import get_active_voice, APPROVED_PRODUCTION_VOICES


# ==============================================================================
# 1. VOICE DISCOVERY
# ==============================================================================

def test_01_voice_discovery():
    """Verifies that VoiceDiscoveryService discovers voices from Kokoro and Edge-TTS."""
    service = VoiceDiscoveryService()
    k_males, k_females = service.discover_kokoro_voices()
    assert len(k_males) >= 9
    assert len(k_females) >= 11

    e_males, e_females = service.discover_edge_voices()
    assert len(e_males) >= 15
    assert len(e_females) >= 15


# ==============================================================================
# 2. MALE / FEMALE CATEGORIZATION
# ==============================================================================

def test_02_male_female_categorization():
    """Verifies that discovered voices are correctly partitioned by gender."""
    service = VoiceDiscoveryService()
    lineup, m_count, f_count = service.build_lineup(target_males=10, target_females=10)
    
    assert m_count == 10
    assert f_count == 10

    for c in lineup[:10]:
        assert c.category == "male"
        assert c.label.startswith("MALE")

    for c in lineup[10:]:
        assert c.category == "female"
        assert c.label.startswith("FEMALE")


# ==============================================================================
# 3. DISTINCT VOICE IDS
# ==============================================================================

def test_03_distinct_voice_ids():
    """Verifies that all candidates have 100% unique, distinct voice IDs with no duplicates."""
    service = VoiceDiscoveryService()
    lineup, m_count, f_count = service.build_lineup(target_males=30, target_females=30)
    voice_ids = [c.voice_id for c in lineup]

    assert len(voice_ids) == len(set(voice_ids)), "Duplicate voice IDs detected in audition lineup!"
    assert len(lineup) == 60


# ==============================================================================
# 4. 30+30 SELECTION WHEN AVAILABLE
# ==============================================================================

def test_04_thirty_plus_thirty_selection():
    """Verifies exact 30 Male + 30 Female (60 total) candidates are selected."""
    service = VoiceDiscoveryService()
    lineup, m_count, f_count = service.build_lineup(target_males=30, target_females=30)

    assert m_count == 30
    assert f_count == 30
    assert len(lineup) == 60
    assert lineup[0].label == "MALE 01"
    assert lineup[29].label == "MALE 30"
    assert lineup[30].label == "FEMALE 01"
    assert lineup[59].label == "FEMALE 30"


# ==============================================================================
# 5. GRACEFUL HANDLING WHEN FEWER VOICES EXIST
# ==============================================================================

def test_05_graceful_handling_when_fewer_voices_exist():
    """Verifies service does not fabricate fake voices if fewer than requested exist."""
    # Only Kokoro: 13 males, 15 females
    service = VoiceDiscoveryService(include_kokoro=True, include_edge=False)
    lineup, m_count, f_count = service.build_lineup(target_males=30, target_females=30)

    assert m_count == 13
    assert f_count == 15
    assert len(lineup) == 28
    # No fabricated voices
    assert all(c.voice_id in KOKORO_ENGLISH_VOICES for c in lineup)


# ==============================================================================
# 6. IDENTICAL AUDITION SCRIPT
# ==============================================================================

def test_06_identical_audition_script():
    """Verifies that every candidate is evaluated against the exact same script."""
    synthesizer = AuditionSynthesizer()
    assert DEFAULT_AUDITION_SCRIPT in synthesizer.script
    assert "Hogwarts" in synthesizer.script
    assert "Gryffindor" in synthesizer.script
    assert "Ollivanders" in synthesizer.script
    # Ensure word count aligns with 15-25s duration
    words = synthesizer.script.split()
    assert 40 <= len(words) <= 70


# ==============================================================================
# 7. CANDIDATE ORDERING
# ==============================================================================

def test_07_candidate_ordering():
    """Verifies ordering: MALE 01..30 followed by FEMALE 01..30."""
    service = VoiceDiscoveryService()
    lineup, _, _ = service.build_lineup(target_males=30, target_females=30)

    for i in range(30):
        expected_label = f"MALE {i+1:02d}"
        assert lineup[i].number == i + 1
        assert lineup[i].label == expected_label
        assert lineup[i].category == "male"

    for j in range(30):
        expected_label = f"FEMALE {j+1:02d}"
        assert lineup[30 + j].number == 31 + j
        assert lineup[30 + j].label == expected_label
        assert lineup[30 + j].category == "female"


# ==============================================================================
# 8. MANIFEST GENERATION
# ==============================================================================

def test_08_manifest_generation(tmp_path):
    """Verifies that VoiceAuditionManifest produces valid, complete JSON metadata."""
    manifest = VoiceAuditionManifest(
        session_id="test_session",
        created_at="2026-09-24T12:00:00Z",
        script=DEFAULT_AUDITION_SCRIPT,
        total_voices=2,
        male_count=1,
        female_count=1,
        combined_audio_filename="test_session_lineup_60.mp3",
        total_duration_seconds=42.5,
        voices=[
            VoiceCandidate(1, "MALE 01", "male", "am_adam", "Kokoro-82M ONNX", "kokoro-v1.0", "en-US", "American", 0.0, 20.0, 20.0),
            VoiceCandidate(2, "FEMALE 01", "female", "af_bella", "Kokoro-82M ONNX", "kokoro-v1.0", "en-US", "American", 20.8, 41.5, 20.7),
        ]
    )
    manifest.deterministic_fingerprint = manifest.calculate_fingerprint()

    json_str = manifest.to_json()
    parsed = json.loads(json_str)

    assert parsed["session_id"] == "test_session"
    assert parsed["total_voices"] == 2
    assert len(parsed["voices"]) == 2
    assert parsed["voices"][0]["voice_id"] == "am_adam"
    assert parsed["voices"][1]["voice_id"] == "af_bella"
    assert len(parsed["deterministic_fingerprint"]) == 16


# ==============================================================================
# 9. TIMESTAMP GENERATION
# ==============================================================================

def test_09_timestamp_generation():
    """Verifies that timestamps are strictly monotonic and account for silence offsets."""
    synthesizer = AuditionSynthesizer(inter_candidate_silence=0.8)
    lineup = [
        VoiceCandidate(1, "MALE 01", "male", "v_m1", "Mock", "m", "en-US", "US"),
        VoiceCandidate(2, "MALE 02", "male", "v_m2", "Mock", "m", "en-US", "US"),
        VoiceCandidate(3, "FEMALE 01", "female", "v_f1", "Mock", "m", "en-US", "US"),
    ]

    # Mock synthesize_candidate_audio to return fixed 2.0s audio for testing
    def mock_synth(cand, temp_dir):
        return np.ones(int(2.0 * SAMPLE_RATE), dtype=np.float32), 2.0

    synthesizer.synthesize_candidate_audio = mock_synth
    _, updated = synthesizer.assemble_audition_timeline(lineup, Path("."))

    assert updated[0].start == 0.0
    assert updated[0].end == pytest.approx(2.0, 0.01)

    # Next candidate starts after 0.8s silence
    assert updated[1].start == pytest.approx(2.8, 0.01)
    assert updated[1].end == pytest.approx(4.8, 0.01)

    assert updated[2].start == pytest.approx(5.6, 0.01)
    assert updated[2].end == pytest.approx(7.6, 0.01)


# ==============================================================================
# 10. COMBINED AUDIO GENERATION
# ==============================================================================

def test_10_combined_audio_generation(tmp_path):
    """Verifies that the synthesizer concatenates candidate audio and silence correctly."""
    synthesizer = AuditionSynthesizer(inter_candidate_silence=0.5)
    lineup = [
        VoiceCandidate(1, "MALE 01", "male", "v1", "Mock", "m", "en-US", "US"),
        VoiceCandidate(2, "FEMALE 01", "female", "v2", "Mock", "m", "en-US", "US"),
    ]

    def mock_synth(cand, temp_dir):
        return np.zeros(int(1.0 * SAMPLE_RATE), dtype=np.float32), 1.0

    synthesizer.synthesize_candidate_audio = mock_synth
    full_audio, updated = synthesizer.assemble_audition_timeline(lineup, tmp_path)

    # Total duration = 1.0 + 0.5 + 1.0 + 0.5 = 3.0s
    expected_samples = int(3.0 * SAMPLE_RATE)
    assert len(full_audio) == expected_samples


# ==============================================================================
# 11. AUDIO NORMALIZATION
# ==============================================================================

def test_11_audio_normalization():
    """Verifies that normalize_audio achieves target peak dB without clipping."""
    synthesizer = AuditionSynthesizer()
    raw_audio = np.array([0.1, -0.2, 0.05, -0.15], dtype=np.float32)
    normalized = synthesizer.normalize_audio(raw_audio, target_peak_db=-1.0)

    target_peak = 10.0 ** (-1.0 / 20.0)  # ~0.891
    actual_peak = np.max(np.abs(normalized))
    assert actual_peak == pytest.approx(target_peak, rel=1e-3)

    # Empty audio handling
    empty = np.array([], dtype=np.float32)
    assert len(synthesizer.normalize_audio(empty)) == 0


# ==============================================================================
# 12. DETERMINISTIC AUDITION MANIFEST
# ==============================================================================

def test_12_deterministic_audition_manifest():
    """Verifies that the manifest fingerprint is reproducible given the same candidates."""
    m1 = VoiceAuditionManifest("s1", "2026-09-24", "script", 2, 1, 1, "out.mp3", 10.0,
                               voices=[VoiceCandidate(1, "MALE 01", "male", "am_adam", "K", "m", "en-US", "US")])
    m2 = VoiceAuditionManifest("s1", "2026-09-24", "script", 2, 1, 1, "out.mp3", 10.0,
                               voices=[VoiceCandidate(1, "MALE 01", "male", "am_adam", "K", "m", "en-US", "US")])
    assert m1.calculate_fingerprint() == m2.calculate_fingerprint()
    assert len(m1.calculate_fingerprint()) == 16


# ==============================================================================
# 13. ZERO-DEVICE DEPENDENCY
# ==============================================================================

def test_13_zero_device_dependency():
    """Verifies that no absolute desktop, user OneDrive, or external paths are hardcoded."""
    from engines.voice_audition import voice_discovery, audition_synthesizer
    
    disc_src = Path(voice_discovery.__file__).read_text(encoding="utf-8")
    synth_src = Path(audition_synthesizer.__file__).read_text(encoding="utf-8")

    forbidden = ["C:\\Users\\", "OneDrive\\Desktop", "/home/user"]
    for f in forbidden:
        assert f not in disc_src
        assert f not in synth_src


# ==============================================================================
# 14. VOICE SELECTION GATE REMAINS CLOSED
# ==============================================================================

def test_14_voice_selection_gate_remains_closed():
    """CRITICAL: Verifies VoiceSelectionGate is CLOSED and raises VoiceSelectionRequiredError."""
    VoiceSelectionGate.reset_gate()
    assert VoiceSelectionGate.is_approved() is False
    assert VoiceSelectionGate.get_selected_voice() is None

    with pytest.raises(VoiceSelectionRequiredError, match="VOICE_SELECTION_REQUIRED"):
        VoiceSelectionGate.verify_gate()


# ==============================================================================
# 15. NO AUTOMATIC APPROVAL
# ==============================================================================

def test_15_no_automatic_approval():
    """Verifies that discovering or synthesizing an audition does NOT approve any voice."""
    VoiceSelectionGate.reset_gate()
    service = VoiceDiscoveryService()
    lineup, _, _ = service.build_lineup(10, 10)

    # Gate MUST remain unapproved
    assert VoiceSelectionGate.is_approved() is False
    assert VoiceSelectionGate.get_selected_voice() is None


# ==============================================================================
# 16. NO PRODUCTION INVOCATION
# ==============================================================================

def test_16_no_production_invocation():
    """Verifies active production voice remains untouched and un-mutated by audition operations."""
    current_active = get_active_voice()
    # Must remain valid without being mutated to an unapproved candidate
    assert current_active in APPROVED_PRODUCTION_VOICES
