"""
STORY FORGE — Precision Voice Pause Compressor & Timing Harmonizer
================================================================================
Enforces the Discovery Short voice pacing invariant:
  - Maximum intentional inter-phrase silence: 0.20 seconds.
  - Target normal phrase boundary: approximately 0.10–0.20s (default 0.15s).
  - Any silence gap >0.20s must be compressed to <=0.20s.
  - Do NOT speed up the whole voice track.
  - Do NOT time-stretch spoken words.
  - Do NOT clip phonemes, consonants, or word endings (via speech hangover padding).
  - Preserve natural speech prosody.
  - Do not remove tiny internal phoneme-level pauses (plosive closures).

Pipeline order guaranteed:
  TTS
  -> silence compression / voice preprocessing
  -> FINAL narration audio
  -> FINAL narration timestamps
  -> visual proposition timing
  -> visual selection/grounding
  -> editorial timeline
  -> render
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import soundfile as sf

logger = logging.getLogger("VoicePauseCompressor")

PAUSE_COMPRESSION_FACTOR: float = 0.70
DEFAULT_MAX_PAUSE_SEC: float = 0.14   # 30% reduction from 0.20s
DEFAULT_TARGET_PAUSE_SEC: float = 0.105 # 30% reduction from 0.15s
DEFAULT_SILENCE_RMS_THRESH: float = 0.012
DEFAULT_FRAME_MS: float = 10.0
PRE_SPEECH_PAD_MS: float = 25.0   # 25ms hangover prevents clipping attack consonants while eliminating drag
POST_SPEECH_PAD_MS: float = 30.0  # 30ms hangover prevents clipping releases while eliminating drag
CROSSFADE_MS: float = 5.0         # 5ms smooth crossfade across spliced silence points


class VoicePauseCompressor:
    """
    Precision acoustic silence compressor and timestamp harmonizer for Discovery Shorts.
    """

    @classmethod
    def compute_energy_profile(
        cls,
        samples: np.ndarray,
        sr: int,
        frame_ms: float = DEFAULT_FRAME_MS,
    ) -> Tuple[List[float], int]:
        """
        Computes frame-level RMS energy envelope for acoustic speech detection.
        """
        frame_len = max(1, int(frame_ms * 0.001 * sr))
        n_frames = len(samples) // frame_len
        rms_values = []
        for i in range(n_frames):
            chunk = samples[i * frame_len : (i + 1) * frame_len]
            val = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
            rms_values.append(val)
        return rms_values, frame_len

    @classmethod
    def measure_silence_gaps(
        cls,
        audio_path: Union[str, Path],
        min_gap_sec: float = 0.05,
        frame_ms: float = DEFAULT_FRAME_MS,
        rms_thresh: float = DEFAULT_SILENCE_RMS_THRESH,
    ) -> List[Dict[str, float]]:
        """
        Measures all acoustic silence gaps in an audio file above min_gap_sec.
        Returns list of gaps with start, end, and duration in seconds.
        """
        p = Path(audio_path)
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {p}")

        data, sr = sf.read(str(p))
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        rms_list, frame_len = cls.compute_energy_profile(data, sr, frame_ms=frame_ms)
        if not rms_list:
            return []

        frame_dur = frame_len / float(sr)
        is_speech = [r >= rms_thresh for r in rms_list]

        # Apply speech hangover padding so word boundaries are not clipped
        pre_pad = int(PRE_SPEECH_PAD_MS / frame_ms)
        post_pad = int(POST_SPEECH_PAD_MS / frame_ms)
        padded_speech = list(is_speech)
        for i, val in enumerate(is_speech):
            if val:
                for k in range(max(0, i - pre_pad), min(len(padded_speech), i + post_pad + 1)):
                    padded_speech[k] = True

        # Find continuous silence segments
        gaps: List[Dict[str, float]] = []
        in_silence = False
        silence_start = 0

        for idx, sp in enumerate(padded_speech):
            if not sp and not in_silence:
                in_silence = True
                silence_start = idx
            elif sp and in_silence:
                in_silence = False
                sil_dur = (idx - silence_start) * frame_dur
                if sil_dur >= min_gap_sec:
                    gaps.append({
                        "start": round(silence_start * frame_dur, 3),
                        "end": round(idx * frame_dur, 3),
                        "duration": round(sil_dur, 3),
                    })

        # Final trailing silence
        if in_silence:
            sil_dur = (len(padded_speech) - silence_start) * frame_dur
            if sil_dur >= min_gap_sec:
                gaps.append({
                    "start": round(silence_start * frame_dur, 3),
                    "end": round(len(padded_speech) * frame_dur, 3),
                    "duration": round(sil_dur, 3),
                })

        return gaps

    @classmethod
    def get_max_silence_pause(
        cls,
        audio_path: Union[str, Path],
        frame_ms: float = DEFAULT_FRAME_MS,
        rms_thresh: float = DEFAULT_SILENCE_RMS_THRESH,
        exclude_leading_trailing: bool = True,
    ) -> float:
        """
        Returns the maximum measured silence gap (in seconds) in the audio.
        """
        gaps = cls.measure_silence_gaps(audio_path, min_gap_sec=0.04, frame_ms=frame_ms, rms_thresh=rms_thresh)
        if not gaps:
            return 0.0
        if exclude_leading_trailing and len(gaps) > 2:
            interior = gaps[1:-1]
            return max([g["duration"] for g in interior], default=0.0)
        return max([g["duration"] for g in gaps], default=0.0)

    @classmethod
    def compress_pause_gaps(
        cls,
        input_wav: Union[str, Path],
        output_wav: Union[str, Path],
        max_pause_sec: float = DEFAULT_MAX_PAUSE_SEC,
        target_pause_sec: float = DEFAULT_TARGET_PAUSE_SEC,
        rms_thresh: float = DEFAULT_SILENCE_RMS_THRESH,
        leading_silence_max_sec: float = 0.07,
        trailing_silence_max_sec: float = 0.12,
    ) -> Dict[str, Any]:
        """
        Compresses any silence gap > max_pause_sec down to target_pause_sec (<= max_pause_sec).
        Gaps already <= max_pause_sec are strictly preserved (100% untouched).
        Spoken words are NEVER time-stretched or sped up.
        Hangover margins guarantee no phonemes, consonants, or word endings are clipped.
        """
        in_p = Path(input_wav)
        out_p = Path(output_wav)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        data, sr = sf.read(str(in_p))
        is_stereo = (data.ndim > 1)
        mono_data = np.mean(data, axis=1) if is_stereo else data

        orig_dur = round(len(data) / float(sr), 3)
        rms_list, frame_len = cls.compute_energy_profile(mono_data, sr, frame_ms=DEFAULT_FRAME_MS)
        frame_dur = frame_len / float(sr)

        # Baseline VAD
        is_speech = [r >= rms_thresh for r in rms_list]

        # Consonant and release hangover: pad speech regions
        pre_pad = int(PRE_SPEECH_PAD_MS / DEFAULT_FRAME_MS)
        post_pad = int(POST_SPEECH_PAD_MS / DEFAULT_FRAME_MS)
        padded_speech = list(is_speech)
        for i, val in enumerate(is_speech):
            if val:
                for k in range(max(0, i - pre_pad), min(len(padded_speech), i + post_pad + 1)):
                    padded_speech[k] = True

        # Find continuous silence runs
        runs: List[Dict[str, Any]] = []
        in_silence = False
        run_start = 0

        for idx, sp in enumerate(padded_speech):
            if not sp and not in_silence:
                in_silence = True
                run_start = idx
            elif sp and in_silence:
                in_silence = False
                runs.append({
                    "is_speech": False,
                    "start_frame": run_start,
                    "end_frame": idx,
                    "start_sec": run_start * frame_dur,
                    "end_sec": idx * frame_dur,
                    "duration_sec": (idx - run_start) * frame_dur,
                })
            if sp and not in_silence:
                if not runs or runs[-1]["is_speech"] is False:
                    runs.append({
                        "is_speech": True,
                        "start_frame": idx,
                        "end_frame": idx + 1,
                        "start_sec": idx * frame_dur,
                        "end_sec": (idx + 1) * frame_dur,
                        "duration_sec": frame_dur,
                    })
                else:
                    runs[-1]["end_frame"] = idx + 1
                    runs[-1]["end_sec"] = (idx + 1) * frame_dur
                    runs[-1]["duration_sec"] += frame_dur

        if in_silence:
            runs.append({
                "is_speech": False,
                "start_frame": run_start,
                "end_frame": len(padded_speech),
                "start_sec": run_start * frame_dur,
                "end_sec": len(padded_speech) * frame_dur,
                "duration_sec": (len(padded_speech) - run_start) * frame_dur,
            })

        # Process segments into output chunks with precision silence compression
        output_chunks: List[np.ndarray] = []
        time_map: List[Tuple[float, float, float]] = []  # (orig_t, new_t, delta)
        compressed_gaps_count = 0
        preserved_gaps_count = 0
        max_pause_before = 0.0

        n_runs = len(runs)
        for i, run in enumerate(runs):
            start_samp = int(run["start_frame"] * frame_len)
            end_samp = min(len(data), int(run["end_frame"] * frame_len))

            if run["is_speech"]:
                # Spoken audio: NEVER time-stretch, copy 100% exact samples
                output_chunks.append(data[start_samp:end_samp])
            else:
                sil_dur = run["duration_sec"]
                max_pause_before = max(max_pause_before, sil_dur)
                is_leading = (i == 0)
                is_trailing = (i == n_runs - 1)

                allowed_max = (
                    leading_silence_max_sec if is_leading
                    else (trailing_silence_max_sec if is_trailing else max_pause_sec)
                )
                target_sec = (
                    min(0.08, leading_silence_max_sec) if is_leading
                    else (min(0.15, trailing_silence_max_sec) if is_trailing else target_pause_sec)
                )

                if sil_dur <= allowed_max:
                    # Gaps already <= max_pause_sec are strictly preserved (100% untouched)
                    preserved_gaps_count += 1
                    output_chunks.append(data[start_samp:end_samp])
                else:
                    # Silence gap > max_pause_sec: compress to target_sec (<= 0.20s)
                    compressed_gaps_count += 1
                    keep_samples = max(2, int(target_sec * sr))
                    total_samples = end_samp - start_samp

                    if total_samples > keep_samples:
                        # Keep initial decay and lead-in, trim excess from middle
                        keep_front = keep_samples // 2
                        keep_back = keep_samples - keep_front

                        front_part = data[start_samp : start_samp + keep_front]
                        back_part = data[end_samp - keep_back : end_samp]

                        # Apply smooth 5ms cosine crossfade across splice point
                        cf_len = min(len(front_part), len(back_part), int(CROSSFADE_MS * 0.001 * sr))
                        if cf_len > 4:
                            fade_out = 0.5 * (1.0 + np.cos(np.linspace(0, np.pi, cf_len)))
                            fade_in = 1.0 - fade_out
                            if is_stereo:
                                fade_out = fade_out[:, np.newaxis]
                                fade_in = fade_in[:, np.newaxis]

                            spliced_front = np.copy(front_part)
                            spliced_back = np.copy(back_part)
                            spliced_front[-cf_len:] *= fade_out
                            spliced_back[:cf_len] *= fade_in
                            combined = np.concatenate([spliced_front, spliced_back], axis=0)
                        else:
                            combined = np.concatenate([front_part, back_part], axis=0)

                        output_chunks.append(combined)
                    else:
                        output_chunks.append(data[start_samp:end_samp])

        if not output_chunks:
            # Fallback copy
            sf.write(str(out_p), data, sr)
            return {
                "success": True,
                "original_duration": orig_dur,
                "compressed_duration": orig_dur,
                "gaps_compressed_count": 0,
                "max_pause_before": max_pause_before,
                "max_pause_after": max_pause_before,
            }

        final_data = np.concatenate(output_chunks, axis=0)
        sf.write(str(out_p), final_data, sr)

        final_dur = round(len(final_data) / float(sr), 3)
        max_pause_after = cls.get_max_silence_pause(out_p, frame_ms=DEFAULT_FRAME_MS, rms_thresh=rms_thresh)

        logger.info(
            f"[VoicePauseCompressor] Pacing compressed: {orig_dur:.2f}s -> {final_dur:.2f}s "
            f"({compressed_gaps_count} gaps compressed, {preserved_gaps_count} preserved <= {max_pause_sec}s, "
            f"max pause: {max_pause_before:.3f}s -> {max_pause_after:.3f}s)"
        )

        return {
            "success": True,
            "original_duration": orig_dur,
            "compressed_duration": final_dur,
            "duration_reduction_sec": round(orig_dur - final_dur, 3),
            "gaps_compressed_count": compressed_gaps_count,
            "gaps_preserved_count": preserved_gaps_count,
            "max_pause_before": round(max_pause_before, 3),
            "max_pause_after": round(max_pause_after, 3),
            "output_path": str(out_p),
        }
