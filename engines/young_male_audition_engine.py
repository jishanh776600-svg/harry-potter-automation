"""
Young Male (18–20 Years Old) Voice Audition Engine.
Generates 20 distinct young male voices across Kokoro-82M ONNX, Edge-TTS Neural,
and custom youth neural blends, specifically tailored for Harry Potter YouTube Shorts.

Features:
- Youthful pitch (+8Hz to +25Hz) and lively tempo (+5% to +15%) calibration
- Diverse accents: British, American, Canadian, Australian, Irish
- Distinct character vibes: Gryffindor Seeker, Marauder Prankster, Ravenclaw Prodigy,
  Viral Shorts Host, Duel Commentator, Forbidden Lore Sleuth
- ITU-R BS.1770 loudness normalization (-15.5 LUFS)
- Interactive HTML5 Player for laptop audition
"""
import os
import json
import asyncio
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import soundfile as sf
import edge_tts
from kokoro_onnx import Kokoro

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YoungMaleAudition")

SCRIPTS = {
    "sample_01": {
        "title": "Novel Hook: Harry's True Eyes",
        "category": "Mystery / Hook",
        "text": (
            "Wait, did you realize what the movies completely cut about Harry's eyes? "
            "In the books, Harry didn't just have green eyes—every single person who knew Lily "
            "saw her fiery defiance living on inside him. That changes everything."
        )
    },
    "sample_02": {
        "title": "Fast Lore: The Elder Wand Myth",
        "category": "Lore / Action",
        "text": (
            "Everyone thinks the Elder Wand was unbeatable, but they're totally wrong! "
            "The original book canon proves it changed hands not by invincible power, "
            "but through betrayal, stealth, and sheer arrogance. Look at what happened in the Death Chamber!"
        )
    }
}

YOUNG_MALE_VOICES: List[Dict[str, Any]] = [
    # --- BRITISH YOUTH (18-20) ---
    {
        "id": "ym_01_ryan_energetic",
        "name": "Ryan (Gryffindor Seeker)",
        "age": "18–19",
        "engine": "Edge-TTS",
        "base_voice": "en-GB-RyanNeural",
        "accent": "British (UK)",
        "pitch": "+18Hz",
        "rate": "+12%",
        "mood": "High Energy / Urgent Hook",
        "vibe": "Energetic 19yo British narrator with breathless revelation and fast hook.",
        "type": "edge"
    },
    {
        "id": "ym_02_ryan_curious",
        "name": "Ryan (Restricted Section Sleuth)",
        "age": "18–19",
        "engine": "Edge-TTS",
        "base_voice": "en-GB-RyanNeural",
        "accent": "British (UK)",
        "pitch": "+10Hz",
        "rate": "+5%",
        "mood": "Intrigued / Conspiratorial",
        "vibe": "Curious 18yo Hogwarts student uncovering forbidden midnight secrets.",
        "type": "edge"
    },
    {
        "id": "ym_03_blend_marauder",
        "name": "Leo (Marauder Mischief)",
        "age": "18–19",
        "engine": "Kokoro Blended",
        "base_voice": "0.65*am_puck + 0.35*bm_lewis",
        "accent": "British Blend",
        "speed": 1.12,
        "lang": "en-gb",
        "mood": "Playful / Smirking / Rebel",
        "vibe": "Fred & George prankster energy with a sharp teenage British bite.",
        "type": "kokoro_blend",
        "blend": [("am_puck", 0.65), ("bm_lewis", 0.35)]
    },
    {
        "id": "ym_04_blend_prodigy",
        "name": "Julian (Ravenclaw Prodigy)",
        "age": "18–19",
        "engine": "Kokoro Blended",
        "base_voice": "0.70*am_liam + 0.30*bm_daniel",
        "accent": "British Blend",
        "speed": 1.10,
        "lang": "en-gb",
        "mood": "Articulate / Clever / Fast",
        "vibe": "Sharp 18yo wizarding scholar breaking down advanced spell lore.",
        "type": "kokoro_blend",
        "blend": [("am_liam", 0.70), ("bm_daniel", 0.30)]
    },

    # --- CELTIC & COMMONWEALTH YOUTH (18-20) ---
    {
        "id": "ym_05_connor_celtic",
        "name": "Connor (Gryffindor Firebrand)",
        "age": "19",
        "engine": "Edge-TTS",
        "base_voice": "en-IE-ConnorNeural",
        "accent": "Irish (Celtic)",
        "pitch": "+16Hz",
        "rate": "+10%",
        "mood": "Fiery / Spirited / Spunky",
        "vibe": "Seamus Finnigan spirited energy; passionate Celtic storytelling.",
        "type": "edge"
    },
    {
        "id": "ym_06_liam_canadian",
        "name": "Liam (Exchange Student)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-CA-LiamNeural",
        "accent": "Canadian",
        "pitch": "+14Hz",
        "rate": "+8%",
        "mood": "Charismatic / Natural / Clear",
        "vibe": "Ultra-clean modern articulation; approachable young adult creator.",
        "type": "edge"
    },
    {
        "id": "ym_07_william_aussie",
        "name": "William (Creatures Explorer)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-AU-WilliamMultilingualNeural",
        "accent": "Australian",
        "pitch": "+12Hz",
        "rate": "+8%",
        "mood": "Adventurous / Upbeat",
        "vibe": "Daring young adventurer tracking down dangerous magical beasts.",
        "type": "edge"
    },
    {
        "id": "ym_08_mitchell_kiwi",
        "name": "Mitchell (Quidditch Fanatic)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-NZ-MitchellNeural",
        "accent": "New Zealand",
        "pitch": "+14Hz",
        "rate": "+9%",
        "mood": "Breezy / Excited / Candid",
        "vibe": "Casual, fast-paced sports and broomstick breakdown style.",
        "type": "edge"
    },

    # --- AMERICAN YOUTH (18-20) - VIRAL CREATOR & TEEN THEORIST ---
    {
        "id": "ym_09_andrew_creator",
        "name": "Andrew (Viral Shorts Host)",
        "age": "18–19",
        "engine": "Edge-TTS",
        "base_voice": "en-US-AndrewNeural",
        "accent": "American",
        "pitch": "+14Hz",
        "rate": "+10%",
        "mood": "Punchy / Engaging / Viral Hook",
        "vibe": "Classic high-retention YouTube Shorts presenter; enthusiastic & clear.",
        "type": "edge"
    },
    {
        "id": "ym_10_andrew_hype",
        "name": "Andrew (Duel Commentator)",
        "age": "18",
        "engine": "Edge-TTS",
        "base_voice": "en-US-AndrewNeural",
        "accent": "American",
        "pitch": "+24Hz",
        "rate": "+14%",
        "mood": "Electrifying / High Tempo",
        "vibe": "Rapid-fire excitement breaking down intense spell duels.",
        "type": "edge"
    },
    {
        "id": "ym_11_brian_conversational",
        "name": "Brian (The Book Fanatic)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-US-BrianNeural",
        "accent": "American",
        "pitch": "+10Hz",
        "rate": "+6%",
        "mood": "Relatable / Honest / Candid",
        "vibe": "Friendly 'movies vs books' debunker who talks straight to the camera.",
        "type": "edge"
    },
    {
        "id": "ym_12_brian_suspense",
        "name": "Brian (Horcrux Hunter)",
        "age": "19",
        "engine": "Edge-TTS",
        "base_voice": "en-US-BrianNeural",
        "accent": "American",
        "pitch": "+16Hz",
        "rate": "+9%",
        "mood": "Tense / Urgent Suspense",
        "vibe": "High-stakes mystery narration with gripping dramatic pauses.",
        "type": "edge"
    },
    {
        "id": "ym_13_christopher_chill",
        "name": "Chris (Fireside Storyteller)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-US-ChristopherNeural",
        "accent": "American",
        "pitch": "+8Hz",
        "rate": "+3%",
        "mood": "Chill / Smooth / Intimate",
        "vibe": "Late-night Gryffindor common room campfire storytelling.",
        "type": "edge"
    },
    {
        "id": "ym_14_christopher_snappy",
        "name": "Chris (Fast-Fact Machine)",
        "age": "18–19",
        "engine": "Edge-TTS",
        "base_voice": "en-US-ChristopherNeural",
        "accent": "American",
        "pitch": "+20Hz",
        "rate": "+12%",
        "mood": "Snappy / Rhythmic / Quick",
        "vibe": "Fast-paced TikTok lore countdowns and rapid discoveries.",
        "type": "edge"
    },
    {
        "id": "ym_15_eric_apprentice",
        "name": "Eric (Wandmaker's Apprentice)",
        "age": "18",
        "engine": "Edge-TTS",
        "base_voice": "en-US-EricNeural",
        "accent": "American",
        "pitch": "+16Hz",
        "rate": "+10%",
        "mood": "Eager / Bright / Focused",
        "vibe": "Passionate 18yo detailing core woods, phoenix feathers, and magic rules.",
        "type": "edge"
    },
    {
        "id": "ym_16_steffan_rebel",
        "name": "Steffan (Dumbledore's Army Underdog)",
        "age": "19",
        "engine": "Edge-TTS",
        "base_voice": "en-US-SteffanNeural",
        "accent": "American",
        "pitch": "+14Hz",
        "rate": "+8%",
        "mood": "Edgy / Defiant / Intense",
        "vibe": "Passionate resistance fighter standing up to Umbridge and Death Eaters.",
        "type": "edge"
    },
    {
        "id": "ym_17_guy_witty",
        "name": "Guy (Sarcastic Slytherin)",
        "age": "19–20",
        "engine": "Edge-TTS",
        "base_voice": "en-US-GuyNeural",
        "accent": "American",
        "pitch": "+14Hz",
        "rate": "+9%",
        "mood": "Witty / Sarcastic / Confident",
        "vibe": "Playful, arrogant-fun commentary pointing out foolish wizard errors.",
        "type": "edge"
    },

    # --- KOKORO-82M ONNX YOUTH PROFILES ---
    {
        "id": "ym_18_kokoro_puck",
        "name": "Puck (The Young Marauder)",
        "age": "18",
        "engine": "Kokoro-82M",
        "base_voice": "am_puck",
        "accent": "American Youth",
        "speed": 1.12,
        "lang": "en-us",
        "mood": "Youthful Mischief / Snappy",
        "vibe": "Brisk, teenage boy vocal texture, playful and quick.",
        "type": "kokoro"
    },
    {
        "id": "ym_19_kokoro_liam",
        "name": "Liam (Freshman Theorist)",
        "age": "18–19",
        "engine": "Kokoro-82M",
        "base_voice": "am_liam",
        "accent": "American Youth",
        "speed": 1.10,
        "lang": "en-us",
        "mood": "Fresh / Modern / Analytical",
        "vibe": "Clean, crisp teen tone with strong modern relatability.",
        "type": "kokoro"
    },
    {
        "id": "ym_20_kokoro_echo",
        "name": "Echo (The Thoughtful Seeker)",
        "age": "19–20",
        "engine": "Kokoro-82M",
        "base_voice": "am_echo",
        "accent": "American Youth",
        "speed": 1.08,
        "lang": "en-us",
        "mood": "Smooth / Mellow / Curious",
        "vibe": "Relaxed young adult voice with natural vocal warmth.",
        "type": "kokoro"
    }
]


class YoungMaleAuditionRunner:
    """Generates audio samples, masters them with broadcast specs, and builds HTML player."""

    def __init__(self, project_root: Path = None):
        if project_root is None:
            self.project_root = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation")
        else:
            self.project_root = project_root
        self.data_dir = self.project_root / "data"
        self.output_root = self.data_dir / "voice_audition" / "young_males"
        self.kokoro_model = self.data_dir / "kokoro-v1.0.onnx"
        self.kokoro_voices = self.data_dir / "voices-v1.0.bin"
        self._kokoro = None

    def _get_kokoro(self) -> Kokoro:
        if self._kokoro is None:
            logger.info("Initializing Kokoro ONNX model...")
            self._kokoro = Kokoro(str(self.kokoro_model), str(self.kokoro_voices))
        return self._kokoro

    async def _synth_edge(self, text: str, voice: str, pitch: str, rate: str, out_path: Path):
        communicate = edge_tts.Communicate(text, voice, pitch=pitch, rate=rate)
        await communicate.save(str(out_path))

    def _synth_kokoro(self, text: str, voice_name: str, speed: float, lang: str, out_path: Path):
        k = self._get_kokoro()
        samples, sr = k.create(text, voice=voice_name, speed=speed, lang=lang)
        sf.write(str(out_path), samples, sr)

    def _synth_kokoro_blend(self, text: str, blend_spec: list, speed: float, lang: str, out_path: Path):
        k = self._get_kokoro()
        blended_vec = None
        for v_name, weight in blend_spec:
            v_style = k.get_voice_style(v_name)
            if blended_vec is None:
                blended_vec = v_style * weight
            else:
                blended_vec += v_style * weight
        samples, sr = k.create(text, voice=blended_vec, speed=speed, lang=lang)
        sf.write(str(out_path), samples, sr)

    def _master_audio(self, in_path: Path, out_path: Path):
        """ITU-R BS.1770 broadcast normalization (-15.5 LUFS, highpass 80Hz, 24kHz mono)."""
        af_chain = "highpass=f=80,loudnorm=I=-15.5:LRA=7.0:tp=-1.2"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-af", af_chain,
            "-ar", "24000",
            "-ac", "1",
            str(out_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            logger.warning(f"Mastering failed for {in_path}: {res.stderr.decode('utf-8', errors='ignore')[:200]}")
            if in_path != out_path:
                import shutil
                shutil.copy2(in_path, out_path)

    def run_audition(self) -> Dict[str, Any]:
        logger.info(f"Starting Young Male Audition Generation: {len(YOUNG_MALE_VOICES)} voices...")
        self.output_root.mkdir(parents=True, exist_ok=True)

        results = []

        for voice_meta in YOUNG_MALE_VOICES:
            v_id = voice_meta["id"]
            voice_dir = self.output_root / v_id
            voice_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"--> Processing {voice_meta['name']} ({voice_meta['age']}yo | {voice_meta['accent']})...")

            samples_generated = {}

            for s_key, s_data in SCRIPTS.items():
                raw_path = voice_dir / f"{v_id}_{s_key}_raw.wav"
                master_path = voice_dir / f"{v_id}_{s_key}.wav"

                # 1. Synthesize
                v_type = voice_meta["type"]
                if v_type == "edge":
                    asyncio.run(self._synth_edge(
                        text=s_data["text"],
                        voice=voice_meta["base_voice"],
                        pitch=voice_meta["pitch"],
                        rate=voice_meta["rate"],
                        out_path=raw_path
                    ))
                elif v_type == "kokoro":
                    self._synth_kokoro(
                        text=s_data["text"],
                        voice_name=voice_meta["base_voice"],
                        speed=voice_meta["speed"],
                        lang=voice_meta["lang"],
                        out_path=raw_path
                    )
                elif v_type == "kokoro_blend":
                    self._synth_kokoro_blend(
                        text=s_data["text"],
                        blend_spec=voice_meta["blend"],
                        speed=voice_meta["speed"],
                        lang=voice_meta["lang"],
                        out_path=raw_path
                    )

                # 2. Master
                self._master_audio(raw_path, master_path)

                # Clean raw file
                if raw_path.exists():
                    raw_path.unlink()

                # Get duration
                try:
                    data, sr = sf.read(str(master_path))
                    dur = round(len(data) / float(sr), 2)
                except Exception:
                    dur = 0.0

                rel_path = f"{v_id}/{master_path.name}"
                samples_generated[s_key] = {
                    "title": s_data["title"],
                    "category": s_data["category"],
                    "duration_sec": dur,
                    "relative_path": rel_path
                }

            results.append({
                **voice_meta,
                "samples": samples_generated
            })

        # Save metadata JSON
        meta_path = self.output_root / "young_males_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "title": "Harry Potter Automation - Young Male Voice Audition (18-20yo)",
                "total_voices": len(results),
                "voices": results,
                "scripts": SCRIPTS
            }, f, indent=2)

        # Generate HTML Player
        self.generate_html_player(results)

        logger.info(f"Audition generation complete! 20 Young Male voices ready in {self.output_root}")
        return {
            "total_voices": len(results),
            "total_samples": len(results) * 2,
            "output_dir": str(self.output_root)
        }

    def generate_html_player(self, voices: List[Dict[str, Any]]):
        html_path = self.output_root / "young_males_player.html"
        cards_html = []

        for idx, v in enumerate(voices, start=1):
            s1 = v["samples"]["sample_01"]
            s2 = v["samples"]["sample_02"]

            engine_badge_cls = "badge-edge" if "Edge" in v["engine"] else ("badge-blend" if "Blend" in v["engine"] else "badge-kokoro")

            cards_html.append(f"""
            <div class="voice-card" data-accent="{v['accent']}" data-engine="{v['engine']}">
                <div class="card-header">
                    <div class="voice-title-row">
                        <span class="voice-num">#{idx:02d}</span>
                        <h3 class="voice-name">{v['name']}</h3>
                        <span class="age-pill">{v['age']} yrs</span>
                    </div>
                    <div class="badges-row">
                        <span class="badge {engine_badge_cls}">{v['engine']}</span>
                        <span class="badge badge-accent">{v['accent']}</span>
                        <span class="badge badge-mood">{v['mood']}</span>
                    </div>
                </div>

                <p class="vibe-desc">{v['vibe']}</p>

                <div class="tuning-info">
                    <span class="param-tag">Base: <code>{v['base_voice']}</code></span>
                    {f"<span class='param-tag'>Pitch: <code>{v['pitch']}</code></span>" if 'pitch' in v else ""}
                    {f"<span class='param-tag'>Rate: <code>{v['rate']}</code></span>" if 'rate' in v else ""}
                    {f"<span class='param-tag'>Speed: <code>{v['speed']}x</code></span>" if 'speed' in v else ""}
                </div>

                <div class="samples-container">
                    <div class="sample-item">
                        <div class="sample-meta">
                            <span class="sample-badge s1">Sample 1: Mystery Hook</span>
                            <span class="sample-dur">{s1['duration_sec']}s</span>
                        </div>
                        <audio controls preload="none" src="{s1['relative_path']}"></audio>
                    </div>

                    <div class="sample-item">
                        <div class="sample-meta">
                            <span class="sample-badge s2">Sample 2: Fast Lore/Action</span>
                            <span class="sample-dur">{s2['duration_sec']}s</span>
                        </div>
                        <audio controls preload="none" src="{s2['relative_path']}"></audio>
                    </div>
                </div>
            </div>
            """)

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harry Potter Young Male Voices (18–20yo) | Audition Gallery</title>
    <style>
        :root {{
            --bg-deep: #0b0e14;
            --bg-card: #151b26;
            --bg-card-hover: #1c2433;
            --gold-primary: #e6b450;
            --gold-glow: rgba(230, 180, 80, 0.25);
            --text-main: #e2e8f0;
            --text-dim: #94a3b8;
            --accent-glow: #38bdf8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{
            background: var(--bg-deep);
            color: var(--text-main);
            padding: 30px 20px 80px;
        }}
        .header {{
            max-width: 1200px;
            margin: 0 auto 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.2rem;
            color: var(--gold-primary);
            text-shadow: 0 0 16px var(--gold-glow);
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        .header p {{
            color: var(--text-dim);
            font-size: 1.05rem;
            max-width: 760px;
            margin: 0 auto;
        }}
        .filter-bar {{
            max-width: 1200px;
            margin: 20px auto 30px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            background: #111622;
            padding: 14px 20px;
            border-radius: 12px;
            border: 1px solid #232c3d;
        }}
        .filter-btn {{
            background: #1a2232;
            border: 1px solid #334155;
            color: var(--text-main);
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.88rem;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{
            background: var(--gold-primary);
            color: #0b0e14;
            border-color: var(--gold-primary);
            box-shadow: 0 0 12px var(--gold-glow);
        }}
        .grid {{
            max-width: 1240px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }}
        .voice-card {{
            background: var(--bg-card);
            border: 1px solid #232c3d;
            border-radius: 14px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
        }}
        .voice-card:hover {{
            transform: translateY(-3px);
            border-color: var(--gold-primary);
            box-shadow: 0 8px 24px var(--gold-glow);
        }}
        .card-header {{
            margin-bottom: 12px;
        }}
        .voice-title-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .voice-num {{
            font-weight: 700;
            color: var(--gold-primary);
            font-size: 0.95rem;
        }}
        .voice-name {{
            font-size: 1.15rem;
            color: #fff;
            flex-grow: 1;
        }}
        .age-pill {{
            background: #25334a;
            color: #38bdf8;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 12px;
            border: 1px solid #38bdf844;
        }}
        .badges-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 8px;
        }}
        .badge {{
            font-size: 0.72rem;
            font-weight: 600;
            padding: 3px 9px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-edge {{ background: #0284c7; color: #fff; }}
        .badge-kokoro {{ background: #059669; color: #fff; }}
        .badge-blend {{ background: #7c3aed; color: #fff; }}
        .badge-accent {{ background: #334155; color: #cbd5e1; }}
        .badge-mood {{ background: #3f2e15; color: #f59e0b; border: 1px solid #f59e0b44; }}
        .vibe-desc {{
            font-size: 0.9rem;
            color: #cbd5e1;
            line-height: 1.4;
            margin-bottom: 12px;
        }}
        .tuning-info {{
            font-size: 0.78rem;
            color: var(--text-dim);
            background: #0f141d;
            padding: 6px 10px;
            border-radius: 6px;
            margin-bottom: 14px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .tuning-info code {{
            color: #38bdf8;
            font-family: monospace;
        }}
        .samples-container {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #0d1117;
            padding: 12px;
            border-radius: 10px;
            border: 1px solid #1e2638;
        }}
        .sample-item {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .sample-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
        }}
        .sample-badge {{
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 4px;
        }}
        .sample-badge.s1 {{ background: #1e3a5f; color: #93c5fd; }}
        .sample-badge.s2 {{ background: #4c1d38; color: #f472b6; }}
        .sample-dur {{ color: var(--text-dim); font-family: monospace; }}
        audio {{
            width: 100%;
            height: 36px;
            border-radius: 6px;
            outline: none;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ Harry Potter Automation — Young Male Voices (18–20yo)</h1>
        <p>Audition 20 new high-tempo, energetic, youthful male voices spanning British, Celtic, American, and Commonwealth accents across Kokoro-82M, Edge-TTS Neural, and Custom Youth Blends.</p>
    </div>

    <div class="filter-bar">
        <button class="filter-btn active" onclick="filterCards('all')">Show All (20)</button>
        <button class="filter-btn" onclick="filterCards('British')">🇬🇧 British (4)</button>
        <button class="filter-btn" onclick="filterCards('Irish')">🇮🇪 Irish / Celtic (1)</button>
        <button class="filter-btn" onclick="filterCards('Canadian')">🇨🇦 Canadian (1)</button>
        <button class="filter-btn" onclick="filterCards('Australian')">🇦🇺 Australian (1)</button>
        <button class="filter-btn" onclick="filterCards('American')">🇺🇸 American (12)</button>
        <button class="filter-btn" onclick="filterEngine('Edge-TTS')">Edge-TTS (13)</button>
        <button class="filter-btn" onclick="filterEngine('Kokoro')">Kokoro & Blends (7)</button>
    </div>

    <div class="grid" id="voicesGrid">
        {''.join(cards_html)}
    </div>

    <script>
        function filterCards(accent) {{
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            const cards = document.querySelectorAll('.voice-card');
            cards.forEach(c => {{
                if (accent === 'all') {{
                    c.style.display = 'flex';
                }} else {{
                    const cardAccent = c.getAttribute('data-accent');
                    if (cardAccent.includes(accent)) {{
                        c.style.display = 'flex';
                    }} else {{
                        c.style.display = 'none';
                    }}
                }}
            }});
        }}

        function filterEngine(eng) {{
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            const cards = document.querySelectorAll('.voice-card');
            cards.forEach(c => {{
                const cardEng = c.getAttribute('data-engine');
                if (cardEng.includes(eng)) {{
                    c.style.display = 'flex';
                }} else {{
                    c.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        logger.info(f"HTML Player written to {html_path}")


if __name__ == "__main__":
    runner = YoungMaleAuditionRunner()
    runner.run_audition()
