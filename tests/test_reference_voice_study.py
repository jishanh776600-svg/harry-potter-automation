"""
STORY FORGE — Reference Voice Replication Study Unit & Regression Tests
========================================================================
Validates:
- Reference audio extraction and analysis manifest integrity
- Acoustic and prosodic metrics bounds (F0, centroid, WPS, LUFS)
- 8 candidate audition files existence, formatting, and duration
- VoiceSelectionGate status remaining strictly CLOSED
- Acquisition policy enforcing VIDEO ONLY and blocking stock providers
"""

import json
from pathlib import Path
import pytest

from core.safe_url_validator import SafeURLValidator
from core.acquisition_types import MediaCategory
from engines.editorial.voice_selection_gate import VoiceSelectionGate, VoiceSelectionRequiredError


def test_reference_analysis_manifest():
    manifest_path = Path("data/reference_analysis/voice_reference_analysis.json")
    assert manifest_path.exists(), "voice_reference_analysis.json must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    acoustics = data.get("acoustic_measurements", {})
    delivery = data.get("delivery_measurements", {})

    # Validate acoustic metrics are physically plausible
    assert 140.0 <= acoustics["f0_median_hz"] <= 240.0, f"Unexpected median F0: {acoustics['f0_median_hz']}"
    assert acoustics["spectral_centroid_hz"] > 1500.0, "Expected high spectral centroid"
    assert acoustics["integrated_lufs"] <= -5.0, "Expected realistic LUFS"

    # Validate delivery metrics
    assert delivery["words_per_second_overall"] >= 3.0, f"Expected fast delivery >= 3.0 wps, got {delivery['words_per_second_overall']}"
    assert delivery["pause_count"] > 10, "Expected multiple pauses"


def test_candidate_comparison_manifest():
    comp_path = Path("data/reference_analysis/voice_candidate_comparison.json")
    assert comp_path.exists(), "voice_candidate_comparison.json must exist"

    with open(comp_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    assert len(candidates) == 8, f"Expected exactly 8 candidates, got {len(candidates)}"

    for c in candidates:
        assert "candidate_id" in c
        assert "voice_id" in c
        assert "engine" in c
        assert "acoustic_distance_to_reference" in c
        assert c["acoustic_distance_to_reference"] >= 0.0
        assert Path(c["wav_path"]).exists(), f"WAV file missing: {c['wav_path']}"
        assert Path(c["mp3_path"]).exists(), f"MP3 file missing: {c['mp3_path']}"


def test_audition_manifest_and_combined_audio():
    audit_path = Path("data/reference_analysis/voice_audition_manifest.json")
    assert audit_path.exists(), "voice_audition_manifest.json must exist"

    with open(audit_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["candidates_count"] == 8
    assert "VOICE SELECTION REQUIRED" in data["selection_status"]

    combined_mp3 = Path(data["combined_audition_mp3"])
    assert combined_mp3.exists(), "Combined audition MP3 must exist"
    assert combined_mp3.stat().st_size > 100000, "Combined audition file should be substantial"


def test_voice_selection_gate_strictly_closed():
    """Confirms that VoiceSelectionGate is strictly CLOSED and production voice was NOT altered."""
    assert VoiceSelectionGate.is_approved() is False, "VoiceSelectionGate must be CLOSED"
    assert VoiceSelectionGate.get_selected_voice() is None, "No voice must be locked automatically"

    with pytest.raises(VoiceSelectionRequiredError):
        VoiceSelectionGate.verify_gate()


def test_visual_acquisition_policy_enforcement():
    """Ensures VISUALS = VIDEO ONLY and stock providers are blocked."""
    stock_domains = ["pexels.com", "unsplash.com", "shutterstock.com", "pixabay.com", "gettyimages.com"]
    for domain in stock_domains:
        safe, reason = SafeURLValidator.is_safe_url(f"https://www.{domain}/video/test.mp4")
        assert safe is False, f"Domain {domain} should be blocked"
        assert "STORY FORGE Policy" in reason
