"""
STORY FORGE — Synthesize Snape's First Words Discovery Short Narration using F5-TTS
===================================================================================
Topic: Snape's First Words to Harry: The Secret Meaning
Format: DISCOVERY_SHORT (Target: ~24–25s)
Voice: Reference F5-TTS clone (reference-conditioned baritone)
Pacing: PART B 30% Pause Compression applied post-mastering
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
logger = logging.getLogger("SynthesizeSnapeFirstWords")

NARRATION_TEXT = (
    "Snape’s very first words to Harry Potter weren’t an insult—they were a hidden apology. "
    "In their first Potions class, Snape demands: "
    "What would I get if I added powdered root of asphodel to an infusion of wormwood? "
    "In Victorian flower language, asphodel is a type of lily meaning my regrets follow you to the grave, "
    "while wormwood symbolizes bitter sorrow. "
    "Combined, Snape's first words secretly told Harry: "
    "I bitterly regret Lily's death."
)


def synthesize_narration():
    logger.info("Initializing F5-TTS Narration Synthesis for Snape's First Words Discovery Short...")

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
    raw_wav = out_dir / "raw_disc_snape_first_words_v1.wav"
    mastered_uncompressed_wav = out_dir / "mastered_raw_disc_snape_first_words_v1.wav"
    final_mastered_wav = out_dir / "narration_disc_snape_first_words_v1.wav"
    words_json = out_dir / "words_disc_snape_first_words_v1.json"

    # 1. Synthesize via F5-TTS
    engine = F5TTSVoiceEngine(device="cpu", nfe_step=32)
    t0 = time.time()
    gen_res = engine.generate(
        text=NARRATION_TEXT,
        reference_audio=str(ref_audio),
        reference_text=ref_text,
        output_path=str(raw_wav),
        speed=1.05,  # Crisp, confident pacing
        seed=42
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
    logger.info(f"Pause compression report: {comp_res}")

    # Re-verify loudness on the final compressed audio
    probe_cmd = [
        "ffmpeg", "-i", str(final_mastered_wav),
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    p_run = subprocess.run(probe_cmd, stderr=subprocess.PIPE, text=True)
    out_lines = p_run.stderr.split("\n")
    lufs_val = -14.0
    for l in reversed(out_lines):
        if "I:" in l and "LUFS" in l:
            try:
                lufs_val = float(l.split("I:")[1].split("LUFS")[0].strip())
                break
            except Exception:
                pass
    logger.info(f"Final mastered narration duration: {comp_res['final_duration_sec']}s, Integrated LUFS: {lufs_val} LUFS")

    # 4. Align Words with CaptionEngine (faster-whisper)
    logger.info("Generating word timestamps via CaptionEngine (faster-whisper)...")
    caption_engine = CaptionEngine()
    words = caption_engine.transcribe_words(final_mastered_wav)

    with open(words_json, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)

    logger.info(f"Aligned {len(words)} words saved to {words_json}")
    if words:
        logger.info(f"First word: '{words[0]['word']}' at {words[0]['start']}s, Last word: '{words[-1]['word']}' at {words[-1]['end']}s")

    return {
        "status": "success",
        "raw_wav": str(raw_wav),
        "final_mastered_wav": str(final_mastered_wav),
        "words_json": str(words_json),
        "duration": comp_res["final_duration_sec"],
        "words_count": len(words),
        "pause_compression": comp_res
    }


if __name__ == "__main__":
    synthesize_narration()
