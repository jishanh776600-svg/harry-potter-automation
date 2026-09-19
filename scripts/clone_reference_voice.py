"""
clone_reference_voice.py
========================
Clones the voice from scratch_ref1.webm using XTTS v2 (Coqui TTS).
Generates a test sample using Short 5 narration text.

Reference: scratch_ref1_mono.wav (73s of clean speech)
Model: XTTS-v2 (multilingual, voice cloning from reference audio)

DO NOT modify production config. This is audition/clone test only.
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

# Ensure the model downloads to our project folder, not user home
os.environ["COQUI_TTS_AGREED"] = "1"

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REF_WAV  = BASE_DIR / "scratch_ref1_mono.wav"
OUT_DIR  = BASE_DIR / "data" / "voice_audition" / "cloned_voice"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Short 5 text (Zoo Snake) — same text used in audition for direct comparison
TEST_TEXT = (
    "At the city zoo, Harry stopped in front of a giant sleeping snake. "
    "Suddenly, the snake woke up and winked at him. "
    "Harry whispered to it, and the snake nodded back politely. "
    "His cousin Dudley pushed Harry aside to get closer. "
    "But the moment Dudley touched the tank, the glass vanished into thin air! "
    "Dudley tumbled straight into the cold water pool. "
    "The friendly snake slithered free, leaving Dudley trapped behind the glass."
)

print("=" * 68)
print("  VOICE CLONING — XTTS v2")
print("=" * 68)
print(f"  Reference audio: {REF_WAV}")
print(f"  Output dir     : {OUT_DIR}")
print(f"  Test text words: {len(TEST_TEXT.split())}")
print()

if not REF_WAV.exists():
    print(f"  ERROR: Reference WAV not found: {REF_WAV}")
    sys.exit(1)

# Load XTTS v2
print("  Loading XTTS v2 model (first run downloads ~2GB)...")
from TTS.api import TTS

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True)
print("  Model loaded.")
print()

# Generate clone samples at different speeds
# XTTS v2 doesn't have a direct rate param, but we can post-process with ffmpeg
samples = [
    ("cloned_normal.wav",   1.0,  "Normal speed (XTTS baseline)"),
    ("cloned_fast.wav",     0.85, "Fast (sox tempo 1.18x equivalent)"),
    ("cloned_vfast.wav",    0.78, "Very fast (sox tempo 1.28x equivalent)"),
]

raw_out = OUT_DIR / "cloned_raw.wav"

print("  Generating raw clone (XTTS v2 with reference speaker)...")
tts.tts_to_file(
    text=TEST_TEXT,
    speaker_wav=str(REF_WAV),
    language="en",
    file_path=str(raw_out),
)
print(f"  Raw clone saved: {raw_out}")
print()

# Post-process: create 3 speed variants using ffmpeg atempo
for filename, tempo, label in samples:
    out_path = OUT_DIR / filename
    if tempo == 1.0:
        # Just copy/normalize
        os.system(
            f'ffmpeg -y -i "{raw_out}" -af "loudnorm" -acodec pcm_s16le -ar 44100 -ac 1 "{out_path}" -loglevel error'
        )
    else:
        # atempo must be between 0.5 and 2.0
        # For tempo 0.78 we need two atempo filters: 0.78 = 0.9 * 0.867 approx
        # Actually for speeding up: if tempo=0.85, we want output that plays faster
        # atempo=1/tempo applied means shorter output
        speed = 1.0 / tempo
        if speed <= 2.0:
            atempo = f"atempo={speed:.3f}"
        else:
            # Chain two atempo filters for >2x
            atempo = f"atempo=2.0,atempo={speed/2.0:.3f}"
        os.system(
            f'ffmpeg -y -i "{raw_out}" -af "{atempo},loudnorm" -acodec pcm_s16le -ar 44100 -ac 1 "{out_path}" -loglevel error'
        )
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  OK: {filename}  ({label})")
    else:
        print(f"  FAILED: {filename}")

print()
print("=" * 68)
print("  CLONED VOICE FILES:")
print(f"  {OUT_DIR}")
print()
for filename, tempo, label in samples:
    p = OUT_DIR / filename
    if p.exists():
        size_kb = p.stat().st_size // 1024
        print(f"    {filename:<30} {size_kb:>6} KB  -- {label}")
print()
print("  COMPARE AGAINST REFERENCE:")
print(f"    scratch_ref1_mono.wav  (original reference audio)")
print()
print("  PRODUCTION VOICE UNCHANGED: en-US-AndrewNeural +24Hz +14%")
print("  Provider unchanged: Azure/Edge TTS")
print("=" * 68)
