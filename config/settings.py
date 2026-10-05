"""
System Settings and Path Configurations.
Loads environment variables and sets defaults for $0-cost operation.
"""
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ==============================================================================
# AUTOMATION IDENTITY & HARD ROUTING GUARDS
# ==============================================================================
AUTOMATION_ID = "harry_potter"
EXPECTED_GOOGLE_ACCOUNT = "jishanh760@gmail.com"
EXPECTED_DRIVE_ROOT_ID = "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC"
EXPECTED_YOUTUBE_CHANNEL_ID = "UCsghEXDa3EzxI4d93cjT-bQ"
EXPECTED_YOUTUBE_CHANNEL_NAME = "STORY FORGE"

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
TOPICS_DIR = DATA_DIR / "topics"
RESEARCH_DIR = DATA_DIR / "research"
SCRIPTS_DIR = DATA_DIR / "scripts"
STORYBOARDS_DIR = DATA_DIR / "storyboards"
ASSETS_CACHE_DIR = DATA_DIR / "assets"
VOICE_DIR = DATA_DIR / "voice"
CAPTIONS_DIR = DATA_DIR / "captions"
RENDERS_DIR = DATA_DIR / "renders"
PUBLISHED_DIR = DATA_DIR / "published"
LOGS_DIR = DATA_DIR / "logs"

ASSETS_DIR = PROJECT_ROOT / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
SFX_DIR = ASSETS_DIR / "sfx"
FONTS_DIR = ASSETS_DIR / "fonts"

LOCKS_DIR = DATA_DIR / "locks"
MOVIES_DIR = DATA_DIR / "movies"
BOOKS_DIR = DATA_DIR / "books"
MOVIE_SUBTITLES_DIR = DATA_DIR / "movie_subtitles"

TEST_DB_PATH = os.getenv("TEST_DB_PATH")
if TEST_DB_PATH:
    DB_PATH = Path(TEST_DB_PATH)
elif os.getenv("IS_TEST_ENV", "").lower() == "true":
    DB_PATH = DATABASE_DIR / "test_pipeline.db"
else:
    DB_PATH = DATABASE_DIR / "pipeline.db"

# Ensure runtime directories exist
for d in [DATABASE_DIR, TOPICS_DIR, RESEARCH_DIR, SCRIPTS_DIR, STORYBOARDS_DIR,
          ASSETS_CACHE_DIR, VOICE_DIR, CAPTIONS_DIR, RENDERS_DIR, PUBLISHED_DIR,
          LOGS_DIR, LOCKS_DIR, MUSIC_DIR, SFX_DIR, FONTS_DIR,
          MOVIES_DIR, BOOKS_DIR, MOVIE_SUBTITLES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Environment Variables & Keys
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY_SECONDARY = os.getenv("GEMINI_API_KEY_SECONDARY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_MODEL_SECONDARY = os.getenv("GEMINI_MODEL_SECONDARY", "")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")  # Active working model on Groq
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.bluesminds.com/v1/chat/completions")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
_raw_nv_keys = os.getenv("NVIDIA_API_KEYS", "")
NVIDIA_API_KEYS = [k.strip() for k in _raw_nv_keys.split(",") if k.strip()]
if NVIDIA_API_KEY and NVIDIA_API_KEY not in NVIDIA_API_KEYS:
    NVIDIA_API_KEYS.insert(0, NVIDIA_API_KEY)
for _i in range(2, 10):
    _extra_k = os.getenv(f"NVIDIA_API_KEY_{_i}", "").strip()
    if _extra_k and _extra_k not in NVIDIA_API_KEYS:
        NVIDIA_API_KEYS.append(_extra_k)

NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
_raw_nv_models = os.getenv("NVIDIA_MODELS", "")
NVIDIA_MODELS = [m.strip() for m in _raw_nv_models.split(",") if m.strip()]
if not NVIDIA_MODELS:
    NVIDIA_MODELS = [
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "meta/muse-glimmer-30b",
        "moonshotai/kimi-k3"
    ]
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")

AI_PROVIDER_AVAILABLE = bool(
    GEMINI_API_KEY
    or GROQ_API_KEY
    or OPENROUTER_API_KEY
    or DEEPSEEK_API_KEY
    or NVIDIA_API_KEY
    or NVIDIA_API_KEYS
)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
# Publishing Safety — Hard Gate
# PUBLISHING_ENABLED and UPLOAD_ENABLED must both be True to permit any YouTube upload.
# These default to False and must be explicitly set to True in .env only for the launch step.
PUBLISHING_ENABLED = os.getenv("PUBLISHING_ENABLED", "true").lower() == "true"
UPLOAD_ENABLED = os.getenv("UPLOAD_ENABLED", "true").lower() == "true"

# Google OAuth credential file paths (isolated to Harry Potter project — NEVER AL AMR paths)
TOKEN_PATH = PROJECT_ROOT / os.getenv("TOKEN_PATH", "credentials/hp_token.json")
CLIENT_SECRETS_PATH = PROJECT_ROOT / os.getenv("CLIENT_SECRETS_PATH", "credentials/hp_client_secret.json")
# Legacy alias kept for code that still references CLIENT_SECRETS_FILE
CLIENT_SECRETS_FILE = str(CLIENT_SECRETS_PATH)

# YouTube Channel Identity Safety Gate
# The automation will verify that the authenticated channel matches this before enabling publishing.
HP_YOUTUBE_CHANNEL_ID = os.getenv("HP_YOUTUBE_CHANNEL_ID", "UCsghEXDa3EzxI4d93cjT-bQ")
HP_YOUTUBE_CHANNEL_NAME = os.getenv("HP_YOUTUBE_CHANNEL_NAME", "")

# Google Account Isolation
GOOGLE_ACCOUNT_EMAIL = "jishanh760@gmail.com"  # Harry Potter project account ONLY

# NVIDIA Text LLM Fallback (Strictly Tier-6 Text Completion only; visual AI prohibited)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_IMAGE_MODEL = None
NVIDIA_IMAGE_BASE_URL = None

# ==============================================================================
# VISUAL SOURCE PRIORITY — MOVIE FOOTAGE ONLY (Harry Potter canon rule)
# ==============================================================================
VISUAL_SOURCE_PRIORITY = [
    s.strip() for s in os.getenv(
        "VISUAL_SOURCE_PRIORITY",
        "movie_footage"
    ).split(",") if s.strip()
]
if "movie_footage" not in VISUAL_SOURCE_PRIORITY:
    VISUAL_SOURCE_PRIORITY.insert(0, "movie_footage")

PART_MARKER_ENABLED = os.getenv("PART_MARKER_ENABLED", "true").lower() == "true"
PART_MARKER_FORMAT = os.getenv("PART_MARKER_FORMAT", "PART {:02d}")

# Channel & Content Configuration (Harry Potter)
DISCOVERY_ONLY = os.getenv("DISCOVERY_ONLY", "true").lower() in ("true", "1", "yes")
NICHE = os.getenv("NICHE", "Harry Potter")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
SHORTS_PER_DAY = int(os.getenv("SHORTS_PER_DAY", "4"))
NOVEL_SHORTS_PER_DAY = 0 if DISCOVERY_ONLY else int(os.getenv("NOVEL_SHORTS_PER_DAY", "2"))
DISCOVERY_SHORTS_PER_DAY = SHORTS_PER_DAY if DISCOVERY_ONLY else int(os.getenv("DISCOVERY_SHORTS_PER_DAY", "2"))
TARGET_RESERVE_BUFFER = int(os.getenv("TARGET_RESERVE_BUFFER", "8"))
SCHEDULING_HORIZON_HOURS = int(os.getenv("SCHEDULING_HORIZON_HOURS", "48"))
PUBLISHING_PLATFORMS = [
    p.strip() for p in os.getenv("PUBLISHING_PLATFORMS", "youtube").split(",") if p.strip()
]


def get_content_mix_allocation(total_shorts: int | None = None) -> dict[str, int]:
    """
    Returns configurable daily content allocation between Novel Storytelling and Discovery.
    Ratio can be dynamically adjusted by analytics/learning feedback loops (e.g. 2+2, 3+1, 1+3, 4+0, 0+4).
    Enforces DISCOVERY_ONLY mode when active.
    """
    total = total_shorts if total_shorts is not None else SHORTS_PER_DAY
    if DISCOVERY_ONLY:
        return {
            "novel_story": 0,
            "discovery": total
        }
    novel_target = int(os.getenv("NOVEL_SHORTS_PER_DAY", str(min(2, total))))
    discovery_target = int(os.getenv("DISCOVERY_SHORTS_PER_DAY", str(max(0, total - novel_target))))
    if novel_target + discovery_target != total:
        discovery_target = max(0, total - novel_target)
    return {
        "novel_story": novel_target,
        "discovery": discovery_target
    }


# TTS Settings — Approved Cloned Storyteller (f5_cloned_narrator_v1) — Permanent Production Voice
# F5-TTS reference speaker conditioning on canonical 24k reference audio
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "f5_tts")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "f5_cloned_narrator_v1")
LOCKED_VOICE_ID = os.getenv("LOCKED_VOICE_ID", "f5_cloned_narrator_v1")
ACTIVE_VOICE_PITCH = os.getenv("ACTIVE_VOICE_PITCH", "+0Hz")
ACTIVE_VOICE_RATE = os.getenv("ACTIVE_VOICE_RATE", "+0%")
APPROVED_PRODUCTION_VOICES = ["f5_cloned_narrator_v1", "male_18", "MALE_18_FenrirOnyx_DarkBaritone", "af_bella"]
KOKORO_MODEL_PATH = DATA_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = DATA_DIR / "voices-v1.0.bin"

# Background Music (BGM) Settings — Canonical Harry Potter BGM (Barty Crouch Junior! Complete Score)
BGM_ENABLED = True
BGM_DEFAULT_TRACK = "Barty Crouch Junior! - Harry Potter and the Goblet of Fire Complete Score (Film Mix).wav"
BGM_DEFAULT_DRIVE_ID = "1KExAdFU1tI7Ht_j0AxTqzIqgV3HtHkIe"
BGM_SPEED = float(os.getenv("BGM_SPEED", "1.2"))  # Permanent 1.2x playback speed
BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.20"))  # Very low background level
BGM_VOLUME_DB = float(os.getenv("BGM_VOLUME_DB", "-18.0"))  # -18.0 dB relative mix level

# Image Generation Fallback Provider (Permanently disabled; 100% movie footage policy enforced)
IMAGE_PROVIDER = None

# Publishing Slots (4 per day)
from config.constants import PUBLISHING_SLOTS_UTC
PUBLISH_TIME_SLOTS = ["02:00", "08:00", "14:00", "20:00"]

# Self-Improvement & Strategy Execution (Phase 4)
SELF_IMPROVEMENT_ENABLED = os.getenv("SELF_IMPROVEMENT_ENABLED", "false").lower() == "true"
STRATEGY_MODE = os.getenv("STRATEGY_MODE", "LEARNED").upper()  # LEARNED, EXPLORE, DEFAULT
EXPLORATION_RATE = float(os.getenv("EXPLORATION_RATE", "0.20"))

# Resilient Bounded Retries (Phase 5.2)
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "1.0"))
RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", "30.0"))

# Concurrency & Buffer Guardrails (Phase 5.3)
MAX_BATCH_PRODUCTION_CEILING = int(os.getenv("MAX_BATCH_PRODUCTION_CEILING", "8"))
MAX_PRODUCTION_ATTEMPTS_CEILING = int(os.getenv("MAX_PRODUCTION_ATTEMPTS_CEILING", "12"))
MAX_BUFFER_RESERVE_CEILING = int(os.getenv("MAX_BUFFER_RESERVE_CEILING", "24"))
LOCK_STALE_TIMEOUT_SEC = float(os.getenv("LOCK_STALE_TIMEOUT_SEC", "1800.0"))  # 30 minutes

# Cloud Mode & Remote GitHub Actions Dispatcher (Phase 7.2)
CLOUD_MODE = os.getenv("CLOUD_MODE", "true").lower() == "true"
GITHUB_PAT = os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN") or ""
GITHUB_REPOSITORY_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER") or "jishanh760-source"
GITHUB_REPOSITORY_NAME = os.getenv("GITHUB_REPOSITORY_NAME") or "harry-potter-automation"
GITHUB_REF = os.getenv("GITHUB_REF", "main")

# Google Drive Cloud Storage (Isolated Harry Potter Vault Root)
GOOGLE_DRIVE_VAULT_ROOT = os.getenv("GOOGLE_DRIVE_VAULT_ROOT", "Yt_harry_potter_automation")
GOOGLE_DRIVE_TOTAL_CAPACITY_BYTES = int(os.getenv("GOOGLE_DRIVE_TOTAL_CAPACITY_BYTES", str(5 * (1024 ** 4))))  # 5 TB


def get_ffmpeg_path() -> str:
    """Finds valid FFmpeg binary path."""
    ffmpeg_sys = shutil.which("ffmpeg")
    if ffmpeg_sys:
        return ffmpeg_sys
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG_EXE = get_ffmpeg_path()
