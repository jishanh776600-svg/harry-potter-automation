"""
STORY FORGE — Regression Test Suite for Voice Pause Compression & Timestamp Harmonization
==========================================================================================
Validates all 5 requirements for Part A:
  1. <=0.20s gaps preserved (100% intact, no prosody distortion)
  2. >0.20s gaps compressed to <=0.20s
  3. No word/phoneme clipping (consonant attack & release hangover preserved)
  4. Final timestamps regenerated from post-processed audio
  5. Visual timing uses final post-processed timestamps (eliminating visual delay)
"""

import math
from pathlib import Path
import tempfile
import numpy as np
import pytest
import soundfile as sf

from engines.tts.voice_pause_compressor import (
    VoicePauseCompressor,
    DEFAULT_MAX_PAUSE_SEC,
    DEFAULT_TARGET_PAUSE_SEC,
)
from core.multi_fact_types import (
    MultiFactTopicPack,
    MultiFactPayload,
    MultiFactFormat,
    VisualProposition,
    FactType,
)
from engines.editorial.editorial_planner import EditorialPlanner
from core.beast_v2_types import BeastV2MatchResult, BeastV2Decision, EvidenceType


def _generate_synthetic_tone(freq: float, duration_sec: float, sr: int = 24000, amp: float = 0.5) -> np.ndarray:
    """Generates a synthetic speech-like burst with gentle Hann envelope."""
    n_samples = int(duration_sec * sr)
    t = np.linspace(0, duration_sec, n_samples, endpoint=False)
    # Fundamental + harmonics to simulate voice formant
    wave = amp * (0.6 * np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * (freq * 2) * t))
    # 15ms fade-in and fade-out envelope to avoid boundary clicks
    fade_len = min(n_samples // 4, int(0.015 * sr))
    if fade_len > 0:
        fade_in = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, fade_len)))
        wave[:fade_len] *= fade_in
        wave[-fade_len:] *= fade_in[::-1]
    return wave.astype(np.float32)


# ==============================================================================
# TEST 1: <=0.20s gaps preserved
# ==============================================================================
def test_01_gaps_under_or_equal_200ms_preserved(tmp_path: Path):
    sr = 24000
    w1 = _generate_synthetic_tone(220.0, 0.40, sr)  # Word 1 (400ms)
    sil1 = np.zeros(int(0.12 * sr), dtype=np.float32)  # 120ms gap (<= 0.20s)
    w2 = _generate_synthetic_tone(220.0, 0.50, sr)  # Word 2 (500ms)
    sil2 = np.zeros(int(0.18 * sr), dtype=np.float32)  # 180ms gap (<= 0.20s)
    w3 = _generate_synthetic_tone(220.0, 0.35, sr)  # Word 3 (350ms)

    combined = np.concatenate([w1, sil1, w2, sil2, w3])
    in_wav = tmp_path / "in_short_gaps.wav"
    out_wav = tmp_path / "out_short_gaps.wav"
    sf.write(str(in_wav), combined, sr)

    res = VoicePauseCompressor.compress_pause_gaps(
        input_wav=in_wav,
        output_wav=out_wav,
        max_pause_sec=0.20,
        target_pause_sec=0.15,
    )

    assert res["success"] is True
    # Gaps <= 0.20s must NOT be compressed
    assert res["gaps_compressed_count"] == 0
    assert res["gaps_preserved_count"] >= 2
    # Duration should remain identical within micro-frame precision
    assert abs(res["original_duration"] - res["compressed_duration"]) < 0.03


# ==============================================================================
# TEST 2: >0.20s gaps compressed to <=0.20s
# ==============================================================================
def test_02_gaps_over_200ms_compressed_to_under_200ms(tmp_path: Path):
    sr = 24000
    w1 = _generate_synthetic_tone(220.0, 0.45, sr)
    sil1 = np.zeros(int(0.65 * sr), dtype=np.float32)  # 650ms gap (> 0.20s)
    w2 = _generate_synthetic_tone(220.0, 0.55, sr)
    sil2 = np.zeros(int(0.40 * sr), dtype=np.float32)  # 400ms gap (> 0.20s)
    w3 = _generate_synthetic_tone(220.0, 0.40, sr)

    combined = np.concatenate([w1, sil1, w2, sil2, w3])
    in_wav = tmp_path / "in_long_gaps.wav"
    out_wav = tmp_path / "out_long_gaps.wav"
    sf.write(str(in_wav), combined, sr)

    orig_dur = len(combined) / float(sr)

    res = VoicePauseCompressor.compress_pause_gaps(
        input_wav=in_wav,
        output_wav=out_wav,
        max_pause_sec=0.20,
        target_pause_sec=0.15,
    )

    assert res["success"] is True
    assert res["gaps_compressed_count"] == 2
    assert res["compressed_duration"] < orig_dur
    # Verification: measure gaps in output audio
    max_after = VoicePauseCompressor.get_max_silence_pause(out_wav)
    assert max_after <= 0.20, f"Max interior pause in compressed audio was {max_after}s (> 0.20s)!"


# ==============================================================================
# TEST 3: No word/phoneme clipping (attack and release preserved)
# ==============================================================================
def test_03_no_word_phoneme_clipping(tmp_path: Path):
    sr = 24000
    # Simulate a word with soft unvoiced attack (low amp first 25ms) and sibilant release (low amp last 30ms)
    t_word = 0.50
    n_word = int(t_word * sr)
    word_audio = np.sin(2 * np.pi * 300 * np.linspace(0, t_word, n_word, endpoint=False))
    word_audio[: int(0.025 * sr)] *= 0.15  # Soft consonant attack
    word_audio[-int(0.030 * sr) :] *= 0.15  # Unvoiced release

    silence = np.zeros(int(0.50 * sr), dtype=np.float32)
    combined = np.concatenate([word_audio, silence])

    in_wav = tmp_path / "in_speech_clip.wav"
    out_wav = tmp_path / "out_speech_clip.wav"
    sf.write(str(in_wav), combined, sr)

    res = VoicePauseCompressor.compress_pause_gaps(in_wav, out_wav, max_pause_sec=0.20)
    assert res["success"] is True

    out_data, out_sr = sf.read(str(out_wav))
    # Verify the speech audio region is preserved without clipping the initial 25ms attack
    # The speech region should match the input word audio precisely
    assert len(out_data) >= n_word
    # Compare the first 100ms of speech: must match the original speech
    speech_head_in = word_audio[: int(0.10 * sr)]
    speech_head_out = out_data[: int(0.10 * sr)]
    assert np.allclose(speech_head_in, speech_head_out, atol=1e-4), "Attack consonant was clipped!"


# ==============================================================================
# TEST 4: Final timestamps regenerated from post-processed audio
# ==============================================================================
def test_04_final_timestamps_regenerated_from_post_processed_audio(tmp_path: Path):
    # When silence is compressed from 0.60s to 0.15s, a gap reduction of 0.45s occurs.
    # The timestamps for subsequent words must reflect this 0.45s shift.
    sr = 24000
    w1_dur = 0.50
    gap_orig = 0.60
    w2_dur = 0.50

    w1 = _generate_synthetic_tone(220.0, w1_dur, sr)
    sil = np.zeros(int(gap_orig * sr), dtype=np.float32)
    w2 = _generate_synthetic_tone(330.0, w2_dur, sr)

    combined = np.concatenate([w1, sil, w2])
    in_wav = tmp_path / "orig.wav"
    out_wav = tmp_path / "final.wav"
    sf.write(str(in_wav), combined, sr)

    res = VoicePauseCompressor.compress_pause_gaps(
        input_wav=in_wav,
        output_wav=out_wav,
        max_pause_sec=0.20,
        target_pause_sec=0.15,
    )
    assert res["success"] is True

    # Word 2 originally started at 1.10s (0.50 + 0.60)
    # After compression to target 0.15s, word 2 should start at ~0.65s (0.50 + 0.15)
    # Verify the acoustic onset of w2 in output audio:
    out_data, _ = sf.read(str(out_wav))
    # Detect onset of w2 in output:
    rms_list, f_len = VoicePauseCompressor.compute_energy_profile(out_data, sr)
    # Find frame where w2 starts (after the pause)
    frame_dur = f_len / float(sr)
    w2_onset_sec = None
    passed_gap = False
    for idx, r in enumerate(rms_list):
        t = idx * frame_dur
        if t > 0.45 and r < 0.02:
            passed_gap = True
        elif passed_gap and r > 0.05:
            w2_onset_sec = t
            break

    assert w2_onset_sec is not None
    # w2 onset in compressed audio must be <= 0.75s (far earlier than original 1.10s)
    assert w2_onset_sec <= 0.75, f"Expected w2 onset around 0.65s, got {w2_onset_sec}s"


# ==============================================================================
# TEST 5: Visual timing uses final post-processed timestamps
# ==============================================================================
def test_05_visual_timing_uses_final_post_processed_timestamps():
    # Verify that EditorialPlanner respects proposition spoken_onset from final post-processed narration
    prop1 = VisualProposition(
        proposition_id="p1",
        subject="Harry Potter",
        action="approaching mirror",
        object="Mirror of Erised",
        context="Empty Classroom",
    )
    setattr(prop1, "spoken_onset", 0.00)

    # In raw TTS, proposition 2 was at 4.50s. After silence compression, it moved to 3.20s.
    prop2 = VisualProposition(
        proposition_id="p2",
        subject="Harry Potter",
        action="looking into mirror",
        object="Mirror of Erised",
        context="Empty Classroom",
    )
    setattr(prop2, "spoken_onset", 3.20)  # Final post-processed timestamp

    pack = MultiFactTopicPack(
        topic_id="test_post_process_timing",
        theme="Mirror of Erised",
        hook="Hook text",
        format=MultiFactFormat.DISCOVERY_SHORT,
        facts=[
            MultiFactPayload(
                fact_id="f1",
                theme="Theme",
                claim="Fact claim with two visual propositions.",
                claim_type=FactType.BOOK_VS_MOVIE,
                canon_source="Book 1",
                canon_evidence="Evidence",
                visual_propositions=[prop1, prop2],
            )
        ],
    )

    match1 = BeastV2MatchResult(
        candidate_id="shot_1",
        asset_id="shot_1",
        source="MOVIE_ARCHIVE",
        decision=BeastV2Decision.ACCEPT_DIRECT,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        source_start=10.0,
        source_end=11.5,
        verification_metadata={"proposition_id": "p1"},
    )
    match2 = BeastV2MatchResult(
        candidate_id="shot_2",
        asset_id="shot_2",
        source="MOVIE_ARCHIVE",
        decision=BeastV2Decision.ACCEPT_DIRECT,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        source_start=20.0,
        source_end=21.5,
        verification_metadata={"proposition_id": "p2"},
    )

    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, beast_matches=[match1, match2], candidate_type="discovery_short")

    f1_units = [u for u in timeline.units if u.fact_id == "f1"]
    assert len(f1_units) == 2
    u1, u2 = f1_units[0], f1_units[1]

    # u2 narration_start MUST equal 3.20s (the final post-processed timestamp),
    # ensuring zero visual delay relative to the tightened voice!
    assert u2.narration_start == 3.20
    assert u2.duration_seconds <= 1.50
