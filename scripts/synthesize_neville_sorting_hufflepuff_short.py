"""
STORY FORGE — Synthesize and Post-Process Narration for Fresh Discovery Short
=============================================================================
Topic: Why Neville Begged The Sorting Hat for Hufflepuff
Format: DISCOVERY_SHORT (25–30s)
Voice: F5-TTS Cloned Baritone
Pacing: Enforces Part A Voice Pause Fix (max silence <= 0.20s)
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
logger = logging.getLogger("SynthesizeNevilleHufflepuff")

NARRATION_TEXT = (
    "You never saw Neville Longbottom's greatest secret in the movie. "
    "During the Sorting ceremony, the film cuts straight from Hermione to Draco Malfoy. "
    "In the book, Neville sat on that stool for nearly a full minute, begging the Sorting Hat for Hufflepuff. "
    "He was terrified of Gryffindor's reputation. "
    "The Hat refused, recognizing the hidden courage that would one day destroy Voldemort's final Horcrux."
)


def synthesize_and_process():
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
    raw_wav = out_dir / "raw_disc_neville_hufflepuff_sorting_v1.wav"
    mastered_wav = out_dir / "mastered_raw_disc_neville_hufflepuff_sorting_v1.wav"
    final_paced_wav = out_dir / "narration_disc_neville_hufflepuff_sorting_v1.wav"
    words_json = out_dir / "words_disc_neville_hufflepuff_sorting_v1.json"

    # Step 1: Synthesize via F5-TTS
    logger.info("Step 1: Synthesizing raw audio via F5-TTS...")
    engine = F5TTSVoiceEngine(device="cpu", nfe_step=32)
    t0 = time.time()
    gen_res = engine.generate(
        text=NARRATION_TEXT,
        reference_audio=str(ref_audio),
        reference_text=ref_text,
        output_path=str(raw_wav),
        speed=1.0,
        seed=42
    )
    t1 = time.time()
    logger.info(f"F5-TTS Synthesis complete in {t1 - t0:.2f}s. Raw duration: {gen_res['duration_s']}s")

    # Step 2: Master Audio (-14 LUFS, -1.0 True Peak)
    logger.info("Step 2: Mastering audio chain...")
    F5TTSVoiceEngine.apply_post_processing(
        raw_wav=str(raw_wav),
        processed_wav=str(mastered_wav),
        highpass_hz=80,
        presence_gain_db=1.5,
        presence_freq_hz=2500,
        deess_freq_hz=6500,
        deess_gain_db=-2.0,
        target_lufs=-14.0,
        max_true_peak_db=-1.0
    )

    # Step 3: Silence Compression (Part A — Voice Pause Fix)
    logger.info("Step 3: Compressing pause gaps (Max pause <= 0.20s)...")
    comp_res = VoicePauseCompressor.compress_pause_gaps(
        input_wav=mastered_wav,
        output_wav=final_paced_wav,
        max_pause_sec=0.20,
        target_pause_sec=0.15,
    )
    logger.info(f"Compression results: {json.dumps(comp_res, indent=2)}")

    # Step 4: Generate FINAL Narration Timestamps on the Post-Processed Audio
    logger.info("Step 4: Transcribing words on FINAL post-processed narration audio...")
    caption_engine = CaptionEngine()
    words = caption_engine.transcribe_words(final_paced_wav)

    with open(words_json, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)

    logger.info(f"Aligned {len(words)} words saved to {words_json}")
    if words:
        logger.info(f"First word: '{words[0]['word']}' at {words[0]['start']}s, Last word: '{words[-1]['word']}' at {words[-1]['end']}s")

    # Measure final silence gaps
    gaps = VoicePauseCompressor.measure_silence_gaps(final_paced_wav, min_gap_sec=0.04)
    interior_gaps = gaps[1:-1] if len(gaps) > 2 else gaps
    max_gap = max([g["duration"] for g in interior_gaps], default=0.0)
    logger.info(f"Maximum interior silence gap in FINAL audio: {max_gap:.3f}s (must be <= 0.20s)")

    return {
        "final_wav": str(final_paced_wav),
        "words_json": str(words_json),
        "duration": comp_res["compressed_duration"],
        "max_pause": max_gap,
        "word_count": len(words),
    }


if __name__ == "__main__":
    res = synthesize_and_process()
    print("SUCCESS:", res)
