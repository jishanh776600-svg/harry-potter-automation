"""
STORY FORGE — Base Asset Source Provider
=========================================
Defines the abstract interface and resilient HTTP streaming mechanics
for all internet and cloud media acquisition providers.
"""

import abc
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from core.acquisition_types import AssetCandidate, MediaCategory
from core.safe_url_validator import SafeURLValidator

logger = logging.getLogger("AssetAcquisition.Provider")

DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 12.0
DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB max download ceiling per asset


class ProviderError(Exception):
    """Base exception for provider failures."""
    pass


class ProviderDownloadError(ProviderError):
    """Raised when downloading an asset fails."""
    pass


class AssetSourceProvider(abc.ABC):
    """
    Abstract base class for all acquisition providers.
    Provides safe streaming, retry resilience, and SSRF prevention.
    """

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        rate_limit_delay: float = 0.5,
        max_retries: int = 3,
        user_agent: Optional[str] = None
    ):
        self.name = name
        self.enabled = enabled
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.last_request_time = 0.0
        self.user_agent = user_agent or (
            "StoryForgeAssetEngine/1.0 (https://github.com/storyforge; contact@storyforge.local)"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def _apply_rate_limit(self) -> None:
        """Enforces a courteous interval between outbound provider requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def is_available(self) -> bool:
        """Checks if the provider is operational and enabled."""
        return self.enabled

    @abc.abstractmethod
    def search(
        self,
        query: str,
        requirements: Optional[Dict[str, Any]] = None,
        limit: int = 5
    ) -> List[AssetCandidate]:
        """
        Executes a media search for candidates matching the query and requirements.
        Must catch internal errors and return empty list rather than crashing.
        """
        pass

    def download(self, candidate: AssetCandidate, dest_path: Path) -> Path:
        """
        Downloads the asset media to the specified local path using bounded streaming.
        """
        if not candidate.download_url:
            raise ProviderDownloadError(f"Candidate '{candidate.candidate_id}' has no download_url")
        return self.stream_to_file(candidate.download_url, dest_path)

    def stream_to_file(
        self,
        url: str,
        dest_path: Path,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout_sec: float = DEFAULT_READ_TIMEOUT,
    ) -> Path:
        """
        Safely streams a remote URL to disk with SSRF checking and bounded memory.
        """
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        if not is_safe:
            raise ProviderDownloadError(f"SSRF rejection for URL '{url}': {reason}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_rate_limit()

        attempt = 0
        backoff = 1.0

        while attempt < self.max_retries:
            attempt += 1
            try:
                with self.session.get(
                    url,
                    stream=True,
                    timeout=(DEFAULT_CONNECT_TIMEOUT, timeout_sec),
                    allow_redirects=True,
                ) as resp:
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", backoff))
                        logger.warning(f"[{self.name}] Rate limited (429). Backing off for {retry_after:.1f}s")
                        time.sleep(retry_after)
                        continue

                    if resp.status_code != 200:
                        raise ProviderDownloadError(
                            f"HTTP {resp.status_code} error downloading from '{url}'"
                        )

                    # Validate redirect target against SSRF
                    if resp.history:
                        for hop in resp.history:
                            hop_safe, hop_reason = SafeURLValidator.is_safe_url(hop.url)
                            if not hop_safe:
                                raise ProviderDownloadError(f"SSRF violation on redirect '{hop.url}': {hop_reason}")

                    content_length = resp.headers.get("Content-Length")
                    if content_length and int(content_length) > max_bytes:
                        raise ProviderDownloadError(
                            f"Remote file size ({content_length} bytes) exceeds maximum ceiling ({max_bytes} bytes)"
                        )

                    bytes_downloaded = 0
                    with open(dest_path, "wb") as f_out:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                bytes_downloaded += len(chunk)
                                if bytes_downloaded > max_bytes:
                                    raise ProviderDownloadError(
                                        f"Download aborted: file exceeded maximum size ({max_bytes} bytes)"
                                    )
                                f_out.write(chunk)

                    if bytes_downloaded == 0:
                        raise ProviderDownloadError(f"Downloaded 0 bytes from '{url}'")

                    logger.debug(f"[{self.name}] Successfully downloaded {bytes_downloaded} bytes to {dest_path.name}")
                    return dest_path

            except (requests.RequestException, IOError) as err:
                logger.warning(f"[{self.name}] Attempt {attempt}/{self.max_retries} failed for '{url}': {err}")
                if attempt >= self.max_retries:
                    if dest_path.exists():
                        dest_path.unlink(missing_ok=True)
                    raise ProviderDownloadError(f"Failed to download '{url}' after {self.max_retries} attempts: {err}")
                time.sleep(backoff)
                backoff *= 2.0

        raise ProviderDownloadError(f"Failed to stream '{url}' after {self.max_retries} attempts")
