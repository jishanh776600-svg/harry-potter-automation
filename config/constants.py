"""
Constants for History Shorts Pipeline.
Defines pipeline state machine, video specs, historical niches, scoring weights, and licensing rules.
"""
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional


class JobState(str, Enum):
    QUEUED = "QUEUED"
    RESEARCHING = "RESEARCHING"
    RESEARCHED = "RESEARCHED"
    FACT_CHECKING = "FACT_CHECKING"
    FACT_CHECKED = "FACT_CHECKED"
    SCRIPTING = "SCRIPTING"
    SCRIPT_READY = "SCRIPT_READY"
    VISUAL_PLANNING = "VISUAL_PLANNING"
    VISUALS_SEARCHING = "VISUALS_SEARCHING"
    VISUALS_READY = "VISUALS_READY"
    VOICE_GENERATING = "VOICE_GENERATING"
    VOICE_READY = "VOICE_READY"
    AUDIO_READY = "AUDIO_READY"
    EDITING = "EDITING"
    QA = "QA"
    RENDERED_QA_PASSED = "RENDERED_QA_PASSED"
    READY_TO_UPLOAD = "READY_TO_UPLOAD"
    UPLOADING = "UPLOADING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ARCHIVED = "ARCHIVED"


PUBLISHING_SLOTS_UTC = [
    (2, 0, "02:00 UTC (07:30 AM IST)"),
    (8, 0, "08:00 UTC (01:30 PM IST)"),
    (14, 0, "14:00 UTC (07:30 PM IST)"),
    (20, 0, "20:00 UTC (01:30 AM IST)"),
]

# Canonical Business Timezone (Asia/Kolkata / IST = UTC+5:30)
BUSINESS_TIMEZONE = "Asia/Kolkata"
BUSINESS_TZ = timezone(timedelta(hours=5, minutes=30), name=BUSINESS_TIMEZONE)


def get_business_day_bounds_utc(reference_dt: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Computes the UTC start and end bounds corresponding to 00:00:00 and 24:00:00
    of the business calendar day in Asia/Kolkata (UTC+5:30).

    If reference_dt is None, uses current instant.
    Returns naive UTC datetimes (start_utc, end_utc) suitable for database comparison against UTC columns.
    """
    if reference_dt is None:
        ref_utc = datetime.now(timezone.utc)
    elif reference_dt.tzinfo is None:
        ref_utc = reference_dt.replace(tzinfo=timezone.utc)
    else:
        ref_utc = reference_dt.astimezone(timezone.utc)

    ref_ist = ref_utc.astimezone(BUSINESS_TZ)
    today_ist = ref_ist.date()

    start_ist = datetime(today_ist.year, today_ist.month, today_ist.day, 0, 0, 0, tzinfo=BUSINESS_TZ)
    end_ist = start_ist + timedelta(days=1)

    start_utc = start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_ist.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


class HarryPotterCategory(str, Enum):
    NOVEL_STORY = "Novel Storytelling"
    BOOK_VS_MOVIE = "Book vs Movie Differences"
    OMITTED_SCENES = "Omitted Scenes & Details"
    CHARACTER_LORE = "Character Lore & Details"
    UNEXPLAINED_DETAILS = "Things Movies Didn't Explain"
    STANDALONE_DISCOVERY = "Standalone Discoveries"
    DISCOVERY_LORE = "Discovery Lore"
    MAGICAL_ARTIFACTS = "Magical Artifacts"
    HOGWARTS_MYSTERIES = "Hogwarts Mysteries"


class ContentType(str, Enum):
    NOVEL_STORY = "NOVEL_STORY"
    DISCOVERY = "DISCOVERY"


class VisualSourcePriority(str, Enum):
    MOVIE_FOOTAGE = "movie_footage"
    BOOK_IMAGERY = "book_imagery"
    AI_GENERATED = "ai_generated"
    STOCK_FOOTAGE = "stock_footage"
    PEXELS = "pexels"


DEFAULT_VISUAL_SOURCE_PRIORITY = [
    VisualSourcePriority.MOVIE_FOOTAGE.value,
    VisualSourcePriority.BOOK_IMAGERY.value,
    VisualSourcePriority.AI_GENERATED.value,
    VisualSourcePriority.STOCK_FOOTAGE.value,
    VisualSourcePriority.PEXELS.value,
]


# Retained for backwards compatibility across existing test harnesses
class HistoricalCategory(str, Enum):
    AMERICAN_HISTORY = "American History"
    EUROPEAN_HISTORY = "European History"
    STRANGE_LAWS = "Strange Historical Laws"
    UNUSUAL_WARS = "Unusual Wars"
    HISTORICAL_MYSTERIES = "Historical Mysteries"
    STRANGE_INVENTIONS = "Strange Inventions"
    LOST_PLACES = "Lost Places"
    UNUSUAL_BORDERS = "Unusual Borders"
    HISTORICAL_COINCIDENCES = "Unexpected Coincidences"
    DOCUMENTED_DISASTERS = "Documented Disasters"
    FORGOTTEN_FIGURES = "Forgotten Figures"


class CurrentAffairsCategory(str, Enum):
    GEOPOLITICS = "Geopolitics"
    GLOBAL_CONFLICT = "Global Conflict"
    WORLD_POLITICS = "World Politics"
    US_POLITICS = "US Politics"
    EUROPE_POLITICS = "Europe Politics"
    GLOBAL_ECONOMY = "Global Economy"
    DIPLOMACY = "Diplomacy"
    SECURITY = "Security"
    MAJOR_WORLD_EVENT = "Major World Event"


class LicenseType(str, Enum):
    PEXELS_LICENSE = "Pexels License (Commercial $0)"
    PUBLIC_DOMAIN_CC0 = "Public Domain / CC0"
    YOUTUBE_AUDIO_LIBRARY = "YouTube Audio Library (Monetizable $0)"
    APACHE_2_0 = "Apache 2.0"
    MIT = "MIT"
    AI_GENERATED_OPEN = "AI Generated (Commercially Permitted)"
    UNKNOWN = "UNKNOWN"


class VisualSourceType(str, Enum):
    ARCHIVAL_PHOTO = "ARCHIVAL_PHOTO"
    ARCHIVAL_VIDEO = "ARCHIVAL_VIDEO"
    HISTORICAL_DOCUMENT = "HISTORICAL_DOCUMENT"
    HISTORICAL_MAP = "HISTORICAL_MAP"
    HISTORICAL_ILLUSTRATION = "HISTORICAL_ILLUSTRATION"
    HISTORICAL_PAINTING = "HISTORICAL_PAINTING"
    HISTORICAL_ENGRAVING = "HISTORICAL_ENGRAVING"
    HISTORICAL_ARTIFACT = "HISTORICAL_ARTIFACT"
    GENERATED_RECONSTRUCTION = "GENERATED_RECONSTRUCTION"
    MODERN_CONTEXTUAL_STOCK = "MODERN_CONTEXTUAL_STOCK"
    ABSTRACT_ATMOSPHERIC = "ABSTRACT_ATMOSPHERIC"
    UNKNOWN = "UNKNOWN"


class HistoricalEventRelation(str, Enum):
    DIRECT_EVENT_EVIDENCE = "DIRECT_EVENT_EVIDENCE"
    EVENT_RELATED_HISTORICAL_CONTEXT = "EVENT_RELATED_HISTORICAL_CONTEXT"
    ERA_CONTEXT = "ERA_CONTEXT"
    GENERIC_MODERN_CONTEXT = "GENERIC_MODERN_CONTEXT"
    UNKNOWN = "UNKNOWN"


class FailureType(str, Enum):
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    RESEARCH_FAILURE = "RESEARCH_FAILURE"
    FACT_VERIFICATION_FAILURE = "FACT_VERIFICATION_FAILURE"
    SCRIPT_FAILURE = "SCRIPT_FAILURE"
    TTS_FAILURE = "TTS_FAILURE"
    VISUAL_FAILURE = "VISUAL_FAILURE"
    AUDIO_FAILURE = "AUDIO_FAILURE"
    CAPTION_FAILURE = "CAPTION_FAILURE"
    RENDER_FAILURE = "RENDER_FAILURE"
    QA_FAILURE = "QA_FAILURE"
    DRIVE_FAILURE = "DRIVE_FAILURE"
    UPLOAD_FAILURE = "UPLOAD_FAILURE"
    YOUTUBE_FAILURE = "YOUTUBE_FAILURE"
    OAUTH_FAILURE = "OAUTH_FAILURE"
    QUOTA_FAILURE = "QUOTA_FAILURE"
    RECONCILIATION_FAILURE = "RECONCILIATION_FAILURE"


# Video Specifications (Strict YouTube Shorts vertical 9:16)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_ASPECT_RATIO = "9:16"

class ContentNiche(str, Enum):
    HARRY_POTTER = "Harry Potter"
    MYSTERY_BIZARRE = "Mystery / Bizarre Real-World Stories"


# Canonical Format Duration Targets (Seconds)
# Novel Story: 45–60 seconds (immersive novel storytelling)
NOVEL_STORY_MIN_DURATION_SEC = 45.0
NOVEL_STORY_MAX_DURATION_SEC = 60.0
NOVEL_STORY_TARGET_DURATION_SEC = 52.5

# Discovery Big: 60–70 seconds (5–7 facts or 1 deep lore breakdown)
DISCOVERY_BIG_MIN_DURATION_SEC = 60.0
DISCOVERY_BIG_MAX_DURATION_SEC = 70.0
DISCOVERY_BIG_TARGET_DURATION_SEC = 65.0

# Discovery Short: 25–30 seconds (1 deep difference or compact discovery)
DISCOVERY_SHORT_MIN_DURATION_SEC = 25.0
DISCOVERY_SHORT_MAX_DURATION_SEC = 30.0
DISCOVERY_SHORT_TARGET_DURATION_SEC = 27.5

# Overall YouTube Shorts Bounds across all formats (25.0s – 70.0s)
MIN_DURATION_SEC = 25.0
MAX_DURATION_SEC = 70.0
TARGET_DURATION_SEC = 52.5

# Visual Part Marker Configuration (Visual only, strictly never spoken)
PART_MARKER_ENABLED = True
PART_MARKER_FORMAT = "PART {:02d}"
PART_MARKER_POSITION = "top_left"
FORBIDDEN_SPOKEN_PART_PATTERNS = [
    r"\bpart\s+\d+\b",
    r"\bpart\s+(one|two|three|four|five|six|seven|eight|nine|ten)\b",
    r"\bepisode\s+\d+\b",
    r"\bbook\s+\d+\b",
    r"\bchapter\s+\d+\b",
    r"\bin this part\b",
    r"\blast part\b",
    r"\bnext part\b"
]

# Configurable Bella Voice Mood/Tone Delivery Profiles (Audition-ready, not permanently locked)
BELLA_VOICE_PROFILES = {
    "BELLA_CANONICAL": {"id": "af_bella", "name": "Bella Canonical", "speed": 1.00, "pause_multiplier": 1.00, "tone": "balanced", "description": "Natural baseline narration: conversational, neutral, clear."},
    "BELLA_CINEMATIC": {"id": "af_bella", "name": "Bella Cinematic Storyteller", "speed": 0.94, "pause_multiplier": 1.10, "tone": "cinematic", "description": "Immersive cinematic delivery for Harry Potter novel storytelling."},
    "BELLA_DISCOVERY": {"id": "af_bella", "name": "Bella Discovery & Intrigue", "speed": 1.03, "pause_multiplier": 0.90, "tone": "engaging_discovery", "description": "Crisp, lively pacing for standalone lore and book vs movie discoveries."},
    "BELLA_DRAMATIC": {"id": "af_bella", "name": "Bella Dramatic", "speed": 0.92, "pause_multiplier": 1.18, "tone": "dramatic", "description": "Heightened tension and emotional weight for climactic confrontations."},
    "BELLA_WARM": {"id": "af_bella", "name": "Bella Warm", "speed": 0.96, "pause_multiplier": 1.05, "tone": "warm", "description": "Nostalgic, gentle, heartfelt storytelling for character moments."},
    "BELLA_CALM": {"id": "af_bella", "name": "Bella Calm", "speed": 0.93, "pause_multiplier": 1.12, "tone": "calm", "description": "Soothing, steady, composed, measured cadence."},
    "BELLA_SUSPENSE": {"id": "af_bella", "name": "Bella Suspense", "speed": 0.90, "pause_multiplier": 1.25, "tone": "suspense", "description": "Whispered anticipation, deliberate pauses, brooding tension."},
    "BELLA_SURPRISED": {"id": "af_bella", "name": "Bella Surprised", "speed": 1.05, "pause_multiplier": 0.88, "tone": "surprised", "description": "Wide-eyed energetic inflection, genuine astonishment."},
    "BELLA_EXCITED": {"id": "af_bella", "name": "Bella Excited", "speed": 1.08, "pause_multiplier": 0.82, "tone": "excited", "description": "High energy, punchy pace, enthusiastic Quidditch-style momentum."},
    "BELLA_SAD": {"id": "af_bella", "name": "Bella Sad", "speed": 0.91, "pause_multiplier": 1.20, "tone": "sad", "description": "Melancholic, softer cadence, subdued resonance."},
    "BELLA_ANGRY": {"id": "af_bella", "name": "Bella Angry", "speed": 1.04, "pause_multiplier": 0.85, "tone": "angry", "description": "Firm, sharp articulation, assertive indignation, tense edge."},
    "BELLA_DARK": {"id": "af_bella", "name": "Bella Dark", "speed": 0.89, "pause_multiplier": 1.22, "tone": "dark", "description": "Deep, ominous, shadowy, cold restraint."},
    "BELLA_SARCASTIC": {"id": "af_bella", "name": "Bella Sarcastic", "speed": 1.01, "pause_multiplier": 0.98, "tone": "sarcastic", "description": "Dry wit, wry irony, knowing comedic inflection."},
    "BELLA_EDUCATIONAL": {"id": "af_bella", "name": "Bella Educational", "speed": 1.01, "pause_multiplier": 0.95, "tone": "educational", "description": "Articulate explainer, clear pedagogical rhythm, instructive."},
    "BELLA_FAST_ENERGETIC": {"id": "af_bella", "name": "Bella Fast Energetic", "speed": 1.10, "pause_multiplier": 0.75, "tone": "fast_energetic", "description": "High tempo, rapid hook delivery, zero dead air, creator punch."},
    "BELLA_EMOTIONAL_RESTRAINED": {"id": "af_bella", "name": "Bella Emotional Restrained", "speed": 0.93, "pause_multiplier": 1.15, "tone": "emotional_restrained", "description": "Poignant, holding back deep feeling, subtle quiver, heartfelt."}
}
DEFAULT_BELLA_PROFILE = "BELLA_CINEMATIC"

# Audio Standards
AUDIO_SAMPLE_RATE = 44100
TARGET_LUFS = -14.0
TARGET_BGM_LUFS = -30.0  # Standardized Stage B BGM bed target loudness (16 dB below narration master)
BGM_MIX_VOLUME_DB = -13.0  # Fallback relative BGM mixing level
MUSIC_DUCK_DB = -24.0
SFX_LEVEL_DB = -18.0
BGM_FADE_IN_SEC = 0.8
BGM_FADE_OUT_SEC = 1.5

# Voiceover Pause Calibration (Restored to Natural Original Bella Delivery)
# Pacing & Pause Calibration — Reduced by 40% for rapid-fire high-retention storytelling
VOICEOVER_PAUSE_MULTIPLIER: float = 0.60

# Base intentional natural conversational pauses (seconds) — scaled down by 40%
BASE_CLAUSE_PAUSE_SEC: float = 0.03
BASE_SENTENCE_PAUSE_SEC: float = 0.11
BASE_PARAGRAPH_PAUSE_SEC: float = 0.15
BASE_EMPHASIS_PAUSE_SEC: float = 0.18
BASE_MAX_SILENCE_CAP_SEC: float = 0.21

# Effective calibrated pause durations (Tight rapid-fire delivery)
EFFECTIVE_CLAUSE_PAUSE_SEC: float = 0.03
EFFECTIVE_SENTENCE_PAUSE_SEC: float = 0.11
EFFECTIVE_PARAGRAPH_PAUSE_SEC: float = 0.15
EFFECTIVE_EMPHASIS_PAUSE_SEC: float = 0.18
EFFECTIVE_MAX_SILENCE_CAP_SEC: float = 0.21

# Audio QA Thresholds
MIN_AUDIO_LOUDNESS_LUFS = -22.0
MAX_AUDIO_LOUDNESS_LUFS = -10.0
MAX_TRUE_PEAK_DBTP = -0.5
MIN_BGM_RMS_ENERGY = 0.005  # Ensures BGM is physically audible in final render

# Novel Story Script Constraints (100-150 words optimal for 45-60s natural delivery)
NOVEL_STORY_MIN_WORD_COUNT = 100
NOVEL_STORY_MAX_WORD_COUNT = 150
NOVEL_STORY_OPTIMAL_WORD_COUNT = 125

# Discovery Short Script Constraints (55-75 words optimal for 25-30s natural delivery)
DISCOVERY_SHORT_MIN_WORD_COUNT = 55
DISCOVERY_SHORT_MAX_WORD_COUNT = 75
DISCOVERY_SHORT_OPTIMAL_WORD_COUNT = 65

# Baseline Word Count Constraints (Discovery Short default)
MIN_WORD_COUNT = 55
MAX_WORD_COUNT = 75
OPTIMAL_WORD_COUNT = 65

# Scheduling & Target Capacity
SCHEDULING_HORIZON_HOURS = 48
DAILY_SHORTS_LIMIT = 4
TARGET_RESERVE_BUFFER = 8
PUBLISHING_PLATFORMS = ["youtube", "instagram", "facebook"]

# API Free Limits (Default Safety Buffers)
PEXELS_FREE_LIMIT_HOURLY = 200
PEXELS_FREE_LIMIT_MONTHLY = 20000
GEMINI_FREE_RPM = 15
YOUTUBE_DAILY_QUOTA_LIMIT = 10000
YOUTUBE_UPLOAD_COST = 1600

# Canonical Buffer Audit & Replenishment Automation (Every 2 Hours, 24/7)
BUFFER_AUDIT_INTERVAL_HOURS = 2
BUFFER_AUDIT_CRON = "0 */2 * * *"
BUFFER_AUDIT_HOURS_UTC = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]


def get_next_buffer_audit_time(reference_dt: Optional[datetime] = None) -> datetime:
    """
    Computes the exact next upcoming 2-hour audit slot:
    00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00 UTC.
    Returns naive UTC datetime suitable for ISO formatting and countdowns.
    """
    from datetime import time as dtime
    if reference_dt is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    elif reference_dt.tzinfo is not None:
        now = reference_dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        now = reference_dt

    for hour in BUFFER_AUDIT_HOURS_UTC:
        slot = datetime.combine(now.date(), dtime(hour=hour, minute=0))
        if slot > now:
            return slot

    # If all slots for today have elapsed, next slot is 00:00 UTC tomorrow
    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, dtime(hour=0, minute=0))


# Recovery & Self-Healing Thresholds (Phase 6)
MAX_JOB_RETRIES = 3
MAX_UPLOAD_RETRIES = 2
STALE_JOB_TIMEOUT_SEC = 3600       # 1 hour
STALE_PROCESSING_TIMEOUT_SEC = 7200 # 2 hours
BACKOFF_BASE_SECONDS = 2.0
RETRY_BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 60.0

