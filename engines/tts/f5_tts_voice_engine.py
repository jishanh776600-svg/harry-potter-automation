"""
STORY FORGE — F5-TTS Reference Voice Cloning Engine
===================================================
Experimental zero-shot voice cloning engine implementing flow-matching
acoustic modeling conditioned on reference prompt audio and transcripts.
Strictly decoupled from production voice configuration.
"""

import logging
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio

# Seamless soundfile patch for torchaudio on platforms where torchcodec C++ DLLs are absent
def _soundfile_load(uri, frame_offset=0, num_frames=-1, channels_first=True, **kwargs):
    data, sr = sf.read(uri, start=frame_offset, frames=num_frames if num_frames > 0 else -1, dtype='float32')
    t = torch.from_numpy(data)
    if t.ndim == 1:
        t = t.unsqueeze(0)
    elif channels_first and t.ndim == 2:
        t = t.t()
    return t, sr

def _soundfile_save(uri, src, sample_rate, channels_first=True, **kwargs):
    arr = src.detach().cpu().numpy()
    if channels_first and arr.ndim == 2:
        arr = arr.T
    sf.write(uri, arr, sample_rate)

torchaudio.load = _soundfile_load
torchaudio.save = _soundfile_save

logger = logging.getLogger("F5TTSVoiceEngine")


class F5TTSVoiceEngine:
    """
    Zero-shot reference speaker conditioning and flow-matching generation engine.
    Compatible with STORY FORGE TTS architecture.
    """

    DEFAULT_MODEL_NAME = "F5-TTS"
    DEFAULT_MODEL_NAME = "F5TTS_v1_Base"
    DEFAULT_REPO = "SWivid/F5-TTS"

    def __init__(
        self,
        device: str = "cpu",
        model_name: str = "F5TTS_v1_Base",
        model_dir: Optional[str] = None,
        use_ema: bool = True,
        ode_method: str = "euler",
        nfe_step: int = 32,
    ):
        self.device = device
        self.model_name = model_name
        self.model_dir = Path(model_dir or "data/models/f5_tts")
        self.use_ema = use_ema
        self.ode_method = ode_method
        self.nfe_step = nfe_step
        self._f5_model = None
        self._initialized = False

    def is_available(self) -> bool:
        """Checks if f5-tts package and torch runtime are importable."""
        try:
            import torch
            import f5_tts
            return True
        except ImportError:
            return False

    def load_model(self) -> None:
        """Lazy loads or downloads F5-TTS model weights from HuggingFace."""
        if self._initialized:
            return

        logger.info(f"[F5-TTS] Initializing {self.model_name} on {self.device}...")
        try:
            from f5_tts.api import F5TTS
            self._f5_model = F5TTS(
                model=self.model_name,
                ode_method=self.ode_method,
                use_ema=self.use_ema,
                device=self.device
            )
            self._initialized = True
            logger.info(f"[F5-TTS] Model successfully loaded on {self.device}.")
        except Exception as exc:
            logger.warning(f"[F5-TTS] Direct F5TTS API load error: {exc}. Attempting checkpoint resolution...")
            raise RuntimeError(f"F5-TTS model initialization failed: {exc}")

    def generate(
        self,
        text: str,
        reference_audio: str,
        reference_text: str,
        output_path: str,
        speed: float = 1.0,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Generates speech conditioned on reference prompt audio.

        Args:
            text: The target text to synthesize.
            reference_audio: Path to the clean speaker conditioning WAV.
            reference_text: Exact transcript of the reference audio.
            output_path: Target path for the output WAV file.
            speed: Speaking rate multiplier (1.0 = normal, 1.15 = brisk Shorts pacing).
            seed: Deterministic random seed for Flow Matching sampling.

        Returns:
            Dict containing output metadata, durations, and status.
        """
        ref_path = Path(reference_audio)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._initialized:
            self.load_model()

        logger.info(f"[F5-TTS] Synthesizing {len(text.split())} words conditioned on '{ref_path.name}' (speed={speed}, seed={seed})")

        # Set deterministic seeds
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        wav, sr, spec = self._f5_model.infer(
            ref_file=str(ref_path.resolve()),
            ref_text=reference_text,
            gen_text=text,
            file_wave=str(out_path.resolve()),
            speed=speed,
            seed=seed,
            nfe_step=self.nfe_step,
        )

        audio_len = len(wav) / sr if wav is not None else 0.0

        return {
            "status": "success",
            "output_path": str(out_path.as_posix()),
            "sample_rate": sr,
            "duration_s": round(audio_len, 2),
            "words_per_second": round(len(text.split()) / max(0.1, audio_len), 2),
            "reference_audio_used": str(ref_path.as_posix()),
            "reference_text_used": reference_text,
            "speed": speed,
            "seed": seed,
            "engine": "F5-TTS (Flow Matching)",
        }

    @staticmethod
    def apply_post_processing(
        raw_wav: str,
        processed_wav: str,
        processed_mp3: Optional[str] = None,
        highpass_hz: int = 80,
        presence_gain_db: float = 1.5,
        presence_freq_hz: int = 2500,
        deess_freq_hz: int = 6500,
        deess_gain_db: float = -2.0,
        target_lufs: float = -14.0,
        max_true_peak_db: float = -1.0,
    ) -> Dict[str, Any]:
        """
        Applies professional mastering matching the reference Short's broadcast character:
        - 80 Hz high-pass (sub-rumble removal)
        - De-essing band notch at 6.5 kHz
        - Presence boost (+1.5 dB @ 2.5 kHz) for crispness
        - Broadcast dynamic compression (-18 dB threshold, 2.5:1 ratio)
        - Integrated EBUR128 loudness normalization
        """
        out_wav_p = Path(processed_wav)
        out_wav_p.parent.mkdir(parents=True, exist_ok=True)

        filter_chain = (
            f"highpass=f={highpass_hz},"
            f"equalizer=f={presence_freq_hz}:t=q:w=1.0:g={presence_gain_db},"
            f"equalizer=f={deess_freq_hz}:t=q:w=1.5:g={deess_gain_db},"
            f"acompressor=threshold=-18dB:ratio=2.5:attack=25:release=100,"
            f"loudnorm=I={target_lufs}:TP={max_true_peak_db}:LRA=7"
        )

        cmd_wav = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", raw_wav,
            "-af", filter_chain,
            "-ar", "44100", "-ac", "1",
            str(out_wav_p.resolve())
        ]
        subprocess.run(cmd_wav, check=True)

        if processed_mp3:
            out_mp3_p = Path(processed_mp3)
            cmd_mp3 = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(out_wav_p.resolve()),
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(out_mp3_p.resolve())
            ]
            subprocess.run(cmd_mp3, check=True)

        return {
            "processed_wav": str(out_wav_p.as_posix()),
            "processed_mp3": str(Path(processed_mp3).as_posix()) if processed_mp3 else None,
            "target_lufs": target_lufs,
            "presence_boost": presence_gain_db,
        }
