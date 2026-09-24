"""
STORY FORGE — Synthesize Battle of Hogwarts Narration using F5-TTS
==================================================================
Synthesizes the approved 6-fact Discovery package narration using the
approved F5-TTS reference voice clone conditioned on the clean reference speaker.
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
logger = logging.getLogger("F5TTSNarrationGen")

# Canonical approved 6-fact Discovery script
NARRATION_TEXT = (
    "Movie finale of the Battle of Hogwarts looks incredible, but it actually reversed the book's most important moments, "
    "starting with the final duel. Harry and Voldemort never flew around the castle merged in smoke. Their confrontation was "
    "a psychological trial in the Great Hall, circled in dead silence by hundreds of spectators as Harry methodically dismantled Riddle's arrogance. "
    "Next, the ground assault that broke the Death Eater lines wasn't wizards. It was led by Kreacher at the head of the Hogwarts house-elves, "
    "brandishing carving knives and cleavers while shouting to fight in the name of brave Regulus. "
    "Right behind them, the Forbidden Forest centaurs broke their neutrality, firing heavy arrows and charging straight into the entrance hall alongside Grawp. "
    "Even Molly Weasley's duel with Bellatrix was far more ferocious. Stone floor beneath them cracked from magical heat before Molly struck Bellatrix "
    "directly over the heart, toppling her dead. "
    "Then comes the Elder Wand. In the film Harry snaps it in half and throws it away. In the book he uses its power for one single task: "
    "repairing his broken phoenix-feather wand before returning the Elder Wand intact to Dumbledore's tomb so its power will die with him. "
    "Which brings us to the biggest betrayal: Voldemort's death. He didn't dissolve into floating flakes. His rebounding curse dropped him to "
    "the stone floor with a dull, mundane thud, leaving behind an ordinary human corpse that was dragged into a chamber away from the hall. "
    "The filmmakers wanted a fantasy spectacle, but Rowling's entire point was the opposite: after decades of terror, Tom Riddle died just like any other man."
)


def synthesize_f5_narration():
    logger.info("Initializing F5-TTS Narration Synthesis...")

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
    raw_wav = out_dir / "raw_f5_battle_of_hogwarts.wav"
    mastered_wav = out_dir / "narration_f5_battle_of_hogwarts.wav"
    words_json = out_dir / "words_f5_battle_of_hogwarts.json"

    # 1. Synthesize via F5-TTS
    engine = F5TTSVoiceEngine(device="cpu", nfe_step=32)
    t0 = time.time()
    # Speed 1.10 targets brisk Shorts pacing (~72-76 seconds for ~269 words)
    gen_res = engine.generate(
        text=NARRATION_TEXT,
        reference_audio=str(ref_audio),
        reference_text=ref_text,
        output_path=str(raw_wav),
        speed=1.10,
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
    words = caption_engine.transcribe_words(str(mastered_wav))

    with open(words_json, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2)

    logger.info(f"Word alignment complete! {len(words)} words saved to {words_json}")

    # Verify duration
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(mastered_wav)
    ]
    p_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True)
    dur = float(json.loads(p_res.stdout)["format"]["duration"])
    wps = len(words) / max(0.1, dur)
    logger.info(f"[F5-TTS SUMMARY] Duration: {dur:.2f}s | Words: {len(words)} | WPS: {wps:.2f}")

    return {
        "mastered_wav": str(mastered_wav),
        "words_json": str(words_json),
        "duration_sec": dur,
        "word_count": len(words),
        "wps": wps
    }


if __name__ == "__main__":
    synthesize_f5_narration()
