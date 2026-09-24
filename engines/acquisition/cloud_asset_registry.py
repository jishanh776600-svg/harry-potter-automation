"""
STORY FORGE — Cloud Asset Registry & Storage Manager
=====================================================
Manages persistent cloud media storage and metadata indexing in Google Drive
under VISUAL_LIBRARY and METADATA/assets with deterministic SHA-256 deduplication
and seamless local fallback for offline/test environments.
"""

import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from config.settings import PROJECT_ROOT, TEST_MODE
from core.acquisition_types import AssetRecord, MediaCategory, SourceCategory

logger = logging.getLogger("AssetAcquisition.CloudRegistry")


class CloudAssetRegistry:
    """
    Deduplicating cloud asset catalog backed by Google Drive and local cache.
    """

    def __init__(
        self,
        local_cache_dir: Optional[Path] = None,
        use_drive: bool = True,
        drive_engine: Optional[Any] = None
    ):
        self.local_cache_dir = local_cache_dir or (PROJECT_ROOT / "data" / "cache" / "asset_registry")
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.local_cache_dir / "asset_index.json"
        self._index: Dict[str, Dict[str, Any]] = {}
        self._url_to_sha: Dict[str, str] = {}
        self.use_drive = use_drive
        self.drive_engine = drive_engine
        self._load_local_index()

    def _load_local_index(self) -> None:
        """Loads local JSON catalog into memory."""
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text(encoding="utf-8"))
                self._index = data.get("assets", {})
                for sha, record_dict in self._index.items():
                    src_url = record_dict.get("provenance", {}).get("source_url")
                    if src_url:
                        self._url_to_sha[src_url] = sha
            except Exception as e:
                logger.warning(f"Failed to read asset index file: {e}")
                self._index = {}

    def _save_local_index(self) -> None:
        """Persists the in-memory catalog to local disk."""
        try:
            payload = {"assets": self._index}
            self.index_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to persist asset index file: {e}")

    def get_drive_engine(self) -> Optional[Any]:
        """Lazy-inits DriveEngine if enabled and available."""
        if not self.use_drive:
            return None
        if self.drive_engine is None:
            try:
                from engines.drive_engine import DriveEngine
                self.drive_engine = DriveEngine()
            except Exception as e:
                logger.warning(f"DriveEngine unavailable, operating in local-only mode: {e}")
                self.use_drive = False
                return None
        return self.drive_engine

    def has_asset_sha(self, sha256: str) -> bool:
        """Checks if an asset with this hash is already registered."""
        return sha256 in self._index

    def has_asset_url(self, url: str) -> bool:
        """Checks if an asset with this source URL is already registered."""
        return url in self._url_to_sha

    def get_by_sha(self, sha256: str, require_production_video: bool = False) -> Optional[AssetRecord]:
        """Retrieves an AssetRecord by its SHA-256 hash."""
        data = self._index.get(sha256)
        if data:
            rec = AssetRecord.from_dict(data)
            if require_production_video and not rec.is_production_video_eligible():
                logger.info(f"[CloudAssetRegistry] Rejecting historical non-video asset {rec.asset_id} for production query.")
                return None
            return rec
        return None

    def get_by_url(self, url: str, require_production_video: bool = False) -> Optional[AssetRecord]:
        """Retrieves an AssetRecord by its source URL."""
        sha = self._url_to_sha.get(url)
        if sha:
            return self.get_by_sha(sha, require_production_video=require_production_video)
        return None

    def register_asset(
        self,
        file_path: Path,
        record: AssetRecord,
        upload_to_cloud: bool = True
    ) -> AssetRecord:
        """
        Stores media file and metadata record into the cloud registry and local cache.
        """
        # Save local copy in cache
        cached_media_path = self.local_cache_dir / f"{record.sha256[:16]}_{record.filename}"
        if not cached_media_path.exists() and file_path != cached_media_path:
            import shutil
            shutil.copy2(str(file_path), str(cached_media_path))
        record.local_cached_path = str(cached_media_path)

        # Upload to Google Drive if active
        if upload_to_cloud and self.use_drive and not TEST_MODE:
            try:
                drive = self.get_drive_engine()
                if drive and hasattr(drive, "get_drive_service"):
                    drive_service = drive.get_drive_service()
                    if drive_service:
                        vault_root = drive.inspect_or_init_vault(create_if_missing=True)
                        root_id = vault_root.get("root")

                        # Locate or create VISUAL_LIBRARY folder
                        vis_folder = drive.find_folder("VISUAL_LIBRARY", parent_id=root_id)
                        if not vis_folder:
                            vis_folder = drive.create_folder("VISUAL_LIBRARY", parent_id=root_id)
                        vis_folder_id = vis_folder["id"]

                        # Upload media binary
                        from googleapiclient.http import MediaFileUpload
                        cloud_name = f"{record.sha256[:12]}_{record.filename}"
                        media_body = MediaFileUpload(str(cached_media_path), mimetype=record.technical_meta.mime_type, resumable=True)
                        uploaded = drive_service.files().create(
                            body={
                                "name": cloud_name,
                                "parents": [vis_folder_id],
                                "description": f"Asset SHA: {record.sha256} | Source: {record.provenance.provider_name}",
                                "properties": {
                                    "sha256": record.sha256,
                                    "automation_id": "harry_potter",
                                    "source_provider": record.provenance.provider_name,
                                    "media_category": record.media_category.value,
                                }
                            },
                            media_body=media_body,
                            fields="id, name"
                        ).execute()

                        record.cloud_file_id = uploaded.get("id")
                        record.cloud_path = f"VISUAL_LIBRARY/{cloud_name}"
                        logger.info(f"[CloudRegistry] Uploaded asset {record.asset_id} to Drive: {record.cloud_file_id}")
            except Exception as drive_err:
                logger.warning(f"[CloudRegistry] Drive upload failed (falling back to local cache): {drive_err}")

        # Update in-memory index & persist
        self._index[record.sha256] = record.to_dict()
        if record.provenance.source_url:
            self._url_to_sha[record.provenance.source_url] = record.sha256
        self._save_local_index()

        # Save individual metadata json
        meta_file = self.local_cache_dir / f"{record.sha256}.json"
        meta_file.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")

        return record

    def list_assets(self, limit: int = 50) -> List[AssetRecord]:
        """Returns indexed asset records."""
        records = [AssetRecord.from_dict(d) for d in self._index.values()]
        return records[:limit]
