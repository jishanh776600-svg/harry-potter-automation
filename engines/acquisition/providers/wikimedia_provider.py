"""
STORY FORGE — Wikimedia Commons Asset Provider
================================================
Searches and acquires open-access, public domain, and Creative Commons
imagery, illustrations, architectural records, and encyclopedic media
from the Wikimedia Commons API.
"""

from datetime import datetime, timezone
import logging
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
from engines.acquisition.providers.base_provider import AssetSourceProvider

logger = logging.getLogger("AssetAcquisition.Wikimedia")

WIKIMEDIA_API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"


class WikimediaCommonsProvider(AssetSourceProvider):
    """
    Retrieves verified media and licensing metadata from Wikimedia Commons.
    """

    def __init__(self, enabled: bool = True, rate_limit_delay: float = 0.5):
        super().__init__(
            name="wikimedia_commons",
            enabled=enabled,
            rate_limit_delay=rate_limit_delay,
            max_retries=3,
        )

    def search(
        self,
        query: str,
        requirements: Optional[Dict[str, Any]] = None,
        limit: int = 5
    ) -> List[AssetCandidate]:
        """
        Queries the Wikimedia Commons MediaWiki API for matching media files.
        """
        if not self.enabled or not query.strip():
            return []

        self._apply_rate_limit()

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query.strip(),
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": min(limit * 2, 20),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
            "origin": "*",
        }

        try:
            resp = self.session.get(WIKIMEDIA_API_ENDPOINT, params=params, timeout=12.0)
            if resp.status_code != 200:
                logger.warning(f"[Wikimedia] API returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return []

            candidates: List[AssetCandidate] = []
            req_media_type = (requirements or {}).get("target_media_category")

            for page_id, page in pages.items():
                imageinfo_list = page.get("imageinfo", [])
                if not imageinfo_list:
                    continue

                info = imageinfo_list[0]
                file_url = info.get("url")
                if not file_url:
                    continue

                mime = info.get("mime", "").lower()
                media_cat = MediaCategory.IMAGE
                if "video" in mime or mime.endswith(("/webm", "/ogg", "/mp4")):
                    media_cat = MediaCategory.VIDEO
                elif "audio" in mime:
                    media_cat = MediaCategory.AUDIO

                if req_media_type and req_media_type != media_cat.value and req_media_type != media_cat:
                    continue

                # Parse rights and licensing
                extmeta = info.get("extmetadata", {})
                license_short = extmeta.get("LicenseShortName", {}).get("value", "Unknown")
                usage_terms = extmeta.get("UsageTerms", {}).get("value", "")
                artist = extmeta.get("Artist", {}).get("value", "")
                license_url = extmeta.get("LicenseUrl", {}).get("value", None)
                credit = extmeta.get("Credit", {}).get("value", "")

                rights_cls = RightsClassification.UNKNOWN
                l_lower = license_short.lower()
                if "public domain" in l_lower or "pd" in l_lower or "cc0" in l_lower:
                    rights_cls = RightsClassification.PUBLIC_DOMAIN
                elif "cc by" in l_lower or "creative commons" in l_lower:
                    rights_cls = RightsClassification.CREATIVE_COMMONS
                else:
                    rights_cls = RightsClassification.EDITORIAL_FAIR_USE

                rights = RightsMetadata(
                    classification=rights_cls,
                    license_name=license_short,
                    license_url=license_url,
                    author=artist or credit or None,
                    attribution_text=credit or artist or None,
                    commercial_cleared=(rights_cls in (RightsClassification.PUBLIC_DOMAIN, RightsClassification.CREATIVE_COMMONS)),
                    notes=usage_terms,
                )

                provenance = AssetProvenance(
                    source_url=info.get("descriptionurl", file_url),
                    provider_name=self.name,
                    search_query=query,
                    retrieved_at_iso=datetime.now(timezone.utc).isoformat(),
                    rights=rights,
                    external_id=str(page_id),
                )

                candidate = AssetCandidate(
                    candidate_id=f"wiki_{page_id}",
                    title=page.get("title", f"File_{page_id}").replace("File:", ""),
                    download_url=file_url,
                    preview_url=info.get("thumburl", file_url),
                    media_category=media_cat,
                    source_category=SourceCategory.ENCYCLOPEDIC,
                    provenance=provenance,
                    score=0.85,
                    estimated_size_bytes=int(info.get("size", 0)),
                    description=page.get("title", ""),
                    extra_attributes={
                        "width": info.get("width", 0),
                        "height": info.get("height", 0),
                        "mime": mime,
                    },
                )
                candidates.append(candidate)
                if len(candidates) >= limit:
                    break

            return candidates

        except Exception as e:
            logger.warning(f"[Wikimedia] Error executing search for '{query}': {e}")
            return []
