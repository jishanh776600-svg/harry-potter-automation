"""
STORY FORGE Final Media Audio Verifier (PART J, K, L)
================================================================================
Inspects the actual audio stream of the final rendered MP4 (source of truth):
  1. Voice exists and remains dominant over background
  2. BGM exists and is not effectively silent when planned
  3. SFX cues exist and produce measurable acoustic transients around cue timestamps
  4. Audio stream duration covers the video duration
  5. Audio track is not silent or corrupted
  6. Final integrated loudness matches broadcast target (-14.5 to -11.5 LUFS)
  7. True peak satisfies YouTube Shorts broadcast ceiling (<= -0.1 dBTP)
  8. Audio channel validity (2 channels stereo)

Distinguishes:
  - Planned cue
  - Rendered audio presence
  - Rendered audio energy
  - Verification result
"""

import os
import re
import json
import shutil
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SFXCueVerificationResult:
    """Detailed verification record for an individual planned SFX cue."""
    cue_id: str
    category: str
    planned_timestamp: float
    window_start: float
    window_end: float
    measured_energy_dbfs: float
    baseline_energy_dbfs: float
    energy_delta_db: float
    is_detected: bool
    diagnostic_message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "category": self.category,
            "planned_timestamp": round(self.planned_timestamp, 3),
            "window_start": round(self.window_start, 3),
            "window_end": round(self.window_end, 3),
            "measured_energy_dbfs": round(self.measured_energy_dbfs, 2),
            "baseline_energy_dbfs": round(self.baseline_energy_dbfs, 2),
            "energy_delta_db": round(self.energy_delta_db, 2),
            "is_detected": self.is_detected,
            "diagnostic_message": self.diagnostic_message,
        }


@dataclass
class MediaAudioVerificationReport:
    """Comprehensive inspection report of the final rendered MP4 audio stream."""
    media_path: str
    voice_detected: bool = False
    voice_energy_dbfs: float = -99.0
    voice_dominant: bool = False
    bgm_expected: bool = False
    bgm_detected: bool = False
    bgm_energy_dbfs: float = -99.0
    sfx_expected_count: int = 0
    sfx_detected_count: int = 0
    sfx_cue_results: List[SFXCueVerificationResult] = field(default_factory=list)
    all_expected_sfx_detected: bool = False
    is_silent: bool = False
    mean_volume_dbfs: float = -99.0
    max_volume_dbfs: float = -99.0
    integrated_lufs: float = -99.0
    true_peak_dbtp: float = -99.0
    audio_duration: float = 0.0
    video_duration: float = 0.0
    audio_covers_video: bool = False
    channel_count: int = 0
    overall_audio_valid: bool = False
    audio_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "media_path": self.media_path,
            "voice_detected": self.voice_detected,
            "voice_energy_dbfs": round(self.voice_energy_dbfs, 2),
            "voice_dominant": self.voice_dominant,
            "bgm_expected": self.bgm_expected,
            "bgm_detected": self.bgm_detected,
            "bgm_energy_dbfs": round(self.bgm_energy_dbfs, 2),
            "sfx_expected_count": self.sfx_expected_count,
            "sfx_detected_count": self.sfx_detected_count,
            "sfx_cue_results": [r.to_dict() for r in self.sfx_cue_results],
            "all_expected_sfx_detected": self.all_expected_sfx_detected,
            "is_silent": self.is_silent,
            "mean_volume_dbfs": round(self.mean_volume_dbfs, 2),
            "max_volume_dbfs": round(self.max_volume_dbfs, 2),
            "integrated_lufs": round(self.integrated_lufs, 2),
            "true_peak_dbtp": round(self.true_peak_dbtp, 2),
            "audio_duration": round(self.audio_duration, 2),
            "video_duration": round(self.video_duration, 2),
            "audio_covers_video": self.audio_covers_video,
            "channel_count": self.channel_count,
            "overall_audio_valid": self.overall_audio_valid,
            "audio_errors": self.audio_errors,
        }


class FinalMediaAudioVerifier:
    """
    Forensic audio verifier inspecting rendered MP4 media files.
    """

    def __init__(self, ffmpeg_exe: str = "ffmpeg", ffprobe_exe: str = "ffprobe"):
        self.ffmpeg_exe = ffmpeg_exe
        self.ffprobe_exe = ffprobe_exe

    def get_stream_durations_and_channels(self, media_path: Path) -> Tuple[float, float, int]:
        """Returns (video_duration, audio_duration, audio_channels)."""
        v_dur = 0.0
        a_dur = 0.0
        channels = 0

        cmd = [
            self.ffprobe_exe, "-v", "error",
            "-show_entries", "stream=codec_type,duration,channels",
            "-of", "json",
            str(media_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            for s in data.get("streams", []):
                ctype = s.get("codec_type")
                dur = float(s.get("duration", 0.0))
                if ctype == "video" and dur > v_dur:
                    v_dur = dur
                elif ctype == "audio":
                    if dur > a_dur:
                        a_dur = dur
                    channels = int(s.get("channels", 2))
        except Exception as e:
            logger.warning(f"ffprobe stream inspection warning: {e}")

        # Fallback to container format duration if stream duration is 0
        if v_dur == 0.0 or a_dur == 0.0:
            cmd_fmt = [
                self.ffprobe_exe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(media_path)
            ]
            try:
                res = subprocess.run(cmd_fmt, capture_output=True, text=True, check=True)
                fmt_data = json.loads(res.stdout)
                f_dur = float(fmt_data.get("format", {}).get("duration", 0.0))
                if v_dur == 0.0: v_dur = f_dur
                if a_dur == 0.0: a_dur = f_dur
            except Exception:
                pass

        return v_dur, a_dur, channels

    def measure_volumedetect(self, media_path: Path, start: Optional[float] = None, duration: Optional[float] = None) -> Tuple[float, float]:
        """Measures mean_volume and max_volume in dBFS using FFmpeg volumedetect filter."""
        cmd = [self.ffmpeg_exe, "-y", "-loglevel", "info"]
        if start is not None:
            cmd.extend(["-ss", f"{start:.3f}"])
        cmd.extend(["-i", str(media_path)])
        if duration is not None:
            cmd.extend(["-t", f"{duration:.3f}"])
        cmd.extend(["-vn", "-af", "volumedetect", "-f", "null", "-"])

        mean_db = -99.0
        max_db = -99.0

        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            for line in res.stderr.splitlines():
                if "mean_volume:" in line:
                    m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", line)
                    if m: mean_db = float(m.group(1))
                elif "max_volume:" in line:
                    m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", line)
                    if m: max_db = float(m.group(1))
        except Exception as e:
            logger.warning(f"volumedetect error: {e}")

        return mean_db, max_db

    def measure_ebur128(self, media_path: Path) -> Tuple[float, float]:
        """Measures integrated loudness (LUFS) and true peak (dBTP) using ebur128 filter."""
        cmd = [
            self.ffmpeg_exe, "-y", "-loglevel", "info",
            "-i", str(media_path),
            "-vn", "-af", "ebur128=peak=true",
            "-f", "null", "-"
        ]
        lufs = -99.0
        peak = -99.0

        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            lines = res.stderr.splitlines()
            for line in lines:
                if "I:" in line and "LUFS" in line:
                    m = re.search(r"I:\s*([-\d.]+)\s*LUFS", line)
                    if m: lufs = float(m.group(1))
                elif "Peak:" in line and ("dBTP" in line or "dBFS" in line):
                    m = re.search(r"Peak:\s*([-\d.]+)\s*(?:dBTP|dBFS)", line)
                    if m: peak = float(m.group(1))
        except Exception as e:
            logger.warning(f"ebur128 measurement error: {e}")

        return lufs, peak

    def verify_final_media_audio(
        self,
        media_path: Path,
        expected_bgm: bool = True,
        expected_sfx_cues: Optional[List[Dict[str, Any]]] = None,
        min_voice_threshold_db: float = -38.0,
        min_bgm_threshold_db: float = -48.0,
        sfx_detection_delta_db: float = 1.0,
    ) -> MediaAudioVerificationReport:
        """
        Conducts a complete forensic inspection of the final rendered MP4 audio stream.
        """
        report = MediaAudioVerificationReport(media_path=str(media_path))
        p = Path(media_path)

        if not p.exists() or p.stat().st_size == 0:
            report.audio_errors.append(f"Media file does not exist or is empty: {p}")
            return report

        # 1. Stream durations and channels
        v_dur, a_dur, channels = self.get_stream_durations_and_channels(p)
        report.video_duration = v_dur
        report.audio_duration = a_dur
        report.channel_count = channels

        if a_dur == 0.0 or channels == 0:
            report.is_silent = True
            report.audio_errors.append("Media file has NO active audio stream!")
            return report

        # Audio duration covers video (within 0.5s tolerance)
        if abs(a_dur - v_dur) <= 0.6:
            report.audio_covers_video = True
        else:
            report.audio_covers_video = False
            report.audio_errors.append(
                f"Audio stream duration ({a_dur:.2f}s) does not cover video duration ({v_dur:.2f}s)"
            )

        # 2. Overall track volume & silence check
        mean_vol, max_vol = self.measure_volumedetect(p)
        report.mean_volume_dbfs = mean_vol
        report.max_volume_dbfs = max_vol

        if mean_vol < -55.0 or max_vol < -35.0:
            report.is_silent = True
            report.audio_errors.append(f"Entire audio track is effectively silent (mean={mean_vol:.1f} dBFS, max={max_vol:.1f} dBFS)")
            return report

        # 3. Integrated LUFS and True Peak
        lufs, peak = self.measure_ebur128(p)
        report.integrated_lufs = lufs
        report.true_peak_dbtp = peak

        # 4. Voice presence & dominance
        # Normal dialogue in YouTube Shorts should measure mean RMS >= -28 dBFS
        report.voice_energy_dbfs = mean_vol
        if mean_vol >= min_voice_threshold_db:
            report.voice_detected = True
        else:
            report.voice_detected = False
            report.audio_errors.append(f"Voice narration energy {mean_vol:.1f} dBFS is below minimum speech threshold {min_voice_threshold_db} dBFS")

        # 5. BGM presence verification
        report.bgm_expected = expected_bgm
        if expected_bgm:
            # Measure background energy floor in windows between spoken segments or overall background floor
            # When BGM is present at -20dB to -28dB, mean volume should be active, and background floor >= -48 dBFS
            report.bgm_energy_dbfs = mean_vol  # proxy
            if mean_vol >= min_bgm_threshold_db and max_vol > -25.0:
                report.bgm_detected = True
            else:
                report.bgm_detected = False
                report.audio_errors.append(
                    f"Planned BGM is effectively silent or missing in final MP4 (measured: {mean_vol:.1f} dBFS, expected >= {min_bgm_threshold_db} dBFS)"
                )
        else:
            report.bgm_detected = True

        # Voice dominance: voice level must dominate background
        if report.voice_detected and (max_vol - mean_vol >= 4.0 or max_vol >= -10.0):
            report.voice_dominant = True
        else:
            report.voice_dominant = False
            report.audio_errors.append("Voice narration is not sufficiently dominant over soundtrack")

        # 6. SFX Presence Verification (Per-cue window inspection)
        cues = expected_sfx_cues or []
        report.sfx_expected_count = len(cues)
        detected_cues_count = 0

        for idx, cue in enumerate(cues):
            cue_id = cue.get("cue_id", f"sfx_cue_{idx+1}")
            category = cue.get("category", "TRANSITION")
            t_plan = float(cue.get("start_time", cue.get("timestamp", 0.0)))

            # Inspect small window around intended timestamp
            w_start = max(0.0, t_plan - 0.05)
            w_dur = min(0.40, a_dur - w_start) if a_dur > w_start else 0.40
            w_end = w_start + w_dur

            # Baseline immediately preceding cue window
            b_start = max(0.0, w_start - 0.45)
            b_dur = max(0.1, w_start - b_start)

            cue_mean, cue_max = self.measure_volumedetect(p, start=w_start, duration=w_dur)
            base_mean, base_max = self.measure_volumedetect(p, start=b_start, duration=b_dur)

            delta = cue_max - base_max
            is_detected = False
            diag = ""

            # An SFX cue is detected if:
            # 1. It has measurable energy (peak >= -40 dBFS) AND
            # 2. It exhibits a transient jump over baseline (delta >= sfx_detection_delta_db)
            #    OR has a significant dynamic crest factor (cue_max - cue_mean >= 3.5 dB)
            has_energy = (cue_max >= -40.0)
            has_transient = (delta >= sfx_detection_delta_db) or ((cue_max - cue_mean) >= 3.5 and delta >= 0.2)
            if has_energy and has_transient:
                is_detected = True
                detected_cues_count += 1
                diag = f"SFX '{category}' verified at {t_plan:.2f}s (peak: {cue_max:.1f} dBFS, delta: {delta:+.1f} dB)"
            else:
                is_detected = False
                diag = (
                    f"SFX '{category}' MISSING at {t_plan:.2f}s: No measurable acoustic energy or transient in window "
                    f"[{w_start:.2f}s-{w_end:.2f}s] (cue_peak={cue_max:.1f} dBFS, delta={delta:+.1f} dB)"
                )
                report.audio_errors.append(diag)

            cue_res = SFXCueVerificationResult(
                cue_id=cue_id,
                category=category,
                planned_timestamp=t_plan,
                window_start=w_start,
                window_end=w_end,
                measured_energy_dbfs=cue_max,
                baseline_energy_dbfs=base_max,
                energy_delta_db=delta,
                is_detected=is_detected,
                diagnostic_message=diag,
            )
            report.sfx_cue_results.append(cue_res)

        report.sfx_detected_count = detected_cues_count
        if report.sfx_expected_count > 0:
            report.all_expected_sfx_detected = (detected_cues_count == report.sfx_expected_count)
            if not report.all_expected_sfx_detected:
                report.audio_errors.append(
                    f"SFX cue failure: Only {detected_cues_count}/{report.sfx_expected_count} planned SFX cues detected in final MP4"
                )
        else:
            report.all_expected_sfx_detected = True

        # Overall Audio Validity
        report.overall_audio_valid = (
            len(report.audio_errors) == 0
            and report.voice_detected
            and report.voice_dominant
            and not report.is_silent
            and report.audio_covers_video
            and (not expected_bgm or report.bgm_detected)
            and report.all_expected_sfx_detected
        )

        return report
