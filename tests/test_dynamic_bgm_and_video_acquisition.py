"""
STORY FORGE — Dynamic BGM Resolution & Video-Only Acquisition Unit Tests
========================================================================
Validates:
1. Dynamic BGM resolution and configuration gate halt on unconfigured state
2. Detection and rejection of stale Esther Abrami No.6
3. BGM SHA-256 and config fingerprint mismatch invalidation
4. Video-only production asset classification
5. Strict rejection of static image formats (JPG, PNG, WEBP, GIF, SVG)
6. Strict rejection of commercial and generic stock providers
7. Proposition-driven acquisition requirement and grounding validation
8. Rejection of ungrounded or unrelated media
9. BEAST V2 NO_VALID_VISUAL immutability through Editorial
10. Direct evidence lineage protection against non-video upgrade
11. Cache invalidation preventing old image-based assets from fulfilling requests
"""

import json
from pathlib import Path
import pytest
import tempfile

from core.acquisition_types import (
    AssetAcquisitionRequest,
    AssetRecord,
    MediaCategory,
    MediaTechnicalMetadata,
    MediaVisualMetadata,
    AssetProvenance,
    ProductionAssetType,
    VisualEvidenceHierarchy,
    SourceCategory,
    FORBIDDEN_IMAGE_EXTENSIONS,
    FORBIDDEN_IMAGE_MIME_TYPES,
)
from core.beast_v2_types import BeastV2Decision, EvidenceType, validate_evidence_lineage
from core.discovery_bgm import DiscoveryBGMConfig, DiscoveryBGMGate, BGMConfigurationError
from core.safe_url_validator import SafeURLValidator
from engines.hp_render_engine import compute_render_fingerprint
from engines.acquisition.cloud_asset_registry import CloudAssetRegistry


# ==============================================================================
# 1. BGM DYNAMIC RESOLUTION & CONFIGURATION GATE TESTS
# ==============================================================================

def test_missing_bgm_configuration_halts_gate(monkeypatch):
    """Gate must strictly halt when Discovery BGM is unconfigured."""
    monkeypatch.setattr(DiscoveryBGMGate, "load_persisted_config", lambda: DiscoveryBGMConfig(status="UNCONFIGURED"))
    with pytest.raises(BGMConfigurationError) as exc_info:
        DiscoveryBGMGate.verify_and_resolve_bgm()
    assert "UNCONFIGURED" in str(exc_info.value)
    assert "The user has not yet specified the new canonical Discovery BGM" in str(exc_info.value)


def test_stale_esther_detection_and_abort(monkeypatch):
    """Gate must strictly reject and abort on any stale Esther Abrami references."""
    stale_config = DiscoveryBGMConfig(
        bgm_filename="Esther Abrami - No.6 In My Dreams (1).wav",
        status="CONFIGURED"
    )
    monkeypatch.setattr(DiscoveryBGMGate, "load_persisted_config", lambda: stale_config)
    with pytest.raises(BGMConfigurationError) as exc_info:
        DiscoveryBGMGate.verify_and_resolve_bgm()
    assert "Stale Esther No.6 detected" in str(exc_info.value)
    assert "strictly prohibited for Discovery Shorts" in str(exc_info.value)


def test_bgm_fingerprint_mismatch_and_cache_invalidation():
    """BGM configuration fingerprint must change when any parameter changes."""
    cfg1 = DiscoveryBGMConfig(
        bgm_filename="canonical_track_a.wav",
        actual_sha256="aaa111",
        speed_multiplier=1.2,
        volume_db=-18.0
    )
    cfg2 = DiscoveryBGMConfig(
        bgm_filename="canonical_track_a.wav",
        actual_sha256="aaa222",  # Different file hash
        speed_multiplier=1.2,
        volume_db=-18.0
    )
    cfg3 = DiscoveryBGMConfig(
        bgm_filename="canonical_track_a.wav",
        actual_sha256="aaa111",
        speed_multiplier=1.0,   # Different speed
        volume_db=-18.0
    )

    fp1 = cfg1.compute_config_fingerprint()
    fp2 = cfg2.compute_config_fingerprint()
    fp3 = cfg3.compute_config_fingerprint()

    assert fp1 != fp2, "Hash difference must alter BGM config fingerprint"
    assert fp1 != fp3, "Speed difference must alter BGM config fingerprint"

    # Invalidate old render fingerprint
    rfp1 = compute_render_fingerprint("short_01", bgm_track="track_a.wav", bgm_sha256="aaa111", bgm_config_fingerprint=fp1)
    rfp2 = compute_render_fingerprint("short_01", bgm_track="track_a.wav", bgm_sha256="aaa222", bgm_config_fingerprint=fp2)
    assert rfp1 != rfp2, "Altered BGM must invalidate render fingerprint"


def test_bgm_sha256_checksum_verification_failure(monkeypatch, tmp_path):
    """Gate must abort if actual file SHA does not match expected SHA."""
    test_audio = tmp_path / "test_bgm.wav"
    test_audio.write_bytes(b"RIFF dummy wav file content for test")

    mismatch_config = DiscoveryBGMConfig(
        bgm_filename=test_audio.name,
        expected_sha256="expected_sha_that_does_not_match_dummy_content",
        status="CONFIGURED"
    )
    monkeypatch.setattr(DiscoveryBGMGate, "load_persisted_config", lambda: mismatch_config)
    monkeypatch.setattr("core.discovery_bgm.MUSIC_DIR", tmp_path)

    with pytest.raises(BGMConfigurationError) as exc_info:
        DiscoveryBGMGate.verify_and_resolve_bgm()
    assert "SHA-256 checksum mismatch" in str(exc_info.value)


# ==============================================================================
# 2. VIDEO-ONLY ACQUISITION & IMAGE / STOCK BAN TESTS
# ==============================================================================

def test_video_only_asset_record_eligibility():
    """AssetRecord must strictly allow VIDEO and reject non-video or images in production."""
    video_rec = AssetRecord(
        asset_id="asset_vid_01",
        sha256="v123",
        filename="battle_scene.mp4",
        media_category=MediaCategory.VIDEO,
        source_category=SourceCategory.ARCHIVAL,
        technical_meta=MediaTechnicalMetadata(mime_type="video/mp4", duration_sec=5.0),
        visual_meta=MediaVisualMetadata(),
        provenance=AssetProvenance(source_url="http://valid.source/video.mp4", provider_name="test", search_query="", retrieved_at_iso=""),
        production_asset_type=ProductionAssetType.VIDEO_ONLY_PRODUCTION_ASSET.value
    )
    assert video_rec.is_production_video_eligible() is True

    image_rec = AssetRecord(
        asset_id="asset_img_01",
        sha256="i123",
        filename="kreacher_still.jpg",
        media_category=MediaCategory.IMAGE,
        source_category=SourceCategory.ARCHIVAL,
        technical_meta=MediaTechnicalMetadata(mime_type="image/jpeg", duration_sec=0.0),
        visual_meta=MediaVisualMetadata(),
        provenance=AssetProvenance(source_url="http://valid.source/image.jpg", provider_name="test", search_query="", retrieved_at_iso=""),
        production_asset_type=ProductionAssetType.VIDEO_ONLY_PRODUCTION_ASSET.value
    )
    assert image_rec.is_production_video_eligible() is False


def test_image_extensions_rejection():
    """SafeURLValidator and forbidden extensions list must reject all static image extensions."""
    test_urls = [
        "https://upload.wikimedia.org/wikipedia/commons/test.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/test.jpeg",
        "https://images.example.com/character.png",
        "https://art.example.com/scene.webp",
        "https://cdn.example.com/illustration.gif",
        "https://vector.example.com/logo.svg",
    ]
    for url in test_urls:
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        assert is_safe is False, f"URL {url} should have been rejected"
        assert "Static image format" in reason or "VIDEO ONLY" in reason


def test_stock_domains_hard_blocked():
    """Commercial and generic stock libraries must be blocked unconditionally."""
    stock_urls = [
        "https://www.pexels.com/video/magic-castle-12345/",
        "https://unsplash.com/photos/ancient-castle-xyz",
        "https://pixabay.com/videos/spell-cast-999/",
        "https://www.shutterstock.com/video/clip-101/",
        "https://www.gettyimages.com/detail/video/news-footage/123",
        "https://www.istockphoto.com/video/magic-wand",
        "https://elements.envato.com/video-templates/123",
    ]
    for url in stock_urls:
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        assert is_safe is False, f"Stock URL {url} should have been blocked"
        assert "Stock media provider" in reason


# ==============================================================================
# 3. PROPOSITION-DRIVEN ACQUISITION & CACHE HARDENING TESTS
# ==============================================================================

def test_proposition_required_acquisition_request():
    """Acquisition request must be tied to a specific Visual Proposition."""
    grounded_req = AssetAcquisitionRequest(
        query="Molly Weasley Bellatrix duel",
        short_id="mf_battle_of_hogwarts_v2",
        fact_id="fact_04_molly_bellatrix",
        proposition_id="prop_04_01",
        subject="Molly Weasley",
        action="CAST",
        object="Curse",
        context="Great Hall",
        required_evidence_class="DIRECT_EVIDENCE",
        target_media_category=MediaCategory.VIDEO,
    )
    assert grounded_req.is_proposition_grounded() is True
    cache_key = grounded_req.compute_cache_key()
    assert len(cache_key) == 64

    ungrounded_req = AssetAcquisitionRequest(
        query="Cool Hogwarts battle shots",
        target_media_category=MediaCategory.VIDEO,
    )
    assert ungrounded_req.is_proposition_grounded() is False


def test_registry_filters_historical_images_for_production():
    """CloudAssetRegistry must not serve historical image assets to video-only queries."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg = CloudAssetRegistry(local_cache_dir=Path(tmp_dir), use_drive=False)

        # Historical image record
        img_rec = AssetRecord(
            asset_id="asset_hist_01",
            sha256="hist_sha_img",
            filename="elder_wand.jpg",
            media_category=MediaCategory.IMAGE,
            source_category=SourceCategory.ARCHIVAL,
            technical_meta=MediaTechnicalMetadata(mime_type="image/jpeg"),
            visual_meta=MediaVisualMetadata(),
            provenance=AssetProvenance(source_url="https://wiki.org/wand.jpg", provider_name="wiki", search_query="", retrieved_at_iso=""),
            production_asset_type=ProductionAssetType.HISTORICAL_ARCHIVE_NON_PRODUCTION.value
        )
        reg._index[img_rec.sha256] = img_rec.to_dict()
        reg._url_to_sha[img_rec.provenance.source_url] = img_rec.sha256

        # Historical query without filter returns the record
        assert reg.get_by_sha(img_rec.sha256, require_production_video=False) is not None

        # Production query with require_production_video=True must reject it
        assert reg.get_by_sha(img_rec.sha256, require_production_video=True) is None
        assert reg.get_by_url(img_rec.provenance.source_url, require_production_video=True) is None


# ==============================================================================
# 4. BEAST V2 IMMUTABILITY & EVIDENCE LINEAGE TESTS
# ==============================================================================

def test_beast_no_valid_visual_immutability():
    """Editorial cannot upgrade BEAST V2 NO_VALID_VISUAL to DIRECT."""
    verdict = validate_evidence_lineage(
        beast_decision=BeastV2Decision.NO_VALID_VISUAL,
        claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
        media_category="video"
    )
    assert verdict == EvidenceType.NO_VALID_VISUAL, "Downstream must retain NO_VALID_VISUAL"


def test_direct_evidence_lineage_protection_rejects_non_video():
    """Non-video assets can NEVER be classified as DIRECT_EVIDENCE."""
    with pytest.raises(ValueError) as exc_info:
        validate_evidence_lineage(
            beast_decision=BeastV2Decision.ACCEPT_DIRECT,
            claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
            media_category="image"  # Artwork / image violation
        )
    assert "LINEAGE VIOLATION" in str(exc_info.value)
    assert "Non-video assets" in str(exc_info.value)


# ==============================================================================
# 5. LIVE PERSISTED CANONICAL DISCOVERY BGM VERIFICATION
# ==============================================================================

def test_persisted_canonical_discovery_bgm_registration():
    """Validates the live registered Discovery BGM configuration from Google Drive."""
    config = DiscoveryBGMGate.verify_and_resolve_bgm()
    assert config.status == "VERIFIED"
    assert config.bgm_filename is not None
    assert "esther" not in config.bgm_filename.lower()
    assert "no.6" not in config.bgm_filename.lower()
    assert config.drive_file_id == "1KExAdFU1tI7Ht_j0AxTqzIqgV3HtHkIe"
    assert config.actual_sha256 is not None and len(config.actual_sha256) == 64
    assert config.speed_multiplier == 1.2
    assert config.volume_db == -18.0
    assert config.duration_sec is not None and config.duration_sec > 30.0
