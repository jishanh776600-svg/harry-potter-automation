"""
STORY FORGE — Direct Web Media Provider
========================================
Acquires assets from direct web endpoints and verified public URLs
with strict SSRF defense, content-type verification, and streaming boundaries.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import urllib.parse

from core.acquisition_types import (
    AssetCandidate,
    AssetProvenance,
    MediaCategory,
    RightsClassification,
    RightsMetadata,
    SourceCategory,
)
from core.safe_url_validator import SafeURLValidator
from engines.acquisition.providers.base_provider import (
    AssetSourceProvider,
    ProviderDownloadError,
)

logger = logging.getLogger("AssetAcquisition.DirectWeb")


class DirectWebProvider(AssetSourceProvider):
    """
    Acquires media directly from public URLs, checking headers,
    content types, and SSRF restrictions before downloading.
    """

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="direct_web",
            enabled=enabled,
            rate_limit_delay=0.2,
            max_retries=3,
        )

    def search(
        self,
        query: str,
        requirements: Optional[Dict[str, Any]] = None,
        limit: int = 5
    ) -> List[AssetCandidate]:
        """
        DirectWebProvider doesn't crawl search engines blindly;
        if query is a direct valid URL, it wraps it into an AssetCandidate.
        """
        if not self.enabled or not query.strip():
            return []

        url = query.strip()
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        if not is_safe:
            logger.debug(f"[DirectWeb] Query is not a safe direct URL: {reason}")
            return []

        # Head request to probe media category and headers
        try:
            head_resp = self.session.head(url, timeout=5.0, allow_redirects=True)
            if head_resp.status_code != 200:
                return []

            content_type = head_resp.headers.get("Content-Type", "").lower()
            media_cat = MediaCategory.IMAGE
            if "video" in content_type or url.lower().endswith((".mp4", ".webm", ".mkv")):
                media_cat = MediaCategory.VIDEO
            elif "audio" in content_type:
                media_cat = MediaCategory.AUDIO

            content_length = int(head_resp.headers.get("Content-Length", 0) or 0)
            parsed_path = urllib.parse.urlparse(url).path
            filename = Path(parsed_path).name or "direct_asset"

            candidate = AssetCandidate(
                candidate_id=f"direct_{abs(hash(url)) % 10000000}",
                title=filename,
                download_url=url,
                preview_url=url if media_cat == MediaCategory.IMAGE else None,
                media_category=media_cat,
                source_category=SourceCategory.DIRECT_WEB,
                provenance=AssetProvenance(
                    source_url=url,
                    provider_name=self.name,
                    search_query=query,
                    retrieved_at_iso=datetime.now(timezone.utc).isoformat(),
                    rights=RightsMetadata(
                        classification=RightsClassification.EDITORIAL_FAIR_USE,
                        license_name="Direct Web Reference",
                        commercial_cleared=False,
                    ),
                ),
                score=0.90,
                estimated_size_bytes=content_length,
                description=f"Direct media from {urllib.parse.urlparse(url).netloc}",
            )
            return [candidate]

        except Exception as e:
            logger.debug(f"[DirectWeb] Probing '{url}' failed: {e}")
            return []
