import subprocess
import pytest
from pathlib import Path
from config.settings import MUSIC_DIR, DATA_DIR, BGM_DEFAULT_TRACK, BGM_SPEED, BGM_VOLUME, BGM_VOLUME_DB
from engines.hp_render_engine import HPRenderEngine, DEFAULT_BGM_TRACK, DEFAULT_BGM_SPEED, DEFAULT_BGM_VOLUME_DB, DEFAULT_BGM_AMIX_WEIGHT

def test_permanent_bgm_configuration():
    assert "Barty Crouch" in DEFAULT_BGM_TRACK
    assert DEFAULT_BGM_SPEED == 1.2
    assert DEFAULT_BGM_VOLUME_DB <= -16.0
    assert DEFAULT_BGM_AMIX_WEIGHT <= 0.25
    assert BGM_SPEED == 1.2
    assert BGM_VOLUME <= 0.25

def test_permanent_bgm_files_exist():
    bgm_wav = MUSIC_DIR / DEFAULT_BGM_TRACK
    assert bgm_wav.exists(), f"Missing {bgm_wav}"
    assert bgm_wav.stat().st_size > 500000

    bgm_12x = MUSIC_DIR / "Barty Crouch Junior! - Harry Potter and the Goblet of Fire Complete Score (Film Mix)_1.2x.wav"
    assert bgm_12x.exists(), f"Missing {bgm_12x}"

def test_mix_master_audio_with_permanent_bgm():
    engine = HPRenderEngine()
    test_dir = DATA_DIR / "test_scratch"
    test_dir.mkdir(parents=True, exist_ok=True)

    narration_wav = test_dir / "test_narr.wav"
    master_wav = test_dir / "test_master.wav"

    # Generate 4-second test narration
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
        "-ar", "44100", "-ac", "2",
        str(narration_wav)
    ], check=True)

    out_wav, measured_lufs = engine.mix_master_audio(
        narration_wav=narration_wav,
        total_duration=4.0,
        output_master_wav=master_wav
    )

    assert out_wav.exists()
    assert -22.0 <= measured_lufs <= -10.0

    # Clean up
    narration_wav.unlink(missing_ok=True)
    master_wav.unlink(missing_ok=True)
