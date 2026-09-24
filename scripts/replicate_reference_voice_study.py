"""
STORY FORGE — Reference Voice Replication Study V1
==================================================
Synthesizes, processes, objectively measures, and compiles the top 8 male voice
candidates against the YouTube Short reference acoustic & delivery profile.
"""

import asyncio
import json
import logging
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import scipy.signal as signal
import soundfile as sf
import edge_tts
from kokoro_onnx import Kokoro

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VoiceReplicationStudy")

AUDITION_SCRIPT = (
    "Did you know why the Deathly Hallows symbol was actually feared by ordinary wizards? "
    "Most fans think it was just Xenophilius Lovegood's weird obsession, but in reality, "
    "Gellert Grindelwald carved that exact mark into the stone walls of Durmstrang decades before "
    "Voldemort rose to power. When Viktor Krum saw it at the Yule Ball, he was ready to duel on "
    "the spot because dark wizards across Europe recognized it as Grindelwald's personal calling card."
)

WORD_COUNT = len(AUDITION_SCRIPT.split())

CANDIDATES_CONFIG = [
    {
        "id": "CANDIDATE_01",
        "label": "Candidate 1: Guy (Edge-TTS)",
        "spoken_label": "Candidate One.",
        "engine": "edge_tts",
        "voice_id": "en-US-GuyNeural",
        "accent": "General American",
        "style_desc": "Punchy broadcast presenter, conversational, energetic",
        "speed_param": "+14%",
        "pitch_param": "+3Hz",
        "kokoro_speed": None,
    },
    {
        "id": "CANDIDATE_02",
        "label": "Candidate 2: Puck (Kokoro-82M)",
        "spoken_label": "Candidate Two.",
        "engine": "kokoro",
        "voice_id": "am_puck",
        "accent": "General American",
        "style_desc": "Youthful curiosity tenor, punchy, high presence",
        "speed_param": None,
        "pitch_param": None,
        "kokoro_speed": 1.18,
    },
    {
        "id": "CANDIDATE_03",
        "label": "Candidate 3: Puck-Liam Blend 70/30 (Kokoro-82M)",
        "spoken_label": "Candidate Three.",
        "engine": "kokoro_blend",
        "voice_id": "blend_puck_liam",
        "blend_weights": {"am_puck": 0.70, "am_liam": 0.30},
        "accent": "General American",
        "style_desc": "Spectral match tenor, youthful insider storytelling",
        "speed_param": None,
        "pitch_param": None,
        "kokoro_speed": 1.16,
    },
    {
        "id": "CANDIDATE_04",
        "label": "Candidate 4: Brian (Edge-TTS)",
        "spoken_label": "Candidate Four.",
        "engine": "edge_tts",
        "voice_id": "en-US-BrianNeural",
        "accent": "General American",
        "style_desc": "Natural conversational storyteller, high vocal presence",
        "speed_param": "+14%",
        "pitch_param": "+2Hz",
        "kokoro_speed": None,
    },
    {
        "id": "CANDIDATE_05",
        "label": "Candidate 5: Eric (Kokoro-82M)",
        "spoken_label": "Candidate Five.",
        "engine": "kokoro",
        "voice_id": "am_eric",
        "accent": "General American",
        "style_desc": "Fast conversational articulation, energetic tempo",
        "speed_param": None,
        "pitch_param": None,
        "kokoro_speed": 1.18,
    },
    {
        "id": "CANDIDATE_06",
        "label": "Candidate 6: Steffan (Edge-TTS)",
        "spoken_label": "Candidate Six.",
        "engine": "edge_tts",
        "voice_id": "en-US-SteffanNeural",
        "accent": "General American",
        "style_desc": "Modern digital creator cadence, upbeat delivery",
        "speed_param": "+16%",
        "pitch_param": "+4Hz",
        "kokoro_speed": None,
    },
    {
        "id": "CANDIDATE_07",
        "label": "Candidate 7: Puck-Adam Blend 65/35 (Kokoro-82M)",
        "spoken_label": "Candidate Seven.",
        "engine": "kokoro_blend",
        "voice_id": "blend_puck_adam",
        "blend_weights": {"am_puck": 0.65, "am_adam": 0.35},
        "accent": "General American",
        "style_desc": "Grounded narrative tenor, matched centroid, authorial clarity",
        "speed_param": None,
        "pitch_param": None,
        "kokoro_speed": 1.18,
    },
    {
        "id": "CANDIDATE_08",
        "label": "Candidate 8: Liam (Kokoro-82M)",
        "spoken_label": "Candidate Eight.",
        "engine": "kokoro",
        "voice_id": "am_liam",
        "accent": "General American",
        "style_desc": "Youthful American conversational insider",
        "speed_param": None,
        "pitch_param": None,
        "kokoro_speed": 1.18,
    },
]


def measure_audio_file(audio_path: str) -> Dict[str, float]:
    """Extracts objective acoustic and prosodic features from an audio file."""
    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        mono = data.mean(axis=1)
    else:
        mono = data

    dur = len(mono) / sr
    rms = float(np.sqrt(np.mean(mono**2)))
    rms_db = round(20 * math.log10(rms + 1e-9), 2)

    # F0 pitch estimation via autocorrelation
    ds_sr = 16000
    mono_ds = signal.resample(mono, int(len(mono) * ds_sr / sr))
    f_len = int(ds_sr * 0.035)
    h_len = int(ds_sr * 0.010)
    pitches = []
    for i in range(0, len(mono_ds) - f_len, h_len):
        frame = mono_ds[i:i+f_len] * signal.windows.hann(f_len)
        corr = np.correlate(frame, frame, mode="full")[f_len-1:]
        min_lag = int(ds_sr / 380)
        max_lag = int(ds_sr / 70)
        if max_lag < len(corr) and corr[0] > 1e-6:
            peak = min_lag + np.argmax(corr[min_lag:max_lag])
            if corr[peak] / corr[0] > 0.45:
                pitches.append(ds_sr / peak)

    pitches = np.array(pitches) if pitches else np.array([160.0])
    f0_median = round(float(np.median(pitches)), 2)
    f0_mean = round(float(np.mean(pitches)), 2)
    f0_min = round(float(np.percentile(pitches, 5)), 2)
    f0_max = round(float(np.percentile(pitches, 95)), 2)
    f0_range = round(f0_max - f0_min, 2)
    f0_std = round(float(np.std(pitches)), 2)

    # Spectral measurements
    fft_vals = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / sr)
    total_power = float(np.sum(fft_vals**2))
    spectral_centroid = round(float(np.sum(freqs * fft_vals) / (np.sum(fft_vals) + 1e-12)), 2)
    cum_energy = np.cumsum(fft_vals**2)
    rolloff_idx = np.searchsorted(cum_energy, 0.85 * total_power)
    spectral_rolloff = round(float(freqs[rolloff_idx]), 2)
    brightness = round(float(np.sum(fft_vals[freqs > 1500]**2) / (total_power + 1e-12)) * 100, 2)
    vocal_presence = round(float(np.sum(fft_vals[(freqs >= 1000) & (freqs < 4000)]**2) / (total_power + 1e-12)) * 100, 2)

    # Dynamic range & LUFS
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", audio_path,
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    lufs = -14.0
    true_peak = -1.0
    for line in res.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p == "I:":
                    try:
                        lufs = float(parts[i+1])
                    except Exception:
                        pass
        elif "Peak:" in line and "dBFS" in line:
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p == "Peak:":
                    try:
                        true_peak = float(parts[i+1])
                    except Exception:
                        pass

    wps = round(WORD_COUNT / max(0.1, dur), 2)

    return {
        "duration_s": round(dur, 2),
        "f0_median_hz": f0_median,
        "f0_mean_hz": f0_mean,
        "f0_min_hz": f0_min,
        "f0_max_hz": f0_max,
        "f0_range_hz": f0_range,
        "f0_std_hz": f0_std,
        "spectral_centroid_hz": spectral_centroid,
        "spectral_rolloff_hz": spectral_rolloff,
        "spectral_brightness_pct": brightness,
        "vocal_presence_pct": vocal_presence,
        "rms_dbfs": rms_db,
        "integrated_lufs": round(lufs, 2),
        "true_peak_db": round(true_peak, 2),
        "words_per_second": wps,
    }


def compute_acoustic_distance(cand_metrics: Dict[str, float], ref_metrics: Dict[str, float]) -> float:
    """Computes normalized multi-dimensional Euclidean acoustic distance to reference."""
    # Target features
    f0_ref = ref_metrics["f0_median_hz"]
    cent_ref = ref_metrics["spectral_centroid_hz"]
    wps_ref = ref_metrics["words_per_second_overall"]
    bright_ref = ref_metrics["spectral_brightness_pct"]
    pres_ref = ref_metrics.get("vocal_presence_pct", 10.0)

    d_f0 = abs(cand_metrics["f0_median_hz"] - f0_ref) / f0_ref
    d_cent = abs(cand_metrics["spectral_centroid_hz"] - cent_ref) / cent_ref
    d_wps = abs(cand_metrics["words_per_second"] - wps_ref) / wps_ref
    d_bright = abs(cand_metrics["spectral_brightness_pct"] - bright_ref) / max(0.1, bright_ref)
    d_pres = abs(cand_metrics["vocal_presence_pct"] - pres_ref) / max(0.1, pres_ref)

    # Weighted Euclidean distance
    weights = [0.35, 0.25, 0.20, 0.10, 0.10]
    deltas = [d_f0, d_cent, d_wps, d_bright, d_pres]
    dist = math.sqrt(sum(w * (d**2) for w, d in zip(weights, deltas)))
    return round(dist, 4)


def apply_reference_post_processing(raw_wav: str, processed_wav: str, processed_mp3: str):
    """
    Applies reference post-processing:
    - 80 Hz high-pass (low-cut)
    - Presence EQ (+1.5 dB @ 2500 Hz, Q=1.0)
    - Broadcast dynamic compression (thresh=-18dB, ratio=2.5, attack=25ms, release=100ms)
    - Integrated loudness normalization to -14.0 LUFS with true-peak <= -1.0 dBTP
    """
    cmd_wav = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", raw_wav,
        "-af",
        "highpass=f=80,"
        "equalizer=f=2500:t=q:w=1.0:g=1.5,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=25:release=100,"
        "loudnorm=I=-14:TP=-1.0:LRA=7",
        "-ar", "44100", "-ac", "1",
        processed_wav
    ]
    subprocess.run(cmd_wav, check=True)

    cmd_mp3 = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", processed_wav,
        "-c:a", "libmp3lame", "-b:a", "192k",
        processed_mp3
    ]
    subprocess.run(cmd_mp3, check=True)


async def run_replication_study():
    work_dir = Path("data/reference_analysis")
    work_dir.mkdir(parents=True, exist_ok=True)

    # Load reference analysis
    ref_analysis_path = work_dir / "voice_reference_analysis.json"
    with open(ref_analysis_path, "r", encoding="utf-8") as f:
        ref_data = json.load(f)

    ref_acoustics = ref_data["acoustic_measurements"]
    ref_delivery = ref_data["delivery_measurements"]
    combined_ref_metrics = {**ref_acoustics, **ref_delivery}

    # Initialize Kokoro
    logger.info("Initializing Kokoro ONNX engine...")
    kokoro = Kokoro("data/kokoro-v1.0.onnx", "data/voices-v1.0.bin")

    audition_candidates_data = []

    for idx, cand in enumerate(CANDIDATES_CONFIG):
        cand_num = idx + 1
        cand_id = cand["id"]
        logger.info(f"--- Processing {cand['label']} ---")

        raw_speech_path = str(work_dir / f"raw_speech_{cand_id.lower()}.wav")
        raw_label_path = str(work_dir / f"raw_label_{cand_id.lower()}.wav")
        stitched_raw_path = str(work_dir / f"raw_full_{cand_id.lower()}.wav")

        processed_wav = str(work_dir / f"{cand_id.lower()}_{cand['voice_id']}.wav")
        processed_mp3 = str(work_dir / f"{cand_id.lower()}_{cand['voice_id']}.mp3")

        # 1. Synthesize Audition Script & Spoken Label
        if cand["engine"] == "edge_tts":
            # Spoken label
            tts_label = edge_tts.Communicate(cand["spoken_label"], cand["voice_id"], rate="+5%", pitch="+0Hz")
            await tts_label.save(raw_label_path)
            # Script
            tts_speech = edge_tts.Communicate(
                AUDITION_SCRIPT,
                cand["voice_id"],
                rate=cand["speed_param"],
                pitch=cand["pitch_param"]
            )
            await tts_speech.save(raw_speech_path)

        elif cand["engine"] == "kokoro":
            # Spoken label
            samples_lbl, sr_lbl = kokoro.create(cand["spoken_label"], voice=cand["voice_id"], speed=1.05, lang="en-us")
            sf.write(raw_label_path, samples_lbl, sr_lbl)
            # Script
            samples_sp, sr_sp = kokoro.create(AUDITION_SCRIPT, voice=cand["voice_id"], speed=cand["kokoro_speed"], lang="en-us")
            sf.write(raw_speech_path, samples_sp, sr_sp)

        elif cand["engine"] == "kokoro_blend":
            # Blend styles
            styles = [kokoro.get_voice_style(v) * w for v, w in cand["blend_weights"].items()]
            blended_style = sum(styles)
            # Spoken label
            samples_lbl, sr_lbl = kokoro.create(cand["spoken_label"], voice=blended_style, speed=1.05, lang="en-us")
            sf.write(raw_label_path, samples_lbl, sr_lbl)
            # Script
            samples_sp, sr_sp = kokoro.create(AUDITION_SCRIPT, voice=blended_style, speed=cand["kokoro_speed"], lang="en-us")
            sf.write(raw_speech_path, samples_sp, sr_sp)

        # 2. Stitch Label + 0.6s silence + Script
        # Generate 0.6s silence
        silence_file = str(work_dir / "silence_0.6s.wav")
        if not os.path.exists(silence_file):
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.6", silence_file],
                check=True
            )

        concat_list = str(work_dir / f"concat_{cand_id.lower()}.txt")
        with open(concat_list, "w", encoding="utf-8") as f_cl:
            f_cl.write(f"file '{Path(raw_label_path).resolve().as_posix()}'\n")
            f_cl.write(f"file '{Path(silence_file).resolve().as_posix()}'\n")
            f_cl.write(f"file '{Path(raw_speech_path).resolve().as_posix()}'\n")

        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", stitched_raw_path],
            check=True
        )

        # 3. Apply reference post-processing
        apply_reference_post_processing(stitched_raw_path, processed_wav, processed_mp3)

        # 4. Measure metrics from processed audio
        metrics = measure_audio_file(processed_wav)
        dist = compute_acoustic_distance(metrics, combined_ref_metrics)

        cand_record = {
            "candidate_id": cand_id,
            "candidate_number": cand_num,
            "label": cand["label"],
            "spoken_label": cand["spoken_label"],
            "engine": cand["engine"],
            "voice_id": cand["voice_id"],
            "accent": cand["accent"],
            "style_description": cand["style_desc"],
            "delivery_settings": {
                "speed_param": cand["speed_param"],
                "pitch_param": cand["pitch_param"],
                "kokoro_speed": cand["kokoro_speed"],
                "blend_weights": cand.get("blend_weights"),
            },
            "post_processing": {
                "highpass_hz": 80,
                "presence_boost_db": 1.5,
                "compression_threshold_db": -18,
                "compression_ratio": 2.5,
                "target_lufs": -14.0,
                "max_true_peak_db": -1.0,
            },
            "measurements": metrics,
            "reference_baseline": {
                "f0_median_hz": ref_acoustics["f0_median_hz"],
                "spectral_centroid_hz": ref_acoustics["spectral_centroid_hz"],
                "words_per_second": ref_delivery["words_per_second_overall"],
                "spectral_brightness_pct": ref_acoustics["spectral_brightness_pct"],
                "vocal_presence_pct": ref_acoustics["vocal_presence_pct"],
            },
            "acoustic_distance_to_reference": dist,
            "wav_path": str(Path(processed_wav).as_posix()),
            "mp3_path": str(Path(processed_mp3).as_posix()),
        }
        audition_candidates_data.append(cand_record)

    # 5. Rank by acoustic distance
    ranked_candidates = sorted(audition_candidates_data, key=lambda x: x["acoustic_distance_to_reference"])
    for rank_idx, c in enumerate(ranked_candidates):
        c["rank"] = rank_idx + 1

    # 6. Build Combined Audition File
    # Create 1.2s silence gap between candidates
    gap_silence = str(work_dir / "silence_1.2s.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1.2", gap_silence],
        check=True
    )

    combined_concat = str(work_dir / "combined_concat.txt")
    with open(combined_concat, "w", encoding="utf-8") as f_cc:
        for c in audition_candidates_data:  # in Candidate 1..8 order
            f_cc.write(f"file '{Path(c['wav_path']).resolve().as_posix()}'\n")
            f_cc.write(f"file '{Path(gap_silence).resolve().as_posix()}'\n")

    combined_wav = str(work_dir / "combined_audition_candidates_01_to_08.wav")
    combined_mp3 = str(work_dir / "combined_audition_candidates_01_to_08.mp3")

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", combined_concat,
         "-af", "loudnorm=I=-14:TP=-1.0:LRA=7",
         "-ar", "44100", "-ac", "1", combined_wav],
        check=True
    )

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", combined_wav, "-c:a", "libmp3lame", "-b:a", "192k", combined_mp3],
        check=True
    )

    # 7. Write Manifests
    comparison_manifest = {
        "title": "STORY FORGE — Reference Voice Candidate Comparison",
        "reference_source": ref_data["reference_source"],
        "script": AUDITION_SCRIPT,
        "script_word_count": WORD_COUNT,
        "reference_acoustic_profile": ref_data["acoustic_measurements"],
        "reference_delivery_profile": ref_data["delivery_measurements"],
        "candidates": ranked_candidates,
    }

    comp_path = work_dir / "voice_candidate_comparison.json"
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison_manifest, f, indent=2)

    audition_manifest = {
        "session_id": "ref_voice_repl_v1",
        "created_at_iso": "2026-09-24T17:20:00Z",
        "combined_audition_wav": str(Path(combined_wav).as_posix()),
        "combined_audition_mp3": str(Path(combined_mp3).as_posix()),
        "candidates_count": len(audition_candidates_data),
        "candidates": audition_candidates_data,
        "selection_status": "VOICE SELECTION REQUIRED — NO PRODUCTION VOICE CHANGED.",
    }

    audit_path = work_dir / "voice_audition_manifest.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audition_manifest, f, indent=2)

    # 8. Copy to Artifacts folder for UI presentation
    artifact_dir = Path("C:/Users/jisha/.gemini/antigravity/brain/eaa301ad-f26a-485c-9af7-0c985361de36/voice_audition_study_v1")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(combined_mp3, artifact_dir / "combined_audition_candidates_01_to_08.mp3")
    for c in audition_candidates_data:
        shutil.copy2(c["mp3_path"], artifact_dir / Path(c["mp3_path"]).name)

    logger.info("Replication study completed successfully!")
    return comparison_manifest


if __name__ == "__main__":
    asyncio.run(run_replication_study())
