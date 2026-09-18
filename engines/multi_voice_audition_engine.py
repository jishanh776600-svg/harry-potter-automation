"""
Multi-Model Voice Audition Engine.
Auditions 20 distinct voices (10 Male + 10 Female) across Kokoro-82M and Edge-TTS Neural models
spanning British, American, and Irish accents with various moods and tones for the Harry Potter channel.
Outputs to data/voice_audition/multi_voice/<gender>/<voice_id>/ with consistent studio mastering.
"""
import os
import json
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import soundfile as sf

from config.settings import DATA_DIR, FFMPEG_EXE, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH

logger = logging.getLogger(__name__)

MULTI_VOICE_ROOT = DATA_DIR / "voice_audition" / "multi_voice"


AUDITION_VOICES: Dict[str, List[Dict[str, Any]]] = {
    "female": [
        {
            "id": "bf_alice",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Alice — Headmistress Authority",
            "mood": "Dignified, intellectual, serene",
            "sample_1": "Hogwarts castle has guarded its ancient mysteries for a thousand years, waiting for those worthy to understand them.",
            "sample_2": "Here is a curious truth the films overlooked: Ravenclaw's common room requires answering a philosophical riddle before the door will open."
        },
        {
            "id": "bf_emma",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Emma — Hermionesque Scholar",
            "mood": "Bright, energetic, articulate",
            "sample_1": "Harry turned the heavy brass doorknob, stepping into the forbidden third-floor corridor where three giant heads snarled in the dark.",
            "sample_2": "Did you know that in the novels, Hermione actually founded an entire organization to fight for house-elf freedom during her fourth year?"
        },
        {
            "id": "bf_isabella",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Isabella — Cinematic Lore Master",
            "mood": "Deep, atmospheric, cinematic warmth",
            "sample_1": "Rain hammered the leaded glass of the astronomy tower as lightning illuminated the forbidden forest below.",
            "sample_2": "The Marauder's Map never lied because it was enchanted with the homunculus charm, tracking the living soul rather than physical appearance."
        },
        {
            "id": "bf_lily",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Lily — Enchanting & Nostalgic",
            "mood": "Gentle, nostalgic, magical warmth",
            "sample_1": "Sitting beside the crackling Gryffindor fire with a warm mug of butterbeer, Harry finally felt he had found a home.",
            "sample_2": "In the book, Mrs. Weasley sent Harry a handmade emerald jumper every single winter, making sure he never felt forgotten."
        },
        {
            "id": "af_sarah",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "American (US)",
            "name": "Sarah — Modern Conversational Explainer",
            "mood": "Engaging, conversational, curiosity-driven",
            "sample_1": "So here is the secret about Ollivander that completely changes how you view wandlore in the wizarding world.",
            "sample_2": "The movies made Ron look clueless, but in the original books, Ron was actually the wizarding world expert who guided Harry through everything."
        },
        {
            "id": "af_nicole",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "American (US)",
            "name": "Nicole — Grounded Storyteller",
            "mood": "Smooth, authentic, rich narrative presence",
            "sample_1": "Ten years in the dark cupboard under the stairs had prepared Harry for hardship, but nothing could prepare him for the letters.",
            "sample_2": "Look closely at the portrait of Phineas Nigellus Black, because he was secretly spying for Dumbledore the entire time."
        },
        {
            "id": "af_sky",
            "model": "Kokoro-82M",
            "gender": "Female",
            "accent": "American (US)",
            "name": "Sky — Fast-Paced Action Punch",
            "mood": "Upbeat, rapid, high-retention hook",
            "sample_1": "Three seconds left on the clock, Harry dives straight down through the rain, dodges a bludger, and snatches the snitch!",
            "sample_2": "Boom! Hagrid breaks the wooden door off its hinges, bends Vernon's shotgun into a knot, and hands Harry a birthday cake!"
        },
        {
            "id": "en-GB-SoniaNeural",
            "model": "Edge-TTS Neural",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Sonia — BBC Documentary Investigator",
            "mood": "Authoritative, serious, investigative",
            "sample_1": "Beneath the surface of the wizarding ministry lies the Department of Mysteries, where the fundamental forces of death and time are studied.",
            "sample_2": "Historical archives confirm that the Triwizard Tournament was banned for over two centuries due to its catastrophic casualty rate."
        },
        {
            "id": "en-GB-LibbyNeural",
            "model": "Edge-TTS Neural",
            "gender": "Female",
            "accent": "British (UK)",
            "name": "Libby — Classic English Storybook",
            "mood": "Lyrical, expressive, fairytale enchantment",
            "sample_1": "Once upon an October night, a tiny bundle was left on the doorstep of number four Privet Drive under the golden streetlamps.",
            "sample_2": "The Great Hall was dressed for Christmas, with twelve towering fir trees sparkling with live fairies and frosted pinecones."
        },
        {
            "id": "en-US-AriaNeural",
            "model": "Edge-TTS Neural",
            "gender": "Female",
            "accent": "American (US)",
            "name": "Aria — Dramatic Movie Trailer",
            "mood": "Intense, cinematic, suspenseful",
            "sample_1": "Darkness was returning to the wizarding world, and inside the graveyard at Little Hangleton, the shadows began to whisper.",
            "sample_2": "Every prophecy locked in the Hall of Prophecies tells a story, but only one determined the fate of the boy who lived."
        }
    ],

    "male": [
        {
            "id": "bm_daniel",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "Daniel — Classical Oxford Narrator",
            "mood": "Cultured, articulate, warm authority",
            "sample_1": "The Hogwarts Express pulled away from platform nine and three-quarters, carrying Harry toward an unimaginable magical destiny.",
            "sample_2": "In wizarding tradition, ancient wands remember the spells of past masters, creating an unbreakable legacy of sorcery."
        },
        {
            "id": "bm_george",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "George — Dark Arts & Ominous Lore",
            "mood": "Deep, ominous, brooding, menacing",
            "sample_1": "Deep in the misty alleys of Knockturn Alley, dark wizards traded in cursed necklaces and withered hands that crawled in the shadows.",
            "sample_2": "The basilisk had slithered through the plumbing of Hogwarts for a thousand years, waiting for the true heir of Slytherin to command it."
        },
        {
            "id": "bm_lewis",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "Lewis — Adventurous Gryffindor",
            "mood": "Youthful, bold, spirited, adventurous",
            "sample_1": "Harry mounted his Nimbus Two Thousand, felt the sudden surge of wind beneath his boots, and rocketed into the clouds.",
            "sample_2": "Fred and George Weasley didn't just leave Hogwarts; they turned the entire east wing into a swamp and flew away on brooms!"
        },
        {
            "id": "bm_fable",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "Fable — Theatrical & Wry Storyteller",
            "mood": "Expressive, witty, slightly sardonic",
            "sample_1": "Uncle Vernon truly believed that locking a young boy in a cupboard beneath the stairs would permanently cure magical talent.",
            "sample_2": "Gilderoy Lockhart was undeniably the most accomplished fraudulent author ever to charm his way into a teaching post."
        },
        {
            "id": "am_adam",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "American (US)",
            "name": "Adam — Epic Baritone Narrator",
            "mood": "Deep, commanding, cinematic power",
            "sample_1": "When the dark lord struck Godric's Hollow, a mother's ancient protection forged an impenetrable shield that defied all dark sorcery.",
            "sample_2": "The sword of Gryffindor only presents itself to a true Gryffindor in moments of supreme peril and unwavering courage."
        },
        {
            "id": "am_michael",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "American (US)",
            "name": "Michael — Documentary Analyst",
            "mood": "Clean, crisp, investigative, matter-of-fact",
            "sample_1": "Declassified records show that the wizarding prison of Azkaban was constructed on a fortress surrounded by endless freezing sea waters.",
            "sample_2": "Here is the exact magical rule: polyjuice potion allows complete physical transformation, but cannot replicate magical animagus powers."
        },
        {
            "id": "am_fenrir",
            "model": "Kokoro-82M",
            "gender": "Male",
            "accent": "American (US)",
            "name": "Fenrir — Gritty & Dark Fantasy",
            "mood": "Husky, raw, tense, atmospheric edge",
            "sample_1": "The shrieking shack groaned in the howling wind as the full moon rose above the jagged horizon of Hogsmeade.",
            "sample_2": "Dementors do not merely cause cold; they drain every happy memory from your soul until you are left with only despair."
        },
        {
            "id": "en-GB-RyanNeural",
            "model": "Edge-TTS Neural",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "Ryan — Modern British Explainer",
            "mood": "Charismatic, relatable, punchy creator",
            "sample_1": "Right then, here is the craziest thing about Peeves the Poltergeist that the movies completely robbed us of seeing.",
            "sample_2": "In the books, Harry didn't snap the Elder Wand at all; he used it to repair his original phoenix feather wand and put it back in Dumbledore's tomb!"
        },
        {
            "id": "en-GB-ThomasNeural",
            "model": "Edge-TTS Neural",
            "gender": "Male",
            "accent": "British (UK)",
            "name": "Thomas — Venerable Hogwarts Professor",
            "mood": "Wise, stately, gentle elder cadence",
            "sample_1": "Words are, in my not-so-humble opinion, our most inexhaustible source of magic, capable of both inflicting injury and remedying it.",
            "sample_2": "The Mirror of Erised shows us neither knowledge nor truth, but simply the deepest and most desperate desire of our hearts."
        },
        {
            "id": "en-IE-ConnorNeural",
            "model": "Edge-TTS Neural",
            "gender": "Male",
            "accent": "Irish (IE)",
            "name": "Connor — Celtic Lore Keeper",
            "mood": "Lyrical Irish cadence, mystical, enchanting",
            "sample_1": "Across the emerald hills of the British isles, magical creatures lived unseen alongside mortals for untold generations.",
            "sample_2": "Seamus Finnigan had an uncanny knack for pyrotechnics, but the Irish Quidditch team was renowned for pure, unbridled aerial wizardry."
        }
    ]
}


class MultiVoiceAuditionRunner:
    """Generates audition samples for 20 voices across Kokoro-82M and Edge-TTS Neural."""

    def __init__(self):
        self.output_root = MULTI_VOICE_ROOT
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.kokoro = None

    def _get_kokoro(self):
        if self.kokoro is None:
            from kokoro_onnx import Kokoro
            self.kokoro = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
        return self.kokoro

    def _apply_mastering(self, in_file: Path, out_file: Path) -> bool:
        """Applies -15.5 LUFS loudness normalization and clean 24kHz mono formatting."""
        try:
            cmd = [
                FFMPEG_EXE, "-y", "-loglevel", "error",
                "-i", str(in_file),
                "-af", "highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=2.2,loudnorm=I=-15.5:tp=-1.2:LRA=9,aformat=sample_rates=24000:channel_layouts=mono",
                str(out_file)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1000
        except Exception as e:
            logger.warning(f"Mastering error: {e}")
            return False

    def generate_kokoro(self, text: str, voice_id: str, out_wav: Path, lang: str = "en-us") -> bool:
        """Synthesizes using Kokoro-82M."""
        kokoro = self._get_kokoro()
        temp_raw = out_wav.parent / f"temp_{out_wav.name}"
        try:
            samples, sr = kokoro.create(text, voice=voice_id, speed=1.0, lang=lang)
            sf.write(str(temp_raw), samples, sr)
            if temp_raw.exists() and temp_raw.stat().st_size > 1000:
                if self._apply_mastering(temp_raw, out_wav):
                    temp_raw.unlink(missing_ok=True)
                    return True
                else:
                    temp_raw.rename(out_wav)
                    return True
        except Exception as e:
            logger.warning(f"Kokoro synthesis error for {voice_id}: {e}")
            temp_raw.unlink(missing_ok=True)
        return False

    def generate_edge(self, text: str, voice_id: str, out_wav: Path) -> bool:
        """Synthesizes using Edge-TTS Neural."""
        temp_mp3 = out_wav.parent / f"temp_{out_wav.stem}.mp3"
        try:
            import edge_tts
            async def _run():
                c = edge_tts.Communicate(text, voice_id)
                await c.save(str(temp_mp3))
            asyncio.run(_run())

            if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
                if self._apply_mastering(temp_mp3, out_wav):
                    temp_mp3.unlink(missing_ok=True)
                    return True
                else:
                    # Direct conversion
                    cmd = [FFMPEG_EXE, "-y", "-loglevel", "error", "-i", str(temp_mp3), str(out_wav)]
                    subprocess.run(cmd)
                    temp_mp3.unlink(missing_ok=True)
                    return out_wav.exists()
        except Exception as e:
            logger.warning(f"Edge-TTS synthesis error for {voice_id}: {e}")
            temp_mp3.unlink(missing_ok=True)
        return False

    def run_audition(self) -> Dict[str, Any]:
        """Generates all 40 audition samples across 20 voices."""
        results = []
        total_voices = 0
        total_samples = 0

        for gender in ["female", "male"]:
            gender_dir = self.output_root / gender
            gender_dir.mkdir(parents=True, exist_ok=True)
            voice_list = AUDITION_VOICES[gender]

            for v in voice_list:
                v_id = v["id"]
                clean_v_slug = v_id.replace("-", "_").lower()
                v_dir = gender_dir / clean_v_slug
                v_dir.mkdir(parents=True, exist_ok=True)
                total_voices += 1

                # Language detection for Kokoro
                lang = "en-gb" if v_id.startswith("b") else "en-us"

                # Sample 1 (Cinematic / Storytelling)
                out_1 = v_dir / f"{clean_v_slug}_sample_01.wav"
                ok_1 = False
                if v["model"] == "Kokoro-82M":
                    ok_1 = self.generate_kokoro(v["sample_1"], v_id, out_1, lang=lang)
                else:
                    ok_1 = self.generate_edge(v["sample_1"], v_id, out_1)

                if ok_1:
                    total_samples += 1
                    logger.info(f"[MULTI_VOICE] Generated {out_1.name} ({out_1.stat().st_size} bytes)")

                # Sample 2 (Discovery / Lore Reveal)
                out_2 = v_dir / f"{clean_v_slug}_sample_02.wav"
                ok_2 = False
                if v["model"] == "Kokoro-82M":
                    ok_2 = self.generate_kokoro(v["sample_2"], v_id, out_2, lang=lang)
                else:
                    ok_2 = self.generate_edge(v["sample_2"], v_id, out_2)

                if ok_2:
                    total_samples += 1
                    logger.info(f"[MULTI_VOICE] Generated {out_2.name} ({out_2.stat().st_size} bytes)")

                results.append({
                    "id": v_id,
                    "slug": clean_v_slug,
                    "gender": v["gender"],
                    "model": v["model"],
                    "accent": v["accent"],
                    "name": v["name"],
                    "mood": v["mood"],
                    "sample_1_file": f"{clean_v_slug}_sample_01.wav" if ok_1 else None,
                    "sample_1_text": v["sample_1"],
                    "sample_2_file": f"{clean_v_slug}_sample_02.wav" if ok_2 else None,
                    "sample_2_text": v["sample_2"],
                    "rel_dir": f"{gender}/{clean_v_slug}"
                })

        # Save metadata JSON
        meta_path = self.output_root / "multi_voice_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        # Generate HTML Player
        player_path = self.output_root / "multi_voice_player.html"
        self._generate_player_html(player_path, results)

        return {
            "total_voices": total_voices,
            "total_samples": total_samples,
            "output_directory": str(self.output_root),
            "player_html": str(player_path),
            "metadata_json": str(meta_path),
            "voices": results
        }

    def _generate_player_html(self, out_html: Path, results: List[Dict[str, Any]]) -> None:
        """Generates comprehensive audio player with filter tabs."""
        female_cards = [r for r in results if r["gender"] == "Female"]
        male_cards = [r for r in results if r["gender"] == "Male"]

        def render_section(cards):
            html = ""
            for c in cards:
                html += f"""
                <div class="voice-card">
                  <div class="card-header">
                    <div class="v-title">{c['name']}</div>
                    <div class="v-badges">
                      <span class="badge badge-model">{c['model']}</span>
                      <span class="badge badge-accent">{c['accent']}</span>
                    </div>
                  </div>
                  <div class="v-mood">🎭 {c['mood']}</div>
                  <div class="samples">
                    <div class="s-block">
                      <div class="s-label">Sample 1 (Cinematic Storytelling):</div>
                      <div class="s-text">"{c['sample_1_text']}"</div>
                      <audio controls preload="none">
                        <source src="{c['rel_dir']}/{c['sample_1_file']}" type="audio/wav">
                      </audio>
                    </div>
                    <div class="s-block">
                      <div class="s-label">Sample 2 (Discovery Lore & Secrets):</div>
                      <div class="s-text">"{c['sample_2_text']}"</div>
                      <audio controls preload="none">
                        <source src="{c['rel_dir']}/{c['sample_2_file']}" type="audio/wav">
                      </audio>
                    </div>
                  </div>
                </div>
                """
            return html

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Harry Potter Voice Audition — 20 Voices (10 Men, 10 Women)</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --gold: #d4af37;
      --accent: #8b949e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 30px 20px;
    }}
    .container {{ max-width: 1300px; margin: 0 auto; }}
    header {{
      text-align: center;
      margin-bottom: 30px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
    }}
    h1 {{ color: var(--gold); font-size: 2.2rem; margin-bottom: 8px; }}
    .sub {{ color: #8b949e; font-size: 1rem; }}
    .section-title {{
      font-size: 1.6rem;
      color: #f0f6fc;
      margin: 35px 0 15px;
      padding-left: 10px;
      border-left: 4px solid var(--gold);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(580px, 1fr));
      gap: 20px;
    }}
    .voice-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      transition: border-color 0.15s ease;
    }}
    .voice-card:hover {{ border-color: var(--gold); }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }}
    .v-title {{ font-size: 1.15rem; font-weight: 600; color: #f0f6fc; }}
    .v-badges {{ display: flex; gap: 6px; }}
    .badge {{
      font-size: 0.72rem;
      padding: 2px 7px;
      border-radius: 10px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .badge-model {{ background: #1f6feb; color: white; }}
    .badge-accent {{ background: #238636; color: white; }}
    .v-mood {{
      font-size: 0.85rem;
      color: #d29922;
      margin-bottom: 14px;
      font-style: italic;
    }}
    .samples {{ display: flex; flex-direction: column; gap: 12px; }}
    .s-block {{
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 6px;
      padding: 10px 12px;
    }}
    .s-label {{ font-size: 0.75rem; color: #8b949e; margin-bottom: 4px; font-weight: 600; }}
    .s-text {{ font-size: 0.88rem; color: #e6edf3; margin-bottom: 8px; font-style: italic; }}
    audio {{ width: 100%; height: 32px; filter: invert(0.88) hue-rotate(180deg); }}
    @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>⚡ Harry Potter Voice Audition Gallery</h1>
      <p class="sub">
        <strong>20 Distinct Voices (10 Men & 10 Women)</strong> across <strong>Kokoro-82M</strong> and <strong>Edge-TTS Neural</strong>.<br>
        Covering British, American, and Celtic accents with diverse moods and tones. All normalized to <strong>-15.5 LUFS</strong>.
      </p>
    </header>

    <h2 class="section-title">👩 10 Female Voices</h2>
    <div class="grid">
      {render_section(female_cards)}
    </div>

    <h2 class="section-title">👨 10 Male Voices</h2>
    <div class="grid">
      {render_section(male_cards)}
    </div>
  </div>
</body>
</html>
"""
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html_content)
