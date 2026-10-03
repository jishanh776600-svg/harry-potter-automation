"""
STORY FORGE — Synthesize Mirror of Erised Discovery Short Narration using F5-TTS
==============================================================================
Synthesizes the validated 25-30s Discovery Short script using the approved F5-TTS
reference voice clone model conditioned on the selected clean reference speaker.
Aligns words using CaptionEngine (faster-whisper).
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
from engines.caption_engine import CaptionEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("F5TTSValidationGen")

NARRATION_TEXT = (
    "The movies hid a brilliant secret on the Mirror of Erised in plain sight. "
    "Carved across the golden arch is a strange inscription. "
    "It reads: Erised stra ehru oyt ube cafru oyt on wohsi. "
    "It looks like an ancient foreign spell, but it is actually plain English. "
    "If you read the carved letters backward in a mirror, the secret appears. "
    "It reveals: I show not your face, but your heart's desire. "
    "That is why the mirror is named Erised. "
    "It is literally the word desire spelled backward. "
    "The mirror only shows what your heart wants most."
)


def synthesize_validation_narration():
    logger.info("Initializing F5-TTS Validation Narration Synthesis...")

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
    raw_wav = out_dir / "raw_validation_disc_mirror_of_erised_v1.wav"
    mastered_wav = out_dir / "narration_validation_disc_mirror_of_erised_v1.wav"
    words_json = out_dir / "words_validation_disc_mirror_of_erised_v1.json"

    # 1. Synthesize via F5-TTS
    engine = F5TTSVoiceEngine(device="cpu", nfe_step=32)
    t0 = time.time()
    # Speed 1.05 targets ~26.0 - 27.5s for 96 words
    gen_res = engine.generate(
        text=NARRATION_TEXT,
        reference_audio=str(ref_audio),
        reference_text=ref_text,
        output_path=str(raw_wav),
        speed=1.05,
        seed=42
    )
    t1 = time.time()
    logger.info(f"F5-TTS Raw Synthesis completed in {t1 - t0:.2f}s. Raw duration: {gen_res['duration_s']}s")

    # 2. Master Audio (Broadcast standard: -14 LUFS, -1.0 True Peak)
    logger.info("Applying broadcast voice mastering chain...")
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
    logger.info(f"Mastered voice saved to {mastered_wav}")

    # 3. Align Words with CaptionEngine (faster-whisper)
    logger.info("Generating word timestamps via CaptionEngine (faster-whisper)...")
    caption_engine = CaptionEngine()
    words = caption_engine.transcribe_words(mastered_wav)

    with open(words_json, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)

    logger.info(f"Aligned {len(words)} words saved to {words_json}")
    if words:
        logger.info(f"First word: '{words[0]['word']}' at {words[0]['start']}s, Last word: '{words[-1]['word']}' at {words[-1]['end']}s")

    return {
        "status": "success",
        "raw_wav": str(raw_wav),
        "mastered_wav": str(mastered_wav),
        "words_json": str(words_json),
        "duration": gen_res["duration_s"],
        "words_count": len(words)
    }


if __name__ == "__main__":
    synthesize_validation_narration()
