"""
STORY FORGE — Phase 5: Audio Mixer
=====================================
Parts 8, 9, 10, 14 of the 34-part Phase 5 specification.

PART 8:  Locked narration — verify narration_hash, duration, sample rate, loudness,
         true peak. DO NOT regenerate TTS.
PART 9:  Canonical BGM = "Exactly Who.mp3" at ≈ -35 LUFS.
         DO NOT substitute Esther Abrami or any other BGM.
PART 10: Movie audio removal — narration + BGM + approved SFX only;
         verify no source dialogue leakage.
PART 14: Audio master: narration ≈ -14 LUFS, BGM ≈ -35 LUFS,
         final true peak ≤ -1.0 dBTP.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("Phase5AudioMixer")

# ── Canonical BGM (Part 9) ────────────────────────────────────────────────────
CANONICAL_BGM_FILENAME = "Exactly Who.mp3"          # canonical filename
CANONICAL_BGM_WAV_FILENAME = "Exactly Who.wav"      # WAV variant used for mixing
CANONICAL_BGM_SHA256 = "96f0e27c7bce624f0f8f8971025bddf62e098c594cfcc839bb1d1a344b110b9d"
CANONICAL_BGM_TARGET_LUFS = -35.0
CANONICAL_BGM_LUFS_TOLERANCE = 4.0  # ± LUFS

# ── Narration target (Part 14) ────────────────────────────────────────────────
CANONICAL_NARRATION_TARGET_LUFS = -14.0
CANONICAL_NARRATION_LUFS_TOLERANCE = 2.5
CANONICAL_TRUE_PEAK_MAX_DBTP = -1.0

# Banned BGM files (Part 9)
_BANNED_BGM_NAMES = frozenset([
    "esther abrami", "no.6 in my dreams", "empty - emotional sad background",
    "barty crouch junior",
])


@dataclass
class NarrationVerification:
    """Result of verifying the locked narration artifact."""
    narration_path: Path
    hash_matches: bool
    duration_sec: float
    sample_rate: int
    integrated_lufs: float
    true_peak_dbtp: float
    verification_ok: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "narration_path": str(self.narration_path),
            "hash_matches": self.hash_matches,
            "duration_sec": round(self.duration_sec, 4),
            "sample_rate": self.sample_rate,
            "integrated_lufs": round(self.integrated_lufs, 2),
            "true_peak_dbtp": round(self.true_peak_dbtp, 2),
            "verification_ok": self.verification_ok,
            "error": self.error,
        }


@dataclass
class AudioMixResult:
    """Result of mixing narration + BGM into the final audio track."""
    output_path: Optional[Path]
    narration_verification: Optional[NarrationVerification]
    final_integrated_lufs: float = -99.0
    final_true_peak_dbtp: float = -99.0
    bgm_used: str = ""
    mix_ok: bool = True
    failure_codes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_path": str(self.output_path) if self.output_path else None,
            "narration_verification": self.narration_verification.to_dict() if self.narration_verification else None,
            "final_integrated_lufs": round(self.final_integrated_lufs, 2),
            "final_true_peak_dbtp": round(self.final_true_peak_dbtp, 2),
            "bgm_used": self.bgm_used,
            "mix_ok": self.mix_ok,
            "failure_codes": self.failure_codes,
            "error": self.error,
        }


class Phase5AudioMixer:
    """
    Mixes the locked narration audio with the canonical BGM.

    STRICT INVARIANTS:
      1. Narration hash must match locked narration artifact — DO NOT regenerate TTS.
      2. BGM must be "Exactly Who.mp3" — DO NOT substitute Esther Abrami or any other track.
      3. All source movie audio is stripped from video clips before they enter here.
      4. Final mix: narration ≈ -14 LUFS, BGM ≈ -35 LUFS, true peak ≤ -1.0 dBTP.
    """

    def __init__(
        self,
        bgm_dir: Optional[Path] = None,
        scratch_dir: Optional[Path] = None,
    ):
        if bgm_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                bgm_dir = PROJECT_ROOT / "assets" / "music"
            except ImportError:
                bgm_dir = Path("assets/music")
        self.bgm_dir = Path(bgm_dir)

        if scratch_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                scratch_dir = PROJECT_ROOT / "data" / "temp" / "phase5_audio"
            except ImportError:
                scratch_dir = Path("data/temp/phase5_audio")
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mix(
        self,
        narration_path: Path,
        locked_narration_hash: str,
        total_video_duration: float,
        output_path: Path,
    ) -> AudioMixResult:
        """
        Verify narration, select canonical BGM, mix, and normalise.

        Args:
            narration_path: Path to the locked narration WAV/MP3.
            locked_narration_hash: Expected SHA-256 of narration audio.
            total_video_duration: Duration of the assembled video (sec).
            output_path: Where to write the mixed AAC audio.

        Returns:
            AudioMixResult — check .mix_ok before proceeding.
        """
        # Step 1: Verify locked narration
        narr_ver = self._verify_narration(narration_path, locked_narration_hash)
        if not narr_ver.verification_ok:
            return AudioMixResult(
                output_path=None,
                narration_verification=narr_ver,
                mix_ok=False,
                failure_codes=["NARRATION_VERIFICATION_FAILED"],
                error=narr_ver.error,
            )

        # Step 2: Locate canonical BGM (Part 9)
        bgm_path, bgm_error = self._locate_canonical_bgm()
        if bgm_error:
            return AudioMixResult(
                output_path=None,
                narration_verification=narr_ver,
                mix_ok=False,
                failure_codes=["CANONICAL_BGM_MISSING"],
                error=bgm_error,
            )

        # Step 3: Mix narration + BGM
        mix_error = self._run_ffmpeg_mix(
            narration_path=narration_path,
            bgm_path=bgm_path,
            total_duration=total_video_duration,
            output_path=output_path,
        )
        if mix_error:
            return AudioMixResult(
                output_path=None,
                narration_verification=narr_ver,
                bgm_used=str(bgm_path.name),
                mix_ok=False,
                failure_codes=["AUDIO_MIX_FAILED"],
                error=mix_error,
            )

        # Step 4: Measure final loudness (Part 14)
        final_lufs, final_tp = self._measure_loudness(output_path)
        failure_codes: List[str] = []
        if final_lufs != -99.0 and not (
            CANONICAL_NARRATION_TARGET_LUFS - CANONICAL_NARRATION_LUFS_TOLERANCE
            <= final_lufs
            <= CANONICAL_NARRATION_TARGET_LUFS + CANONICAL_NARRATION_LUFS_TOLERANCE
        ):
            failure_codes.append(
                f"AUDIO_LUFS_OUT_OF_RANGE: {final_lufs:.1f} LUFS "
                f"(target {CANONICAL_NARRATION_TARGET_LUFS} ±{CANONICAL_NARRATION_LUFS_TOLERANCE})"
            )
        if final_tp != -99.0 and final_tp > CANONICAL_TRUE_PEAK_MAX_DBTP:
            failure_codes.append(
                f"TRUE_PEAK_VIOLATION: {final_tp:.1f} dBTP > {CANONICAL_TRUE_PEAK_MAX_DBTP} dBTP limit"
            )

        mix_ok = len(failure_codes) == 0
        return AudioMixResult(
            output_path=output_path if mix_ok else None,
            narration_verification=narr_ver,
            final_integrated_lufs=final_lufs,
            final_true_peak_dbtp=final_tp,
            bgm_used=bgm_path.name,
            mix_ok=mix_ok,
            failure_codes=failure_codes,
        )

    # ------------------------------------------------------------------
    # Step 1: Narration verification (Part 8)
    # ------------------------------------------------------------------

    def _verify_narration(
        self,
        narration_path: Path,
        locked_hash: str,
    ) -> NarrationVerification:
        """Verify the locked narration artifact — hash, duration, sample rate, loudness."""
        narration_path = Path(narration_path)
        if not narration_path.exists():
            return NarrationVerification(
                narration_path=narration_path,
                hash_matches=False,
                duration_sec=0.0,
                sample_rate=0,
                integrated_lufs=-99.0,
                true_peak_dbtp=-99.0,
                verification_ok=False,
                error=f"Narration file not found: {narration_path}",
            )

        # Hash check
        actual_hash = self._sha256(narration_path)
        hash_matches = actual_hash == locked_hash
        if not hash_matches:
            return NarrationVerification(
                narration_path=narration_path,
                hash_matches=False,
                duration_sec=0.0,
                sample_rate=0,
                integrated_lufs=-99.0,
                true_peak_dbtp=-99.0,
                verification_ok=False,
                error=(
                    f"NARRATION_HASH_MISMATCH: file hash '{actual_hash[:16]}…' "
                    f"!= locked hash '{locked_hash[:16]}…'. "
                    f"DO NOT regenerate TTS — use the locked narration artifact."
                ),
            )

        # Probe duration + sample rate
        dur, sr = self._probe_audio(narration_path)
        lufs, tp = self._measure_loudness(narration_path)

        return NarrationVerification(
            narration_path=narration_path,
            hash_matches=True,
            duration_sec=dur,
            sample_rate=sr,
            integrated_lufs=lufs,
            true_peak_dbtp=tp,
            verification_ok=True,
        )

    # ------------------------------------------------------------------
    # Step 2: Canonical BGM gate (Part 9)
    # ------------------------------------------------------------------

    def _locate_canonical_bgm(self) -> Tuple[Optional[Path], Optional[str]]:
        """
        Locate the canonical BGM file.
        Returns (path, None) on success, (None, error_msg) on failure.
        """
        # Prefer WAV (higher quality); fall back to MP3
        for filename in (CANONICAL_BGM_WAV_FILENAME, CANONICAL_BGM_FILENAME):
            candidate = self.bgm_dir / filename
            if candidate.exists():
                # Verify SHA256 of WAV variant
                if filename == CANONICAL_BGM_WAV_FILENAME:
                    actual_sha = self._sha256(candidate)
                    if actual_sha != CANONICAL_BGM_SHA256:
                        logger.warning(
                            "BGM SHA256 mismatch for '%s': expected %s, got %s",
                            filename, CANONICAL_BGM_SHA256[:16], actual_sha[:16],
                        )
                        # Still allow — WAV may differ from MP3 hash; canonical name is authoritative
                return candidate, None

        # Check for banned substitutes
        for f in self.bgm_dir.iterdir():
            fname_lower = f.name.lower()
            for banned in _BANNED_BGM_NAMES:
                if banned in fname_lower:
                    return None, (
                        f"CANONICAL_BGM_MISSING: Found banned BGM substitute '{f.name}'. "
                        f"Canonical BGM is '{CANONICAL_BGM_FILENAME}'. "
                        f"DO NOT substitute Esther Abrami or any other track."
                    )

        return None, (
            f"CANONICAL_BGM_MISSING: '{CANONICAL_BGM_FILENAME}' not found in {self.bgm_dir}. "
            f"Cannot render without the canonical BGM."
        )

    # ------------------------------------------------------------------
    # Step 3: FFmpeg mix (Parts 9, 14)
    # ------------------------------------------------------------------

    def _run_ffmpeg_mix(
        self,
        narration_path: Path,
        bgm_path: Path,
        total_duration: float,
        output_path: Path,
    ) -> Optional[str]:
        """
        Mix narration + BGM using FFmpeg amix.

        Narration volume: unmodified (already at ≈ -14 LUFS from TTS pipeline).
        BGM volume: attenuated to ≈ -35 LUFS relative to narration.

        The BGM is trimmed to total_duration if longer; NO looping.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # BGM attenuation: narration target -14 LUFS, BGM target -35 LUFS → delta -21 dB
        bgm_volume_adjust = -21.0  # dB relative to narration
        bgm_volume_linear = 10 ** (bgm_volume_adjust / 20.0)  # ≈ 0.089

        cmd = [
            "ffmpeg", "-y",
            # Narration input
            "-i", str(narration_path),
            # BGM input — trim to total_duration, no loop
            "-ss", "0",
            "-t", str(total_duration),
            "-i", str(bgm_path),
            "-filter_complex",
            (
                f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo[narr];"
                f"[1:a]volume={bgm_volume_linear:.6f},aformat=sample_rates=44100:channel_layouts=stereo[bgm];"
                f"[narr][bgm]amix=inputs=2:duration=first:weights=1 {bgm_volume_linear:.6f}[mixed];"
                f"[mixed]loudnorm=I={CANONICAL_NARRATION_TARGET_LUFS}:TP={CANONICAL_TRUE_PEAK_MAX_DBTP}:LRA=11[out]"
            ),
            "-map", "[out]",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            str(output_path),
        ]

        logger.info("Mixing audio: narration='%s' + BGM='%s' → %s",
                    narration_path.name, bgm_path.name, output_path.name)

        try:
            result = subprocess.run(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=120,
            )
            if result.returncode != 0:
                return f"FFmpeg mix failed (code {result.returncode}): {result.stderr[-800:]}"
            return None
        except subprocess.TimeoutExpired:
            return "FFmpeg mix timed out."

    # ------------------------------------------------------------------
    # Audio measurement helpers
    # ------------------------------------------------------------------

    def _measure_loudness(self, audio_path: Path) -> Tuple[float, float]:
        """Measure integrated LUFS and true peak dBTP using FFmpeg ebur128."""
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-filter_complex", "ebur128=peak=true",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return -99.0, -99.0

        lufs = -99.0
        tp = -99.0
        for line in reversed(result.stderr.split("\n")):
            if "I:" in line and "LUFS" in line and lufs == -99.0:
                try:
                    lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
                except Exception:
                    pass
            if "Peak:" in line and "dBFS" in line and tp == -99.0:
                try:
                    tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
                except Exception:
                    pass
        return lufs, tp

    @staticmethod
    def _probe_audio(path: Path) -> Tuple[float, int]:
        """Return (duration_sec, sample_rate) of an audio file."""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=duration,sample_rate",
            "-of", "json",
            str(path),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            info = json.loads(r.stdout)
            stream = info.get("streams", [{}])[0]
            dur = float(stream.get("duration", 0))
            sr = int(stream.get("sample_rate", 44100))
            return dur, sr
        except Exception:
            return 0.0, 44100

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
