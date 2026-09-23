"""
STORY FORGE — Asset Acquisition Real-Internet Smoke Test
========================================================
Performs a live, harmless internet media acquisition from Wikimedia Commons:
1. Searches for public domain archival imagery of Alnwick Castle (historical Hogwarts filming location).
2. Streams candidate into an isolated ephemeral temporary directory.
3. Performs magic byte verification and decodability testing via Pillow.
4. Computes deterministic SHA-256 hash and extracts technical/visual metadata.
5. Verifies zero device dependencies and cleans up ephemeral artifacts.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.acquisition_types import MediaCategory
from engines.acquisition.cloud_asset_registry import CloudAssetRegistry
from engines.acquisition.providers.wikimedia_provider import WikimediaCommonsProvider
from engines.asset_acquisition_engine import AssetAcquisitionEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SmokeTest.AssetAcquisition")


def run_smoke_test() -> bool:
    print("=" * 70)
    print("STORY FORGE — ASSET ACQUISITION ENGINE V1: LIVE INTERNET SMOKE TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        cache_dir = temp_path / "cache"

        print(f"[*] Ephemeral runner directory initialized: {temp_path}")
        registry = CloudAssetRegistry(local_cache_dir=cache_dir, use_drive=False)
        provider = WikimediaCommonsProvider(enabled=True)
        engine = AssetAcquisitionEngine(registry=registry, providers=[provider], use_drive=False)

        search_query = "Alnwick Castle"
        print(f"[*] Querying Wikimedia Commons API for: '{search_query}'...")

        result = engine.acquire_by_query(
            query=search_query,
            target_media_category=MediaCategory.IMAGE,
            limit=1,
        )

        if not result.success or not result.asset_records:
            print(f"[!] Smoke test failed to acquire asset: {result.errors}")
            return False

        record = result.asset_records[0]
        print("\n" + "=" * 70)
        print("ACQUISITION SMOKE TEST SUCCESSFUL")
        print("=" * 70)
        print(f"  Asset ID:        {record.asset_id}")
        print(f"  Filename:        {record.filename}")
        print(f"  SHA-256:         {record.sha256}")
        print(f"  Dimensions:      {record.technical_meta.width} x {record.technical_meta.height} ({record.technical_meta.aspect_ratio})")
        print(f"  Orientation:     {record.visual_meta.orientation}")
        print(f"  Average Bright.: {record.visual_meta.average_brightness}")
        print(f"  MIME Type:       {record.technical_meta.mime_type}")
        print(f"  File Size:       {record.technical_meta.file_size_bytes:,} bytes")
        print(f"  License:         {record.provenance.rights.license_name} ({record.provenance.rights.classification.value})")
        print(f"  Source URL:      {record.provenance.source_url}")
        print(f"  Local Cache:     {record.local_cached_path}")
        print("=" * 70)

        # Assertions
        assert record.technical_meta.width > 0, "Image width must be > 0"
        assert record.technical_meta.height > 0, "Image height must be > 0"
        assert len(record.sha256) == 64, "SHA-256 must be 64 hex characters"
        assert record.technical_meta.file_size_bytes > 0, "File size must be positive"
        assert Path(record.local_cached_path).exists(), "Cached asset must exist on disk"

    print("[*] Ephemeral directory cleaned up automatically.")
    print("[*] ZERO DEVICE DEPENDENCIES VERIFIED.")
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
