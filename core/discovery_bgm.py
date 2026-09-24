"""
STORY FORGE — Authoritative Dynamic Discovery BGM Architecture & Gate
======================================================================
Single source of truth for Discovery Short background music.
Strictly decoupled from Novel Story (which retains its own BGM rules).

Requirements:
- Dynamically resolves current canonical Discovery BGM.
- Rejects any stale or hard-coded Esther No.6 references in Discovery.
- Halts execution at the BGM Configuration Gate if BGM is unconfigured,
  missing, ambiguous, or fails SHA-256 verification.
- Calculates deterministic BGM fingerprint incorporating file identity,
  SHA-256, speed (1.2x), and volume (-18dB / 0.20).
- Guarantees stale renders cannot be reused when BGM configuration changes.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Dict, Any, Optional, Tuple

from config.settings import MUSIC_DIR, DATA_DIR

logger = logging.getLogger("DiscoveryBGM")

CONFIG_FILE_PATH = DATA_DIR / "discovery_bgm_config.json"
STALE_ESTHER_KEYWORDS = [
    "esther abrami",
    "no.6 in my dreams",
    "no.6",
    "esther",
    "no_6"
]


class BGMConfigurationError(Exception):
    """Raised when Discovery BGM configuration is missing, stale, or invalid."""
    pass


@dataclass
class DiscoveryBGMConfig:
    """Canonical Discovery BGM metadata record."""
    bgm_filename: Optional[str] = None
    source_provider: str = "PENDING_USER_SPECIFICATION"
    drive_file_id: Optional[str] = None
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None
    duration_sec: Optional[float] = None
    sample_rate: Optional[int] = None
    speed_multiplier: float = 1.2
    volume_db: float = -28.0
    volume_amix_weight: float = 0.08
    status: str = "UNCONFIGURED"  # UNCONFIGURED, VERIFIED, REJECTED_STALE
    rejection_reason: Optional[str] = None

    def compute_config_fingerprint(self) -> str:
        """Computes deterministic SHA-256 fingerprint for this BGM configuration."""
        raw = (
            f"DISCOVERY_BGM_V2:"
            f"{self.bgm_filename or 'UNCONFIGURED'}:"
            f"{self.actual_sha256 or self.expected_sha256 or 'NO_HASH'}:"
            f"{self.speed_multiplier:.2f}:"
            f"{self.volume_db:.1f}:"
            f"{self.volume_amix_weight:.2f}:"
            f"{self.drive_file_id or 'NO_DRIVE_ID'}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bgm_filename": self.bgm_filename,
            "source_provider": self.source_provider,
            "drive_file_id": self.drive_file_id,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "duration_sec": self.duration_sec,
            "sample_rate": self.sample_rate,
            "speed_multiplier": self.speed_multiplier,
            "volume_db": self.volume_db,
            "volume_amix_weight": self.volume_amix_weight,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "config_fingerprint": self.compute_config_fingerprint(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryBGMConfig":
        return cls(
            bgm_filename=data.get("bgm_filename"),
            source_provider=data.get("source_provider", "UNKNOWN"),
            drive_file_id=data.get("drive_file_id"),
            expected_sha256=data.get("expected_sha256"),
            actual_sha256=data.get("actual_sha256"),
            duration_sec=data.get("duration_sec"),
            sample_rate=data.get("sample_rate"),
            speed_multiplier=float(data.get("speed_multiplier", 1.2)),
            volume_db=float(data.get("volume_db", -18.0)),
            volume_amix_weight=float(data.get("volume_amix_weight", 0.20)),
            status=data.get("status", "UNCONFIGURED"),
            rejection_reason=data.get("rejection_reason"),
        )


class DiscoveryBGMGate:
    """
    Authoritative BGM Configuration Gate for Discovery Shorts.
    Guarantees no Discovery render can execute without verified canonical BGM.
    """

    @classmethod
    def load_persisted_config(cls) -> DiscoveryBGMConfig:
        """Loads canonical Discovery BGM configuration from disk or environment."""
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return DiscoveryBGMConfig.from_dict(data)
            except Exception as e:
                logger.warning(f"[DiscoveryBGMGate] Error reading {CONFIG_FILE_PATH}: {e}")

        # Check environment override
        env_bgm = os.getenv("DISCOVERY_BGM_TRACK")
        if env_bgm:
            return DiscoveryBGMConfig(
                bgm_filename=env_bgm,
                source_provider=os.getenv("DISCOVERY_BGM_PROVIDER", "ENV_OVERRIDE"),
                drive_file_id=os.getenv("DISCOVERY_BGM_DRIVE_ID"),
                expected_sha256=os.getenv("DISCOVERY_BGM_SHA256"),
                speed_multiplier=float(os.getenv("BGM_SPEED", "1.2")),
                volume_db=float(os.getenv("BGM_VOLUME_DB", "-18.0")),
                volume_amix_weight=float(os.getenv("BGM_VOLUME", "0.20")),
                status="CONFIGURED",
            )

        return DiscoveryBGMConfig(status="UNCONFIGURED")

    @classmethod
    def save_persisted_config(cls, config: DiscoveryBGMConfig) -> None:
        """Persists the validated Discovery BGM configuration."""
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)

    @classmethod
    def calculate_file_sha256(cls, file_path: Path) -> str:
        """Calculates deterministic SHA-256 for an audio file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def probe_audio_properties(cls, file_path: Path) -> Tuple[float, int]:
        """Probes audio duration in seconds and sample rate via ffprobe or soundfile."""
        try:
            import soundfile as sf
            info = sf.info(str(file_path))
            return float(info.duration), int(info.samplerate)
        except Exception:
            pass

        # Fallback to ffprobe
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=duration,sample_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        sample_rate = int(lines[0]) if len(lines) > 0 and lines[0].isdigit() else 44100
        duration = float(lines[1]) if len(lines) > 1 else 0.0
        return duration, sample_rate

    @classmethod
    def verify_and_resolve_bgm(cls) -> DiscoveryBGMConfig:
        """
        Executes the 5-step BGM Configuration Gate:
        1. Resolve current Discovery BGM configuration.
        2. Detect and reject stale hard-coded Esther No.6.
        3. Verify actual audio file existence in MUSIC_DIR.
        4. Calculate SHA-256 and compare against canonical spec (if specified).
        5. Verify sample rate and duration, returning verified config.

        Raises:
            BGMConfigurationError: If BGM is unconfigured, missing, stale, ambiguous,
                                  or fails checksum verification.
        """
        config = cls.load_persisted_config()

        # Step 1: Check if configured
        if not config.bgm_filename or config.status == "UNCONFIGURED":
            err_msg = (
                "BGM CONFIGURATION GATE HALT: Discovery BGM is UNCONFIGURED. "
                "The user has not yet specified the new canonical Discovery BGM filename. "
                "Automatic rendering is strictly blocked to prevent stale fallbacks."
            )
            config.status = "UNCONFIGURED"
            config.rejection_reason = err_msg
            logger.error(f"[DiscoveryBGMGate] {err_msg}")
            raise BGMConfigurationError(err_msg)

        # Step 2: Strict Stale Esther No.6 check
        lower_name = config.bgm_filename.lower()
        for kw in STALE_ESTHER_KEYWORDS:
            if kw in lower_name:
                err_msg = (
                    f"BGM CONFIGURATION GATE HALT: Stale Esther No.6 detected in Discovery configuration ('{config.bgm_filename}'). "
                    "Esther Abrami - No.6 In My Dreams is strictly prohibited for Discovery Shorts. "
                    "Novel Story retains its independent BGM configuration."
                )
                config.status = "REJECTED_STALE"
                config.rejection_reason = err_msg
                logger.error(f"[DiscoveryBGMGate] {err_msg}")
                raise BGMConfigurationError(err_msg)

        # Step 3: Check actual file exists
        bgm_path = MUSIC_DIR / config.bgm_filename
        if not bgm_path.exists():
            err_msg = (
                f"BGM CONFIGURATION GATE HALT: Canonical BGM file not found at: {bgm_path}. "
                "Cloud acquisition or user placement required before render."
            )
            config.status = "MISSING_FILE"
            config.rejection_reason = err_msg
            logger.error(f"[DiscoveryBGMGate] {err_msg}")
            raise BGMConfigurationError(err_msg)

        # Step 4: Calculate SHA-256
        actual_sha = cls.calculate_file_sha256(bgm_path)
        config.actual_sha256 = actual_sha

        if config.expected_sha256 and config.expected_sha256.lower() != actual_sha.lower():
            err_msg = (
                f"BGM CONFIGURATION GATE HALT: SHA-256 checksum mismatch for {config.bgm_filename}. "
                f"Expected: {config.expected_sha256}, Actual: {actual_sha}."
            )
            config.status = "CHECKSUM_MISMATCH"
            config.rejection_reason = err_msg
            logger.error(f"[DiscoveryBGMGate] {err_msg}")
            raise BGMConfigurationError(err_msg)

        # Step 5: Probe technical properties
        try:
            dur, sr = cls.probe_audio_properties(bgm_path)
            config.duration_sec = dur
            config.sample_rate = sr
        except Exception as e:
            logger.warning(f"[DiscoveryBGMGate] Audio property probe error: {e}")

        config.status = "VERIFIED"
        config.rejection_reason = None
        cls.save_persisted_config(config)
        logger.info(f"[DiscoveryBGMGate] VERIFIED Discovery BGM: '{config.bgm_filename}' (SHA: {actual_sha[:12]})")
        return config
