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
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")  # llama-3.3-70b-versatile was retired (HTTP 404)
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.bluesminds.com/v1/chat/completions")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")

AI_PROVIDER_AVAILABLE = bool(
    GEMINI_API_KEY
    or GROQ_API_KEY
    or OPENROUTER_API_KEY
    or DEEPSEEK_API_KEY
    or NVIDIA_API_KEY
)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
# Publishing Safety — Hard Gate
# PUBLISHING_ENABLED and UPLOAD_ENABLED must both be True to permit any YouTube upload.
# These default to False and must be explicitly set to True in .env only for the launch step.
PUBLISHING_ENABLED = os.getenv("PUBLISHING_ENABLED", "false").lower() == "true"
UPLOAD_ENABLED = os.getenv("UPLOAD_ENABLED", "false").lower() == "true"

# Google OAuth credential file paths (isolated to Harry Potter project — NEVER AL AMR paths)
TOKEN_PATH = PROJECT_ROOT / os.getenv("TOKEN_PATH", "credentials/hp_token.json")
CLIENT_SECRETS_PATH = PROJECT_ROOT / os.getenv("CLIENT_SECRETS_PATH", "credentials/hp_client_secret.json")
# Legacy alias kept for code that still references CLIENT_SECRETS_FILE
CLIENT_SECRETS_FILE = str(CLIENT_SECRETS_PATH)

# YouTube Channel Identity Safety Gate
# The automation will verify that the authenticated channel matches this before enabling publishing.
# Leave empty — the auth script will populate these after OAuth verification.
HP_YOUTUBE_CHANNEL_ID = os.getenv("HP_YOUTUBE_CHANNEL_ID", "")
HP_YOUTUBE_CHANNEL_NAME = os.getenv("HP_YOUTUBE_CHANNEL_NAME", "")

# Google Account Isolation
GOOGLE_ACCOUNT_EMAIL = "jishanh760@gmail.com"  # Harry Potter project account ONLY

# NVIDIA Image Generation
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_IMAGE_MODEL = os.getenv("NVIDIA_IMAGE_MODEL", "nvidia/consistory")
NVIDIA_IMAGE_BASE_URL = os.getenv("NVIDIA_IMAGE_BASE_URL", "https://ai.api.nvidia.com/v1/genai")

# ==============================================================================
# VISUAL SOURCE PRIORITY — MOVIE FOOTAGE IS ATTEMPT #1 FOR EVERY VISUAL BEAT
# The system tries movie clip first for each narration sentence/visual requirement.
# Images/AI/stock are per-beat fallbacks when no suitable movie clip can be found.
# ==============================================================================
VISUAL_SOURCE_PRIORITY = [
    s.strip() for s in os.getenv(
        "VISUAL_SOURCE_PRIORITY",
        "movie_footage,book_imagery,ai_generated,stock_footage,pexels"
    ).split(",") if s.strip()
]
# Ensure movie_footage is always first — enforce programmatically as well as in env
if "movie_footage" not in VISUAL_SOURCE_PRIORITY:
    VISUAL_SOURCE_PRIORITY.insert(0, "movie_footage")
elif VISUAL_SOURCE_PRIORITY[0] != "movie_footage":
    VISUAL_SOURCE_PRIORITY.remove("movie_footage")
    VISUAL_SOURCE_PRIORITY.insert(0, "movie_footage")
# Pexels is last resort — ensure it remains at the end
if "pexels" in VISUAL_SOURCE_PRIORITY and VISUAL_SOURCE_PRIORITY[-1] != "pexels":
    VISUAL_SOURCE_PRIORITY.remove("pexels")
    VISUAL_SOURCE_PRIORITY.append("pexels")

PART_MARKER_ENABLED = os.getenv("PART_MARKER_ENABLED", "true").lower() == "true"
PART_MARKER_FORMAT = os.getenv("PART_MARKER_FORMAT", "PART {:02d}")

# Channel & Content Configuration (Harry Potter)
NICHE = os.getenv("NICHE", "Harry Potter")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
SHORTS_PER_DAY = int(os.getenv("SHORTS_PER_DAY", "4"))
NOVEL_SHORTS_PER_DAY = int(os.getenv("NOVEL_SHORTS_PER_DAY", "2"))
DISCOVERY_SHORTS_PER_DAY = int(os.getenv("DISCOVERY_SHORTS_PER_DAY", "2"))
TARGET_RESERVE_BUFFER = int(os.getenv("TARGET_RESERVE_BUFFER", "8"))
SCHEDULING_HORIZON_HOURS = int(os.getenv("SCHEDULING_HORIZON_HOURS", "48"))
PUBLISHING_PLATFORMS = [
    p.strip() for p in os.getenv("PUBLISHING_PLATFORMS", "youtube").split(",") if p.strip()
]


def get_content_mix_allocation(total_shorts: int | None = None) -> dict[str, int]:
    """
    Returns configurable daily content allocation between Novel Storytelling and Discovery.
    Ratio can be dynamically adjusted by analytics/learning feedback loops (e.g. 2+2, 3+1, 1+3, 4+0, 0+4).
    """
    total = total_shorts if total_shorts is not None else SHORTS_PER_DAY
    novel_target = int(os.getenv("NOVEL_SHORTS_PER_DAY", str(min(2, total))))
    discovery_target = int(os.getenv("DISCOVERY_SHORTS_PER_DAY", str(max(0, total - novel_target))))
    if novel_target + discovery_target != total:
        discovery_target = max(0, total - novel_target)
    return {
        "novel_story": novel_target,
        "discovery": discovery_target
    }


# TTS Settings — Sarah (af_sarah) — Permanent Production Voice
# Kokoro-82M ONNX US Female voice with tight, rapid-fire pacing (-40% pause intervals)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "kokoro")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_sarah")
ACTIVE_VOICE_PITCH = os.getenv("ACTIVE_VOICE_PITCH", "+0Hz")
ACTIVE_VOICE_RATE = os.getenv("ACTIVE_VOICE_RATE", "+0%")
APPROVED_PRODUCTION_VOICES = ["af_sarah"]
KOKORO_MODEL_PATH = DATA_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = DATA_DIR / "voices-v1.0.bin"

# Background Music (BGM) Settings
BGM_ENABLED = True
BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.14"))  # -17 dB ducking relative to speech

# Image Generation Fallback Provider
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")

# Publishing Slots (4 per day)
from config.constants import PUBLISHING_SLOTS_UTC
PUBLISH_TIME_SLOTS = ["06:00", "10:00", "14:00", "18:00"]

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
GOOGLE_DRIVE_VAULT_ROOT = os.getenv("GOOGLE_DRIVE_VAULT_ROOT", "Harry_Potter_Shorts_Vault")
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
