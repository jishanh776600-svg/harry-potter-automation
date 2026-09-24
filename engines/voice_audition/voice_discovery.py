"""
STORY FORGE — Voice Discovery Service
================================================================================
Discovers available voices from configured TTS providers (Kokoro-82M ONNX and
Edge-TTS Neural), categorizes them into male and female, filters out duplicates,
and assembles an exact 30 Male + 30 Female (60 total) audition lineup.
"""

import asyncio
import logging
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

from core.voice_audition_types import VoiceCandidate
from config.settings import KOKORO_MODEL_PATH, KOKORO_VOICES_PATH

logger = logging.getLogger("VoiceDiscoveryService")


# Curated catalog of Kokoro-82M ONNX English voices with precise metadata
KOKORO_ENGLISH_VOICES = {
    # American Males (9)
    "am_adam": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Calm, narrative"},
    "am_echo": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Resonant, deep"},
    "am_eric": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Dynamic, clear"},
    "am_fenrir": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Gravelly, dramatic"},
    "am_liam": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Youthful, energetic"},
    "am_michael": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Authoritative, announcer"},
    "am_onyx": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Rich, baritone"},
    "am_puck": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Playful, animated"},
    "am_santa": {"gender": "male", "locale": "en-US", "accent": "American", "style": "Warm, booming"},
    # British Males (4)
    "bm_daniel": {"gender": "male", "locale": "en-GB", "accent": "British", "style": "Formal, documentary"},
    "bm_fable": {"gender": "male", "locale": "en-GB", "accent": "British", "style": "Theatrical storyteller"},
    "bm_george": {"gender": "male", "locale": "en-GB", "accent": "British", "style": "Classic British, refined"},
    "bm_lewis": {"gender": "male", "locale": "en-GB", "accent": "British", "style": "Crisp, factual"},
    # American Females (11)
    "af_bella": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Cinematic storyteller"},
    "af_sarah": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Conversational, clear"},
    "af_alloy": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Modern, balanced"},
    "af_aoede": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Melodic, lyrical"},
    "af_heart": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Warm, intimate"},
    "af_jessica": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Engaging, bright"},
    "af_kore": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Crisp, articulate"},
    "af_nicole": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Professional, smooth"},
    "af_nova": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Energetic, upbeat"},
    "af_river": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Relaxed, natural"},
    "af_sky": {"gender": "female", "locale": "en-US", "accent": "American", "style": "Airy, gentle"},
    # British Females (4)
    "bf_alice": {"gender": "female", "locale": "en-GB", "accent": "British", "style": "Aristocratic, composed"},
    "bf_emma": {"gender": "female", "locale": "en-GB", "accent": "British", "style": "Expressive British narrator"},
    "bf_isabella": {"gender": "female", "locale": "en-GB", "accent": "British", "style": "Sophisticated, warm"},
    "bf_lily": {"gender": "female", "locale": "en-GB", "accent": "British", "style": "Youthful British"},
}


# Curated authoritative catalog of Edge-TTS English neural voices for offline determinism
EDGE_ENGLISH_VOICES = {
    # Males (23)
    "en-US-AndrewNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Andrew Online (Natural) - English (United States)"},
    "en-US-BrianNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Brian Online (Natural) - English (United States)"},
    "en-US-ChristopherNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Christopher Online (Natural) - English (United States)"},
    "en-US-EricNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Eric Online (Natural) - English (United States)"},
    "en-US-GuyNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Guy Online (Natural) - English (United States)"},
    "en-US-RogerNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Roger Online (Natural) - English (United States)"},
    "en-US-SteffanNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Steffan Online (Natural) - English (United States)"},
    "en-US-AndrewMultilingualNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Andrew Multilingual Online (Natural) - English (United States)"},
    "en-US-BrianMultilingualNeural": {"gender": "male", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Brian Multilingual Online (Natural) - English (United States)"},
    "en-GB-RyanNeural": {"gender": "male", "locale": "en-GB", "accent": "British", "friendly_name": "Microsoft Ryan Online (Natural) - English (United Kingdom)"},
    "en-GB-ThomasNeural": {"gender": "male", "locale": "en-GB", "accent": "British", "friendly_name": "Microsoft Thomas Online (Natural) - English (United Kingdom)"},
    "en-AU-WilliamMultilingualNeural": {"gender": "male", "locale": "en-AU", "accent": "Australian", "friendly_name": "Microsoft William Multilingual Online (Natural) - English (Australia)"},
    "en-CA-LiamNeural": {"gender": "male", "locale": "en-CA", "accent": "Canadian", "friendly_name": "Microsoft Liam Online (Natural) - English (Canada)"},
    "en-IE-ConnorNeural": {"gender": "male", "locale": "en-IE", "accent": "Irish", "friendly_name": "Microsoft Connor Online (Natural) - English (Ireland)"},
    "en-NZ-MitchellNeural": {"gender": "male", "locale": "en-NZ", "accent": "New Zealand", "friendly_name": "Microsoft Mitchell Online (Natural) - English (New Zealand)"},
    "en-ZA-LukeNeural": {"gender": "male", "locale": "en-ZA", "accent": "South African", "friendly_name": "Microsoft Luke Online (Natural) - English (South Africa)"},
    "en-IN-PrabhatNeural": {"gender": "male", "locale": "en-IN", "accent": "Indian", "friendly_name": "Microsoft Prabhat Online (Natural) - English (India)"},
    "en-SG-WayneNeural": {"gender": "male", "locale": "en-SG", "accent": "Singapore", "friendly_name": "Microsoft Wayne Online (Natural) - English (Singapore)"},
    "en-PH-JamesNeural": {"gender": "male", "locale": "en-PH", "accent": "Philippines", "friendly_name": "Microsoft James Online (Natural) - English (Philippines)"},
    "en-HK-SamNeural": {"gender": "male", "locale": "en-HK", "accent": "Hong Kong", "friendly_name": "Microsoft Sam Online (Natural) - English (Hong Kong)"},
    "en-KE-ChilembaNeural": {"gender": "male", "locale": "en-KE", "accent": "Kenya", "friendly_name": "Microsoft Chilemba Online (Natural) - English (Kenya)"},
    "en-NG-AbeoNeural": {"gender": "male", "locale": "en-NG", "accent": "Nigeria", "friendly_name": "Microsoft Abeo Online (Natural) - English (Nigeria)"},
    "en-TZ-ElimuNeural": {"gender": "male", "locale": "en-TZ", "accent": "Tanzania", "friendly_name": "Microsoft Elimu Online (Natural) - English (Tanzania)"},
    # Females (24)
    "en-US-AvaNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Ava Online (Natural) - English (United States)"},
    "en-US-EmmaNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Emma Online (Natural) - English (United States)"},
    "en-US-JennyNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Jenny Online (Natural) - English (United States)"},
    "en-US-AnaNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Ana Online (Natural) - English (United States)"},
    "en-US-AriaNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Aria Online (Natural) - English (United States)"},
    "en-US-MichelleNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Michelle Online (Natural) - English (United States)"},
    "en-US-AvaMultilingualNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Ava Multilingual Online (Natural) - English (United States)"},
    "en-US-EmmaMultilingualNeural": {"gender": "female", "locale": "en-US", "accent": "American", "friendly_name": "Microsoft Emma Multilingual Online (Natural) - English (United States)"},
    "en-GB-LibbyNeural": {"gender": "female", "locale": "en-GB", "accent": "British", "friendly_name": "Microsoft Libby Online (Natural) - English (United Kingdom)"},
    "en-GB-MaisieNeural": {"gender": "female", "locale": "en-GB", "accent": "British", "friendly_name": "Microsoft Maisie Online (Natural) - English (United Kingdom)"},
    "en-GB-SoniaNeural": {"gender": "female", "locale": "en-GB", "accent": "British", "friendly_name": "Microsoft Sonia Online (Natural) - English (United Kingdom)"},
    "en-AU-NatashaNeural": {"gender": "female", "locale": "en-AU", "accent": "Australian", "friendly_name": "Microsoft Natasha Online (Natural) - English (Australia)"},
    "en-CA-ClaraNeural": {"gender": "female", "locale": "en-CA", "accent": "Canadian", "friendly_name": "Microsoft Clara Online (Natural) - English (Canada)"},
    "en-IE-EmilyNeural": {"gender": "female", "locale": "en-IE", "accent": "Irish", "friendly_name": "Microsoft Emily Online (Natural) - English (Ireland)"},
    "en-NZ-MollyNeural": {"gender": "female", "locale": "en-NZ", "accent": "New Zealand", "friendly_name": "Microsoft Molly Online (Natural) - English (New Zealand)"},
    "en-ZA-LeahNeural": {"gender": "female", "locale": "en-ZA", "accent": "South African", "friendly_name": "Microsoft Leah Online (Natural) - English (South Africa)"},
    "en-IN-NeerjaExpressiveNeural": {"gender": "female", "locale": "en-IN", "accent": "Indian", "friendly_name": "Microsoft Neerja Expressive Online (Natural) - English (India)"},
    "en-IN-NeerjaNeural": {"gender": "female", "locale": "en-IN", "accent": "Indian", "friendly_name": "Microsoft Neerja Online (Natural) - English (India)"},
    "en-SG-LunaNeural": {"gender": "female", "locale": "en-SG", "accent": "Singapore", "friendly_name": "Microsoft Luna Online (Natural) - English (Singapore)"},
    "en-PH-RosaNeural": {"gender": "female", "locale": "en-PH", "accent": "Philippines", "friendly_name": "Microsoft Rosa Online (Natural) - English (Philippines)"},
    "en-HK-YanNeural": {"gender": "female", "locale": "en-HK", "accent": "Hong Kong", "friendly_name": "Microsoft Yan Online (Natural) - English (Hong Kong)"},
    "en-KE-AsiliaNeural": {"gender": "female", "locale": "en-KE", "accent": "Kenya", "friendly_name": "Microsoft Asilia Online (Natural) - English (Kenya)"},
    "en-NG-EzinneNeural": {"gender": "female", "locale": "en-NG", "accent": "Nigeria", "friendly_name": "Microsoft Ezinne Online (Natural) - English (Nigeria)"},
    "en-TZ-ImaniNeural": {"gender": "female", "locale": "en-TZ", "accent": "Tanzania", "friendly_name": "Microsoft Imani Online (Natural) - English (Tanzania)"},
}


class VoiceDiscoveryService:
    """
    Discovers, filters, and standardizes available TTS voices from the platform.
    """

    def __init__(self, include_kokoro: bool = True, include_edge: bool = True):
        self.include_kokoro = include_kokoro
        self.include_edge = include_edge

    def discover_kokoro_voices(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Discovers valid English voices available from Kokoro ONNX."""
        males = []
        females = []

        if not self.include_kokoro:
            return males, females

        if not (KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists()):
            logger.info("Kokoro ONNX files not found locally, checking internal voice table.")

        for voice_id, meta in KOKORO_ENGLISH_VOICES.items():
            entry = {
                "voice_id": voice_id,
                "provider": "Kokoro-82M ONNX",
                "model": "kokoro-v1.0",
                "locale": meta["locale"],
                "accent": meta["accent"],
                "gender": meta["gender"],
                "config": {"style": meta["style"], "engine": "kokoro"},
            }
            if meta["gender"] == "male":
                males.append(entry)
            else:
                females.append(entry)

        return males, females

    def discover_edge_voices(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Discovers valid English voices available from Edge-TTS (with offline catalog fallback)."""
        males = []
        females = []

        if not self.include_edge:
            return males, females

        # First populate from authoritative static catalog
        for voice_id, meta in EDGE_ENGLISH_VOICES.items():
            entry = {
                "voice_id": voice_id,
                "provider": "Edge-TTS Neural",
                "model": "ms-edge-neural",
                "locale": meta["locale"],
                "accent": meta["accent"],
                "gender": meta["gender"],
                "config": {"friendly_name": meta.get("friendly_name", ""), "engine": "edge_tts"},
            }
            if meta["gender"] == "male":
                males.append(entry)
            else:
                females.append(entry)

        # Optionally attempt live query if reachable without error
        try:
            import edge_tts
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            voices = loop.run_until_complete(edge_tts.list_voices())
            en_voices = [v for v in voices if v.get("Locale", "").startswith("en-")]
            if en_voices:
                # Augment or refresh if live call succeeded
                live_males = []
                live_females = []
                for v in en_voices:
                    voice_id = v.get("ShortName", "")
                    gender = v.get("Gender", "").lower()
                    locale = v.get("Locale", "en-US")
                    accent = "American" if locale == "en-US" else (
                        "British" if locale == "en-GB" else (
                            "Australian" if locale == "en-AU" else (
                                "Canadian" if locale == "en-CA" else (
                                    "Irish" if locale == "en-IE" else (
                                        "New Zealand" if locale == "en-NZ" else (
                                            "Indian" if locale == "en-IN" else (
                                                "South African" if locale == "en-ZA" else "International English"
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                    entry = {
                        "voice_id": voice_id,
                        "provider": "Edge-TTS Neural",
                        "model": "ms-edge-neural",
                        "locale": locale,
                        "accent": accent,
                        "gender": gender,
                        "config": {"friendly_name": v.get("FriendlyName", ""), "engine": "edge_tts"},
                    }
                    if gender == "male":
                        live_males.append(entry)
                    elif gender == "female":
                        live_females.append(entry)
                if live_males and live_females:
                    males, females = live_males, live_females
        except Exception as e:
            logger.debug(f"Offline test environment or network restricted, using authoritative Edge catalog: {e}")

        return males, females

    def build_lineup(
        self,
        target_males: int = 30,
        target_females: int = 30
    ) -> Tuple[List[VoiceCandidate], int, int]:
        """
        Builds the ordered audition lineup of exactly target_males + target_females.
        Ensures 100% distinct voice IDs.
        Gracefully handles scenarios where fewer voices exist.
        """
        k_males, k_females = self.discover_kokoro_voices()
        e_males, e_females = self.discover_edge_voices()

        # Combine and deduplicate
        all_male_pool = []
        seen_male_ids = set()
        for m in k_males + e_males:
            vid = m["voice_id"]
            if vid not in seen_male_ids:
                seen_male_ids.add(vid)
                all_male_pool.append(m)

        all_female_pool = []
        seen_female_ids = set()
        for f in k_females + e_females:
            vid = f["voice_id"]
            if vid not in seen_female_ids:
                seen_female_ids.add(vid)
                all_female_pool.append(f)

        selected_males = all_male_pool[:target_males]
        selected_females = all_female_pool[:target_females]

        lineup: List[VoiceCandidate] = []

        # 1. Add Males (Numbers 1 to len(selected_males))
        for idx, m in enumerate(selected_males, start=1):
            label = f"MALE {idx:02d}"
            candidate = VoiceCandidate(
                number=idx,
                label=label,
                category="male",
                voice_id=m["voice_id"],
                provider=m["provider"],
                model=m["model"],
                locale=m["locale"],
                accent=m["accent"],
                config=m.get("config", {}),
            )
            lineup.append(candidate)

        # 2. Add Females (Numbers len(selected_males)+1 to total)
        female_start_num = len(selected_males) + 1
        for idx, f in enumerate(selected_females, start=1):
            num = female_start_num + (idx - 1)
            label = f"FEMALE {idx:02d}"
            candidate = VoiceCandidate(
                number=num,
                label=label,
                category="female",
                voice_id=f["voice_id"],
                provider=f["provider"],
                model=f["model"],
                locale=f["locale"],
                accent=f["accent"],
                config=f.get("config", {}),
            )
            lineup.append(candidate)

        return lineup, len(selected_males), len(selected_females)
