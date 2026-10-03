"""
STORY FORGE — Phase 5: Pre-Render EDL Validator
================================================
Part 2 of the 34-part Phase 5 specification.

Validates the VisualEDL BEFORE any rendering begins.
Returns explicit failure codes — does NOT auto-repair.

Failure codes:
    EDL_INCOMPLETE          — EDL.is_complete is False
    EDL_STALE               — EDL lineage hash invalid or lineage mismatch
    SOURCE_MISSING          — A source movie clip file is missing
    INVALID_INTERVAL        — source_clip_start >= source_clip_end, or < 0
    NARRATION_MISMATCH      — narration_hash mismatch with provided locked narration
    LINEAGE_MISMATCH        — EDL lineage binding broken
    UNFULFILLED_DIRECT_BEAT — A DIRECT beat has UNFULFILLED coverage state
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

from engines.edl.models import (
    VisualEDL,
    EDLEntry,
    CoverageState,
)

logger = logging.getLogger("EDLValidator")


class EDLValidationFailureCode(str, Enum):
    """Explicit failure codes for pre-render EDL validation."""
    EDL_INCOMPLETE = "EDL_INCOMPLETE"
    EDL_STALE = "EDL_STALE"
    SOURCE_MISSING = "SOURCE_MISSING"
    INVALID_INTERVAL = "INVALID_INTERVAL"
    NARRATION_MISMATCH = "NARRATION_MISMATCH"
    LINEAGE_MISMATCH = "LINEAGE_MISMATCH"
    UNFULFILLED_DIRECT_BEAT = "UNFULFILLED_DIRECT_BEAT"


@dataclass
class EDLValidationResult:
    """Result of pre-render EDL validation."""
    passed: bool
    failure_codes: List[EDLValidationFailureCode] = field(default_factory=list)
    failure_details: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    entries_validated: int = 0
    entries_rejected: int = 0

    def add_failure(self, code: EDLValidationFailureCode, detail: str) -> None:
        self.passed = False
        self.failure_codes.append(code)
        self.failure_details.append(f"[{code.value}] {detail}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_codes": [c.value for c in self.failure_codes],
            "failure_details": self.failure_details,
            "warnings": self.warnings,
            "entries_validated": self.entries_validated,
            "entries_rejected": self.entries_rejected,
        }


class EDLValidator:
    """
    Validates the VisualEDL before any rendering begins.

    CRITICAL: This validator NEVER modifies the EDL.
    On failure it returns the structured EDLValidationResult.
    The caller must stop and surface the failure — do NOT auto-repair.
    """

    def __init__(
        self,
        movies_dir: Optional[Path] = None,
        require_source_files: bool = True,
    ):
        """
        Args:
            movies_dir: directory where source movie files live.
            require_source_files: if False, skip SOURCE_MISSING check
                                  (useful for isolated unit tests without real movies).
        """
        if movies_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                movies_dir = PROJECT_ROOT / "data" / "movies"
            except ImportError:
                movies_dir = Path("data/movies")

        self.movies_dir = Path(movies_dir)
        self.require_source_files = require_source_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        edl: VisualEDL,
        narration_hash: Optional[str] = None,
    ) -> EDLValidationResult:
        """
        Run all pre-render validation gates.

        Args:
            edl: The VisualEDL to validate.
            narration_hash: Expected narration SHA-256 hash from locked narration.
                            If provided, validated against EDL lineage.
        Returns:
            EDLValidationResult — if .passed is False, DO NOT RENDER.
        """
        result = EDLValidationResult(passed=True)

        self._check_completeness(edl, result)
        self._check_lineage(edl, result)
        self._check_narration_hash(edl, narration_hash, result)
        self._check_entries(edl, result)

        return result

    # ------------------------------------------------------------------
    # Gate 1: Completeness
    # ------------------------------------------------------------------

    def _check_completeness(self, edl: VisualEDL, result: EDLValidationResult) -> None:
        """EDL must be marked complete — no UNFULFILLED direct beats."""
        if not edl.is_complete:
            reason = edl.failure_reason or "EDL.is_complete is False — direct beats are unfulfilled."
            result.add_failure(EDLValidationFailureCode.EDL_INCOMPLETE, reason)

    # ------------------------------------------------------------------
    # Gate 2: Lineage integrity
    # ------------------------------------------------------------------

    def _check_lineage(self, edl: VisualEDL, result: EDLValidationResult) -> None:
        """Lineage hash must be valid (64 hex chars)."""
        lineage = edl.lineage
        if not lineage.is_valid():
            result.add_failure(
                EDLValidationFailureCode.EDL_STALE,
                f"EDL lineage hash is invalid or absent (hash='{lineage.edl_hash}'). EDL may be stale or corrupted.",
            )
            return

        # Cross-check: content_id consistent
        if lineage.content_id != edl.content_id:
            result.add_failure(
                EDLValidationFailureCode.LINEAGE_MISMATCH,
                f"Lineage content_id '{lineage.content_id}' does not match EDL content_id '{edl.content_id}'.",
            )

    # ------------------------------------------------------------------
    # Gate 3: Narration hash
    # ------------------------------------------------------------------

    def _check_narration_hash(
        self,
        edl: VisualEDL,
        narration_hash: Optional[str],
        result: EDLValidationResult,
    ) -> None:
        """If a locked narration hash is provided, verify it matches the EDL lineage."""
        if narration_hash is None:
            result.warnings.append("No narration_hash provided — skipping narration integrity check.")
            return

        edl_narration_hash = edl.lineage.narration_hash
        if edl_narration_hash != narration_hash:
            result.add_failure(
                EDLValidationFailureCode.NARRATION_MISMATCH,
                (
                    f"Narration hash mismatch: "
                    f"EDL lineage has '{edl_narration_hash}', "
                    f"locked narration provides '{narration_hash}'. "
                    f"EDL was built for a different narration recording — do NOT render."
                ),
            )

    # ------------------------------------------------------------------
    # Gate 4: Entry-level checks
    # ------------------------------------------------------------------

    def _check_entries(self, edl: VisualEDL, result: EDLValidationResult) -> None:
        """Validate each EDL entry individually."""
        if not edl.entries:
            result.add_failure(
                EDLValidationFailureCode.EDL_INCOMPLETE,
                "EDL contains zero entries — nothing to render.",
            )
            return

        result.entries_validated = len(edl.entries)

        for entry in edl.entries:
            self._check_entry(entry, result)

    def _check_entry(self, entry: EDLEntry, result: EDLValidationResult) -> None:
        """Validate a single EDL entry."""
        # --- Interval validity ---
        if entry.source_clip_start < 0:
            result.entries_rejected += 1
            result.add_failure(
                EDLValidationFailureCode.INVALID_INTERVAL,
                f"Beat '{entry.beat_id}': source_clip_start={entry.source_clip_start} is negative.",
            )
        if entry.source_clip_end <= entry.source_clip_start:
            result.entries_rejected += 1
            result.add_failure(
                EDLValidationFailureCode.INVALID_INTERVAL,
                (
                    f"Beat '{entry.beat_id}': source_clip_end={entry.source_clip_end} "
                    f"<= source_clip_start={entry.source_clip_start}. Zero or negative clip duration."
                ),
            )
        if entry.narration_end <= entry.narration_start:
            result.entries_rejected += 1
            result.add_failure(
                EDLValidationFailureCode.INVALID_INTERVAL,
                (
                    f"Beat '{entry.beat_id}': narration_end={entry.narration_end} "
                    f"<= narration_start={entry.narration_start}. Zero narration duration."
                ),
            )

        # --- Unfulfilled direct beats ---
        if entry.coverage_state == CoverageState.UNFULFILLED:
            result.entries_rejected += 1
            result.add_failure(
                EDLValidationFailureCode.UNFULFILLED_DIRECT_BEAT,
                (
                    f"Beat '{entry.beat_id}' has coverage_state=UNFULFILLED. "
                    f"Required entities: {entry.required_entities}. "
                    f"This beat requires verified visual evidence before rendering."
                ),
            )

        # --- Source file presence (if enabled) ---
        if self.require_source_files and entry.source_video:
            source_path = self._resolve_source_path(entry)
            if not source_path.exists():
                result.entries_rejected += 1
                result.add_failure(
                    EDLValidationFailureCode.SOURCE_MISSING,
                    (
                        f"Beat '{entry.beat_id}': source video not found at '{source_path}'. "
                        f"source_video='{entry.source_video}', movie_id={entry.source_movie_id}."
                    ),
                )

    def _resolve_source_path(self, entry: EDLEntry) -> Path:
        """Attempt to resolve the full path of an EDL source video."""
        if Path(entry.source_video).is_absolute():
            return Path(entry.source_video)
        # Try movies_dir / source_video directly
        candidate = self.movies_dir / entry.source_video
        if candidate.exists():
            return candidate
        # Try movie subdirectory
        candidate2 = self.movies_dir / f"hp{entry.source_movie_id}" / entry.source_video
        return candidate2
