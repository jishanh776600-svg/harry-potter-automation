"""
STORY FORGE — Synthesize Chamber Parseltongue Discovery Short Narration using F5-TTS
====================================================================================
Topic: The Parseltongue Secret of the Chamber Entrance
Content ID: disc_chamber_parseltongue_v1
Voice: Reference F5-TTS clone
Pacing: 30% Pause Compression applied post-mastering (max pause <= 0.140s)
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engines.tts.f5_tts_voice_engine import F5TTSVoiceEngine
from engines.tts.voice_pause_compressor import VoicePauseCompressor
from engines.caption_engine import CaptionEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SynthesizeChamberParseltongue")

NARRATION_TEXT = (
    "Everyone believed the Chamber of Secrets could only be opened through dark, ancient magic. "
    "When Harry Potter examined the central stone sink in Moaning Myrtle's bathroom, "
    "he found a tiny snake carved into the copper tap. "
    "Harry didn't cast a spell. "
    "Instead, he hissed in Parseltongue. "
    "The copper snake glowed, the massive washbasins slid apart, and the stone floor collapsed downward into the darkness, "
    "revealing the vertical entrance pipe."
)


def synthesize_narration():
    logger.info("Initializing F5-TTS Narration Synthesis for Chamber Parseltongue Discovery Short...")

    ref_audio = PROJECT_ROOT / "data" / "voice_cloning" / "f5_tts" / "reference" / "selected_reference_speaker_24k.wav"
    meta_json = PROJECT_ROOT / "data" / "voice_cloning" / "f5_tts" / "reference" / "selected_reference_metadata.json"

    if not ref_audio.exists():
        raise FileNotFoundError(f"Reference audio missing: {ref_audio}")
    if not meta_json.exists():
        raise FileNotFoundError(f"Reference metadata missing: {meta_json}")

    with open(meta_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
    ref_text = meta["selected_reference"]["transcript_text"]
    logger.info(f"Conditioning reference text: '{ref_text}'")

    out_dir = PROJECT_ROOT / "data" / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_wav = out_dir / "raw_disc_chamber_parseltongue_v1.wav"
    mastered_uncompressed_wav = out_dir / "mastered_raw_disc_chamber_parseltongue_v1.wav"
    final_mastered_wav = out_dir / "narration_disc_chamber_parseltongue_v1.wav"
    words_json = out_dir / "words_disc_chamber_parseltongue_v1.json"

    # 1. Synthesize via F5-TTS
    engine = F5TTSVoiceEngine(device="cpu", nfe_step=32)
    t0 = time.time()
    gen_res = engine.generate(
        text=NARRATION_TEXT,
        reference_audio=str(ref_audio),
        reference_text=ref_text,
        output_path=str(raw_wav),
        speed=1.06,  # Confident, crisp pacing
        seed=101
    )
    t1 = time.time()
    logger.info(f"F5-TTS Raw Synthesis completed in {t1 - t0:.2f}s. Raw duration: {gen_res['duration_s']}s")

    # 2. Master Audio (Broadcast standard: -14 LUFS, -1.0 True Peak)
    logger.info("Applying broadcast voice mastering chain...")
    F5TTSVoiceEngine.apply_post_processing(
        raw_wav=str(raw_wav),
        processed_wav=str(mastered_uncompressed_wav),
        highpass_hz=80,
        presence_gain_db=1.5,
        presence_freq_hz=2500,
        deess_freq_hz=6500,
        deess_gain_db=-2.0,
        target_lufs=-14.0,
        max_true_peak_db=-1.0
    )

    # 3. Apply PART B 30% Pause Compression
    # max_pause_sec=0.14, target_pause_sec=0.105
    logger.info("Applying PART B Precision Voice Pause Compression (30% reduction, max gap <= 0.14s)...")
    comp_res = VoicePauseCompressor.compress_pause_gaps(
        input_wav=mastered_uncompressed_wav,
        output_wav=final_mastered_wav,
        max_pause_sec=0.14,
        target_pause_sec=0.105,
        leading_silence_max_sec=0.07,
        trailing_silence_max_sec=0.12,
    )
    logger.info(f"Pause Compression Result: Original: {comp_res['original_duration_sec']}s -> Compressed: {comp_res['compressed_duration_sec']}s (Cut: {comp_res['total_silence_cut_sec']}s)")

    # Verify pause compression
    gaps = VoicePauseCompressor.measure_silence_gaps(final_mastered_wav, min_gap_sec=0.04)
    dur = comp_res['compressed_duration_sec']
    interior_gaps = [g for g in gaps if 0.10 < g["start"] < (dur - 0.20)]
    max_pause = max([g["duration"] for g in interior_gaps], default=0.0)
    logger.info(f"Interior silence gaps: {len(interior_gaps)}, Max interior pause: {max_pause:.3f}s (Ceiling: <= 0.140s)")
    if max_pause > 0.140:
        logger.warning(f"Warning: interior pause {max_pause:.3f}s slightly exceeds 0.140s")

    # 4. Word-level alignment via Whisper
    logger.info("Generating word-level alignment using CaptionEngine...")
    caption_engine = CaptionEngine(model_size="base")
    words = caption_engine.transcribe_words(final_mastered_wav)
    logger.info(f"Aligned {len(words)} words.")

    with open(words_json, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)
    logger.info(f"Words JSON saved to {words_json}")

    print("\n--- SYNTHESIS COMPLETE ---")
    print(f"Mastered Compressed Narration: {final_mastered_wav}")
    print(f"Total Duration: {dur:.2f}s")
    print(f"Word Count: {len(words)}")
    return final_mastered_wav, words_json, dur


if __name__ == "__main__":
    synthesize_narration()
