"""
STORY FORGE — Zero-Device-Dependency & Cloud Portability Audit Test
===================================================================
Statically inspects all code in the acquisition subsystem to guarantee
zero hardcoded local machine paths, desktop folders, or user environments.
"""

from pathlib import Path
import pytest
from config.settings import PROJECT_ROOT


RESTRICTED_PATH_PATTERNS = [
    "c:\\users\\",
    "c:/users/",
    "/users/",
    "onedrive",
    "desktop",
]

ACQUISITION_DIRS = [
    PROJECT_ROOT / "core" / "acquisition_types.py",
    PROJECT_ROOT / "core" / "safe_url_validator.py",
    PROJECT_ROOT / "engines" / "acquisition",
    PROJECT_ROOT / "engines" / "asset_acquisition_engine.py",
]


def test_zero_device_dependency_static_audit():
    """
    Scans every Python file in the Asset Acquisition Engine to ensure
    no hardcoded local machine paths exist.
    """
    files_to_check = []
    for item in ACQUISITION_DIRS:
        if item.is_file() and item.suffix == ".py":
            files_to_check.append(item)
        elif item.is_dir():
            files_to_check.extend([p for p in item.rglob("*.py") if "__pycache__" not in str(p)])

    assert len(files_to_check) >= 6, f"Expected at least 6 acquisition subsystem files, found {len(files_to_check)}"

    violations = []
    for f in files_to_check:
        content = f.read_text(encoding="utf-8").lower()
        for pattern in RESTRICTED_PATH_PATTERNS:
            if pattern in content:
                # Find line number for reporting
                for idx, line in enumerate(content.splitlines(), start=1):
                    if pattern in line:
                        violations.append(f"{f.name}:{idx} -> Contains prohibited pattern '{pattern}': {line.strip()}")

    assert not violations, "Zero-device-dependency violations found:\n" + "\n".join(violations)


def test_acquisition_engine_initializes_without_local_devices(tmp_path):
    """
    Verifies that the AssetAcquisitionEngine can initialize in an isolated environment
    using only temporary directories without touching any local personal paths.
    """
    from engines.asset_acquisition_engine import AssetAcquisitionEngine
    from engines.acquisition.cloud_asset_registry import CloudAssetRegistry

    registry = CloudAssetRegistry(local_cache_dir=tmp_path / "cache", use_drive=False)
    engine = AssetAcquisitionEngine(registry=registry, use_drive=False)

    assert "wikimedia_commons" in engine.providers
    assert "archive_org" in engine.providers
    assert "direct_web" in engine.providers
    assert engine.registry.local_cache_dir == tmp_path / "cache"
