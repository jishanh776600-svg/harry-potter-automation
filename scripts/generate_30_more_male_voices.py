"""
STORY FORGE — Generate 30 More Diverse Male Audition Voices (Individual Files)
================================================================================
Generates 30 NEW, genuinely distinct male voice samples as individual MP3 files
in a dedicated folder for direct listening and comparison.
"""

import os
import sys
import asyncio
import shutil
import logging
from pathlib import Path
import numpy as np
import soundfile as sf
import subprocess

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import KOKORO_MODEL_PATH, KOKORO_VOICES_PATH
from engines.voice_audition.audition_synthesizer import DEFAULT_AUDITION_SCRIPT, AuditionSynthesizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Generate30MoreMales")

SAMPLE_RATE = 24000

# Definition of the 30 new, distinct male voices
NEW_MALE_VOICES = [
    # Group A: Microsoft Neural Voices (Distinct characters)
    {
        "id": "MALE_01_Christopher_DeepAuthoritative",
        "label": "Voice Male 01",
        "type": "edge_tts",
        "voice": "en-US-ChristopherNeural",
        "style": "Deep, authoritative US narrative",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_02_Eric_ConversationalUS",
        "label": "Voice Male 02",
        "type": "edge_tts",
        "voice": "en-US-EricNeural",
        "style": "Conversational, engaging US voice",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_03_Guy_BroadcastEnergetic",
        "label": "Voice Male 03",
        "type": "edge_tts",
        "voice": "en-US-GuyNeural",
        "style": "Punchy US broadcast presenter",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_04_Roger_MatureStoryteller",
        "label": "Voice Male 04",
        "type": "edge_tts",
        "voice": "en-US-RogerNeural",
        "style": "Seasoned, mature US storyteller",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_05_Steffan_DynamicSharp",
        "label": "Voice Male 05",
        "type": "edge_tts",
        "voice": "en-US-SteffanNeural",
        "style": "Crisp, dynamic articulation",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_06_Brian_MultilingualNatural",
        "label": "Voice Male 06",
        "type": "edge_tts",
        "voice": "en-US-BrianMultilingualNeural",
        "style": "Modern cinematic US narrator",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_07_Aled_WelshWarmth",
        "label": "Voice Male 07",
        "type": "edge_tts",
        "voice": "cy-GB-AledNeural",
        "style": "Welsh Celtic wizarding warmth",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_08_Remy_EuropeanElegance",
        "label": "Voice Male 08",
        "type": "edge_tts",
        "voice": "fr-FR-RemyMultilingualNeural",
        "style": "Beauxbatons / Refined European flair",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_09_Florian_DurmstrangAcademic",
        "label": "Voice Male 09",
        "type": "edge_tts",
        "voice": "de-DE-FlorianMultilingualNeural",
        "style": "Commanding European academic",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    {
        "id": "MALE_10_Giuseppe_CharismaticNarrator",
        "label": "Voice Male 10",
        "type": "edge_tts",
        "voice": "it-IT-GiuseppeMultilingualNeural",
        "style": "Charismatic, expressive cadence",
        "rate": "+0%",
        "pitch": "+0Hz"
    },

    # Group B: Specially Tuned Viral Shorts Profiles
    {
        "id": "MALE_11_Andrew_ViralHype",
        "label": "Voice Male 11",
        "type": "edge_tts",
        "voice": "en-US-AndrewNeural",
        "style": "Ultra high-tempo Shorts delivery",
        "rate": "+14%",
        "pitch": "+18Hz"
    },
    {
        "id": "MALE_12_Brian_DarkCinemaTrailer",
        "label": "Voice Male 12",
        "type": "edge_tts",
        "voice": "en-US-BrianNeural",
        "style": "Ominous cinematic trailer gravitas",
        "rate": "-4%",
        "pitch": "-15Hz"
    },
    {
        "id": "MALE_13_Ryan_DocumentaryFast",
        "label": "Voice Male 13",
        "type": "edge_tts",
        "voice": "en-GB-RyanNeural",
        "style": "Fast BBC documentary pacing",
        "rate": "+8%",
        "pitch": "+5Hz"
    },
    {
        "id": "MALE_14_Thomas_AncientLore",
        "label": "Voice Male 14",
        "type": "edge_tts",
        "voice": "en-GB-ThomasNeural",
        "style": "Dark mystery / Horcrux lore",
        "rate": "-5%",
        "pitch": "-10Hz"
    },
    {
        "id": "MALE_15_William_ActionPunch",
        "label": "Voice Male 15",
        "type": "edge_tts",
        "voice": "en-AU-WilliamMultilingualNeural",
        "style": "High-adrenaline action punch",
        "rate": "+10%",
        "pitch": "+8Hz"
    },
    {
        "id": "MALE_16_Liam_YouthfulCreator",
        "label": "Voice Male 16",
        "type": "edge_tts",
        "voice": "en-CA-LiamNeural",
        "style": "Youthful creator tone",
        "rate": "+10%",
        "pitch": "+12Hz"
    },
    {
        "id": "MALE_17_Connor_CelticLore",
        "label": "Voice Male 17",
        "type": "edge_tts",
        "voice": "en-IE-ConnorNeural",
        "style": "Irish storytelling depth",
        "rate": "+5%",
        "pitch": "-4Hz"
    },

    # Group C: Kokoro Acoustic Blends (Linear Interpolation of Style Vectors)
    {
        "id": "MALE_18_FenrirOnyx_DarkBaritone",
        "label": "Voice Male 18",
        "type": "kokoro_blend",
        "blend": [("am_fenrir", 0.6), ("am_onyx", 0.4)],
        "speed": 1.05,
        "style": "Deep gothic baritone narrator"
    },
    {
        "id": "MALE_19_MichaelLiam_DynamicHost",
        "label": "Voice Male 19",
        "type": "kokoro_blend",
        "blend": [("am_michael", 0.65), ("am_liam", 0.35)],
        "speed": 1.05,
        "style": "Authoritative yet youthful show host"
    },
    {
        "id": "MALE_20_GeorgeDaniel_AristocratUK",
        "label": "Voice Male 20",
        "type": "kokoro_blend",
        "blend": [("bm_george", 0.6), ("bm_daniel", 0.4)],
        "speed": 1.02,
        "style": "Refined Hogwarts headmaster tone"
    },
    {
        "id": "MALE_21_PuckAdam_CuriousAnimated",
        "label": "Voice Male 21",
        "type": "kokoro_blend",
        "blend": [("am_puck", 0.55), ("am_adam", 0.45)],
        "speed": 1.05,
        "style": "Curious trivia investigator"
    },
    {
        "id": "MALE_22_FableEcho_EpicFantasy",
        "label": "Voice Male 22",
        "type": "kokoro_blend",
        "blend": [("bm_fable", 0.7), ("am_echo", 0.3)],
        "speed": 1.02,
        "style": "Mythic fantasy legend storyteller"
    },
    {
        "id": "MALE_23_AdamEric_CrispDocumentary",
        "label": "Voice Male 23",
        "type": "kokoro_blend",
        "blend": [("am_adam", 0.5), ("am_eric", 0.5)],
        "speed": 1.05,
        "style": "Razor-sharp factual documentary"
    },
    {
        "id": "MALE_24_OnyxLewis_InvestigativeLore",
        "label": "Voice Male 24",
        "type": "kokoro_blend",
        "blend": [("am_onyx", 0.7), ("bm_lewis", 0.3)],
        "speed": 1.04,
        "style": "Investigative podcast timbre"
    },
    {
        "id": "MALE_25_FenrirGeorge_DarkGothic",
        "label": "Voice Male 25",
        "type": "kokoro_blend",
        "blend": [("am_fenrir", 0.5), ("bm_george", 0.5)],
        "speed": 1.02,
        "style": "Dramatic Death Eater / Dark Arts tone"
    },
    {
        "id": "MALE_26_LiamPuck_HyperShorts",
        "label": "Voice Male 26",
        "type": "kokoro_blend",
        "blend": [("am_liam", 0.6), ("am_puck", 0.4)],
        "speed": 1.12,
        "style": "Rapid YouTube Shorts cadence"
    },
    {
        "id": "MALE_27_MichaelEcho_ResonantTrailer",
        "label": "Voice Male 27",
        "type": "kokoro_blend",
        "blend": [("am_michael", 0.5), ("am_echo", 0.5)],
        "speed": 1.03,
        "style": "Deep resonant movie trailer"
    },
    {
        "id": "MALE_28_LewisAdam_CanonScholar",
        "label": "Voice Male 28",
        "type": "kokoro_blend",
        "blend": [("bm_lewis", 0.6), ("am_adam", 0.4)],
        "speed": 1.04,
        "style": "Analytical Pottermore scholar"
    },
    {
        "id": "MALE_29_SantaOnyx_WiseElder",
        "label": "Voice Male 29",
        "type": "kokoro_blend",
        "blend": [("am_santa", 0.5), ("am_onyx", 0.5)],
        "speed": 1.02,
        "style": "Warm Dumbledore-like elder gravitas"
    },
    {
        "id": "MALE_30_DanielFenrir_AncientHistorian",
        "label": "Voice Male 30",
        "type": "kokoro_blend",
        "blend": [("bm_daniel", 0.6), ("am_fenrir", 0.4)],
        "speed": 1.02,
        "style": "Grim wizarding war historian"
    },
]


def normalize(audio: np.ndarray, target_peak_db: float = -1.0) -> np.ndarray:
    if len(audio) == 0:
        return audio
    peak = np.max(np.abs(audio))
    if peak < 1e-6:
        return audio
    target_linear = 10.0 ** (target_peak_db / 20.0)
    gain = target_linear / peak
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)


async def synthesize_edge(text: str, voice: str, rate: str, pitch: str, out_wav: Path):
    import edge_tts
    temp_mp3 = out_wav.with_suffix(".temp.mp3")
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(str(temp_mp3))
    data, sr = sf.read(str(temp_mp3))
    temp_mp3.unlink(missing_ok=True)
    if len(data.shape) > 1:
        data = data[:, 0]
    data = data.astype(np.float32)
    if sr != SAMPLE_RATE:
        num_samples = int(len(data) * float(SAMPLE_RATE) / float(sr))
        data = np.interp(np.linspace(0, len(data), num_samples), np.arange(len(data)), data).astype(np.float32)
    norm = normalize(data, -1.0)
    sf.write(str(out_wav), norm, SAMPLE_RATE)


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-qscale:a", "2", str(mp3_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        wav_path.unlink(missing_ok=True)
    except Exception:
        # If ffmpeg is unavailable, keep wav
        pass


def main():
    logger.info("==================================================")
    logger.info("GENERATING 30 MORE DISTINCT MALE AUDITION SAMPLES")
    logger.info("==================================================")

    output_dir = Path(__file__).parent.parent / "data" / "auditions" / "male_voices_30_lineup_2"
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts_dir = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36") / "male_voices_lineup_2"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Kokoro
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    manifest_entries = []

    for idx, cfg in enumerate(NEW_MALE_VOICES, start=1):
        voice_id = cfg["id"]
        spoken_label = cfg["label"]
        script_with_label = f"{spoken_label}. {DEFAULT_AUDITION_SCRIPT}"
        
        wav_path = output_dir / f"{voice_id}.wav"
        mp3_path = output_dir / f"{voice_id}.mp3"

        logger.info(f"[{idx}/30] Generating: {voice_id} ({cfg['style']})...")

        if cfg["type"] == "edge_tts":
            loop.run_until_complete(synthesize_edge(
                text=script_with_label,
                voice=cfg["voice"],
                rate=cfg.get("rate", "+0%"),
                pitch=cfg.get("pitch", "+0Hz"),
                out_wav=wav_path
            ))
            convert_wav_to_mp3(wav_path, mp3_path)
            target_audio = mp3_path if mp3_path.exists() else wav_path

        elif cfg["type"] == "kokoro_blend":
            # Compute blended style vector
            blended_style = None
            for v_name, weight in cfg["blend"]:
                style = kokoro.get_voice_style(v_name)
                if blended_style is None:
                    blended_style = weight * style
                else:
                    blended_style += weight * style
            
            samples, sr = kokoro.create(
                script_with_label,
                voice=blended_style,
                speed=cfg.get("speed", 1.05),
                lang="en-us"
            )
            samples = samples.astype(np.float32)
            norm = normalize(samples, -1.0)
            sf.write(str(wav_path), norm, sr)
            convert_wav_to_mp3(wav_path, mp3_path)
            target_audio = mp3_path if mp3_path.exists() else wav_path

        # Copy each file to the user artifact directory as well
        art_copy = artifacts_dir / target_audio.name
        shutil.copy2(target_audio, art_copy)

        # Record entry
        manifest_entries.append({
            "number": idx,
            "filename": target_audio.name,
            "voice_id": voice_id,
            "style": cfg["style"],
            "engine": cfg["type"],
            "config": {k: v for k, v in cfg.items() if k not in ("id", "label")}
        })

    # Write lineup manifest JSON in both locations
    import json
    manifest_data = {
        "lineup_name": "30 More Distinct Male Voices",
        "count": len(manifest_entries),
        "voices": manifest_entries
    }
    (output_dir / "lineup_manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    (artifacts_dir / "lineup_manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    logger.info(f"All 30 separate male voice files generated in: {output_dir}")
    logger.info(f"All 30 separate male voice files copied to: {artifacts_dir}")


if __name__ == "__main__":
    main()
