"""
STORY FORGE — Asset Acquisition Engine Unit & Integration Tests
================================================================
Comprehensive test suite covering:
  - SSRF defense (SafeURLValidator)
  - Tiered query generation (AcquisitionQueryGenerator)
  - Media header & magic bytes verification (MediaAnalyzer)
  - Decodability and perceptual hashing (MediaAnalyzer)
  - Deduplicating registry storage (CloudAssetRegistry)
  - Provider failure isolation and fallback resilience
"""

import io
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from core.acquisition_types import (
    AssetCandidate,
    AssetProvenance,
    AssetRecord,
    MediaCategory,
    RightsClassification,
    RightsMetadata,
    SourceCategory,
)
from core.safe_url_validator import SafeURLValidator
from engines.acquisition.cloud_asset_registry import CloudAssetRegistry
from engines.acquisition.media_analyzer import MediaAnalyzer, MediaValidationError
from engines.acquisition.providers.base_provider import AssetSourceProvider, ProviderDownloadError
from engines.acquisition.query_generator import AcquisitionQueryGenerator
from engines.asset_acquisition_engine import AssetAcquisitionEngine


# ==============================================================================
# 1. SSRF & SAFE URL VALIDATOR TESTS
# ==============================================================================

def test_safe_url_validator_allowed():
    safe_urls = [
        "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "https://archive.org/download/item/file.mp4",
        "http://example.com/image.png",
    ]
    for url in safe_urls:
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        assert is_safe, f"Expected safe for {url}: {reason}"


def test_safe_url_validator_blocked():
    blocked_urls = [
        "http://localhost:8080/secret",
        "http://127.0.0.1:5000/api",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://10.0.0.1/router",
        "http://192.168.1.1/admin",
        "http://172.16.5.1/internal",
        "file:///etc/passwd",
        "ftp://example.com/asset.mp4",
        "javascript:alert(1)",
        "",
    ]
    for url in blocked_urls:
        is_safe, reason = SafeURLValidator.is_safe_url(url)
        assert not is_safe, f"Expected blocked for {url}"


# ==============================================================================
# 2. QUERY GENERATOR TESTS
# ==============================================================================

def test_query_generator_tiered():
    req = {
        "primary_entity": "Neville Longbottom",
        "secondary_entity": "Sorting Hat",
        "action_descriptor": "pleading to be in Hufflepuff",
        "location_descriptor": "Great Hall",
    }
    class MockReq:
        primary_subject = "Neville Longbottom"
        secondary_subject = "Sorting Hat"
        required_action = "pleading to be in Hufflepuff"
        required_location = "Great Hall"
        required_objects = ["Sorting Hat"]

    queries = AcquisitionQueryGenerator.generate_queries(MockReq())
    assert len(queries) >= 2
    assert "Neville Longbottom Sorting Hat" in queries[0]
    assert any("Great Hall" in q for q in queries)


# ==============================================================================
# 3. MEDIA ANALYZER TESTS
# ==============================================================================

def test_media_analyzer_valid_jpeg(tmp_path):
    img_path = tmp_path / "valid_image.jpg"
    img = Image.new("RGB", (100, 150), color=(200, 100, 50))
    img.save(img_path, format="JPEG")

    mime = MediaAnalyzer.validate_magic_bytes(img_path)
    assert mime == "image/jpeg"

    tech, visual = MediaAnalyzer.analyze_asset(img_path)
    assert tech.width == 100
    assert tech.height == 150
    assert visual.is_vertical is True
    assert visual.orientation == "vertical"
    assert visual.perceptual_hash is not None
    assert tech.file_size_bytes > 0


def test_media_analyzer_rejects_html_error(tmp_path):
    html_file = tmp_path / "fake_image.jpg"
    html_file.write_text("<!DOCTYPE html><html><body>404 Not Found</body></html>", encoding="utf-8")

    with pytest.raises(MediaValidationError, match="HTML/XML markup"):
        MediaAnalyzer.validate_magic_bytes(html_file)


def test_media_analyzer_rejects_json_error(tmp_path):
    json_file = tmp_path / "fake_image.png"
    json_file.write_text('{"error": "Forbidden", "status": 403}', encoding="utf-8")

    with pytest.raises(MediaValidationError, match="JSON error"):
        MediaAnalyzer.validate_magic_bytes(json_file)


def test_media_analyzer_sha256(tmp_path):
    f1 = tmp_path / "file1.bin"
    f1.write_bytes(b"STORY_FORGE_MEDIA_TEST_PAYLOAD")
    hash1 = MediaAnalyzer.calculate_sha256(f1)
    assert len(hash1) == 64

    f2 = tmp_path / "file2.bin"
    f2.write_bytes(b"STORY_FORGE_MEDIA_TEST_PAYLOAD")
    hash2 = MediaAnalyzer.calculate_sha256(f2)
    assert hash1 == hash2


# ==============================================================================
# 4. CLOUD ASSET REGISTRY TESTS
# ==============================================================================

def test_cloud_asset_registry_caching(tmp_path):
    cache_dir = tmp_path / "registry"
    registry = CloudAssetRegistry(local_cache_dir=cache_dir, use_drive=False)

    img_path = tmp_path / "test_thumb.jpg"
    img = Image.new("RGB", (50, 50), color="blue")
    img.save(img_path, format="JPEG")

    tech, visual = MediaAnalyzer.analyze_asset(img_path)
    sha = MediaAnalyzer.calculate_sha256(img_path)

    record = AssetRecord(
        asset_id="asset_test_123",
        sha256=sha,
        filename=img_path.name,
        media_category=MediaCategory.IMAGE,
        source_category=SourceCategory.ENCYCLOPEDIC,
        technical_meta=tech,
        visual_meta=visual,
        provenance=AssetProvenance(
            source_url="https://example.com/test_thumb.jpg",
            provider_name="test_provider",
            search_query="blue square",
            retrieved_at_iso="2026-09-24T00:00:00Z",
        ),
    )

    registered = registry.register_asset(img_path, record, upload_to_cloud=False)
    assert registered.local_cached_path is not None
    assert registry.has_asset_sha(sha) is True
    assert registry.has_asset_url("https://example.com/test_thumb.jpg") is True

    # Retrieve by hash and url
    by_sha = registry.get_by_sha(sha)
    assert by_sha is not None
    assert by_sha.asset_id == "asset_test_123"

    by_url = registry.get_by_url("https://example.com/test_thumb.jpg")
    assert by_url is not None
    assert by_url.sha256 == sha


# ==============================================================================
# 5. ASSET ACQUISITION ENGINE END-TO-END FLOW (MOCKED PROVIDER)
# ==============================================================================

class MockTestProvider(AssetSourceProvider):
    def __init__(self, sample_file: Path, media_category: MediaCategory = MediaCategory.VIDEO):
        super().__init__(name="mock_test_provider", enabled=True)
        self.sample_file = sample_file
        self.media_category = media_category

    def search(self, query: str, requirements=None, limit: int = 5):
        return [
            AssetCandidate(
                candidate_id="mock_001",
                title="Mock Hogwarts Footage",
                download_url=f"https://archive.org/download/mock/{self.sample_file.name}",
                preview_url="https://archive.org/download/mock/thumb.jpg",
                media_category=self.media_category,
                source_category=SourceCategory.ARCHIVAL,
                provenance=AssetProvenance(
                    source_url=f"https://archive.org/download/mock/{self.sample_file.name}",
                    provider_name=self.name,
                    search_query=query,
                    retrieved_at_iso="2026-09-24T00:00:00Z",
                    rights=RightsMetadata(classification=RightsClassification.PUBLIC_DOMAIN),
                ),
                score=0.95,
            )
        ]

    def download(self, candidate, dest_path: Path):
        import shutil
        shutil.copy2(str(self.sample_file), str(dest_path))
        return dest_path


def _create_mock_video(target_path: Path):
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )


def test_asset_acquisition_engine_mock_end_to_end(tmp_path):
    # Setup mock video
    sample_vid = tmp_path / "mock_castle.mp4"
    _create_mock_video(sample_vid)

    registry = CloudAssetRegistry(local_cache_dir=tmp_path / "cache", use_drive=False)
    mock_provider = MockTestProvider(sample_vid, media_category=MediaCategory.VIDEO)

    engine = AssetAcquisitionEngine(registry=registry, providers=[mock_provider], use_drive=False)

    result = engine.acquire_by_query("Hogwarts Castle", limit=1)

    assert result.success is True
    assert len(result.asset_records) == 1
    record = result.asset_records[0]
    assert record.technical_meta.width == 320
    assert record.technical_meta.height == 240
    assert record.provenance.provider_name == "mock_test_provider"
    assert registry.has_asset_sha(record.sha256) is True


def test_provider_error_isolation(tmp_path):
    """Verifies that an error in one provider does not crash the acquisition process."""
    class FailingProvider(AssetSourceProvider):
        def __init__(self):
            super().__init__(name="failing_provider", enabled=True)

        def search(self, query: str, requirements=None, limit: int = 5):
            raise RuntimeError("Provider connection exploded")

    sample_vid = tmp_path / "fallback.mp4"
    _create_mock_video(sample_vid)

    mock_provider = MockTestProvider(sample_vid, media_category=MediaCategory.VIDEO)
    failing_provider = FailingProvider()

    registry = CloudAssetRegistry(local_cache_dir=tmp_path / "cache", use_drive=False)
    engine = AssetAcquisitionEngine(
        registry=registry,
        providers=[failing_provider, mock_provider],
        use_drive=False
    )

    result = engine.acquire_by_query("Hogwarts", limit=1)
    assert result.success is True
    assert len(result.asset_records) == 1
    assert any("Provider 'failing_provider' error" in err for err in result.errors)


def test_policy_blocks_images_and_disallowed_stock_domains(tmp_path):
    """Enforces STORY FORGE rules: VISUALS = VIDEO ONLY and stock providers blocked."""
    # 1. Test blocked stock domains in SafeURLValidator
    stock_urls = [
        "https://www.pexels.com/video/hogwarts-12345/",
        "https://images.unsplash.com/photo-123",
        "https://pixabay.com/videos/download/castle.mp4",
        "https://www.shutterstock.com/video/clip-123.mp4",
        "https://media.gettyimages.com/videos/hp-123.mp4",
        "https://www.istockphoto.com/video/castle-123.mp4",
    ]
    for url in stock_urls:
        safe, reason = SafeURLValidator.is_safe_url(url)
        assert safe is False
        assert "STORY FORGE Policy: Stock media provider" in reason

    # 2. Test candidate with IMAGE category is rejected
    sample_img = tmp_path / "mock_castle.jpg"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(sample_img, format="JPEG")

    registry = CloudAssetRegistry(local_cache_dir=tmp_path / "cache", use_drive=False)
    image_provider = MockTestProvider(sample_img, media_category=MediaCategory.IMAGE)
    engine = AssetAcquisitionEngine(registry=registry, providers=[image_provider], use_drive=False)

    res = engine.acquire_by_query("Hogwarts Castle Image", limit=1)
    # Must reject images per VISUALS = VIDEO ONLY policy
    assert res.success is False
    assert len(res.asset_records) == 0
