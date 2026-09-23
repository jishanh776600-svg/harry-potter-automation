"""
STORY FORGE — Internet Archive Asset Provider
==============================================
Searches and acquires open archival video, historical recordings,
and public domain media from the Internet Archive (archive.org).
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any

from core.acquisition_types import (
    AssetCandidate,
    AssetProvenance,
    MediaCategory,
    RightsClassification,
    RightsMetadata,
    SourceCategory,
)
from engines.acquisition.providers.base_provider import AssetSourceProvider

logger = logging.getLogger("AssetAcquisition.ArchiveOrg")

ARCHIVE_SEARCH_ENDPOINT = "https://archive.org/advancedsearch.php"
ARCHIVE_METADATA_ENDPOINT = "https://archive.org/metadata"


class InternetArchiveProvider(AssetSourceProvider):
    """
    Retrieves archival open video and imagery from archive.org.
    """

    def __init__(self, enabled: bool = True, rate_limit_delay: float = 0.5):
        super().__init__(
            name="archive_org",
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
        Searches archive.org for matching video/image items.
        """
        if not self.enabled or not query.strip():
            return []

        self._apply_rate_limit()

        req_media_type = (requirements or {}).get("target_media_category")
        media_filter = "mediatype:(movies OR image)"
        if req_media_type == MediaCategory.VIDEO or req_media_type == "video":
            media_filter = "mediatype:(movies)"
        elif req_media_type == MediaCategory.IMAGE or req_media_type == "image":
            media_filter = "mediatype:(image)"

        clean_q = query.replace('"', "").strip()
        search_query = f"({clean_q}) AND {media_filter}"

        params = {
            "q": search_query,
            "fl[]": ["identifier", "title", "description", "mediatype", "licenseurl", "publicdate"],
            "sort[]": "downloads desc",
            "rows": min(limit * 2, 10),
            "page": 1,
            "output": "json",
        }

        try:
            resp = self.session.get(ARCHIVE_SEARCH_ENDPOINT, params=params, timeout=12.0)
            if resp.status_code != 200:
                logger.warning(f"[ArchiveOrg] API search returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            docs = data.get("response", {}).get("docs", [])
            if not docs:
                return []

            candidates: List[AssetCandidate] = []

            for doc in docs:
                identifier = doc.get("identifier")
                if not identifier:
                    continue

                # Fetch item files to locate best media stream
                meta_url = f"{ARCHIVE_METADATA_ENDPOINT}/{identifier}"
                try:
                    meta_resp = self.session.get(meta_url, timeout=10.0)
                    if meta_resp.status_code != 200:
                        continue
                    item_meta = meta_resp.json()
                except Exception:
                    continue

                files = item_meta.get("files", [])
                target_file = None
                is_video = doc.get("mediatype") == "movies"

                if is_video:
                    for f in files:
                        fmt = f.get("format", "").lower()
                        name = f.get("name", "").lower()
                        if (fmt in ("512kb mpeg4", "h.264", "mp4") or name.endswith(".mp4")) and not name.startswith("."):
                            target_file = f
                            break
                else:
                    for f in files:
                        fmt = f.get("format", "").lower()
                        name = f.get("name", "").lower()
                        if fmt in ("jpeg", "png") or name.endswith((".jpg", ".png", ".webp")):
                            target_file = f
                            break

                if not target_file:
                    continue

                filename = target_file.get("name")
                download_url = f"https://archive.org/download/{identifier}/{filename}"
                preview_url = f"https://archive.org/services/img/{identifier}"

                license_url = doc.get("licenseurl", "")
                rights_cls = RightsClassification.PUBLIC_DOMAIN if "publicdomain" in license_url.lower() else RightsClassification.CREATIVE_COMMONS

                provenance = AssetProvenance(
                    source_url=f"https://archive.org/details/{identifier}",
                    provider_name=self.name,
                    search_query=query,
                    retrieved_at_iso=datetime.now(timezone.utc).isoformat(),
                    rights=RightsMetadata(
                        classification=rights_cls,
                        license_name="Archive.org Open Access",
                        license_url=license_url or None,
                        notes="Internet Archive Open Media collection",
                    ),
                    external_id=identifier,
                )

                candidate = AssetCandidate(
                    candidate_id=f"archive_{identifier}",
                    title=doc.get("title", identifier),
                    download_url=download_url,
                    preview_url=preview_url,
                    media_category=MediaCategory.VIDEO if is_video else MediaCategory.IMAGE,
                    source_category=SourceCategory.ARCHIVAL,
                    provenance=provenance,
                    score=0.80,
                    estimated_size_bytes=int(target_file.get("size", 0) or 0),
                    description=doc.get("description", "") or "",
                    extra_attributes={"identifier": identifier, "filename": filename},
                )
                candidates.append(candidate)
                if len(candidates) >= limit:
                    break

            return candidates

        except Exception as e:
            logger.warning(f"[ArchiveOrg] Error searching for '{query}': {e}")
            return []
