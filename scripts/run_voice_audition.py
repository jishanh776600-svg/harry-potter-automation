"""
STEP: Azure/Edge Voice Audition for Reference Match
Generates labeled WAV files for all male en-US Azure/Edge voices
at multiple speaking rates to find the best match for scratch_ref1.webm.

Reference measurements:
  Median F0   : 176.4 Hz
  Mean F0     : 185.9 Hz
  WPM         : 214.2 (extremely fast)
  Pauses      : 2 in 73s (essentially seamless)
  Centroid    : 2539 Hz (bright/clear)
  Prosody var : 37.6% (high expressiveness)
  Accent      : General American English

DO NOT modify production config. Audition only.
"""

import asyncio
import json
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import edge_tts

# ── Test text (Short 5, unchanged) ───────────────────────────────────────────
TEST_TEXT = (
    "At the city zoo, Harry stopped in front of a giant sleeping snake. "
    "Suddenly, the snake woke up and winked at him. "
    "Harry whispered to it, and the snake nodded back politely. "
    "His cousin Dudley pushed Harry aside to get closer. "
    "But the moment Dudley touched the tank, the glass vanished into thin air! "
    "Dudley tumbled straight into the cold water pool. "
    "The friendly snake slithered free, leaving Dudley trapped behind the glass."
)
WORD_COUNT = len(TEST_TEXT.split())

# ── Candidate voices (all available en-US Male from edge-tts --list-voices) ──
CANDIDATES = [
    # id,                            label,         why_candidate
    ("en-US-AndrewNeural",     "Andrew",    "Current production voice (baseline)"),
    ("en-US-GuyNeural",        "Guy",       "Passion tag — energetic storytelling"),
    ("en-US-RogerNeural",      "Roger",     "Lively tag — young energetic"),
    ("en-US-BrianNeural",      "Brian",     "Casual/sincere — conversational warmth"),
    ("en-US-EricNeural",       "Eric",      "Rational/clear — precise delivery"),
    ("en-US-ChristopherNeural","Christopher","Authority/reliable — strong narrator"),
    ("en-US-SteffanNeural",    "Steffan",   "Rational/clear — alternative to Eric"),
]

# ── Rate configurations to test ───────────────────────────────────────────────
# Reference is ~214 WPM. Test 3 rates per voice.
# Each voice has a natural baseline; boosts shift it toward 214+ WPM.
RATE_CONFIGS = [
    ("+15%", "+0Hz"),   # Moderate boost
    ("+25%", "+0Hz"),   # Approaching reference speed
    ("+30%", "+0Hz"),   # At/above reference speed
]

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "voice_audition", "reference_match")
OUT_DIR = os.path.normpath(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)

WAV_PATH_REF = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "scratch_ref1_mono.wav")
)

# ── Acoustic measurement helper ───────────────────────────────────────────────
def measure_wav(wav_path: str) -> dict:
    """Quick acoustic measurements on a WAV file using numpy + parselmouth."""
    result = {"error": None}
    try:
        import librosa
        import parselmouth
        from parselmouth.praat import call

        y, sr = librosa.load(wav_path, sr=None, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)
        result["duration_sec"] = round(duration, 2)

        # Speaking rate from word count and duration
        result["word_count"] = WORD_COUNT
        result["wpm"] = round((WORD_COUNT / duration) * 60, 1) if duration > 0 else 0

        # Pitch via Praat
        snd = parselmouth.Sound(wav_path)
        pitch_obj = call(snd, "To Pitch", 0.0, 50, 600)
        pv = pitch_obj.selected_array["frequency"]
        voiced = pv[pv > 0]
        if len(voiced) > 0:
            result["mean_f0"]   = round(float(np.mean(voiced)), 1)
            result["median_f0"] = round(float(np.median(voiced)), 1)
            result["min_f0"]    = round(float(np.min(voiced)), 1)
            result["max_f0"]    = round(float(np.max(voiced)), 1)
            result["std_f0"]    = round(float(np.std(voiced)), 1)
            result["f0_range"]  = round(float(np.max(voiced) - np.min(voiced)), 1)
            result["prosody_var_pct"] = round(float(np.std(voiced) / np.mean(voiced)) * 100, 1)
        else:
            result["mean_f0"] = result["median_f0"] = 0

        # Pauses
        frame_len = int(sr * 0.025)
        hop_len   = int(sr * 0.010)
        rms = librosa.feature.rms(y=y, frame_length=frame_len, hop_length=hop_len)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_len)
        in_sil = False; p_start = 0; pauses = []
        for i, r in enumerate(rms):
            if r < 0.005 and not in_sil:
                in_sil = True; p_start = times[i]
            elif r >= 0.005 and in_sil:
                in_sil = False
                pd = times[i] - p_start
                if pd > 0.08: pauses.append(round(float(pd), 3))
        result["pause_count"] = len(pauses)
        result["avg_pause_ms"] = round(float(np.mean(pauses)) * 1000, 0) if pauses else 0

        # Spectral centroid
        sc = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        result["spectral_centroid_hz"] = round(float(np.mean(sc)), 1)

        # Loudness (RMS dB)
        rms_all = librosa.feature.rms(y=y)[0]
        result["loudness_rms_db"] = round(float(20 * np.log10(np.mean(rms_all) + 1e-9)), 1)

    except Exception as e:
        result["error"] = str(e)
    return result


# ── TTS generation ────────────────────────────────────────────────────────────
async def generate_mp3(voice_id: str, rate: str, pitch: str, out_mp3: str):
    """Generate speech via edge-tts and save as MP3."""
    communicate = edge_tts.Communicate(TEST_TEXT, voice=voice_id, rate=rate, pitch=pitch)
    await communicate.save(out_mp3)


def generate_wav(voice_id: str, rate: str, pitch: str, out_wav: str) -> bool:
    """Generate MP3 via edge-tts then convert to WAV with ffmpeg."""
    mp3_path = out_wav.replace(".wav", ".mp3")
    try:
        asyncio.run(generate_mp3(voice_id, rate, pitch, mp3_path))
        ret = os.system(
            f'ffmpeg -y -i "{mp3_path}" -acodec pcm_s16le -ar 44100 -ac 1 "{out_wav}" -loglevel error'
        )
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
        return ret == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
    except Exception as e:
        print(f"    ERROR generating {voice_id} rate={rate}: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  AZURE/EDGE VOICE AUDITION — Reference Match")
    print("=" * 72)
    print(f"  Test text  : {WORD_COUNT} words")
    print(f"  Output dir : {OUT_DIR}")
    print(f"  Voices     : {len(CANDIDATES)}")
    print(f"  Rates each : {len(RATE_CONFIGS)}")
    print(f"  Total files: {len(CANDIDATES) * len(RATE_CONFIGS)}")
    print()

    # Reference measurements
    print("  REFERENCE (scratch_ref1.webm):")
    print("    Median F0   : 176.4 Hz")
    print("    Mean F0     : 185.9 Hz")
    print("    WPM         : 214.2 (extremely fast)")
    print("    Pauses      : 2 in 73s")
    print("    Centroid    : 2539 Hz")
    print("    Prosody var : 37.6%")
    print()

    results = []
    file_index = 1

    for voice_id, label, why in CANDIDATES:
        print(f"  [{label}] {voice_id}")
        print(f"    Why: {why}")

        for rate, pitch in RATE_CONFIGS:
            rate_tag = rate.replace("+", "p").replace("%", "pct").replace("-", "m")
            pitch_tag = pitch.replace("+", "p").replace("Hz", "hz").replace("-", "m")
            filename = f"{file_index:02d}_{label}_rate{rate_tag}_pitch{pitch_tag}.wav"
            out_path = os.path.join(OUT_DIR, filename)

            print(f"    rate={rate} pitch={pitch} -> {filename}")
            ok = generate_wav(voice_id, rate, pitch, out_path)
            time.sleep(0.5)  # be polite to the API

            if ok:
                measurements = measure_wav(out_path)
                measurements["file"] = filename
                measurements["voice_id"] = voice_id
                measurements["label"] = label
                measurements["rate"] = rate
                measurements["pitch"] = pitch
                measurements["why"] = why
                measurements["file_index"] = file_index

                # Similarity scores vs reference
                ref_median = 176.4
                ref_wpm    = 214.2
                ref_cent   = 2539.3
                ref_pv     = 37.6
                ref_pauses = 2.0

                f0_delta  = abs(measurements.get("median_f0", 0) - ref_median)
                wpm_delta = abs(measurements.get("wpm", 0) - ref_wpm)
                cnt_delta = abs(measurements.get("spectral_centroid_hz", 0) - ref_cent)
                pv_delta  = abs(measurements.get("prosody_var_pct", 0) - ref_pv)
                pz_delta  = abs(measurements.get("pause_count", 0) - ref_pauses)

                # Weighted composite score (lower = closer to reference)
                composite = (
                    f0_delta  * 0.3 +
                    wpm_delta * 0.3 +
                    cnt_delta * 0.01 +
                    pv_delta  * 1.0 +
                    pz_delta  * 5.0
                )
                measurements["f0_delta"]        = round(f0_delta, 1)
                measurements["wpm_delta"]       = round(wpm_delta, 1)
                measurements["centroid_delta"]  = round(cnt_delta, 1)
                measurements["prosody_delta"]   = round(pv_delta, 1)
                measurements["pause_delta"]     = round(pz_delta, 1)
                measurements["composite_score"] = round(composite, 2)

                print(f"      OK | dur={measurements.get('duration_sec','?')}s | "
                      f"WPM={measurements.get('wpm','?')} | "
                      f"F0med={measurements.get('median_f0','?')}Hz | "
                      f"pauses={measurements.get('pause_count','?')} | "
                      f"score={measurements.get('composite_score','?')}")
            else:
                measurements = {
                    "file": filename, "voice_id": voice_id, "label": label,
                    "rate": rate, "pitch": pitch, "why": why,
                    "file_index": file_index, "error": "Generation failed"
                }
                print(f"      FAILED")

            results.append(measurements)
            file_index += 1

        print()

    # ── Save metadata JSON ──────────────────────────────────────────────────────
    meta_path = os.path.join(OUT_DIR, "audition_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "test_text": TEST_TEXT,
            "word_count": WORD_COUNT,
            "reference": {
                "file": "scratch_ref1_mono.wav",
                "median_f0_hz": 176.4,
                "mean_f0_hz": 185.9,
                "wpm": 214.2,
                "pause_count": 2,
                "avg_pause_ms": 95,
                "spectral_centroid_hz": 2539.3,
                "prosody_var_pct": 37.6,
            },
            "candidates": results,
        }, f, indent=2)

    # ── Summary table ───────────────────────────────────────────────────────────
    print("=" * 72)
    print("  ACOUSTIC COMPARISON TABLE")
    print("=" * 72)
    print(f"  {'File':<45} {'WPM':>6} {'F0med':>6} {'Pauses':>7} {'Score':>7}")
    print(f"  {'REF: scratch_ref1.webm':<45} {'214.2':>6} {'176.4':>6} {'2':>7} {'--':>7}")
    print(f"  {'-'*45} {'-'*6} {'-'*6} {'-'*7} {'-'*7}")

    valid = [r for r in results if "error" not in r or r.get("error") is None]
    valid_clean = [r for r in valid if isinstance(r.get("composite_score"), (int, float))]
    ranked = sorted(valid_clean, key=lambda x: x["composite_score"])

    for r in results:
        wpm = r.get("wpm", "ERR")
        f0  = r.get("median_f0", "ERR")
        pz  = r.get("pause_count", "ERR")
        sc  = r.get("composite_score", "ERR")
        print(f"  {r['file']:<45} {str(wpm):>6} {str(f0):>6} {str(pz):>7} {str(sc):>7}")

    print()
    print("=" * 72)
    print("  TOP 5 CLOSEST TO REFERENCE (by composite score):")
    print("=" * 72)
    for i, r in enumerate(ranked[:5], 1):
        print(f"  #{i}: {r['file']}")
        print(f"       WPM={r.get('wpm')} | F0med={r.get('median_f0')}Hz | "
              f"Pauses={r.get('pause_count')} | Score={r.get('composite_score')}")
    print()

    print("=" * 72)
    print("  AUDITION FILES LOCATION:")
    print(f"  {OUT_DIR}")
    print("=" * 72)
    print()
    print("  Metadata saved to:", meta_path)
    print()
    print("  PRODUCTION VOICE UNCHANGED: en-US-AndrewNeural +24Hz +14%")
    print("  Provider unchanged: Azure/Edge TTS")
    print()
    print("  DONE — Listen to the files and choose your preferred voice.")


if __name__ == "__main__":
    main()
