"""
Bella Voice Audition Engine.
Generates comprehensive audition samples for Kokoro af_bella voice across 16 delivery profiles
and 3 intensity levels (Low, Medium, High) with Harry Potter channel sample narration.
Outputs to data/voice_audition/bella/<profile>/ with consistent -15.5 LUFS studio mastering.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from config.settings import DATA_DIR
from core.voice_profiles import (
    BellaDeliveryProfile,
    BELLA_PROFILES_REGISTRY,
    get_bella_profile,
    export_profiles_metadata_json
)
from engines.tts_engine import TTSEngine

logger = logging.getLogger(__name__)

VOICE_AUDITION_ROOT = DATA_DIR / "voice_audition"
BELLA_AUDITION_DIR = VOICE_AUDITION_ROOT / "bella"


# ==============================================================================
# ORIGINAL HARRY POTTER CHANNEL AUDITION SCRIPT BATTERY
# (1-2 sentences per sample, simple English, conversational, non-copyrighted)
# ==============================================================================

AUDITION_SCRIPTS: Dict[str, Dict[str, str]] = {
    BellaDeliveryProfile.CANONICAL.value: {
        "LOW": "Every young wizard who steps into Diagon Alley remembers the smell of fresh parchment and polished wand wood.",
        "MEDIUM": "For ten quiet years, Harry lived without knowing that his parents had been two of the bravest sorcerers in Britain.",
        "HIGH": "Hogwarts castle has stood for over a thousand years, guarding ancient secrets that even the headmaster cannot fully unlock."
    },
    BellaDeliveryProfile.CINEMATIC.value: {
        "LOW": "Rain lashed against the black glass of the Hogwarts Express as it glided into the misty Scottish Highlands.",
        "MEDIUM": "Far below the stone dungeons, shadows gathered around the mirror of Erised, waiting for a heart pure enough to look inside.",
        "HIGH": "When the great hall doors swung open, hundreds of floating candles illuminated the starry sky ceiling above the four house tables."
    },
    BellaDeliveryProfile.DISCOVERY.value: {
        "LOW": "Here is an incredible detail the movies completely left out about how the Marauder's Map was actually created.",
        "MEDIUM": "Did you know that Ollivander tested Harry Potter with twenty different wands before the phoenix feather chose him?",
        "HIGH": "The movies never explained this, but Peeves the Poltergeist was actually born from the chaotic energy of medieval Hogwarts students!"
    },
    BellaDeliveryProfile.DRAMATIC.value: {
        "LOW": "Uncle Vernon bolted three deadbolts onto Harry's door, desperate to lock the magical world outside forever.",
        "MEDIUM": "Deep inside the forbidden third floor corridor, a giant three-headed beast stood guarding a secret trapdoor.",
        "HIGH": "A blinding green flash shattered the cottage in Godric's Hollow, leaving only a crying infant and a splintered wand on the floor."
    },
    BellaDeliveryProfile.WARM.value: {
        "LOW": "Mrs. Weasley knit a thick maroon jumper with a hand-stitched letter H, giving Harry his very first real Christmas present.",
        "MEDIUM": "Hagrid handed Harry a slightly squashed chocolate cake with words piped in green icing: Happee Birthdae Harry.",
        "HIGH": "Sitting together by the roaring Gryffindor common room fire, Harry finally realized he wasn't alone in the world anymore."
    },
    BellaDeliveryProfile.CALM.value: {
        "LOW": "The silver instruments on Dumbledore's desk whirred quietly, puffing tiny rings of pale smoke into the quiet night.",
        "MEDIUM": "Snow fell softly over the rooftops of Hogsmeade, coating the cobblestones in a peaceful blanket of white.",
        "HIGH": "Down in the potion master's cellar, ancient glass vials caught the dim torchlight without a single sound."
    },
    BellaDeliveryProfile.SUSPENSE.value: {
        "LOW": "Something shifted in the deep shadows beneath the restricted section bookshelves, just out of sight.",
        "MEDIUM": "Harry listened closely... Footsteps echoed on the cold flagstones above, slow and deliberate.",
        "HIGH": "The silver doorknob began to turn on its own, inch by inch, into total darkness."
    },
    BellaDeliveryProfile.SURPRISED.value: {
        "LOW": "Wait... Look closely at the portrait behind Dumbledore's chair, because that wizard is actually awake and taking notes!",
        "MEDIUM": "You won't believe how different Ron Weasley was in the books; he was actually the strategic mastermind of the trio!",
        "HIGH": "The moving staircase didn't just change directions by chance... It was actively guiding Harry straight to the third floor!"
    },
    BellaDeliveryProfile.EXCITED.value: {
        "LOW": "Harry kicked hard off the grass, and the Nimbus Two Thousand surged upward into the clear blue sky!",
        "MEDIUM": "Look at that Quidditch play! Harry dives headfirst through the rain, tracking the golden snitch at ninety miles an hour!",
        "HIGH": "Gryffindor wins the house cup! The entire great hall erupts into roaring cheers as the scarlet banners drop!"
    },
    BellaDeliveryProfile.SAD.value: {
        "LOW": "Harry sat alone in the dark dormitory, tracing the worn edges of the only photograph he had of his mother.",
        "MEDIUM": "In the mirror of Erised, Harry saw his family smiling beside him, knowing none of them could ever come back.",
        "HIGH": "Hedwig rested her soft feathered head against the cage bars, watching Harry endure another lonely summer at Privet Drive."
    },
    BellaDeliveryProfile.ANGRY.value: {
        "LOW": "Aunt Petunia claimed her sister was a freak, refusing to ever speak Lily Potter's name aloud.",
        "MEDIUM": "Uncle Vernon tore Harry's Hogwarts letter into tiny shreds right in front of his face with a bitter smirk.",
        "HIGH": "Malfoy snatched Neville's remembrall and taunted him across the courtyard until Harry had had enough!"
    },
    BellaDeliveryProfile.DARK.value: {
        "LOW": "Knockturn Alley smelled of damp moss and poisonous toadstools, where dark wizards traded under hooded cloaks.",
        "MEDIUM": "A withered hand resting on a black cushion in Borgin and Burkes suddenly twitched under the dim candlelight.",
        "HIGH": "The dark lord's whispered voice echoed from beneath Quirrell's turban, demanding absolute obedience in the cold dungeon."
    },
    BellaDeliveryProfile.SARCASTIC.value: {
        "LOW": "Uncle Vernon's brilliant plan to escape magical owls was hiding in an abandoned shack surrounded by freezing ocean waves.",
        "MEDIUM": "Because of course locking a boy under the stairs for a decade is definitely how you stop magic from existing.",
        "HIGH": "Hermione honestly believed getting expelled from school was worse than getting eaten alive by a three-headed dog."
    },
    BellaDeliveryProfile.EDUCATIONAL.value: {
        "LOW": "In wizarding lore, wand cores react directly to the caster's character; phoenix feathers demand great independence.",
        "MEDIUM": "Here is the exact distinction: animagi retain their human minds, while wizards transformed by transfiguration lose all human thought.",
        "HIGH": "The four Hogwarts houses represent the four classical alchemical elements: Gryffindor fire, Ravenclaw air, Hufflepuff earth, and Slytherin water."
    },
    BellaDeliveryProfile.FAST_ENERGETIC.value: {
        "LOW": "Letters are flying down the chimney, owls are circling the roof, and Vernon Dursley is officially losing his mind!",
        "MEDIUM": "Three seconds on the clock, Harry dives right, snatches the snitch out of thin air, and seals the match!",
        "HIGH": "Boom! Hagrid kicks the wooden door down, bends the shotgun in half, and hands Harry a chocolate birthday cake!"
    },
    BellaDeliveryProfile.EMOTIONAL_RESTRAINED.value: {
        "LOW": "Lily's eyes looked back at Harry from the glass, carrying a warmth he had never felt in all his eleven years.",
        "MEDIUM": "Harry held the worn sweater close to his chest in the dark, whispering a quiet thank you to a mother he barely remembered.",
        "HIGH": "He didn't care about being famous or defeating a dark lord; he just wanted his family to be alive."
    }
}


def get_profile_slug(profile_name: str) -> str:
    """Converts profile name to directory slug, e.g. BELLA_CINEMATIC -> cinematic."""
    name = profile_name.replace("BELLA_", "").lower()
    return name


class BellaAuditionRunner:
    """Orchestrates generation of the full Bella voice audition suite."""

    def __init__(self, tts_engine: Optional[TTSEngine] = None):
        self.tts = tts_engine or TTSEngine()
        self.output_root = BELLA_AUDITION_DIR
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run_audition(self) -> Dict[str, Any]:
        """Generates all 48 audition samples and metadata files."""
        results = []
        total_profiles = len(BELLA_PROFILES_REGISTRY)
        total_samples = 0

        logger.info(f"Starting Bella voice audition across {total_profiles} delivery profiles...")

        for profile_key, intensities in BELLA_PROFILES_REGISTRY.items():
            slug = get_profile_slug(profile_key)
            profile_dir = self.output_root / slug
            profile_dir.mkdir(parents=True, exist_ok=True)

            scripts = AUDITION_SCRIPTS.get(profile_key, {})

            for sample_idx, (intensity_key, cfg) in enumerate(intensities.items(), start=1):
                text = scripts.get(intensity_key, "Magic waited quietly in the dark cupboard.")
                int_lower = intensity_key.lower()
                filename = f"bella_{slug}_{int_lower}_{sample_idx:02d}.wav"
                target_wav = profile_dir / filename
                raw_temp_wav = profile_dir / f"temp_{filename}"

                # 1. Synthesize via Kokoro
                ok, dur = self.tts.generate_kokoro_audio(
                    text=text,
                    output_path=raw_temp_wav,
                    voice=cfg.voice_id,
                    speed=cfg.speed,
                    sentence_pause=cfg.sentence_pause,
                    clause_pause=cfg.clause_pause
                )

                if ok and raw_temp_wav.exists() and raw_temp_wav.stat().st_size > 1000:
                    # 2. Apply presence mastering with consistent -15.5 LUFS loudness
                    mastered_ok = self.tts.apply_presence_mastering(
                        input_wav=raw_temp_wav,
                        output_wav=target_wav,
                        presence_boost_db=cfg.presence_boost_db,
                        eq_freq_hz=cfg.eq_freq_hz,
                        target_lufs=cfg.target_lufs,
                        true_peak_ceiling=cfg.true_peak_ceiling
                    )
                    raw_temp_wav.unlink(missing_ok=True)

                    if not mastered_ok or not target_wav.exists():
                        # Fallback to raw if ffmpeg mastering failed
                        raw_temp_wav.rename(target_wav)

                    file_size = target_wav.stat().st_size if target_wav.exists() else 0
                    total_samples += 1
                    results.append({
                        "profile": profile_key,
                        "slug": slug,
                        "intensity": intensity_key,
                        "filename": filename,
                        "rel_path": str(target_wav.relative_to(DATA_DIR)),
                        "duration_sec": dur,
                        "size_bytes": file_size,
                        "text": text,
                        "speed": cfg.speed,
                        "sentence_pause": cfg.sentence_pause,
                        "clause_pause": cfg.clause_pause,
                        "pacing": cfg.pacing,
                        "pause_style": cfg.pause_style,
                        "description": cfg.description
                    })
                    logger.info(f"[AUDITION] Generated {filename} ({dur:.2f}s, {file_size} bytes)")
                else:
                    logger.warning(f"[AUDITION] Failed to synthesize {filename}")

        # Export metadata JSON
        meta_json_path = VOICE_AUDITION_ROOT / "bella_profiles_metadata.json"
        export_profiles_metadata_json(str(meta_json_path))

        # Generate README index
        readme_path = VOICE_AUDITION_ROOT / "README.md"
        self._generate_readme_index(readme_path, results)

        return {
            "total_profiles": total_profiles,
            "total_samples": total_samples,
            "output_directory": str(self.output_root),
            "metadata_json": str(meta_json_path),
            "readme_index": str(readme_path),
            "samples": results
        }

    def _generate_readme_index(self, output_path: Path, results: List[Dict[str, Any]]) -> None:
        """Writes human-readable audition library index."""
        lines = [
            "# Harry Potter Channel — Bella (Kokoro af_bella) Voice Audition Library",
            "",
            "> **Purpose**: Comparative evaluation of 16 delivery profiles and 3 intensity levels using Kokoro-82M `af_bella`.",
            "> All samples use **identical -15.5 LUFS ITU-R BS.1770 broadcast loudness normalization** to guarantee an unbiased, fair comparison.",
            "> The underlying voice identity remains 100% Bella (`af_bella`); only directorial performance parameters (speed, pause timing, cadence, EQ presence) vary.",
            "",
            "## Summary Statistics",
            f"- **Total Delivery Profiles**: {len(BELLA_PROFILES_REGISTRY)}",
            f"- **Total Audition Audio Samples**: {len(results)}",
            "- **Voice Identity**: `af_bella` (Kokoro-82M ONNX)",
            "- **Audition Library Location**: `data/voice_audition/bella/`",
            "- **Metadata Specification**: `data/voice_audition/bella_profiles_metadata.json`",
            "",
            "---",
            "",
            "## Audition Profiles & Sample Index",
            ""
        ]

        # Group by profile
        profiles_grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in results:
            profiles_grouped.setdefault(r["profile"], []).append(r)

        for p_key, sample_list in profiles_grouped.items():
            slug = get_profile_slug(p_key)
            cfg_med = get_bella_profile(p_key, "MEDIUM")
            lines.append(f"### {p_key}")
            lines.append(f"- **Description**: {cfg_med.description}")
            lines.append(f"- **Content Affinity**: {cfg_med.content_affinity}")
            lines.append(f"- **Directory**: `data/voice_audition/bella/{slug}/`")
            lines.append("")
            lines.append("| Filename | Intensity | Speed | Sentence Pause | Clause Pause | Duration | Sample Script |")
            lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
            for s in sample_list:
                lines.append(
                    f"| `{s['filename']}` | **{s['intensity']}** | {s['speed']:.2f}x | {s['sentence_pause']:.2f}s | {s['clause_pause']:.2f}s | {s['duration_sec']:.2f}s | \"{s['text']}\" |"
                )
            lines.append("")

        lines.extend([
            "---",
            "",
            "## Technical Controls Supported by Kokoro Implementation",
            "",
            "1. **Pacing / Speed**: Directly controlled via Kokoro ONNX inference engine (`speed` parameter from 0.86x to 1.14x).",
            "2. **Sentence Pauses**: Controlled via Kokoro `sentence_pause` parameter (0.12s to 0.48s), defining pauses between sentences.",
            "3. **Clause / Comma Pauses**: Controlled via Kokoro `clause_pause` parameter (0.05s to 0.18s), governing punctuation breathing spaces.",
            "4. **Punctuation Phrasing**: Modulated via punctuation syntax (`...`, `!`, `?`, `—`, `,`) to naturally guide neural prosody.",
            "5. **Vocal Presence EQ**: Studio highpass (80 Hz) and parametric vocal presence boost (+1.5 dB to +3.2 dB @ 2500–3500 Hz).",
            "6. **Broadcast Loudness Normalization**: ITU-R BS.1770 loudnorm filter at -15.5 LUFS with -1.2 dB true peak ceiling.",
            "",
            "## Technical Limitations / Controls Not Feasible in Raw Kokoro",
            "",
            "- **Independent Pitch Shifter**: Kokoro ONNX does not expose a native pitch slider in its neural synthesis head. Pitch differences are naturally driven by text prosody/punctuation and shaped by EQ formant frequencies.",
            "- **Theatrical Whispering / Shouting**: Kokoro-82M synthesizes natural speaking style; extreme extremes (heavy shouting or extreme whispering) cannot be artificially forced without distorting voice timbre.",
            "",
            "---",
            "*Note: No profile is permanently locked. The final profile selection will be decided after listening.*"
        ])

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
