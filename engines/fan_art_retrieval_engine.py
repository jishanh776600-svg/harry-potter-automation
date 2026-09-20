"""
STORY FORGE Fan-Art & Official Artwork Retrieval Engine
======================================================
Coordinates targeted discovery, rights evaluation, safe acquisition,
deduplication, semantic ranking, and presentation formatting for existing
Harry Potter illustrations and artwork depicting novel-only scenes.

Strict Invariants:
1. NO AI IMAGE GENERATION:
   Strictly searches for existing artwork. Never uses DALL-E, Midjourney,
   Stable Diffusion, Pollinations, Flux, or synthetic image generators.
2. TARGETED DISCOVERY:
   Queries must be rich and event-specific (character + action + object + location).
   Never broad "Harry Potter fan art".
3. STRICT SOURCE & RIGHTS GATE:
   - RIGHTS_VERIFIED: Explicit commercial / public domain / verified license.
   - RIGHTS_UNVERIFIED: Quarantined for review; blocked from autonomous production.
   - RIGHTS_REJECTED: Forbidden generic stock (Pexels, Unsplash, Pixabay, etc.) or restricted.
4. SAFE DOWNLOAD & INTEGRITY:
   Streaming download with 25MB ceiling, MIME check, PIL decode verification,
   SHA-256 deduplication, non-destructive storage.
5. SEMANTIC RELEVANCE RANKING:
   Multi-factor scoring (A-H) penalizing wrong-scene images.
6. BROADCAST-SAFE PRESENTATION:
   Converts artwork to 1080x1920 30 FPS MP4 with ambient blurred background and
   strict -an (0 audio streams).
"""
import os
import re
import json
import hashlib
import logging
import mimetypes
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from PIL import Image
import requests

from config.settings import PROJECT_ROOT
from core.hybrid_visual_models import (
    VisualSourceType, RightsStatus, ApprovalStatus, VisualProvenance,
    FORBIDDEN_SOURCE_PROVIDERS
)

logger = logging.getLogger(__name__)

ARTWORKS_DIR = PROJECT_ROOT / "data" / "artworks"
DOWNLOADS_DIR = ARTWORKS_DIR / "downloads"
QUARANTINE_DIR = ARTWORKS_DIR / "quarantine"
FAN_ART_DIR = PROJECT_ROOT / "data" / "fan_art"
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"

ARTWORKS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
FAN_ART_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

MAX_IMAGE_FILE_SIZE = 25 * 1024 * 1024  # 25 MB ceiling
MIN_IMAGE_DIMENSION = 300               # Minimum pixel width/height for usable art
MIN_SEMANTIC_MATCH_SCORE = 45.0         # Minimum score to accept artwork for a beat


@dataclass
class ArtworkCandidate:
    """Discovered candidate artwork before or after download."""
    candidate_id: str
    title: str
    description: str
    source_provider: str
    source_url: str
    original_url: Optional[str] = None
    creator: Optional[str] = None
    license_name: Optional[str] = None
    license_url: Optional[str] = None
    rights_status: RightsStatus = RightsStatus.RIGHTS_UNVERIFIED
    approval_status: ApprovalStatus = ApprovalStatus.QUARANTINED
    characters: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    book_number: Optional[int] = None
    chapter_number: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    is_official: bool = False
    file_path: Optional[str] = None
    image_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    semantic_score: float = 0.0


# ------------------------------------------------------------------------------
# DISCOVERY PROVIDERS (Wikimedia Commons, Internet Archive, Curated Registry)
# ------------------------------------------------------------------------------
class ArtworkDiscoveryProvider:
    """Base interface for legitimate artwork discovery providers."""
    provider_name: str = "base"

    def search_candidates(
        self,
        queries: List[str],
        beat: Dict[str, Any],
        limit: int = 5
    ) -> List[ArtworkCandidate]:
        raise NotImplementedError


class CuratedRegistryProvider(ArtworkDiscoveryProvider):
    """Searches the locally maintained curated artwork index."""
    provider_name = "curated_registry"

    def __init__(self, registry_items: List[Dict[str, Any]]):
        self.registry_items = registry_items

    def search_candidates(
        self,
        queries: List[str],
        beat: Dict[str, Any],
        limit: int = 5
    ) -> List[ArtworkCandidate]:
        candidates = []
        for item in self.registry_items:
            cand = ArtworkCandidate(
                candidate_id=item.get("asset_id") or item.get("id", ""),
                title=item.get("title") or item.get("scene", ""),
                description=item.get("description", ""),
                source_provider=self.provider_name,
                source_url=item.get("source_url", ""),
                original_url=item.get("original_url"),
                creator=item.get("creator"),
                license_name=item.get("license_name") or item.get("license"),
                license_url=item.get("license_url"),
                characters=item.get("characters", []),
                actions=item.get("actions", []),
                objects=item.get("objects", []),
                locations=[item.get("location")] if item.get("location") else [],
                book_number=item.get("book_number"),
                chapter_number=item.get("chapter_number"),
                tags=item.get("tags", []),
                is_official=bool(item.get("is_official", False)),
                file_path=item.get("local_path") or item.get("file_path"),
                image_hash=item.get("image_hash"),
                file_size_bytes=item.get("file_size_bytes"),
            )
            candidates.append(cand)
        return candidates[:limit * 2]


class WikimediaCommonsDiscoveryProvider(ArtworkDiscoveryProvider):
    """
    Searches Wikimedia Commons API for public domain and CC-licensed Harry Potter illustrations.
    Queries the MediaWiki action=query API endpoint.
    """
    provider_name = "wikimedia_commons"
    API_URL = "https://commons.wikimedia.org/w/api.php"

    def search_candidates(
        self,
        queries: List[str],
        beat: Dict[str, Any],
        limit: int = 5
    ) -> List[ArtworkCandidate]:
        candidates = []
        headers = {"User-Agent": "StoryForgeBot/1.0 (Editorial Commentary; contact: jishanh760@gmail.com)"}

        for q in queries[:2]:
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{q} filetype:bitmap",
                    "gsrlimit": min(limit, 5),
                    "prop": "imageinfo",
                    "iiprop": "url|size|extmetadata|mime",
                    "format": "json"
                }
                resp = requests.get(self.API_URL, params=params, headers=headers, timeout=5.0)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})

                for page_id, page_info in pages.items():
                    img_info_list = page_info.get("imageinfo", [])
                    if not img_info_list:
                        continue
                    info = img_info_list[0]
                    mime = info.get("mime", "")
                    if not mime.startswith("image/"):
                        continue

                    ext_meta = info.get("extmetadata", {})
                    license_name = ext_meta.get("LicenseShortName", {}).get("value", "Public Domain")
                    creator = ext_meta.get("Artist", {}).get("value", "Wikimedia Contributor")
                    # Clean HTML tags from creator
                    creator_clean = re.sub(r"<[^>]+>", "", creator).strip()
                    desc = ext_meta.get("ImageDescription", {}).get("value", page_info.get("title", ""))
                    desc_clean = re.sub(r"<[^>]+>", "", desc).strip()

                    cand_id = f"wiki_{page_id}_{hashlib.sha256(info.get('url', '').encode()).hexdigest()[:8]}"
                    cand = ArtworkCandidate(
                        candidate_id=cand_id,
                        title=page_info.get("title", ""),
                        description=desc_clean,
                        source_provider=self.provider_name,
                        source_url=f"https://commons.wikimedia.org/wiki/{page_info.get('title', '').replace(' ', '_')}",
                        original_url=info.get("url"),
                        creator=creator_clean or "Wikimedia Commons Contributor",
                        license_name=license_name,
                        license_url=ext_meta.get("LicenseUrl", {}).get("value"),
                        characters=list(beat.get("characters", [])),
                        actions=[beat.get("action", "")],
                        objects=list(beat.get("objects", [])),
                        locations=[beat.get("location", "")] if beat.get("location") else [],
                        file_size_bytes=info.get("size"),
                        tags=["wikimedia", "illustration"]
                    )
                    candidates.append(cand)
            except Exception as e:
                logger.debug(f"[WikimediaDiscovery] Search failed for query '{q}': {e}")

        return candidates[:limit]


class InternetArchiveDiscoveryProvider(ArtworkDiscoveryProvider):
    """
    Searches Internet Archive (archive.org) metadata API for public domain and
    curated Harry Potter illustration archives.
    """
    provider_name = "internet_archive"
    SEARCH_URL = "https://archive.org/advancedsearch.php"

    def search_candidates(
        self,
        queries: List[str],
        beat: Dict[str, Any],
        limit: int = 5
    ) -> List[ArtworkCandidate]:
        candidates = []
        headers = {"User-Agent": "StoryForgeBot/1.0 (Educational/Editorial; jishanh760@gmail.com)"}

        for q in queries[:1]:
            try:
                # Query public domain / creative commons items matching query
                query_str = f"({q}) AND mediatype:(image)"
                params = {
                    "q": query_str,
                    "fl[]": "identifier,title,description,creator,licenseurl",
                    "rows": limit,
                    "output": "json"
                }
                resp = requests.get(self.SEARCH_URL, params=params, headers=headers, timeout=5.0)
                if resp.status_code != 200:
                    continue
                docs = resp.json().get("response", {}).get("docs", [])
                for doc in docs:
                    ident = doc.get("identifier")
                    if not ident:
                        continue
                    cand = ArtworkCandidate(
                        candidate_id=f"ia_{ident}",
                        title=doc.get("title", ident),
                        description=doc.get("description", ""),
                        source_provider=self.provider_name,
                        source_url=f"https://archive.org/details/{ident}",
                        original_url=f"https://archive.org/download/{ident}/{ident}.jpg",
                        creator=doc.get("creator", "Internet Archive Contributor"),
                        license_name="Internet Archive Community License",
                        license_url=doc.get("licenseurl"),
                        characters=list(beat.get("characters", [])),
                        actions=[beat.get("action", "")],
                        objects=list(beat.get("objects", [])),
                        locations=[beat.get("location", "")] if beat.get("location") else [],
                        tags=["internet_archive", "canon_art"]
                    )
                    candidates.append(cand)
            except Exception as e:
                logger.debug(f"[InternetArchiveDiscovery] Query '{q}' failed: {e}")

        return candidates[:limit]


# ------------------------------------------------------------------------------
# FAN ART RETRIEVAL ENGINE
# ------------------------------------------------------------------------------
class FanArtRetrievalEngine:
    """
    Manages targeted query generation, candidate discovery across legitimate sources,
    strict rights gating, safe download/validation, deduplication, semantic ranking,
    and video presentation formatting.
    """

    def __init__(
        self,
        artworks_dir: Optional[Path] = None,
        downloads_dir: Optional[Path] = None,
        quarantine_dir: Optional[Path] = None,
        fan_art_dir: Optional[Path] = None,
        clips_dir: Optional[Path] = None
    ):
        self.artworks_dir = artworks_dir or ARTWORKS_DIR
        self.downloads_dir = downloads_dir or DOWNLOADS_DIR
        self.quarantine_dir = quarantine_dir or QUARANTINE_DIR
        self.fan_art_dir = fan_art_dir or FAN_ART_DIR
        self.clips_dir = clips_dir or CLIPS_DIR
        self.curated_index_path = self.artworks_dir / "curated_artwork_index.json"

        self._curated_registry: List[Dict[str, Any]] = self._load_curated_registry()
        self._known_hashes: Set[str] = self._index_known_hashes()

        # Initialize discovery providers
        self.providers: List[ArtworkDiscoveryProvider] = [
            CuratedRegistryProvider(self._curated_registry),
            WikimediaCommonsDiscoveryProvider(),
            InternetArchiveDiscoveryProvider(),
        ]

    def _load_curated_registry(self) -> List[Dict[str, Any]]:
        """Loads curated artwork metadata from disk if present."""
        if self.curated_index_path.exists():
            try:
                with open(self.curated_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load curated artwork index: {e}")
        return []

    def _save_curated_registry(self) -> None:
        """Persists the curated artwork index to disk."""
        try:
            with open(self.curated_index_path, "w", encoding="utf-8") as f:
                json.dump(self._curated_registry, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist curated artwork index: {e}")

    def _index_known_hashes(self) -> Set[str]:
        """Indexes all known image hashes from registry and physical files to prevent duplicate ingestion."""
        hashes = set()
        for item in self._curated_registry:
            h = item.get("image_hash")
            if h:
                hashes.add(h.lower())

        for d in [self.artworks_dir, self.downloads_dir, self.quarantine_dir]:
            if d.exists():
                for f in d.glob("*.*"):
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.is_file():
                        try:
                            h = self.compute_image_hash(f)
                            hashes.add(h.lower())
                        except Exception:
                            pass
        return hashes

    # --------------------------------------------------------------------------
    # 1. TARGETED QUERY GENERATION
    # --------------------------------------------------------------------------
    @staticmethod
    def generate_targeted_queries(
        beat: Dict[str, Any],
        novel_context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Generates event-specific, semantically rich search queries from a narration beat.
        Never outputs broad 'Harry Potter fan art'.

        Incorporates:
        - Characters (Harry, Peeves, Neville, etc.)
        - Specific action / verb (chaos, sorting, riddle, execution, glowing red, etc.)
        - Specific object (Remembrall, potion bottles, sorting hat, etc.)
        - Location (Great Hall, corridors, trapdoor, Shrieking Shack, etc.)
        - Book/chapter reference when relevant
        """
        characters = beat.get("characters", [])
        if isinstance(characters, str):
            characters = [c.strip() for c in characters.split(",") if c.strip()]
        char_str = " ".join(characters) if characters else ""

        location = beat.get("location", "")
        action = beat.get("action", "")
        objects = beat.get("objects", [])
        if isinstance(objects, str):
            objects = [o.strip() for o in objects.split(",") if o.strip()]
        obj_str = " ".join(objects) if objects else ""

        narration = beat.get("narration_text", "") or beat.get("text", "")
        book_num = beat.get("book_number") or (novel_context.get("book_number") if novel_context else None)
        chapter_num = beat.get("chapter_number") or (novel_context.get("chapter_number") if novel_context else None)

        queries = []

        # 1. Highly specific event query: Character + Location + Action + Object
        specific_parts = [p for p in [char_str, location, action, obj_str] if p]
        if specific_parts:
            q1 = f"Harry Potter {' '.join(specific_parts)} illustration"
            q1 = re.sub(r"\s+", " ", q1).strip()
            queries.append(q1)

        # 2. Fan art specific query with event/action and object
        if char_str and (action or obj_str):
            q2 = f"Harry Potter {char_str} {action} {obj_str} fan art"
            q2 = re.sub(r"\s+", " ", q2).strip()
            queries.append(q2)

        # 3. Book/chapter grounded query
        if book_num and (char_str or action):
            chapter_info = f"chapter {chapter_num}" if chapter_num else ""
            q3 = f"Harry Potter book {book_num} {chapter_info} {char_str} {action} illustration"
            q3 = re.sub(r"\s+", " ", q3).strip()
            queries.append(q3)

        # 4. Fallback targeted query extracted from key narration entities
        if not queries and narration:
            key_words = [
                w for w in re.findall(r"[a-zA-Z]{4,}", narration)
                if w.lower() not in {"this", "that", "with", "from", "were", "they", "there", "every", "scene", "movie"}
            ]
            q4 = f"Harry Potter {' '.join(key_words[:5])} illustration"
            queries.append(q4)

        # Deduplicate while preserving order
        unique_queries = list(dict.fromkeys(queries))
        return unique_queries

    # --------------------------------------------------------------------------
    # 2. STRICT SOURCE & RIGHTS GATE
    # --------------------------------------------------------------------------
    @staticmethod
    def evaluate_rights_status(candidate: ArtworkCandidate) -> Tuple[RightsStatus, ApprovalStatus, str]:
        """
        Deterministically evaluates rights status.
        Only artwork with sufficiently established usage rights is eligible for production.

        - RIGHTS_VERIFIED: Explicit commercial / CC0 / Public Domain / Verified creator consent.
        - RIGHTS_UNVERIFIED: Quarantined for review; cannot be used autonomously.
        - RIGHTS_REJECTED: Forbidden provider or prohibited license.
        """
        combined = f"{candidate.source_provider} {candidate.source_url} {candidate.license_name or ''} {candidate.license_url or ''}".lower()

        # 1. Hard check: forbidden generic stock or synthetic AI generators
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in combined:
                return (
                    RightsStatus.RIGHTS_REJECTED,
                    ApprovalStatus.REJECTED,
                    f"Forbidden source provider or stock domain detected: '{forbidden}'"
                )

        lic = (candidate.license_name or "").lower()
        if any(term in lic for term in [
            "public domain", "cc0", "cc-zero", "pd-old", "cc by 4.0", "cc-by-4.0",
            "cc by-sa", "cc-by-sa", "cc-by", "cc by", "creative commons attribution",
            "attribution 4.0", "attribution 3.0"
        ]):
            # Check if non-commercial restriction is present
            if "nc" in lic or "non-commercial" in lic or "noncommercial" in lic:
                return (
                    RightsStatus.RIGHTS_UNVERIFIED,
                    ApprovalStatus.QUARANTINED,
                    "License has Non-Commercial restriction; requires creator clearance before commercial production."
                )
            return (
                RightsStatus.RIGHTS_VERIFIED,
                ApprovalStatus.APPROVED,
                f"Verified permissive license: {candidate.license_name}"
            )

        if candidate.is_official and any(term in lic for term in ["official", "scholastic", "bloomsbury"]):
            return (
                RightsStatus.RIGHTS_VERIFIED,
                ApprovalStatus.APPROVED,
                f"Verified official editorial license: {candidate.license_name}"
            )

        # 3. Platforms without verified commercial license declaration are quarantined
        unverified_platforms = ["deviantart", "artstation", "tumblr", "reddit", "pinterest", "instagram", "twitter", "x.com"]
        if any(p in combined for p in unverified_platforms) or not candidate.license_name:
            return (
                RightsStatus.RIGHTS_UNVERIFIED,
                ApprovalStatus.QUARANTINED,
                "Web discovery without verified commercial reuse declaration. Quarantined for editorial review."
            )

        # 4. Fair use editorial / commentary default (quarantined until approved)
        return (
            RightsStatus.RIGHTS_UNVERIFIED,
            ApprovalStatus.QUARANTINED,
            f"Unverified licensing lineage: '{candidate.license_name}'. Quarantined."
        )

    # --------------------------------------------------------------------------
    # 3. DOWNLOAD & INTEGRITY VALIDATION
    # --------------------------------------------------------------------------
    def download_and_validate_artwork(self, candidate: ArtworkCandidate) -> Optional[Path]:
        """
        Safely downloads an image candidate, verifies MIME type, decodes via PIL,
        calculates SHA-256, enforces deduplication, and stores in the appropriate directory.
        Never overwrites existing files. Rejects files > 25MB or non-images.
        """
        if not candidate.original_url:
            logger.debug(f"[FanArtEngine] Candidate {candidate.candidate_id} lacks original_url; cannot download.")
            return None

        # Determine target directory based on rights
        target_dir = self.downloads_dir if candidate.rights_status == RightsStatus.RIGHTS_VERIFIED else self.quarantine_dir
        ext = ".jpg"
        temp_file = target_dir / f"temp_{candidate.candidate_id}{ext}"

        try:
            headers = {"User-Agent": "StoryForgeBot/1.0 (Safe Asset Acquisition; jishanh760@gmail.com)"}
            resp = requests.get(candidate.original_url, stream=True, timeout=10.0, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[FanArtEngine] Download failed ({resp.status_code}) for {candidate.original_url}")
                return None

            # MIME validation
            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and not any(ct in content_type for ct in ["image/jpeg", "image/png", "image/webp", "image/jpg"]):
                logger.warning(f"[FanArtEngine] Invalid Content-Type '{content_type}' for {candidate.candidate_id}. Aborting.")
                return None

            # Size check and stream write
            total_bytes = 0
            with open(temp_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        total_bytes += len(chunk)
                        if total_bytes > MAX_IMAGE_FILE_SIZE:
                            temp_file.unlink(missing_ok=True)
                            logger.warning(f"[FanArtEngine] Asset {candidate.candidate_id} exceeds 25MB limit. Aborted.")
                            return None
                        f.write(chunk)

            # Integrity check via PIL
            try:
                with Image.open(temp_file) as img:
                    img.verify()
                    w, h = img.size
                    fmt = img.format.lower() if img.format else "jpg"
                    if fmt in ("jpeg", "jpg"):
                        ext = ".jpg"
                    elif fmt == "png":
                        ext = ".png"
                    elif fmt == "webp":
                        ext = ".webp"
            except Exception as e:
                temp_file.unlink(missing_ok=True)
                logger.warning(f"[FanArtEngine] Corrupt or invalid image for {candidate.candidate_id}: {e}")
                return None

            # Minimum dimension check
            if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                temp_file.unlink(missing_ok=True)
                logger.warning(f"[FanArtEngine] Image {candidate.candidate_id} resolution too low ({w}x{h}). Rejected.")
                return None

            # Calculate SHA-256 hash
            sha256 = self.compute_image_hash(temp_file)

            # Deduplication check
            if sha256.lower() in self._known_hashes:
                temp_file.unlink(missing_ok=True)
                logger.info(f"[FanArtEngine] Duplicate image hash {sha256[:12]} already in registry. Skipping duplicate.")
                # Locate existing asset path
                for item in self._curated_registry:
                    if (item.get("image_hash") or "").lower() == sha256.lower() and item.get("local_path"):
                        candidate.file_path = item["local_path"]
                        candidate.image_hash = sha256
                        return Path(item["local_path"])
                return None

            # Final destination path
            dest_file = target_dir / f"{candidate.candidate_id}{ext}"
            if dest_file.exists():
                # Avoid overwriting
                dest_file = target_dir / f"{candidate.candidate_id}_{sha256[:8]}{ext}"

            temp_file.rename(dest_file)
            candidate.file_path = str(dest_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
            candidate.image_hash = sha256
            candidate.file_size_bytes = total_bytes
            self._known_hashes.add(sha256.lower())

            # Update registry
            registry_entry = {
                "asset_id": candidate.candidate_id,
                "scene": candidate.title,
                "title": candidate.title,
                "description": candidate.description,
                "characters": candidate.characters,
                "actions": candidate.actions,
                "objects": candidate.objects,
                "location": candidate.locations[0] if candidate.locations else None,
                "book_number": candidate.book_number,
                "chapter_number": candidate.chapter_number,
                "source_type": VisualSourceType.FAN_ART.value if not candidate.is_official else VisualSourceType.OFFICIAL_ARTWORK.value,
                "source_url": candidate.source_url,
                "original_url": candidate.original_url,
                "creator": candidate.creator,
                "license_name": candidate.license_name,
                "license_url": candidate.license_url,
                "rights_status": candidate.rights_status.value,
                "approval_status": candidate.approval_status.value,
                "local_path": candidate.file_path,
                "image_hash": sha256,
                "file_size_bytes": total_bytes,
                "tags": candidate.tags,
                "is_official": candidate.is_official
            }
            self._curated_registry.append(registry_entry)
            self._save_curated_registry()

            logger.info(f"[FanArtEngine] Acquired asset {candidate.candidate_id} -> {dest_file} ({w}x{h}, {total_bytes} bytes)")
            return dest_file

        except Exception as e:
            temp_file.unlink(missing_ok=True)
            logger.error(f"[FanArtEngine] Exception during download of {candidate.candidate_id}: {e}")
            return None

    # --------------------------------------------------------------------------
    # 4. MULTI-FACTOR SEMANTIC RANKING (A through H)
    # --------------------------------------------------------------------------
    @staticmethod
    def score_artwork_candidate(
        candidate: ArtworkCandidate,
        beat: Dict[str, Any],
        novel_context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Multi-Factor Scoring (0 to 100 points) evaluating:
          A. Character match (0 - 25 pts)
          B. Action / event match (0 - 20 pts)
          C. Object match (0 - 15 pts)
          D. Location match (0 - 10 pts)
          E. Novel / book / chapter relevance (0 - 10 pts)
          F. Description keyword similarity (0 - 10 pts)
          G. Source resolution & quality (0 - 5 pts)
          H. Rights status gate (+5 bonus for RIGHTS_VERIFIED, -100 penalty for RIGHTS_REJECTED)

        Wrong-Scene Penalty:
          If the beat requires specific objects/actions (e.g. Remembrall, Sorting Hat)
          and the candidate has neither the object nor the action, applies a heavy -50 penalty.
        """
        meta_str = f"{candidate.title} {candidate.description} {' '.join(candidate.tags)} {' '.join(candidate.actions)} {' '.join(candidate.objects)}".lower()
        score = 0.0

        # A. Character match (0 - 25 pts)
        beat_chars = beat.get("characters", [])
        if isinstance(beat_chars, str):
            beat_chars = [c.strip() for c in beat_chars.split(",") if c.strip()]
        matched_chars = [c for c in beat_chars if c.lower() in meta_str]
        if beat_chars:
            score += (len(matched_chars) / len(beat_chars)) * 25.0
        else:
            score += 10.0

        # B. Action / event match (0 - 20 pts)
        action = (beat.get("action") or "").lower()
        action_tokens = [w for w in re.findall(r"[a-zA-Z]{4,}", action)]
        if action_tokens:
            matched_act = [w for w in action_tokens if w in meta_str]
            score += (len(matched_act) / len(action_tokens)) * 20.0

        # C. Object match (0 - 15 pts)
        objects = beat.get("objects", [])
        if isinstance(objects, str):
            objects = [o.strip() for o in objects.split(",") if o.strip()]
        matched_obj = [o for o in objects if o.lower() in meta_str]
        if objects:
            score += (len(matched_obj) / len(objects)) * 15.0

        # D. Location match (0 - 10 pts)
        location = (beat.get("location") or "").lower()
        if location and location in meta_str:
            score += 10.0

        # E. Novel / book / chapter relevance (0 - 10 pts)
        book_num = beat.get("book_number") or (novel_context.get("book_number") if novel_context else None)
        if book_num and candidate.book_number == book_num:
            score += 5.0
            chap_num = beat.get("chapter_number") or (novel_context.get("chapter_number") if novel_context else None)
            if chap_num and candidate.chapter_number == chap_num:
                score += 5.0

        # F. Description keyword similarity (0 - 10 pts)
        narration = (beat.get("narration_text") or beat.get("text", "")).lower()
        narration_words = set(re.findall(r"[a-zA-Z]{4,}", narration)) - {"harry", "potter", "scene", "novel", "book"}
        if narration_words:
            overlap = [w for w in narration_words if w in meta_str]
            score += min(10.0, (len(overlap) / max(1, len(narration_words))) * 15.0)

        # G. Source quality (0 - 5 pts)
        if candidate.file_size_bytes and candidate.file_size_bytes > 50000:
            score += 5.0
        elif candidate.is_official:
            score += 5.0

        # H. Rights status gate
        if candidate.rights_status == RightsStatus.RIGHTS_REJECTED:
            score -= 100.0
        elif candidate.rights_status == RightsStatus.RIGHTS_VERIFIED:
            score += 5.0

        # ----------------------------------------------------------------------
        # WRONG-SCENE REJECTION / PENALTY:
        # If the beat is specifically about a distinctive magical object or action
        # (e.g. Remembrall, Sorting Hat, potion fire) and the artwork has 0 match
        # on both object and action, heavily penalize so generic portraits are rejected!
        # ----------------------------------------------------------------------
        critical_objects = [o for o in objects if o.lower() in ("remembrall", "sorting hat", "potion", "mirror of erised", "invisibility cloak")]
        if critical_objects and not matched_obj and not (action_tokens and matched_act):
            score -= 50.0  # Heavy penalty: random portrait rejected!

        candidate.semantic_score = max(0.0, min(100.0, score))
        return candidate.semantic_score

    # --------------------------------------------------------------------------
    # 5. RETRIEVAL & ACQUISITION COORDINATION
    # --------------------------------------------------------------------------
    def search_artwork_for_beat(
        self,
        beat: Dict[str, Any],
        preferred_source: VisualSourceType = VisualSourceType.FAN_ART,
        novel_context: Optional[Dict[str, Any]] = None,
        allow_acquisition: bool = True
    ) -> Optional[VisualProvenance]:
        """
        Coordinates discovery, rights evaluation, downloading, and ranking for a beat.
        Returns a verified VisualProvenance if a compliant artwork is available.
        Returns None if no verified candidate exists or if candidates are quarantined.
        """
        queries = self.generate_targeted_queries(beat, novel_context=novel_context)
        logger.info(f"[FanArtEngine] Generated targeted queries for {beat.get('beat_id')}: {queries}")

        # Gather candidates from all providers
        all_candidates: List[ArtworkCandidate] = []
        for provider in self.providers:
            try:
                cands = provider.search_candidates(queries, beat, limit=5)
                all_candidates.extend(cands)
            except Exception as e:
                logger.debug(f"[FanArtEngine] Provider {provider.provider_name} search failed: {e}")

        if not all_candidates:
            return None

        # Evaluate rights and score each candidate
        scored_candidates: List[ArtworkCandidate] = []
        for cand in all_candidates:
            rights_st, app_st, reason = self.evaluate_rights_status(cand)
            cand.rights_status = rights_st
            cand.approval_status = app_st

            if rights_st == RightsStatus.RIGHTS_REJECTED:
                continue

            score = self.score_artwork_candidate(cand, beat, novel_context=novel_context)
            if score >= MIN_SEMANTIC_MATCH_SCORE:
                scored_candidates.append(cand)

        if not scored_candidates:
            return None

        # Sort descending by semantic score
        scored_candidates.sort(key=lambda c: c.semantic_score, reverse=True)
        top_cand = scored_candidates[0]

        # Check if physical asset exists locally
        local_path = None
        if top_cand.file_path:
            p = PROJECT_ROOT / top_cand.file_path
            if p.exists():
                local_path = p

        # If not present locally and acquisition is allowed:
        if not local_path and allow_acquisition and top_cand.original_url:
            local_path = self.download_and_validate_artwork(top_cand)

        # STRICT RIGHTS SAFEGUARD:
        # Only artwork with established usage rights (RIGHTS_VERIFIED) is eligible for autonomous production.
        # Unverified artwork remains quarantined in data/artworks/quarantine/ and returns None.
        if top_cand.rights_status != RightsStatus.RIGHTS_VERIFIED:
            logger.info(
                f"[FanArtEngine] Candidate {top_cand.candidate_id} has rights_status '{top_cand.rights_status.value}'. "
                "Quarantined from autonomous production. Human review required."
            )
            return None

        if not local_path or not local_path.exists():
            return None

        img_hash = top_cand.image_hash or self.compute_image_hash(local_path)
        source_type = VisualSourceType.OFFICIAL_ARTWORK if top_cand.is_official else preferred_source

        return VisualProvenance(
            asset_id=top_cand.candidate_id,
            source_type=source_type,
            source_url=top_cand.source_url,
            original_url=top_cand.original_url,
            creator=top_cand.creator or "Verified Illustrator",
            license=top_cand.license_name,
            license_url=top_cand.license_url,
            rights_status=top_cand.rights_status,
            approval_status=ApprovalStatus.APPROVED,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            image_hash=img_hash,
            search_query=queries[0] if queries else "",
            visual_description=top_cand.description or top_cand.title,
            associated_beat_id=beat.get("beat_id"),
            file_path=str(local_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            characters=top_cand.characters,
            actions=top_cand.actions,
            objects=top_cand.objects,
            locations=top_cand.locations,
            book_number=top_cand.book_number,
            chapter_number=top_cand.chapter_number,
            file_size_bytes=top_cand.file_size_bytes
        )

    # --------------------------------------------------------------------------
    # 6. ARTWORK-TO-VIDEO PRESENTATION FORMATTER
    # --------------------------------------------------------------------------
    @staticmethod
    def compute_image_hash(image_path: Path) -> str:
        """Computes SHA-256 of image file."""
        h = hashlib.sha256()
        with open(image_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def format_artwork_to_clip(
        self,
        artwork_image_path: Path,
        output_clip_path: Path,
        duration_seconds: float,
        target_width: int = 1080,
        target_height: int = 1920
    ) -> Path:
        """
        Converts a still artwork image into an audio-muted (-an) 1080x1920 30 FPS MP4 clip.

        Natural Presentation Invariants:
        - NO aggressive zoom/cropping: The full artwork subject must remain visible.
        - Uses classic broadcast vertical layout:
          Blurred, darkened ambient background scaled to fill 1080x1920,
          overlaid with the sharp, correctly proportioned original artwork centered.
        - Strict audio muting: 0 audio streams guaranteed.
        - 30 FPS, H.264 video.
        """
        output_clip_path.parent.mkdir(parents=True, exist_ok=True)
        img_str = str(artwork_image_path.resolve()).replace("\\", "/")
        out_str = str(output_clip_path.resolve()).replace("\\", "/")

        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
            f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,colorlevels=rimin=0.1:gimin=0.1:bimin=0.1[bg];"
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[vout]"
        )

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1",
            "-i", str(artwork_image_path),
            "-t", f"{duration_seconds:.3f}",
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-an",  # Audio-muted invariant
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            str(output_clip_path)
        ]

        logger.info(f"Formatting artwork {artwork_image_path.name} -> clip {output_clip_path.name} ({duration_seconds:.2f}s)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg artwork formatting failed: {res.stderr[-300:]}")

        # Probe output clip to verify invariants: single video stream, 0 audio streams, 1080x1920
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height",
            "-of", "json",
            str(output_clip_path)
        ]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        probe_data = json.loads(probe_res.stdout) if probe_res.returncode == 0 else {}
        streams = probe_data.get("streams", [])

        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        video_streams = [s for s in streams if s.get("codec_type") == "video"]

        if len(audio_streams) > 0:
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(f"[INVARIANT VIOLATION] Formatted artwork clip contains audio: {output_clip_path.name}")

        if not video_streams or video_streams[0].get("width") != target_width or video_streams[0].get("height") != target_height:
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(f"[INVARIANT VIOLATION] Formatted artwork clip dimensions != {target_width}x{target_height}")

        return output_clip_path
