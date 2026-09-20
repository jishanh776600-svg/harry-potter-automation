"""
STORY FORGE Hybrid Visual Source Models & Provenance Schema
===========================================================
Defines canonical data contracts for truthful visual source resolution:
1. MOVIE_DIRECT      — Exact filmed moment in Movies 1–8.
2. FAN_ART           — Legitimate existing fan art / illustration for novel-only moments.
3. OFFICIAL_ARTWORK  — Official/licensed artwork (e.g. Mary GrandPré, Jim Kay, MinaLima).
4. NO_VALID_VISUAL   — Neither movie footage nor approved artwork exists.

Permanent Rules:
- NEVER generic stock imagery (Pexels, Unsplash, generic B-roll permanently forbidden).
- NEVER unrelated movie footage to fill time.
- NEVER generate a bespoke AI image for every novel scene.
- EVERY VISUAL MUST REPRESENT THE SPECIFIC NARRATION BEAT.
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


class RightsStatus(str, Enum):
    """Licensing and rights status for visual assets."""
    VERIFIED_FREE = "VERIFIED_FREE"              # Explicit CC0, Public Domain, or verified commercial license
    CREATIVE_COMMONS = "CREATIVE_COMMONS"        # CC-BY / CC-BY-SA attribution required
    OFFICIAL_LICENSED = "OFFICIAL_LICENSED"      # Studio / publisher licensed
    FAIR_USE_EDITORIAL = "FAIR_USE_EDITORIAL"    # Transformative commentary / criticism with attribution
    RIGHTS_UNVERIFIED = "RIGHTS_UNVERIFIED"      # Web discovery without verified license (quarantined)


# Forbidden visual sources that must NEVER be used
FORBIDDEN_SOURCE_PROVIDERS = {
    "pexels", "unsplash", "shutterstock", "getty", "istock",
    "generic_stock", "generic_broll", "pollinations", "midjourney",
    "dall-e", "stable_diffusion", "ai_generated_placeholder"
}


@dataclass
class VisualProvenance:
    """Complete provenance and licensing lineage for an artwork or visual asset."""
    asset_id: str
    source_type: VisualSourceType
    source_url: str                                     # Web page or collection URL where found
    original_url: Optional[str] = None                 # Direct image/media URL
    creator: Optional[str] = None                       # Artist / illustrator / creator name
    license: Optional[str] = None                       # License identifier or description
    license_url: Optional[str] = None                   # Link to license terms
    rights_status: RightsStatus = RightsStatus.RIGHTS_UNVERIFIED
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    image_hash: Optional[str] = None                    # SHA-256 hash of image file
    search_query: str = ""                              # Exact targeted query that discovered it
    visual_description: str = ""                        # Description of what the visual depicts
    associated_beat_id: Optional[str] = None            # Associated narration beat ID
    notes: Optional[str] = None                         # Additional editorial or context notes
    file_path: Optional[str] = None                     # Local path to downloaded/cached asset

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value if isinstance(self.source_type, VisualSourceType) else self.source_type
        d["rights_status"] = self.rights_status.value if isinstance(self.rights_status, RightsStatus) else self.rights_status
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualProvenance":
        source_type = data.get("source_type", VisualSourceType.FAN_ART)
        if isinstance(source_type, str):
            source_type = VisualSourceType(source_type)
        rights_status = data.get("rights_status", RightsStatus.RIGHTS_UNVERIFIED)
        if isinstance(rights_status, str):
            rights_status = RightsStatus(rights_status)
        return cls(
            asset_id=data.get("asset_id", ""),
            source_type=source_type,
            source_url=data.get("source_url", ""),
            original_url=data.get("original_url"),
            creator=data.get("creator"),
            license=data.get("license"),
            license_url=data.get("license_url"),
            rights_status=rights_status,
            retrieved_at=data.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
            image_hash=data.get("image_hash"),
            search_query=data.get("search_query", ""),
            visual_description=data.get("visual_description", ""),
            associated_beat_id=data.get("associated_beat_id"),
            notes=data.get("notes"),
            file_path=data.get("file_path"),
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
    rights_status: Optional[str] = None
    search_query: Optional[str] = None
    notes: Optional[str] = None
    movie_number: Optional[int] = None
    clip_start_seconds: Optional[float] = None
    clip_end_seconds: Optional[float] = None
    duration_seconds: float = 2.5

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["visual_source"] = self.visual_source.value if isinstance(self.visual_source, VisualSourceType) else self.visual_source
        return d
