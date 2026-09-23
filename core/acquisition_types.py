"""
STORY FORGE — Asset Acquisition Types & Domain Models
======================================================
Defines strongly-typed data structures for multi-stage visual asset
retrieval, streaming ingestion, deep validation, and cloud registry storage.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


class MediaCategory(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"


class SourceCategory(str, Enum):
    ARCHIVAL = "archival"
    PROMOTIONAL = "promotional"
    PRODUCTION_STILL = "production_still"
    ENCYCLOPEDIC = "encyclopedic"
    ARTWORK = "artwork"
    DIRECT_WEB = "direct_web"
    USER_UPLOADED = "user_uploaded"


class RightsClassification(str, Enum):
    PUBLIC_DOMAIN = "public_domain"
    CREATIVE_COMMONS = "creative_commons"
    EDITORIAL_FAIR_USE = "editorial_fair_use"
    PROPRIETARY_REFERENCE = "proprietary_reference"
    UNKNOWN = "unknown"


@dataclass
class RightsMetadata:
    classification: RightsClassification = RightsClassification.UNKNOWN
    license_name: str = "Unknown"
    license_url: Optional[str] = None
    author: Optional[str] = None
    attribution_text: Optional[str] = None
    commercial_cleared: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "license_name": self.license_name,
            "license_url": self.license_url,
            "author": self.author,
            "attribution_text": self.attribution_text,
            "commercial_cleared": self.commercial_cleared,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RightsMetadata":
        return cls(
            classification=RightsClassification(data.get("classification", RightsClassification.UNKNOWN.value)),
            license_name=data.get("license_name", "Unknown"),
            license_url=data.get("license_url"),
            author=data.get("author"),
            attribution_text=data.get("attribution_text"),
            commercial_cleared=data.get("commercial_cleared", False),
            notes=data.get("notes", ""),
        )


@dataclass
class AssetProvenance:
    source_url: str
    provider_name: str
    search_query: str
    retrieved_at_iso: str
    rights: RightsMetadata = field(default_factory=RightsMetadata)
    external_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "provider_name": self.provider_name,
            "search_query": self.search_query,
            "retrieved_at_iso": self.retrieved_at_iso,
            "rights": self.rights.to_dict(),
            "external_id": self.external_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssetProvenance":
        rights_data = data.get("rights", {})
        return cls(
            source_url=data.get("source_url", ""),
            provider_name=data.get("provider_name", "unknown"),
            search_query=data.get("search_query", ""),
            retrieved_at_iso=data.get("retrieved_at_iso", ""),
            rights=RightsMetadata.from_dict(rights_data) if rights_data else RightsMetadata(),
            external_id=data.get("external_id"),
        )


@dataclass
class MediaTechnicalMetadata:
    width: int = 0
    height: int = 0
    aspect_ratio: float = 0.0
    duration_sec: float = 0.0
    fps: float = 0.0
    codec: str = ""
    container: str = ""
    file_size_bytes: int = 0
    mime_type: str = ""
    has_audio: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "duration_sec": self.duration_sec,
            "fps": self.fps,
            "codec": self.codec,
            "container": self.container,
            "file_size_bytes": self.file_size_bytes,
            "mime_type": self.mime_type,
            "has_audio": self.has_audio,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaTechnicalMetadata":
        return cls(
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            aspect_ratio=float(data.get("aspect_ratio", 0.0)),
            duration_sec=float(data.get("duration_sec", 0.0)),
            fps=float(data.get("fps", 0.0)),
            codec=data.get("codec", ""),
            container=data.get("container", ""),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            mime_type=data.get("mime_type", ""),
            has_audio=bool(data.get("has_audio", False)),
        )


@dataclass
class MediaVisualMetadata:
    keyframe_paths: List[str] = field(default_factory=list)
    perceptual_hash: Optional[str] = None
    dominant_colors: List[str] = field(default_factory=list)
    average_brightness: float = 0.0
    is_vertical: bool = False
    orientation: str = "landscape"  # "vertical", "square", "landscape"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyframe_paths": self.keyframe_paths,
            "perceptual_hash": self.perceptual_hash,
            "dominant_colors": self.dominant_colors,
            "average_brightness": self.average_brightness,
            "is_vertical": self.is_vertical,
            "orientation": self.orientation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaVisualMetadata":
        return cls(
            keyframe_paths=data.get("keyframe_paths", []),
            perceptual_hash=data.get("perceptual_hash"),
            dominant_colors=data.get("dominant_colors", []),
            average_brightness=float(data.get("average_brightness", 0.0)),
            is_vertical=bool(data.get("is_vertical", False)),
            orientation=data.get("orientation", "landscape"),
        )


@dataclass
class AssetCandidate:
    candidate_id: str
    title: str
    download_url: str
    preview_url: Optional[str] = None
    media_category: MediaCategory = MediaCategory.IMAGE
    source_category: SourceCategory = SourceCategory.ARCHIVAL
    provenance: Optional[AssetProvenance] = None
    score: float = 0.0
    estimated_size_bytes: int = 0
    description: str = ""
    extra_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetRecord:
    asset_id: str
    sha256: str
    filename: str
    media_category: MediaCategory
    source_category: SourceCategory
    technical_meta: MediaTechnicalMetadata
    visual_meta: MediaVisualMetadata
    provenance: AssetProvenance
    cloud_file_id: Optional[str] = None
    cloud_path: Optional[str] = None
    local_cached_path: Optional[str] = None
    created_at_iso: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "sha256": self.sha256,
            "filename": self.filename,
            "media_category": self.media_category.value,
            "source_category": self.source_category.value,
            "technical_meta": self.technical_meta.to_dict(),
            "visual_meta": self.visual_meta.to_dict(),
            "provenance": self.provenance.to_dict(),
            "cloud_file_id": self.cloud_file_id,
            "cloud_path": self.cloud_path,
            "local_cached_path": self.local_cached_path,
            "created_at_iso": self.created_at_iso,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssetRecord":
        return cls(
            asset_id=data["asset_id"],
            sha256=data["sha256"],
            filename=data["filename"],
            media_category=MediaCategory(data["media_category"]),
            source_category=SourceCategory(data["source_category"]),
            technical_meta=MediaTechnicalMetadata.from_dict(data.get("technical_meta", {})),
            visual_meta=MediaVisualMetadata.from_dict(data.get("visual_meta", {})),
            provenance=AssetProvenance.from_dict(data.get("provenance", {})),
            cloud_file_id=data.get("cloud_file_id"),
            cloud_path=data.get("cloud_path"),
            local_cached_path=data.get("local_cached_path"),
            created_at_iso=data.get("created_at_iso", ""),
            tags=data.get("tags", []),
        )


@dataclass
class AssetAcquisitionRequest:
    query: str
    beat_id: Optional[str] = None
    target_media_category: MediaCategory = MediaCategory.IMAGE
    primary_entity: Optional[str] = None
    secondary_entity: Optional[str] = None
    action_descriptor: Optional[str] = None
    location_descriptor: Optional[str] = None
    era: Optional[str] = None
    max_candidates: int = 5
    timeout_sec: float = 30.0
    preferred_providers: List[str] = field(default_factory=list)


@dataclass
class AssetAcquisitionResult:
    success: bool
    asset_records: List[AssetRecord] = field(default_factory=list)
    candidates_evaluated: int = 0
    errors: List[str] = field(default_factory=list)
    query_used: str = ""
    cache_hit: bool = False
