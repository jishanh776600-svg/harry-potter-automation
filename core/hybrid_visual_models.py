"""
STORY FORGE Hybrid Visual Source Models & Provenance Schema
===========================================================
Defines canonical data contracts for truthful visual source resolution:
1. MOVIE_DIRECT      — Exact filmed moment in Movies 1–8.
2. FAN_ART           — Legitimate existing fan art / illustration for novel-only moments.
3. OFFICIAL_ARTWORK  — Official/licensed artwork (e.g. Mary GrandPré, Jim Kay, MinaLima).
4. NO_VALID_VISUAL   — Neither movie footage nor approved artwork exists.

Strict Rights Architecture:
- ARTIST_LICENSE_STATUS: What the creator/illustrator declared (verified, unverified, rejected).
- COMMERCIAL_CLEARANCE_STATUS: Whether the asset is legally cleared for autonomous commercial
  YouTube video production (cleared, review required, rejected).
  * Invariant: A CC-BY or open license from an artist on derivative Harry Potter fan art does
    NOT convey commercial production clearance; it remains review-required.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple


class VisualSourceType(str, Enum):
    """Explicit classification of visual sources."""
    MOVIE_DIRECT = "MOVIE_DIRECT"          # Exact filmed moment in Movies 1–8
    FAN_ART = "FAN_ART"                    # Existing fan art / illustration for novel-only scene
    OFFICIAL_ARTWORK = "OFFICIAL_ARTWORK"  # Officially licensed/published artwork
    NO_VALID_VISUAL = "NO_VALID_VISUAL"    # No truthful visual available; adapt or flag


class ArtistLicenseStatus(str, Enum):
    """Status of the artist/creator license declaration."""
    ARTIST_LICENSE_VERIFIED = "ARTIST_LICENSE_VERIFIED"      # Permissive license (CC0, CC-BY, Public Domain, verified grant)
    ARTIST_LICENSE_UNVERIFIED = "ARTIST_LICENSE_UNVERIFIED"  # Missing, ambiguous, all-rights-reserved, or unverified platform
    ARTIST_LICENSE_REJECTED = "ARTIST_LICENSE_REJECTED"      # Explicitly prohibited or forbidden provider


class CommercialClearanceStatus(str, Enum):
    """Status of commercial production clearance for autonomous monetization."""
    COMMERCIAL_PRODUCTION_CLEARED = "COMMERCIAL_PRODUCTION_CLEARED"                # Explicitly cleared for autonomous production
    COMMERCIAL_PRODUCTION_REVIEW_REQUIRED = "COMMERCIAL_PRODUCTION_REVIEW_REQUIRED"  # Derivative fan work or uncertain IP status; quarantined
    COMMERCIAL_PRODUCTION_REJECTED = "COMMERCIAL_PRODUCTION_REJECTED"              # Legally/contractually barred from commercial production


class RightsStatus(str, Enum):
    """Composite licensing and rights status for visual assets."""
    RIGHTS_VERIFIED = "RIGHTS_VERIFIED"          # Permissive creator license AND commercial production cleared
    RIGHTS_UNVERIFIED = "RIGHTS_UNVERIFIED"      # Creator license unverified OR commercial clearance requires review (quarantined)
    RIGHTS_REJECTED = "RIGHTS_REJECTED"          # Explicitly forbidden or non-compliant

    # Legacy aliases preserved for backward compatibility
    VERIFIED_FREE = "VERIFIED_FREE"
    CREATIVE_COMMONS = "CREATIVE_COMMONS"
    OFFICIAL_LICENSED = "OFFICIAL_LICENSED"
    FAIR_USE_EDITORIAL = "FAIR_USE_EDITORIAL"

    @property
    def is_production_eligible(self) -> bool:
        """Returns True if rights and clearance are sufficiently established for autonomous production."""
        return self in (
            RightsStatus.RIGHTS_VERIFIED,
            RightsStatus.VERIFIED_FREE,
            RightsStatus.OFFICIAL_LICENSED,
        )


class ApprovalStatus(str, Enum):
    """Editorial and automation approval status for acquired artwork."""
    APPROVED = "APPROVED"          # Rights and commercial clearance verified; ready for autonomous production
    QUARANTINED = "QUARANTINED"    # Creator unverified or commercial review required; blocked from autonomous production
    REJECTED = "REJECTED"          # Prohibited license, forbidden stock provider, or corrupt asset


# Forbidden visual sources that must NEVER be used
FORBIDDEN_SOURCE_PROVIDERS = {
    "pexels", "unsplash", "pixabay", "shutterstock", "getty", "istock",
    "generic_stock", "generic_broll", "pollinations", "midjourney",
    "dall-e", "stable_diffusion", "ai_generated_placeholder", "flux"
}


@dataclass
class VisualProvenance:
    """Complete provenance, licensing lineage, and clearance for an artwork or visual asset."""
    asset_id: str
    source_type: VisualSourceType
    source_url: str                                     # Web page or collection URL where found
    original_url: Optional[str] = None                 # Direct image/media URL
    creator: Optional[str] = None                       # Artist / illustrator / creator name
    license: Optional[str] = None                       # License identifier or description
    license_url: Optional[str] = None                   # Link to license terms
    artist_license_status: ArtistLicenseStatus = ArtistLicenseStatus.ARTIST_LICENSE_UNVERIFIED
    commercial_clearance: CommercialClearanceStatus = CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED
    rights_status: RightsStatus = RightsStatus.RIGHTS_UNVERIFIED
    approval_status: ApprovalStatus = ApprovalStatus.QUARANTINED
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    image_hash: Optional[str] = None                    # SHA-256 hash of image file
    search_query: str = ""                              # Exact targeted query that discovered it
    visual_description: str = ""                        # Description of what the visual depicts
    associated_beat_id: Optional[str] = None            # Associated narration beat ID
    notes: Optional[str] = None                         # Additional editorial or context notes
    file_path: Optional[str] = None                     # Local path to downloaded/cached asset
    characters: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    book_number: Optional[int] = None
    chapter_number: Optional[int] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    image_dimensions: Optional[Tuple[int, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value if isinstance(self.source_type, VisualSourceType) else self.source_type
        d["artist_license_status"] = self.artist_license_status.value if isinstance(self.artist_license_status, ArtistLicenseStatus) else self.artist_license_status
        d["commercial_clearance"] = self.commercial_clearance.value if isinstance(self.commercial_clearance, CommercialClearanceStatus) else self.commercial_clearance
        d["rights_status"] = self.rights_status.value if isinstance(self.rights_status, RightsStatus) else self.rights_status
        d["approval_status"] = self.approval_status.value if isinstance(self.approval_status, ApprovalStatus) else self.approval_status
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualProvenance":
        source_type = data.get("source_type", VisualSourceType.FAN_ART)
        if isinstance(source_type, str):
            source_type = VisualSourceType(source_type)

        raw_artist = data.get("artist_license_status", ArtistLicenseStatus.ARTIST_LICENSE_UNVERIFIED)
        if isinstance(raw_artist, str):
            try:
                artist_license_status = ArtistLicenseStatus(raw_artist)
            except ValueError:
                artist_license_status = ArtistLicenseStatus.ARTIST_LICENSE_UNVERIFIED
        else:
            artist_license_status = raw_artist

        raw_clearance = data.get("commercial_clearance", CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED)
        if isinstance(raw_clearance, str):
            try:
                commercial_clearance = CommercialClearanceStatus(raw_clearance)
            except ValueError:
                commercial_clearance = CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED
        else:
            commercial_clearance = raw_clearance

        raw_rights = data.get("rights_status", RightsStatus.RIGHTS_UNVERIFIED)
        if isinstance(raw_rights, str):
            try:
                rights_status = RightsStatus(raw_rights)
            except ValueError:
                rights_status = RightsStatus.RIGHTS_UNVERIFIED
        else:
            rights_status = raw_rights

        raw_approval = data.get("approval_status", ApprovalStatus.QUARANTINED)
        if isinstance(raw_approval, str):
            try:
                approval_status = ApprovalStatus(raw_approval)
            except ValueError:
                approval_status = ApprovalStatus.QUARANTINED
        else:
            approval_status = raw_approval

        return cls(
            asset_id=data.get("asset_id", ""),
            source_type=source_type,
            source_url=data.get("source_url", ""),
            original_url=data.get("original_url"),
            creator=data.get("creator"),
            license=data.get("license") or data.get("license_name"),
            license_url=data.get("license_url"),
            artist_license_status=artist_license_status,
            commercial_clearance=commercial_clearance,
            rights_status=rights_status,
            approval_status=approval_status,
            retrieved_at=data.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
            image_hash=data.get("image_hash"),
            search_query=data.get("search_query", ""),
            visual_description=data.get("visual_description", "") or data.get("description", ""),
            associated_beat_id=data.get("associated_beat_id"),
            notes=data.get("notes"),
            file_path=data.get("file_path") or data.get("local_path"),
            characters=data.get("characters", []),
            actions=data.get("actions", []),
            objects=data.get("objects", []),
            locations=data.get("locations", []),
            book_number=data.get("book_number"),
            chapter_number=data.get("chapter_number"),
            mime_type=data.get("mime_type"),
            file_size_bytes=data.get("file_size_bytes"),
            image_dimensions=data.get("image_dimensions"),
        )


@dataclass
class StoryboardBeatMetadata:
    """Timeline metadata for a single visual beat in the storyboard."""
    beat_id: str
    visual_source: VisualSourceType
    description: str
    source_url: Optional[str] = None
    original_url: Optional[str] = None
    creator: Optional[str] = None
    license: Optional[str] = None
    license_url: Optional[str] = None
    artist_license_status: Optional[str] = None
    commercial_clearance: Optional[str] = None
    rights_status: Optional[str] = None
    approval_status: Optional[str] = None
    search_query: Optional[str] = None
    notes: Optional[str] = None
    movie_number: Optional[int] = None
    clip_start_seconds: Optional[float] = None
    clip_end_seconds: Optional[float] = None
    duration_seconds: float = 2.5
    characters: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["visual_source"] = self.visual_source.value if isinstance(self.visual_source, VisualSourceType) else self.visual_source
        return d
