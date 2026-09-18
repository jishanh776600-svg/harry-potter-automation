"""
Visual Source Router — Harry Potter Automation
============================================================
ARCHITECTURE: Movie footage is ALWAYS attempt #1 for every visual beat.

Per-beat retrieval cascade (applied to EACH narration sentence / visual requirement):

    Narration sentence / visual beat
            ↓
    [1] Movie Clip Retrieval  ← ALWAYS FIRST
            ↓  found?
            ├── YES  →  use movie clip
            └── NO
                 ↓
    [2] Book Image / Canonical Illustration
                 ↓  found?
                 ├── YES  →  use book image
                 └── NO
                      ↓
    [3] AI-Generated Visual (NVIDIA / Pollinations fallback)
                      ↓  found?
                      ├── YES  →  use AI image
                      └── NO
                           ↓
    [4] Stock / Archival / Wikimedia
                           ↓  found?
                           ├── YES  →  use stock image
                           └── NO
                                ↓
    [5] Pexels  ← ABSOLUTE LAST RESORT
                                ↓  found?
                                ├── YES  →  use pexels asset
                                └── NO
                                     ↓
    [6] Procedural neutral fallback canvas

The FINAL Short therefore uses as much relevant movie footage as realistically
available, with image/AI/stock only where a suitable movie clip cannot be found.

Movie Source Directories (populated separately):
  data/movies/           → MP4 files for HP films 1-3 (and more)
  data/movie_subtitles/  → SRT files for each movie

The SRT-based semantic clip retrieval engine will be built in a later step.
This router provides the interface that the storyboard/render engine will call,
so all downstream code already uses the correct movie-first contract.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from config.settings import (
    VISUAL_SOURCE_PRIORITY,
    MOVIES_DIR,
    MOVIE_SUBTITLES_DIR,
    ASSETS_CACHE_DIR,
    PEXELS_API_KEY,
    NVIDIA_API_KEY,
    IMAGE_PROVIDER
)

logger = logging.getLogger(__name__)


# ==============================================================================
# VISUAL SOURCE TYPES (mirrors config/constants.py VisualSourceType enum)
# ==============================================================================
SOURCE_MOVIE_CLIP    = "movie_footage"
SOURCE_BOOK_IMAGE    = "book_imagery"
SOURCE_AI_GENERATED  = "ai_generated"
SOURCE_STOCK         = "stock_footage"
SOURCE_PEXELS        = "pexels"
SOURCE_PROCEDURAL    = "procedural_canvas"


class VisualSourceResult:
    """Container for a resolved visual asset."""
    def __init__(
        self,
        source_type: str,
        file_path: Optional[Path] = None,
        clip_start_sec: Optional[float] = None,
        clip_end_sec: Optional[float] = None,
        movie_title: Optional[str] = None,
        query: str = "",
        is_video: bool = False,
        license: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.source_type = source_type
        self.file_path = file_path
        self.clip_start_sec = clip_start_sec
        self.clip_end_sec = clip_end_sec
        self.movie_title = movie_title
        self.query = query
        self.is_video = is_video
        self.license = license
        self.metadata = metadata or {}

    def __repr__(self):
        return (
            f"VisualSourceResult(source={self.source_type}, "
            f"is_video={self.is_video}, "
            f"path={self.file_path})"
        )


class MovieClipRetriever:
    """
    Retrieves relevant Harry Potter movie clips for a given narration beat.

    CURRENT STATE: Stub — SRT semantic retrieval to be implemented in a later step.
    The movies and SRT files are placed in:
      data/movies/         → HP film MP4s
      data/movie_subtitles/ → HP SRT files

    FUTURE IMPLEMENTATION (next step):
      - Load SRT for each movie
      - Semantically match subtitle text to narration sentence
      - Retrieve timestamp range
      - Extract clip using FFmpeg
      - Return VisualSourceResult with movie clip path and timecodes
    """

    def __init__(self):
        self.movies_dir = MOVIES_DIR
        self.subtitles_dir = MOVIE_SUBTITLES_DIR
        self._movie_index: Optional[List[Dict]] = None

    def _build_movie_index(self) -> List[Dict]:
        """Scans movies/ and movie_subtitles/ to build an index of available content."""
        index = []
        if not self.movies_dir.exists():
            return index

        for mp4 in sorted(self.movies_dir.glob("*.mp4")):
            # Find matching SRT
            srt_candidates = [
                self.subtitles_dir / (mp4.stem + ".srt"),
                self.subtitles_dir / (mp4.stem + ".en.srt"),
            ]
            srt_path = next((s for s in srt_candidates if s.exists()), None)
            index.append({
                "movie_file": mp4,
                "movie_title": mp4.stem,
                "srt_file": srt_path,
                "has_subtitles": srt_path is not None,
            })
        return index

    @property
    def movie_index(self) -> List[Dict]:
        if self._movie_index is None:
            self._movie_index = self._build_movie_index()
        return self._movie_index

    @property
    def movies_available(self) -> bool:
        return len(self.movie_index) > 0

    def retrieve_clip_for_beat(
        self,
        narration_sentence: str,
        visual_cue: str = "",
        duration_target_sec: float = 4.0
    ) -> Optional[VisualSourceResult]:
        """
        Attempts to find and extract a movie clip matching the narration beat.

        Returns VisualSourceResult if a clip is found, None otherwise.

        CURRENT STATE: Returns None (stub) — SRT semantic engine to be built in next step.
        This method signature is the stable contract for the storyboard/render engine.
        """
        if not self.movies_available:
            logger.debug("[MOVIE_RETRIEVER] No movies available in data/movies/. Returning None.")
            return None

        logger.debug(
            f"[MOVIE_RETRIEVER] Attempting movie clip for: '{narration_sentence[:60]}...'"
            f" ({len(self.movie_index)} movies available)"
        )

        # TODO (next step): SRT-based semantic retrieval
        # 1. Parse SRT for each movie
        # 2. Embed narration_sentence + visual_cue
        # 3. Find best matching subtitle segment by semantic similarity
        # 4. Extract clip (timestamp ± buffer) using FFmpeg
        # 5. Return VisualSourceResult with clip path and timecodes

        # For now: return None so the cascade falls through to image fallbacks
        return None


class VisualSourceRouter:
    """
    Routes each visual beat through the prioritized source cascade.

    USAGE:
        router = VisualSourceRouter()
        result = router.resolve(
            narration_sentence="Harry stood before the Mirror of Erised...",
            visual_cue="Harry Potter Mirror of Erised Hogwarts",
        )
        # result.source_type tells you what was used
        # result.file_path is the asset path
        # result.is_video tells you if it's a clip (True) or image (False)
    """

    def __init__(self):
        self.movie_retriever = MovieClipRetriever()
        self.priority = VISUAL_SOURCE_PRIORITY
        logger.info(f"[VISUAL_ROUTER] Visual source priority: {self.priority}")
        logger.info(f"[VISUAL_ROUTER] Movies available: {self.movie_retriever.movies_available}")
        if self.movie_retriever.movies_available:
            for m in self.movie_retriever.movie_index:
                srt_status = "WITH SRT" if m["has_subtitles"] else "NO SRT"
                logger.info(f"  [{srt_status}] {m['movie_title']}")

    def resolve(
        self,
        narration_sentence: str,
        visual_cue: str = "",
        duration_target_sec: float = 4.0,
        db=None
    ) -> VisualSourceResult:
        """
        Resolves the best visual asset for a narration beat, following the
        movie-first cascade defined in VISUAL_SOURCE_PRIORITY.

        Args:
            narration_sentence: The narration text for this beat.
            visual_cue:         A descriptive search query for the visual requirement.
            duration_target_sec: Target clip duration (used for video sources).
            db:                  SQLAlchemy session (optional, for dedup checking).

        Returns:
            VisualSourceResult with the best available visual for this beat.
        """
        query = visual_cue or narration_sentence

        for source_type in self.priority:

            # ─── 1. MOVIE CLIP — ALWAYS FIRST ─────────────────────────────────
            if source_type == SOURCE_MOVIE_CLIP:
                try:
                    result = self.movie_retriever.retrieve_clip_for_beat(
                        narration_sentence=narration_sentence,
                        visual_cue=visual_cue,
                        duration_target_sec=duration_target_sec
                    )
                    if result:
                        logger.info(f"[VISUAL_ROUTER] ✅ MOVIE CLIP for: '{query[:50]}'")
                        return result
                    logger.debug(f"[VISUAL_ROUTER] No movie clip found for: '{query[:50]}' — falling through.")
                except Exception as e:
                    logger.warning(f"[VISUAL_ROUTER] Movie clip retrieval error: {e}")

            # ─── 2. BOOK IMAGE / CANONICAL ILLUSTRATION ──────────────────────
            elif source_type == SOURCE_BOOK_IMAGE:
                try:
                    result = self._try_book_image(query)
                    if result:
                        logger.info(f"[VISUAL_ROUTER] ✅ BOOK IMAGE for: '{query[:50]}'")
                        return result
                except Exception as e:
                    logger.warning(f"[VISUAL_ROUTER] Book image error: {e}")

            # ─── 3. AI GENERATED VISUAL ──────────────────────────────────────
            elif source_type == SOURCE_AI_GENERATED:
                try:
                    result = self._try_ai_image(query)
                    if result:
                        logger.info(f"[VISUAL_ROUTER] ✅ AI IMAGE for: '{query[:50]}'")
                        return result
                except Exception as e:
                    logger.warning(f"[VISUAL_ROUTER] AI image error: {e}")

            # ─── 4. STOCK FOOTAGE ─────────────────────────────────────────────
            elif source_type == SOURCE_STOCK:
                try:
                    result = self._try_stock(query)
                    if result:
                        logger.info(f"[VISUAL_ROUTER] ✅ STOCK for: '{query[:50]}'")
                        return result
                except Exception as e:
                    logger.warning(f"[VISUAL_ROUTER] Stock footage error: {e}")

            # ─── 5. PEXELS — ABSOLUTE LAST RESORT ────────────────────────────
            elif source_type == SOURCE_PEXELS:
                try:
                    result = self._try_pexels(query)
                    if result:
                        logger.info(f"[VISUAL_ROUTER] ✅ PEXELS (last resort) for: '{query[:50]}'")
                        return result
                except Exception as e:
                    logger.warning(f"[VISUAL_ROUTER] Pexels error: {e}")

        # ─── 6. PROCEDURAL FALLBACK ──────────────────────────────────────────
        logger.warning(f"[VISUAL_ROUTER] All sources exhausted for: '{query[:50]}' — using procedural canvas.")
        return VisualSourceResult(
            source_type=SOURCE_PROCEDURAL,
            is_video=False,
            query=query,
            license="cc0"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Internal per-source retrieval methods (stubs — each will be fleshed out)
    # ──────────────────────────────────────────────────────────────────────────

    def _try_book_image(self, query: str) -> Optional[VisualSourceResult]:
        """Attempt to find a Harry Potter book illustration or canonical image."""
        # TODO: Implement book imagery retrieval (e.g. scan data/books/ for matching pages)
        return None

    def _try_ai_image(self, query: str) -> Optional[VisualSourceResult]:
        """Attempt to generate an AI image via NVIDIA (primary) or Pollinations (fallback)."""
        if not NVIDIA_API_KEY and IMAGE_PROVIDER == "nvidia":
            logger.debug("[VISUAL_ROUTER] NVIDIA API key not configured — skipping AI image.")
        # TODO: Implement NVIDIA/Pollinations image generation
        return None

    def _try_stock(self, query: str) -> Optional[VisualSourceResult]:
        """Attempt to find archival/Wikimedia stock imagery."""
        # TODO: Implement stock/archival retrieval
        return None

    def _try_pexels(self, query: str) -> Optional[VisualSourceResult]:
        """LAST RESORT: Attempt Pexels search."""
        if not PEXELS_API_KEY:
            logger.debug("[VISUAL_ROUTER] Pexels API key not configured — skipping.")
            return None
        # TODO: Implement Pexels API call (delegating to existing asset_fetcher.py)
        return None


def get_visual_source_router() -> VisualSourceRouter:
    """Factory function — returns the singleton visual source router."""
    return VisualSourceRouter()
