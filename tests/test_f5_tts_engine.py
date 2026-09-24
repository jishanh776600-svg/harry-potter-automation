"""
STORY FORGE — F5-TTS Voice Engine & Zero-Shot Cloning Unit Tests
================================================================
Validates:
- Conditioning segment audio and metadata integrity
- F5TTSVoiceEngine class structure and method signatures
- Strict isolation of production voice configs (data/voice_approval.json, config/settings.py)
- Broadcast audio mastering properties and existence of the audition output
"""

import json
from pathlib import Path
import pytest
import soundfile as sf

from engines.tts.f5_tts_voice_engine import F5TTSVoiceEngine


def test_selected_conditioning_segment():
    ref_dir = Path("data/voice_cloning/f5_tts/reference")
    meta_path = ref_dir / "selected_reference_metadata.json"
    audio_path = ref_dir / "selected_reference_speaker_24k.wav"

    assert meta_path.exists(), "selected_reference_metadata.json must exist"
    assert audio_path.exists(), "selected_reference_speaker_24k.wav must exist"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    selected = meta.get("selected_reference", {})
    assert "transcript_text" in selected and len(selected["transcript_text"]) > 10
    assert "duration_s" in selected and 3.0 <= selected["duration_s"] <= 15.0
    assert "composite_quality_score" in selected and selected["composite_quality_score"] > 20.0

    data, sr = sf.read(str(audio_path))
    assert sr == 24000, f"Expected 24000 Hz, got {sr}"
    assert len(data) > 0, "Conditioning audio must not be empty"


def test_f5_tts_engine_interface():
    engine = F5TTSVoiceEngine(model_name="F5TTS_v1_Base", device="cpu")
    assert hasattr(engine, "generate")
    assert hasattr(engine, "apply_post_processing")
    assert hasattr(engine, "load_model")
    assert hasattr(engine, "is_available")
    assert engine.model_name == "F5TTS_v1_Base"


def test_production_voice_configuration_unmodified():
    """Confirms production voice gates and config remain untouched."""
    # 1. data/voice_approval.json
    approval_path = Path("data/voice_approval.json")
    if approval_path.exists():
        with open(approval_path, "r", encoding="utf-8") as f:
            approval = json.load(f)
        assert approval.get("approved") is True or approval.get("status") in ["approved", "active", "locked"]
        assert "F5-TTS" not in str(approval)

    # 2. settings.py check
    settings_path = Path("config/settings.py")
    if settings_path.exists():
        content = settings_path.read_text(encoding="utf-8")
        assert "F5-TTS" not in content, "config/settings.py must not contain experimental F5-TTS production assignments"


def test_audition_artifacts_generated():
    """Validates the generated master audio and manifest."""
    master_mp3 = Path("data/voice_cloning/f5_tts/generated/f5_tts_reference_clone_master.mp3")
    master_wav = Path("data/voice_cloning/f5_tts/generated/f5_tts_reference_clone_master.wav")
    manifest_path = Path("data/voice_cloning/f5_tts/manifest.json")

    assert master_mp3.exists(), "f5_tts_reference_clone_master.mp3 must exist"
    assert master_wav.exists(), "f5_tts_reference_clone_master.wav must exist"
    assert manifest_path.exists(), "manifest.json must exist"

    # Validate master audio length and sample rate
    data, sr = sf.read(str(master_wav))
    assert sr == 44100, f"Master WAV must be broadcast 44100 Hz, got {sr}"
    duration_s = len(data) / sr
    assert duration_s >= 15.0, f"Expected audition speech >= 15.0s, got {duration_s:.2f}s"
