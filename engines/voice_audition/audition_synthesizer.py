"""
STORY FORGE — Voice Audition Synthesizer
================================================================================
Synthesizes the single 60-voice audition audio containing all 30 Male and
30 Female candidates, separated by consistent silences, with spoken candidate
labels ("Voice Male 01.", etc.) and uniform peak/RMS audio normalization.
Produces the combined audio file and authoritative audition manifest.
"""

import os
import asyncio
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import numpy as np
import soundfile as sf

from core.voice_audition_types import VoiceCandidate, VoiceAuditionManifest
from config.settings import KOKORO_MODEL_PATH, KOKORO_VOICES_PATH, DATA_DIR

logger = logging.getLogger("AuditionSynthesizer")

# Canonical non-copyrighted original Harry Potter factual Shorts audition script
DEFAULT_AUDITION_SCRIPT = (
    "Behind the hidden walls of Hogwarts, centuries of forgotten magic remain buried in plain sight. "
    "From Godric Gryffindor's enchanted goblin-wrought sword to the dark secrets of Ollivanders wand lore, "
    "the most astonishing wizarding truths were never shown on screen. "
    "And what the archives finally reveal will completely change how you see the chosen one."
)

SAMPLE_RATE = 24000
INTER_CANDIDATE_SILENCE_SEC = 0.8


class AuditionSynthesizer:
    """
    Synthesizes and combines all 60 audition candidates into a single normalized master track.
    """

    def __init__(
        self,
        script: str = DEFAULT_AUDITION_SCRIPT,
        sample_rate: int = SAMPLE_RATE,
        inter_candidate_silence: float = INTER_CANDIDATE_SILENCE_SEC,
    ):
        self.script = script
        self.sample_rate = sample_rate
        self.inter_candidate_silence = inter_candidate_silence
        self._kokoro = None

    def _get_kokoro(self):
        """Lazy-loads Kokoro ONNX instance if available."""
        if self._kokoro is None and KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists():
            try:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
            except Exception as e:
                logger.warning(f"Failed to load Kokoro ONNX: {e}")
        return self._kokoro

    @classmethod
    def get_candidate_spoken_label(cls, candidate: VoiceCandidate) -> str:
        """
        Derives spoken identification label for candidate.
        Example: 'Voice Male 01.' or 'Voice Female 01.'
        """
        cat_title = candidate.category.capitalize()
        if candidate.category == "male":
            num = candidate.number
        else:
            # Candidate number 31 becomes Female 01
            num = candidate.number - 30 if candidate.number > 30 else candidate.number
        return f"Voice {cat_title} {num:02d}."

    @classmethod
    def normalize_audio(cls, audio: np.ndarray, target_peak_db: float = -1.0) -> np.ndarray:
        """
        Normalizes peak amplitude to target_peak_db without compression or distortion.
        Preserves natural vocal timbre while equalizing raw provider level disparities.
        """
        if len(audio) == 0:
            return audio

        peak = np.max(np.abs(audio))
        if peak < 1e-6:
            return audio

        target_peak_linear = 10.0 ** (target_peak_db / 20.0)
        gain = target_peak_linear / peak
        normalized = audio * gain
        return np.clip(normalized, -1.0, 1.0).astype(np.float32)

    def synthesize_candidate_audio(
        self,
        candidate: VoiceCandidate,
        temp_dir: Path
    ) -> Tuple[np.ndarray, float]:
        """
        Synthesizes spoken label + audition script for a single voice candidate.
        Returns (audio_samples, duration_seconds).
        """
        spoken_label = self.get_candidate_spoken_label(candidate)
        full_text = f"{spoken_label} {self.script}"

        # 1. Kokoro ONNX synthesis
        if candidate.provider == "Kokoro-82M ONNX":
            kokoro = self._get_kokoro()
            if kokoro:
                try:
                    lang = "en-gb" if candidate.locale.startswith("en-GB") else "en-us"
                    samples, sr = kokoro.create(
                        full_text,
                        voice=candidate.voice_id,
                        speed=1.05,
                        lang=lang
                    )
                    samples = samples.astype(np.float32)
                    dur = len(samples) / float(sr)
                    return samples, dur
                except Exception as e:
                    logger.warning(f"Kokoro synthesis failed for {candidate.voice_id}: {e}")

        # 2. Edge-TTS synthesis fallback/primary
        try:
            import edge_tts
            temp_file = temp_dir / f"temp_{candidate.number:02d}_{candidate.voice_id}.mp3"
            
            async def _synthesize():
                comm = edge_tts.Communicate(full_text, candidate.voice_id)
                await comm.save(str(temp_file))

            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(_synthesize())

            if temp_file.exists() and temp_file.stat().st_size > 0:
                data, sr = sf.read(str(temp_file))
                temp_file.unlink(missing_ok=True)
                if len(data.shape) > 1:
                    data = data[:, 0]  # Mono
                data = data.astype(np.float32)
                # Resample if needed
                if sr != self.sample_rate:
                    # Simple linear resample if sample rates differ
                    num_samples = int(len(data) * float(self.sample_rate) / float(sr))
                    data = np.interp(
                        np.linspace(0, len(data), num_samples),
                        np.arange(len(data)),
                        data
                    ).astype(np.float32)

                dur = len(data) / float(self.sample_rate)
                return data, dur

        except Exception as e:
            logger.warning(f"Edge-TTS synthesis failed for {candidate.voice_id}: {e}")

        # Graceful synthetic silence placeholder if both providers fail
        fallback_dur = 15.0
        samples = np.zeros(int(fallback_dur * self.sample_rate), dtype=np.float32)
        return samples, fallback_dur

    def assemble_audition_timeline(
        self,
        lineup: List[VoiceCandidate],
        temp_dir: Path
    ) -> Tuple[np.ndarray, List[VoiceCandidate]]:
        """
        Synthesizes all candidates in sequence, inserting calibrated silence between them,
        normalizing each candidate, and tracking exact start and end timestamps.
        """
        combined_audio_chunks = []
        updated_candidates: List[VoiceCandidate] = []
        current_time_sec = 0.0

        silence_samples = np.zeros(int(self.inter_candidate_silence * self.sample_rate), dtype=np.float32)

        for candidate in lineup:
            logger.info("Synthesizing [%s] %s (%s)...", candidate.label, candidate.voice_id, candidate.provider)
            raw_audio, _ = self.synthesize_candidate_audio(candidate, temp_dir)
            normalized_audio = self.normalize_audio(raw_audio, target_peak_db=-1.0)

            dur_sec = len(normalized_audio) / float(self.sample_rate)
            start_time = current_time_sec
            end_time = current_time_sec + dur_sec

            updated_c = VoiceCandidate(
                number=candidate.number,
                label=candidate.label,
                category=candidate.category,
                voice_id=candidate.voice_id,
                provider=candidate.provider,
                model=candidate.model,
                locale=candidate.locale,
                accent=candidate.accent,
                start=start_time,
                end=end_time,
                duration=dur_sec,
                config=candidate.config,
            )
            updated_candidates.append(updated_c)

            combined_audio_chunks.append(normalized_audio)
            combined_audio_chunks.append(silence_samples)

            current_time_sec = end_time + self.inter_candidate_silence

        full_audio = np.concatenate(combined_audio_chunks)
        return full_audio, updated_candidates

    def generate_audition_session(
        self,
        lineup: List[VoiceCandidate],
        output_dir: Path,
        session_id: str = "voice_audition_v1"
    ) -> Tuple[Path, Path, VoiceAuditionManifest]:
        """
        Main entrypoint: builds the complete audition session audio & manifest JSON.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = output_dir / "temp_synth"
        temp_dir.mkdir(parents=True, exist_ok=True)

        full_audio, candidates = self.assemble_audition_timeline(lineup, temp_dir)

        # Write audio files (WAV and MP3 if available)
        audio_filename = f"{session_id}_lineup_60.wav"
        audio_path = output_dir / audio_filename
        sf.write(str(audio_path), full_audio, self.sample_rate)

        # Also write MP3 version if ffmpeg/soundfile allows
        mp3_path = output_dir / f"{session_id}_lineup_60.mp3"
        try:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path), "-codec:a", "libmp3lame", "-qscale:a", "2", str(mp3_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            # If ffmpeg conversion fails, audio_path (WAV) remains primary
            mp3_path = audio_path

        total_dur = len(full_audio) / float(self.sample_rate)
        males_count = sum(1 for c in candidates if c.category == "male")
        females_count = sum(1 for c in candidates if c.category == "female")

        manifest = VoiceAuditionManifest(
            session_id=session_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            script=self.script,
            total_voices=len(candidates),
            male_count=males_count,
            female_count=females_count,
            combined_audio_filename=mp3_path.name,
            total_duration_seconds=total_dur,
            voices=candidates,
        )
        manifest.deterministic_fingerprint = manifest.calculate_fingerprint()

        manifest_path = output_dir / f"{session_id}_manifest.json"
        manifest_path.write_text(manifest.to_json(indent=2), encoding="utf-8")

        # Cleanup temp directory
        for f in temp_dir.glob("*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            temp_dir.rmdir()
        except Exception:
            pass

        return mp3_path, manifest_path, manifest
