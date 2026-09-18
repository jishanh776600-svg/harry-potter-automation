"""
Bella Voice Delivery Profiles & Directorial Architecture.
Defines 16 distinct delivery profiles for Kokoro af_bella voice in the Harry Potter automation channel.
Supports Low, Medium, High intensity levels with controlled pacing, pause styles, and presence mastering.
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional
import json


class BellaDeliveryProfile(str, Enum):
    CANONICAL = "BELLA_CANONICAL"
    CINEMATIC = "BELLA_CINEMATIC"
    DISCOVERY = "BELLA_DISCOVERY"
    DRAMATIC = "BELLA_DRAMATIC"
    WARM = "BELLA_WARM"
    CALM = "BELLA_CALM"
    SUSPENSE = "BELLA_SUSPENSE"
    SURPRISED = "BELLA_SURPRISED"
    EXCITED = "BELLA_EXCITED"
    SAD = "BELLA_SAD"
    ANGRY = "BELLA_ANGRY"
    DARK = "BELLA_DARK"
    SARCASTIC = "BELLA_SARCASTIC"
    EDUCATIONAL = "BELLA_EDUCATIONAL"
    FAST_ENERGETIC = "BELLA_FAST_ENERGETIC"
    EMOTIONAL_RESTRAINED = "BELLA_EMOTIONAL_RESTRAINED"


class IntensityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class BellaProfileConfig:
    profile_id: str
    display_name: str
    voice_id: str = "af_bella"
    intensity: str = "MEDIUM"
    speed: float = 1.00
    sentence_pause: float = 0.25
    clause_pause: float = 0.09
    pacing: str = "moderate"
    pause_style: str = "natural"
    emphasis: str = "moderate"
    pitch_energy_direction: str = "BALANCED"
    presence_boost_db: float = 2.2
    eq_freq_hz: int = 3000
    target_lufs: float = -15.5
    true_peak_ceiling: float = -1.2
    description: str = ""
    content_affinity: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 16 AUDITION DELIVERY PROFILES MATRIX (CONFIGURABLE PRESETS)
# ==============================================================================

BELLA_PROFILES_REGISTRY: Dict[str, Dict[str, BellaProfileConfig]] = {
    BellaDeliveryProfile.CANONICAL.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_CANONICAL",
            display_name="Bella Canonical (Low)",
            intensity="LOW",
            speed=0.98,
            sentence_pause=0.28,
            clause_pause=0.10,
            pacing="relaxed",
            pause_style="natural",
            emphasis="subtle",
            pitch_energy_direction="CALM",
            presence_boost_db=1.8,
            eq_freq_hz=3000,
            description="Natural baseline narration: conversational, relaxed, clear articulation.",
            content_affinity="General introductions, baseline storytelling"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_CANONICAL",
            display_name="Bella Canonical (Medium)",
            intensity="MEDIUM",
            speed=1.00,
            sentence_pause=0.25,
            clause_pause=0.09,
            pacing="moderate",
            pause_style="natural",
            emphasis="moderate",
            pitch_energy_direction="BALANCED",
            presence_boost_db=2.2,
            eq_freq_hz=3000,
            description="Natural baseline narration: balanced conversational flow with clear neutral cadence.",
            content_affinity="Standard channel voiceover, balanced storytelling"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_CANONICAL",
            display_name="Bella Canonical (High)",
            intensity="HIGH",
            speed=1.02,
            sentence_pause=0.22,
            clause_pause=0.08,
            pacing="brisk",
            pause_style="tight",
            emphasis="assertive",
            pitch_energy_direction="ELEVATED",
            presence_boost_db=2.5,
            eq_freq_hz=3000,
            description="Natural baseline narration: crisp, assertive, elevated mobile clarity.",
            content_affinity="Engaging openers, direct narrative exposition"
        )
    },

    BellaDeliveryProfile.CINEMATIC.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_CINEMATIC",
            display_name="Bella Cinematic (Low)",
            intensity="LOW",
            speed=0.96,
            sentence_pause=0.32,
            clause_pause=0.12,
            pacing="measured",
            pause_style="controlled",
            emphasis="moderate",
            pitch_energy_direction="WARM",
            presence_boost_db=2.0,
            eq_freq_hz=2800,
            description="Cinematic storytelling: smooth, immersive, gentle emotional warmth.",
            content_affinity="Novel setting descriptions, atmospheric scenery"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_CINEMATIC",
            display_name="Bella Cinematic (Medium)",
            intensity="MEDIUM",
            speed=0.94,
            sentence_pause=0.35,
            clause_pause=0.14,
            pacing="deliberate",
            pause_style="cinematic_hold",
            emphasis="controlled",
            pitch_energy_direction="BALANCED",
            presence_boost_db=2.4,
            eq_freq_hz=2800,
            description="Cinematic storytelling: controlled emotion, rich depth, cinematic pauses.",
            content_affinity="Novel story arcs, epic wizarding lore, high-production storytelling"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_CINEMATIC",
            display_name="Bella Cinematic (High)",
            intensity="HIGH",
            speed=0.92,
            sentence_pause=0.40,
            clause_pause=0.15,
            pacing="slow_dramatic",
            pause_style="pregnant_pause",
            emphasis="profound",
            pitch_energy_direction="INTENSE",
            presence_boost_db=2.8,
            eq_freq_hz=2800,
            description="Cinematic storytelling: deep immersion, profound weight, majestic cinematic gravity.",
            content_affinity="Climax moments, magical revelations, iconic novel scenes"
        )
    },

    BellaDeliveryProfile.DISCOVERY.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_DISCOVERY",
            display_name="Bella Discovery (Low)",
            intensity="LOW",
            speed=1.00,
            sentence_pause=0.24,
            clause_pause=0.09,
            pacing="moderate",
            pause_style="informative",
            emphasis="moderate",
            pitch_energy_direction="CURIOUS",
            presence_boost_db=2.0,
            eq_freq_hz=3200,
            description="Curiosity narration: quiet intrigue, informative revelation.",
            content_affinity="Subtle book vs movie differences, background trivia"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_DISCOVERY",
            display_name="Bella Discovery (Medium)",
            intensity="MEDIUM",
            speed=1.03,
            sentence_pause=0.20,
            clause_pause=0.08,
            pacing="brisk",
            pause_style="reveal_hook",
            emphasis="pointed",
            pitch_energy_direction="ELEVATED",
            presence_boost_db=2.4,
            eq_freq_hz=3200,
            description="Curiosity narration: engaging reveal, slight excitement, brisk explanatory pace.",
            content_affinity="Things movies didn't explain, magical artifact secrets"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_DISCOVERY",
            display_name="Bella Discovery (High)",
            intensity="HIGH",
            speed=1.06,
            sentence_pause=0.18,
            clause_pause=0.07,
            pacing="punchy",
            pause_style="tight_reveal",
            emphasis="visceral_curiosity",
            pitch_energy_direction="HIGH_ENERGY",
            presence_boost_db=2.8,
            eq_freq_hz=3300,
            description="Curiosity narration: intense discovery energy, sharp revelation hooks.",
            content_affinity="Mind-blowing lore revelations, overlooked canon secrets"
        )
    },

    BellaDeliveryProfile.DRAMATIC.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_DRAMATIC",
            display_name="Bella Dramatic (Low)",
            intensity="LOW",
            speed=0.95,
            sentence_pause=0.30,
            clause_pause=0.12,
            pacing="measured",
            pause_style="suspenseful",
            emphasis="firm",
            pitch_energy_direction="TENSE",
            presence_boost_db=2.2,
            eq_freq_hz=2900,
            description="Dramatic narration: controlled tension, serious narrative weight.",
            content_affinity="Rising tension, conflict development"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_DRAMATIC",
            display_name="Bella Dramatic (Medium)",
            intensity="MEDIUM",
            speed=0.92,
            sentence_pause=0.36,
            clause_pause=0.14,
            pacing="deliberate",
            pause_style="dramatic_hold",
            emphasis="strong",
            pitch_energy_direction="INTENSE",
            presence_boost_db=2.6,
            eq_freq_hz=2900,
            description="Dramatic narration: strong emotional impact, palpable tension, restrained power.",
            content_affinity="Crucial story turning points, confrontations, grave peril"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_DRAMATIC",
            display_name="Bella Dramatic (High)",
            intensity="HIGH",
            speed=0.89,
            sentence_pause=0.42,
            clause_pause=0.16,
            pacing="heavy",
            pause_style="staccato_impact",
            emphasis="commanding",
            pitch_energy_direction="CLIMAX",
            presence_boost_db=3.0,
            eq_freq_hz=2900,
            description="Dramatic narration: maximum dramatic punch, intense impact without overacting.",
            content_affinity="Life-or-death duels, catastrophic events, battle climaxes"
        )
    },

    BellaDeliveryProfile.WARM.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_WARM",
            display_name="Bella Warm (Low)",
            intensity="LOW",
            speed=0.98,
            sentence_pause=0.28,
            clause_pause=0.11,
            pacing="gentle",
            pause_style="intimate",
            emphasis="soft",
            pitch_energy_direction="WARM",
            presence_boost_db=1.8,
            eq_freq_hz=2600,
            description="Warm narration: soft, gentle, intimate bedside-style storytelling.",
            content_affinity="Quiet character moments, solitary reflections"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_WARM",
            display_name="Bella Warm (Medium)",
            intensity="MEDIUM",
            speed=0.96,
            sentence_pause=0.30,
            clause_pause=0.12,
            pacing="relaxed",
            pause_style="comforting",
            emphasis="gentle",
            pitch_energy_direction="NOSTALGIC",
            presence_boost_db=2.2,
            eq_freq_hz=2600,
            description="Warm narration: nostalgic, human, heartfelt warmth and fond remembrance.",
            content_affinity="Friendship milestones, Christmas at Hogwarts, family moments"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_WARM",
            display_name="Bella Warm (High)",
            intensity="HIGH",
            speed=0.94,
            sentence_pause=0.34,
            clause_pause=0.13,
            pacing="flowing",
            pause_style="emotive",
            emphasis="affectionate",
            pitch_energy_direction="HEARTFELT",
            presence_boost_db=2.5,
            eq_freq_hz=2600,
            description="Warm narration: deeply affectionate, profound nostalgia, comforting reassurance.",
            content_affinity="Touching farewells, emotional bonding, heartwarming triumphs"
        )
    },

    BellaDeliveryProfile.CALM.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_CALM",
            display_name="Bella Calm (Low)",
            intensity="LOW",
            speed=0.96,
            sentence_pause=0.30,
            clause_pause=0.12,
            pacing="steady",
            pause_style="peaceful",
            emphasis="gentle",
            pitch_energy_direction="SERENE",
            presence_boost_db=1.5,
            eq_freq_hz=2700,
            description="Calm narration: tranquil, meditative, serene pacing.",
            content_affinity="Atmospheric descriptions, nocturnal Hogwarts scenes"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_CALM",
            display_name="Bella Calm (Medium)",
            intensity="MEDIUM",
            speed=0.93,
            sentence_pause=0.35,
            clause_pause=0.13,
            pacing="measured",
            pause_style="soothing",
            emphasis="controlled",
            pitch_energy_direction="COMPOSED",
            presence_boost_db=1.8,
            eq_freq_hz=2700,
            description="Calm narration: composed, steady, reassuring clarity.",
            content_affinity="Dumbledore's wisdom, ancient magical artifacts lore"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_CALM",
            display_name="Bella Calm (High)",
            intensity="HIGH",
            speed=0.90,
            sentence_pause=0.38,
            clause_pause=0.15,
            pacing="slow_steady",
            pause_style="deliberate",
            emphasis="profound",
            pitch_energy_direction="UNSHAKABLE",
            presence_boost_db=2.0,
            eq_freq_hz=2700,
            description="Calm narration: unwavering composure amidst chaos, tranquil authority.",
            content_affinity="Philosophical reflections, peaceful resolutions"
        )
    },

    BellaDeliveryProfile.SUSPENSE.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_SUSPENSE",
            display_name="Bella Suspense (Low)",
            intensity="LOW",
            speed=0.94,
            sentence_pause=0.36,
            clause_pause=0.14,
            pacing="hesitant",
            pause_style="anticipatory",
            emphasis="moderate",
            pitch_energy_direction="MYSTERIOUS",
            presence_boost_db=2.2,
            eq_freq_hz=3100,
            description="Suspense narration: creeping curiosity, quiet stealth.",
            content_affinity="Prowling corridors after hours, restricted section exploration"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_SUSPENSE",
            display_name="Bella Suspense (Medium)",
            intensity="MEDIUM",
            speed=0.90,
            sentence_pause=0.42,
            clause_pause=0.16,
            pacing="drawn_out",
            pause_style="brooding_pause",
            emphasis="tense",
            pitch_energy_direction="TENSE",
            presence_boost_db=2.6,
            eq_freq_hz=3100,
            description="Suspense narration: heavy anticipation, deliberate pregnant pauses, brooding tension.",
            content_affinity="Dark corridors, listening for footsteps, unseen dangers"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_SUSPENSE",
            display_name="Bella Suspense (High)",
            intensity="HIGH",
            speed=0.87,
            sentence_pause=0.48,
            clause_pause=0.18,
            pacing="edge_of_seat",
            pause_style="hair_trigger",
            emphasis="visceral_tension",
            pitch_energy_direction="CHILLING",
            presence_boost_db=3.0,
            eq_freq_hz=3100,
            description="Suspense narration: spine-tingling suspense, heart-stopping pauses.",
            content_affinity="Imminent trapdoor descent, facing the mirror alone"
        )
    },

    BellaDeliveryProfile.SURPRISED.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_SURPRISED",
            display_name="Bella Surprised (Low)",
            intensity="LOW",
            speed=1.02,
            sentence_pause=0.22,
            clause_pause=0.08,
            pacing="lively",
            pause_style="questioning",
            emphasis="inquisitive",
            pitch_energy_direction="CURIOUS",
            presence_boost_db=2.2,
            eq_freq_hz=3400,
            description="Surprised narration: mild astonishment, eyebrow-raise inflection.",
            content_affinity="Curious book details, unexpected character quirks"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_SURPRISED",
            display_name="Bella Surprised (Medium)",
            intensity="MEDIUM",
            speed=1.05,
            sentence_pause=0.19,
            clause_pause=0.07,
            pacing="punchy",
            pause_style="double_take",
            emphasis="astonished",
            pitch_energy_direction="ELEVATED",
            presence_boost_db=2.6,
            eq_freq_hz=3400,
            description="Surprised narration: genuine astonishment, wide-eyed revelation inflection.",
            content_affinity="Omitted scenes, surprising plot twists"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_SURPRISED",
            display_name="Bella Surprised (High)",
            intensity="HIGH",
            speed=1.08,
            sentence_pause=0.16,
            clause_pause=0.06,
            pacing="shocked",
            pause_style="gasp_hook",
            emphasis="electrified",
            pitch_energy_direction="SHOCK",
            presence_boost_db=3.0,
            eq_freq_hz=3500,
            description="Surprised narration: jaw-dropping disbelief, high-retention curiosity hook.",
            content_affinity="Major canon contradictions, unbelievable book revelations"
        )
    },

    BellaDeliveryProfile.EXCITED.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_EXCITED",
            display_name="Bella Excited (Low)",
            intensity="LOW",
            speed=1.04,
            sentence_pause=0.20,
            clause_pause=0.08,
            pacing="upbeat",
            pause_style="perky",
            emphasis="bright",
            pitch_energy_direction="OPTIMISTIC",
            presence_boost_db=2.2,
            eq_freq_hz=3300,
            description="Excited narration: energetic enthusiasm, bright tone.",
            content_affinity="First broomstick flight, opening acceptance letters"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_EXCITED",
            display_name="Bella Excited (Medium)",
            intensity="MEDIUM",
            speed=1.08,
            sentence_pause=0.17,
            clause_pause=0.06,
            pacing="accelerated",
            pause_style="rapid_momentum",
            emphasis="electric",
            pitch_energy_direction="HIGH_ENERGY",
            presence_boost_db=2.6,
            eq_freq_hz=3300,
            description="Excited narration: high-energy momentum, punchy Quidditch-style excitement.",
            content_affinity="Quidditch match action, magical discoveries"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_EXCITED",
            display_name="Bella Excited (High)",
            intensity="HIGH",
            speed=1.12,
            sentence_pause=0.14,
            clause_pause=0.05,
            pacing="hyper_kinetic",
            pause_style="zero_dead_air",
            emphasis="celebratory",
            pitch_energy_direction="EUPHORIC",
            presence_boost_db=3.0,
            eq_freq_hz=3400,
            description="Excited narration: peak adrenaline, victory celebration, relentless tempo.",
            content_affinity="House cup triumphs, snitch captures, thrilling escapes"
        )
    },

    BellaDeliveryProfile.SAD.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_SAD",
            display_name="Bella Sad (Low)",
            intensity="LOW",
            speed=0.95,
            sentence_pause=0.32,
            clause_pause=0.13,
            pacing="somber",
            pause_style="mournful",
            emphasis="subdued",
            pitch_energy_direction="MELANCHOLY",
            presence_boost_db=1.5,
            eq_freq_hz=2500,
            description="Sad narration: melancholic, wistful, tender sadness.",
            content_affinity="Harry's loneliness at the Dursleys"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_SAD",
            display_name="Bella Sad (Medium)",
            intensity="MEDIUM",
            speed=0.91,
            sentence_pause=0.38,
            clause_pause=0.15,
            pacing="sorrowful",
            pause_style="grief_pause",
            emphasis="heartbreaking",
            pitch_energy_direction="POIGNANT",
            presence_boost_db=1.8,
            eq_freq_hz=2500,
            description="Sad narration: deep sorrow, poignant pauses, delicate resonance.",
            content_affinity="Mirror of Erised grief, lost parents, bittersweet moments"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_SAD",
            display_name="Bella Sad (High)",
            intensity="HIGH",
            speed=0.88,
            sentence_pause=0.44,
            clause_pause=0.17,
            pacing="heavy_grief",
            pause_style="choked_silence",
            emphasis="shattering",
            pitch_energy_direction="DEVASTATED",
            presence_boost_db=2.0,
            eq_freq_hz=2500,
            description="Sad narration: profound heartbreak, lingering tragic silence.",
            content_affinity="Tragic character deaths, devastating sacrifices"
        )
    },

    BellaDeliveryProfile.ANGRY.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_ANGRY",
            display_name="Bella Angry (Low)",
            intensity="LOW",
            speed=1.00,
            sentence_pause=0.22,
            clause_pause=0.09,
            pacing="taut",
            pause_style="curt",
            emphasis="sharp",
            pitch_energy_direction="INDIGNANT",
            presence_boost_db=2.4,
            eq_freq_hz=3200,
            description="Angry narration: sharp irritation, firm indignation.",
            content_affinity="Dursley cruelty, unfair house point deductions"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_ANGRY",
            display_name="Bella Angry (Medium)",
            intensity="MEDIUM",
            speed=1.04,
            sentence_pause=0.18,
            clause_pause=0.07,
            pacing="cutting",
            pause_style="bite",
            emphasis="fervent",
            pitch_energy_direction="INCENSED",
            presence_boost_db=2.8,
            eq_freq_hz=3300,
            description="Angry narration: cutting edge, fierce confrontation, righteous anger.",
            content_affinity="Standing up to bullies, confronting betrayal"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_ANGRY",
            display_name="Bella Angry (High)",
            intensity="HIGH",
            speed=1.08,
            sentence_pause=0.15,
            clause_pause=0.06,
            pacing="furious",
            pause_style="snapping",
            emphasis="blistering",
            pitch_energy_direction="RAGE",
            presence_boost_db=3.2,
            eq_freq_hz=3400,
            description="Angry narration: blistering fury, powerful defiance without screaming.",
            content_affinity="Furious showdowns, explosive magical outbursts"
        )
    },

    BellaDeliveryProfile.DARK.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_DARK",
            display_name="Bella Dark (Low)",
            intensity="LOW",
            speed=0.93,
            sentence_pause=0.35,
            clause_pause=0.14,
            pacing="shadowy",
            pause_style="cryptic",
            emphasis="cold",
            pitch_energy_direction="OMINOUS",
            presence_boost_db=2.2,
            eq_freq_hz=2600,
            description="Dark narration: ominous whisper, cold shadows, sinister atmosphere.",
            content_affinity="Knockturn Alley, cursed objects, dark arts lore"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_DARK",
            display_name="Bella Dark (Medium)",
            intensity="MEDIUM",
            speed=0.89,
            sentence_pause=0.40,
            clause_pause=0.16,
            pacing="sinister",
            pause_style="menacing",
            emphasis="chilling",
            pitch_energy_direction="MALEVOLENT",
            presence_boost_db=2.6,
            eq_freq_hz=2600,
            description="Dark narration: chilling restraint, deep menacing tone.",
            content_affinity="Voldemort whispers, death eater plots, cursed blood"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_DARK",
            display_name="Bella Dark (High)",
            intensity="HIGH",
            speed=0.86,
            sentence_pause=0.45,
            clause_pause=0.18,
            pacing="macabre",
            pause_style="void_pause",
            emphasis="dread",
            pitch_energy_direction="ELDRITCH",
            presence_boost_db=3.0,
            eq_freq_hz=2600,
            description="Dark narration: pure dread, abyss-like coldness, supreme horror.",
            content_affinity="Horcrux revelations, dark rituals, dementor encounters"
        )
    },

    BellaDeliveryProfile.SARCASTIC.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_SARCASTIC",
            display_name="Bella Sarcastic (Low)",
            intensity="LOW",
            speed=0.99,
            sentence_pause=0.26,
            clause_pause=0.11,
            pacing="dry",
            pause_style="smirk",
            emphasis="deadpan",
            pitch_energy_direction="WRY",
            presence_boost_db=2.0,
            eq_freq_hz=3100,
            description="Sarcastic narration: dry British wit, amused deadpan irony.",
            content_affinity="Vernon's ridiculous antics, Lockhart's pomposity"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_SARCASTIC",
            display_name="Bella Sarcastic (Medium)",
            intensity="MEDIUM",
            speed=1.01,
            sentence_pause=0.24,
            clause_pause=0.12,
            pacing="quippy",
            pause_style="ironic_beat",
            emphasis="mocking",
            pitch_energy_direction="SATIRICAL",
            presence_boost_db=2.4,
            eq_freq_hz=3200,
            description="Sarcastic narration: knowing chuckle, witty mockery, sharp comedic timing.",
            content_affinity="Hermione's priority logic, Dudley's absurd tantrums"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_SARCASTIC",
            display_name="Bella Sarcastic (High)",
            intensity="HIGH",
            speed=1.03,
            sentence_pause=0.22,
            clause_pause=0.13,
            pacing="roast",
            pause_style="punchline",
            emphasis="sardonic",
            pitch_energy_direction="SCATHING",
            presence_boost_db=2.8,
            eq_freq_hz=3200,
            description="Sarcastic narration: savage satire, laugh-out-loud commentary.",
            content_affinity="Hilarious plot holes, ridiculous wizarding bureaucracy"
        )
    },

    BellaDeliveryProfile.EDUCATIONAL.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_EDUCATIONAL",
            display_name="Bella Educational (Low)",
            intensity="LOW",
            speed=0.98,
            sentence_pause=0.28,
            clause_pause=0.11,
            pacing="pedagogical",
            pause_style="structured",
            emphasis="instructive",
            pitch_energy_direction="SCHOLARLY",
            presence_boost_db=2.0,
            eq_freq_hz=3000,
            description="Educational narration: clear lecture cadence, patient instructional clarity.",
            content_affinity="Wandlore mechanics, magical herbology"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_EDUCATIONAL",
            display_name="Bella Educational (Medium)",
            intensity="MEDIUM",
            speed=1.01,
            sentence_pause=0.24,
            clause_pause=0.09,
            pacing="informative",
            pause_style="clarifying",
            emphasis="authoritative",
            pitch_energy_direction="BALANCED",
            presence_boost_db=2.3,
            eq_freq_hz=3000,
            description="Educational narration: authoritative teacher cadence, crisp, engaging explainer.",
            content_affinity="Animagus vs transfiguration distinctions, house lore"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_EDUCATIONAL",
            display_name="Bella Educational (High)",
            intensity="HIGH",
            speed=1.03,
            sentence_pause=0.20,
            clause_pause=0.08,
            pacing="rapid_fact",
            pause_style="concise",
            emphasis="definitive",
            pitch_energy_direction="MASTERCLASS",
            presence_boost_db=2.6,
            eq_freq_hz=3000,
            description="Educational narration: rapid-fire masterclass, definitive expert delivery.",
            content_affinity="Magical law breakdowns, historical timeline deep dives"
        )
    },

    BellaDeliveryProfile.FAST_ENERGETIC.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_FAST_ENERGETIC",
            display_name="Bella Fast Energetic (Low)",
            intensity="LOW",
            speed=1.06,
            sentence_pause=0.18,
            clause_pause=0.07,
            pacing="brisk",
            pause_style="quick",
            emphasis="dynamic",
            pitch_energy_direction="UPBEAT",
            presence_boost_db=2.4,
            eq_freq_hz=3400,
            description="Fast energetic narration: creator-style briskness with zero lag.",
            content_affinity="Quick-hit book facts, fast countdown lists"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_FAST_ENERGETIC",
            display_name="Bella Fast Energetic (Medium)",
            intensity="MEDIUM",
            speed=1.10,
            sentence_pause=0.15,
            clause_pause=0.06,
            pacing="rapid",
            pause_style="tight_momentum",
            emphasis="punchy",
            pitch_energy_direction="HIGH_ENERGY",
            presence_boost_db=2.8,
            eq_freq_hz=3400,
            description="Fast energetic narration: modern creator punch, high retention hook momentum.",
            content_affinity="Action recaps, urgent 25-second Shorts storytelling"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_FAST_ENERGETIC",
            display_name="Bella Fast Energetic (High)",
            intensity="HIGH",
            speed=1.14,
            sentence_pause=0.12,
            clause_pause=0.05,
            pacing="breakneck",
            pause_style="zero_pause",
            emphasis="relentless",
            pitch_energy_direction="TURBO",
            presence_boost_db=3.2,
            eq_freq_hz=3500,
            description="Fast energetic narration: breakneck speed, extreme retention pacing.",
            content_affinity="Lightning speed book vs movie recaps, 60-second challenges"
        )
    },

    BellaDeliveryProfile.EMOTIONAL_RESTRAINED.value: {
        "LOW": BellaProfileConfig(
            profile_id="BELLA_EMOTIONAL_RESTRAINED",
            display_name="Bella Emotional Restrained (Low)",
            intensity="LOW",
            speed=0.96,
            sentence_pause=0.32,
            clause_pause=0.12,
            pacing="tender",
            pause_style="holding_back",
            emphasis="fragile",
            pitch_energy_direction="VULNERABLE",
            presence_boost_db=1.8,
            eq_freq_hz=2700,
            description="Emotional restrained: holding back tears, quiet heartfelt honesty.",
            content_affinity="Harry remembering Lily's green eyes, orphan childhood"
        ),
        "MEDIUM": BellaProfileConfig(
            profile_id="BELLA_EMOTIONAL_RESTRAINED",
            display_name="Bella Emotional Restrained (Medium)",
            intensity="MEDIUM",
            speed=0.93,
            sentence_pause=0.36,
            clause_pause=0.14,
            pacing="poignant",
            pause_style="trembling_hold",
            emphasis="heartfelt",
            pitch_energy_direction="POIGNANT",
            presence_boost_db=2.2,
            eq_freq_hz=2700,
            description="Emotional restrained: profound vulnerability, subtle emotional quiver, dignified restraint.",
            content_affinity="Whispering to the mirror, holding the worn sweater"
        ),
        "HIGH": BellaProfileConfig(
            profile_id="BELLA_EMOTIONAL_RESTRAINED",
            display_name="Bella Emotional Restrained (High)",
            intensity="HIGH",
            speed=0.90,
            sentence_pause=0.42,
            clause_pause=0.16,
            pacing="choked_dignity",
            pause_style="grief_silence",
            emphasis="devastating_restraint",
            pitch_energy_direction="PROFOUND",
            presence_boost_db=2.6,
            eq_freq_hz=2700,
            description="Emotional restrained: deeply touching, devastating emotional weight carried quietly.",
            content_affinity="He just wanted his parents alive, silent sacrifices"
        )
    }
}


def get_bella_profile(profile_name: str, intensity: str = "MEDIUM") -> BellaProfileConfig:
    """Retrieves a specific Bella profile configuration by name and intensity."""
    p_name = profile_name.upper()
    int_name = intensity.upper()
    if p_name in BELLA_PROFILES_REGISTRY:
        return BELLA_PROFILES_REGISTRY[p_name].get(int_name, BELLA_PROFILES_REGISTRY[p_name]["MEDIUM"])
    # Fallback to CANONICAL
    return BELLA_PROFILES_REGISTRY[BellaDeliveryProfile.CANONICAL.value][int_name if int_name in ("LOW", "MEDIUM", "HIGH") else "MEDIUM"]


def list_all_bella_profiles() -> List[BellaProfileConfig]:
    """Returns a flat list of all registered profile variations."""
    all_profiles = []
    for p_name, intensities in BELLA_PROFILES_REGISTRY.items():
        for i_name, cfg in intensities.items():
            all_profiles.append(cfg)
    return all_profiles


def export_profiles_metadata_json(output_path: Optional[str] = None) -> str:
    """Serializes all Bella profile metadata to formatted JSON for pipeline consumption."""
    data = {}
    for p_name, intensities in BELLA_PROFILES_REGISTRY.items():
        data[p_name] = {i_name: cfg.to_dict() for i_name, cfg in intensities.items()}
    json_str = json.dumps(data, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
    return json_str
