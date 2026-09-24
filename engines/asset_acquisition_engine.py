"""
STORY FORGE — Asset Acquisition Engine V1
=========================================
Unified multi-stage internet-native, cloud-native media discovery,
streaming ingestion, validation, analysis, and cloud persistence.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
import uuid
from typing import Dict, List, Optional, Any

from core.acquisition_types import (
    AssetAcquisitionRequest,
    AssetAcquisitionResult,
    AssetCandidate,
    AssetProvenance,
    AssetRecord,
    MediaCategory,
    SourceCategory,
)
from engines.acquisition.cloud_asset_registry import CloudAssetRegistry
from engines.acquisition.media_analyzer import MediaAnalyzer, MediaValidationError
from engines.acquisition.providers.base_provider import AssetSourceProvider, ProviderError
from engines.acquisition.providers.archive_org_provider import InternetArchiveProvider
from engines.acquisition.providers.direct_web_provider import DirectWebProvider
from engines.acquisition.providers.movie_archive_provider import MovieArchiveProvider
from engines.acquisition.providers.wikimedia_provider import WikimediaCommonsProvider
from engines.acquisition.query_generator import AcquisitionQueryGenerator
from core.safe_url_validator import SafeURLValidator

logger = logging.getLogger("AssetAcquisitionEngine")


class AssetAcquisitionEngine:
    """
    Orchestrates intelligent search query synthesis, provider querying,
    bounded streaming download, decodability validation, technical analysis,
    SHA-256 deduplication, and Google Drive cloud registration.
    """

    def __init__(
        self,
        registry: Optional[CloudAssetRegistry] = None,
        providers: Optional[List[AssetSourceProvider]] = None,
        use_drive: bool = True
    ):
        self.registry = registry or CloudAssetRegistry(use_drive=use_drive)
        self.providers: Dict[str, AssetSourceProvider] = {}

        default_providers = providers or [
            MovieArchiveProvider(enabled=True),
            WikimediaCommonsProvider(enabled=True),
            InternetArchiveProvider(enabled=True),
            DirectWebProvider(enabled=True),
        ]
        for p in default_providers:
            self.providers[p.name] = p

    def register_provider(self, provider: AssetSourceProvider) -> None:
        """Registers an additional media acquisition provider."""
        self.providers[provider.name] = provider

    def acquire_for_requirement(
        self,
        requirement: Any,
        target_media_category: MediaCategory = MediaCategory.VIDEO,
        limit: int = 1
    ) -> AssetAcquisitionResult:
        """
        Main entry point for story beats and BeastVisualRequirement specifications.
        Enforces permanent STORY FORGE Policy: VISUALS = VIDEO ONLY.
        """
        if target_media_category == MediaCategory.IMAGE:
            logger.warning("[AssetAcquisition] Overriding IMAGE request: STORY FORGE Policy enforces VISUALS = VIDEO ONLY.")
            target_media_category = MediaCategory.VIDEO

        queries = AcquisitionQueryGenerator.generate_queries(requirement, target_media=target_media_category)
        logger.info(f"[AssetAcquisition] Generated {len(queries)} query tiers: {queries}")

        collected_records: List[AssetRecord] = []
        errors: List[str] = []
        candidates_evaluated = 0

        for q in queries:
            result = self.acquire_by_query(
                query=q,
                target_media_category=target_media_category,
                limit=limit - len(collected_records),
            )
            candidates_evaluated += result.candidates_evaluated
            errors.extend(result.errors)
            collected_records.extend(result.asset_records)

            if len(collected_records) >= limit:
                break

        return AssetAcquisitionResult(
            success=len(collected_records) > 0,
            asset_records=collected_records,
            candidates_evaluated=candidates_evaluated,
            errors=errors,
            query_used=queries[0] if queries else "",
            cache_hit=any(r.local_cached_path for r in collected_records),
        )

    def acquire_by_query(
        self,
        query: str,
        target_media_category: MediaCategory = MediaCategory.VIDEO,
        limit: int = 1
    ) -> AssetAcquisitionResult:
        """
        Queries all active providers, validates candidates, and indexes verified media.
        Enforces permanent STORY FORGE Policy: VISUALS = VIDEO ONLY.
        """
        if target_media_category == MediaCategory.IMAGE:
            logger.warning("[AssetAcquisition] Overriding IMAGE query request: STORY FORGE Policy enforces VISUALS = VIDEO ONLY.")
            target_media_category = MediaCategory.VIDEO

        logger.info(f"[AssetAcquisition] Executing acquisition for query: '{query}'")
        candidates: List[AssetCandidate] = []
        errors: List[str] = []

        # 1. Query available providers
        for name, provider in self.providers.items():
            if not provider.is_available():
                continue
            try:
                provider_candidates = provider.search(
                    query=query,
                    requirements={"target_media_category": target_media_category},
                    limit=limit * 2,
                )
                candidates.extend(provider_candidates)
            except Exception as e:
                err_msg = f"Provider '{name}' error during search: {e}"
                logger.warning(err_msg)
                errors.append(err_msg)

        if not candidates:
            return AssetAcquisitionResult(
                success=False,
                asset_records=[],
                candidates_evaluated=0,
                errors=errors,
                query_used=query,
                cache_hit=False,
            )

        # 2. Ingest, validate, and register candidates
        verified_records: List[AssetRecord] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for cand in candidates:
                # STORY FORGE Hard Policy: VISUALS = VIDEO ONLY. Never acquire images or non-video visual assets.
                if cand.media_category != MediaCategory.VIDEO:
                    logger.debug(f"[AssetAcquisition] Rejecting candidate '{cand.title}': media category '{cand.media_category}' is not VIDEO.")
                    continue

                # Check URL extension for forbidden static image formats
                import urllib.parse
                from core.acquisition_types import FORBIDDEN_IMAGE_EXTENSIONS, FORBIDDEN_IMAGE_MIME_TYPES, FORBIDDEN_IMAGE_TERMS, ProductionAssetType
                parsed_url = urllib.parse.urlparse(cand.download_url)
                cand_suffix = Path(parsed_url.path).suffix.lower()
                if cand_suffix in FORBIDDEN_IMAGE_EXTENSIONS:
                    logger.warning(f"[AssetAcquisition] Rejecting candidate '{cand.title}': Forbidden image extension '{cand_suffix}'. VIDEO ONLY.")
                    continue

                # SSRF & Disallowed Stock Media Provider Validation
                is_safe, reason = SafeURLValidator.is_safe_url(cand.download_url)
                if not is_safe:
                    logger.warning(f"[AssetAcquisition] Candidate '{cand.title}' rejected by security policy: {reason}")
                    errors.append(f"Security validation rejected {cand.download_url}: {reason}")
                    continue

                # Fast URL check in registry — strictly require production video eligibility
                cached_by_url = self.registry.get_by_url(cand.download_url, require_production_video=True)
                if cached_by_url:
                    logger.info(f"[AssetAcquisition] Cache hit by URL for {cand.title}")
                    verified_records.append(cached_by_url)
                    if len(verified_records) >= limit:
                        break
                    continue

                provider = self.providers.get(cand.provenance.provider_name if cand.provenance else "")
                if not provider:
                    continue

                download_target = temp_path / f"cand_{uuid.uuid4().hex[:8]}_{cand.title.replace(' ', '_')[:30]}"
                try:
                    downloaded_file = provider.download(cand, download_target)

                    # Compute SHA-256 for deterministic deduplication
                    sha256 = MediaAnalyzer.calculate_sha256(downloaded_file)

                    # Check if already registered by hash — strictly require production video eligibility
                    cached_by_sha = self.registry.get_by_sha(sha256, require_production_video=True)
                    if cached_by_sha:
                        logger.info(f"[AssetAcquisition] Cache hit by SHA-256 for {cand.title} ({sha256[:12]})")
                        verified_records.append(cached_by_sha)
                        if len(verified_records) >= limit:
                            break
                        continue

                    # Deep analysis & decodability verification
                    tech_meta, vis_meta = MediaAnalyzer.analyze_asset(
                        file_path=downloaded_file,
                        expected_category=MediaCategory.VIDEO,
                    )

                    # Strict post-download rejection of image mime types or 0-duration assets
                    if tech_meta.mime_type in FORBIDDEN_IMAGE_MIME_TYPES:
                        logger.warning(f"[AssetAcquisition] Rejecting candidate '{cand.title}': Detected image mime '{tech_meta.mime_type}'.")
                        continue

                    if tech_meta.duration_sec <= 0.0:
                        logger.warning(f"[AssetAcquisition] Rejecting candidate '{cand.title}': Zero duration non-video asset.")
                        continue

                    # Assemble complete AssetRecord with VIDEO_ONLY_PRODUCTION_ASSET typing
                    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
                    provenance = cand.provenance or AssetProvenance(
                        source_url=cand.download_url,
                        provider_name=provider.name,
                        search_query=query,
                        retrieved_at_iso=datetime.now(timezone.utc).isoformat(),
                    )

                    record = AssetRecord(
                        asset_id=asset_id,
                        sha256=sha256,
                        filename=downloaded_file.name,
                        media_category=MediaCategory.VIDEO,
                        source_category=cand.source_category,
                        technical_meta=tech_meta,
                        visual_meta=vis_meta,
                        provenance=provenance,
                        created_at_iso=datetime.now(timezone.utc).isoformat(),
                        tags=[query, cand.title],
                        production_asset_type=ProductionAssetType.VIDEO_ONLY_PRODUCTION_ASSET.value,
                    )

                    # Persist into registry & cloud storage
                    registered = self.registry.register_asset(
                        file_path=downloaded_file,
                        record=record,
                        upload_to_cloud=True,
                    )
                    verified_records.append(registered)
                    logger.info(f"[AssetAcquisition] Successfully registered video asset '{registered.asset_id}' ({registered.filename})")

                    if len(verified_records) >= limit:
                        break

                except MediaValidationError as val_err:
                    logger.warning(f"Media validation failed for candidate '{cand.title}': {val_err}")
                    errors.append(str(val_err))
                except ProviderError as prov_err:
                    logger.warning(f"Provider download error for candidate '{cand.title}': {prov_err}")
                    errors.append(str(prov_err))
                except Exception as exc:
                    logger.warning(f"Unexpected error acquiring candidate '{cand.title}': {exc}")
                    errors.append(str(exc))

        return AssetAcquisitionResult(
            success=len(verified_records) > 0,
            asset_records=verified_records,
            candidates_evaluated=len(candidates),
            errors=errors,
            query_used=query,
            cache_hit=False,
        )

    def acquire_from_url(self, url: str) -> Optional[AssetRecord]:
        """Direct acquisition of a specific media URL."""
        res = self.acquire_by_query(query=url, limit=1)
        if res.success and res.asset_records:
            return res.asset_records[0]
        return None
