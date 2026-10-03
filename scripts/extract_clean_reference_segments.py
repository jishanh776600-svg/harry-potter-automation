"""
STORY FORGE — Clean Speaker Reference Segment Selection Engine
==============================================================
Analyzes reference audio tracks from Wizards' Laboratory Shorts, identifies
complete continuous sentence clauses, scores acoustic cleanliness, BGM interference,
volume stability, and phonetic diversity, and selects the optimal speaker reference
segment for F5-TTS conditioning.
"""

import json
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import scipy.signal as signal
import soundfile as sf
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ReferenceSegmentSelector")


def compute_spectral_cleanliness(segment_audio: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Computes objective acoustic quality metrics for speaker conditioning:
    - SNR proxy: ratio of high-energy speech frames to low-energy trough frames
    - Volume stability: standard deviation of frame RMS
    - Spectral flatness: lower flatness indicates distinct harmonic speech formants rather than noise/music
    """
    frame_len = int(sr * 0.030)
    hop_len = int(sr * 0.010)

    frame_rms = []
    spectral_flatness_list = []

    for i in range(0, len(segment_audio) - frame_len, hop_len):
        frame = segment_audio[i:i+frame_len]
        rms = np.sqrt(np.mean(frame**2))
        frame_rms.append(rms)

        # Spectral flatness
        fft_vals = np.abs(np.fft.rfft(frame * np.hanning(len(frame)))) + 1e-12
        geometric_mean = np.exp(np.mean(np.log(fft_vals)))
        arithmetic_mean = np.mean(fft_vals)
        flatness = geometric_mean / arithmetic_mean
        spectral_flatness_list.append(flatness)

    frame_rms = np.array(frame_rms)
    p90 = np.percentile(frame_rms, 90)
    p10 = np.percentile(frame_rms, 10)
    snr_proxy = float(20 * np.log10((p90 + 1e-6) / (p10 + 1e-6)))

    rms_std = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-6))
    mean_flatness = float(np.mean(spectral_flatness_list))

    return {
        "snr_proxy_db": round(snr_proxy, 2),
        "rms_stability": round(rms_std, 3),
        "mean_spectral_flatness": round(mean_flatness, 4),
    }


def phonetic_diversity_score(text: str) -> float:
    """Estimates unique phoneme/character distribution across text."""
    words = text.lower().split()
    unique_words = set(words)
    diversity = len(unique_words) / max(1, len(words))
    # Count unique character n-grams (bigrams)
    cleaned = "".join([c for c in text.lower() if c.isalnum() or c.isspace()])
    bigrams = set(cleaned[i:i+2] for i in range(len(cleaned)-1))
    score = (diversity * 0.5) + (min(len(bigrams), 50) / 50.0 * 0.5)
    return round(float(score), 3)


def find_candidate_segments(audio_path: str, source_id: str, whisper_model: WhisperModel) -> List[Dict[str, Any]]:
    logger.info(f"Transcribing and locating continuous sentence segments in: {audio_path}")
    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        mono = data.mean(axis=1)
    else:
        mono = data

    segments, _ = whisper_model.transcribe(audio_path, word_timestamps=True)
    seg_list = list(segments)
    all_sentences: List[Dict[str, Any]] = []

    # Iterate through segments and group consecutive segments into 4.5s - 9.5s spans
    for i in range(len(seg_list)):
        combined_text = []
        start_t = seg_list[i].start
        end_t = seg_list[i].end

        for j in range(i, min(i + 4, len(seg_list))):
            combined_text.append(seg_list[j].text.strip())
            end_t = seg_list[j].end
            dur = end_t - start_t
            if 4.5 <= dur <= 9.5 and len(" ".join(combined_text).split()) >= 12:
                all_sentences.append({
                    "source_id": source_id,
                    "text": " ".join(combined_text),
                    "start": round(start_t, 3),
                    "end": round(end_t, 3),
                    "duration": round(dur, 3),
                })
                break

    candidates = []
    for idx, cand in enumerate(all_sentences):
        s_sample = int(cand["start"] * sr)
        e_sample = int(cand["end"] * sr)
        clip_audio = mono[s_sample:e_sample]

        metrics = compute_spectral_cleanliness(clip_audio, sr)
        p_score = phonetic_diversity_score(cand["text"])

        # Composite Cleanliness Score (higher is better)
        # Higher SNR proxy, lower flatness (clearer harmonics), higher phonetic diversity
        composite_score = (
            (metrics["snr_proxy_db"] * 0.40) +
            ((1.0 - min(metrics["mean_spectral_flatness"] * 10, 0.9)) * 30.0) +
            (p_score * 20.0) -
            (metrics["rms_stability"] * 10.0)
        )

        cand_record = {
            "candidate_id": f"{source_id}_cand_{idx+1:02d}",
            "source_audio": audio_path,
            "text": cand["text"],
            "start_s": cand["start"],
            "end_s": cand["end"],
            "duration_s": cand["duration"],
            "snr_proxy_db": metrics["snr_proxy_db"],
            "rms_stability": metrics["rms_stability"],
            "spectral_flatness": metrics["mean_spectral_flatness"],
            "phonetic_diversity": p_score,
            "composite_quality_score": round(float(composite_score), 2),
            "audio_samples": clip_audio,
            "sample_rate": sr,
        }
        candidates.append(cand_record)

    return candidates


def select_best_reference_segment() -> Dict[str, Any]:
    ref1_path = "data/reference_analysis/reference_audio.wav"
    ref2_path = "data/reference_analysis/barty_crouch_audio.wav"

    out_base = Path("data/voice_cloning/f5_tts/reference")
    cand_dir = out_base / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing faster-whisper for segment segmentation...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    all_cands = []
    if os.path.exists(ref1_path):
        cands1 = find_candidate_segments(ref1_path, "snape", whisper_model)
        all_cands.extend(cands1)

    if os.path.exists(ref2_path):
        cands2 = find_candidate_segments(ref2_path, "barty", whisper_model)
        all_cands.extend(cands2)

    if not all_cands:
        raise RuntimeError("No suitable continuous sentence segments found in reference audio.")

    # Sort candidates by composite quality score descending
    all_cands.sort(key=lambda x: x["composite_quality_score"], reverse=True)

    logger.info(f"Evaluated {len(all_cands)} candidate speech segments across both reference Shorts.")

    # Export candidate WAVs and metadata
    saved_candidates = []
    for c in all_cands[:6]:
        cand_wav = cand_dir / f"{c['candidate_id']}.wav"
        # Apply highpass 80Hz to eliminate sub-rumble
        filtered = signal.sosfilt(signal.butter(4, 80, 'hp', fs=c['sample_rate'], output='sos'), c["audio_samples"])
        sf.write(str(cand_wav), filtered, c["sample_rate"])

        saved_candidates.append({
            "candidate_id": c["candidate_id"],
            "source_audio": c["source_audio"],
            "text": c["text"],
            "duration_s": c["duration_s"],
            "snr_proxy_db": c["snr_proxy_db"],
            "rms_stability": c["rms_stability"],
            "spectral_flatness": c["spectral_flatness"],
            "phonetic_diversity": c["phonetic_diversity"],
            "composite_quality_score": c["composite_quality_score"],
            "wav_path": str(cand_wav.as_posix()),
        })

    # Best candidate
    best = all_cands[0]
    best_wav_path = out_base / "selected_reference_speaker.wav"
    best_json_path = out_base / "selected_reference_metadata.json"

    # Save best segment
    best_filtered = signal.sosfilt(signal.butter(4, 80, 'hp', fs=best['sample_rate'], output='sos'), best["audio_samples"])
    sf.write(str(best_wav_path), best_filtered, best["sample_rate"])

    # Convert to 16-bit 24kHz standard for TTS prompt conditioning
    best_24k_wav = out_base / "selected_reference_speaker_24k.wav"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(best_wav_path),
        "-ar", "24000", "-ac", "1",
        str(best_24k_wav)
    ], check=True)

    selection_report = {
        "selected_reference": {
            "candidate_id": best["candidate_id"],
            "source_short": best["source_audio"],
            "transcript_text": best["text"],
            "duration_s": best["duration_s"],
            "start_time_s": best["start_s"],
            "end_time_s": best["end_s"],
            "composite_quality_score": best["composite_quality_score"],
            "snr_proxy_db": best["snr_proxy_db"],
            "spectral_flatness": best["spectral_flatness"],
            "phonetic_diversity": best["phonetic_diversity"],
            "raw_wav_path": str(best_wav_path.as_posix()),
            "conditioned_24k_wav_path": str(best_24k_wav.as_posix()),
        },
        "all_evaluated_candidates": saved_candidates,
    }

    with open(best_json_path, "w", encoding="utf-8") as f:
        json.dump(selection_report, f, indent=2)

    logger.info(f"Optimal speaker reference segment selected: {best['candidate_id']} ({best['duration_s']}s)")
    logger.info(f"Prompt text: '{best['text']}'")
    logger.info(f"Saved conditioning audio to: {best_24k_wav}")

    return selection_report


if __name__ == "__main__":
    res = select_best_reference_segment()
    print("\n=== REFERENCE SELECTION COMPLETE ===")
    print("Selected Segment ID:", res["selected_reference"]["candidate_id"])
    print("Duration:", res["selected_reference"]["duration_s"], "seconds")
    print("Text:", res["selected_reference"]["transcript_text"])
    print("Score:", res["selected_reference"]["composite_quality_score"])
