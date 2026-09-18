"""
Visual Source Router — Harry Potter Automation
============================================================
HARD INVARIANT - VISUAL POLICY: Movie footage ONLY.
No AI visuals, stock footage, Pexels, or book images.

Per-beat retrieval:
    Narration sentence / visual beat
            ↓
    [1] Movie Clip Retrieval (SRT-indexed dialogue/scene match)
            ↓  found?
            ├── YES  →  use movie clip (strictly audio-muted via -an)
            └── NO   →  fail/flag beat (NO AI, NO STOCK, NO PEXELS FALLBACKS)

Movie Source Directories:
  data/movies/           → MP4/MKV files for HP films 1-8
  data/movie_subtitles/  → SRT files for HP films 1-8
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
        Attempts to find matching movie scene timestamps from the indexed SRT database.
        Returns VisualSourceResult with exact start/end timecodes if a scene is found.
        """
        search_query = visual_cue or narration_sentence
        try:
            from engines.movie_asset_engine import MovieAssetEngine
            engine = MovieAssetEngine()
            matches = engine.search_movie_scenes(search_query, limit=1)
            if matches:
                m = matches[0]
                logger.info(f"[MOVIE_RETRIEVER] Found matching scene in Movie {m['movie_number']}: '{m['text'][:60]}...' ({m['start_timecode']} - {m['end_timecode']})")
                return VisualSourceResult(
                    source_type=SOURCE_MOVIE_CLIP,
                    clip_start_sec=m["start_seconds"],
                    clip_end_sec=m["end_seconds"],
                    movie_title=m["movie_title"],
                    query=search_query,
                    is_video=True,
                    metadata={
                        "chunk_id": m["chunk_id"],
                        "start_timecode": m["start_timecode"],
                        "end_timecode": m["end_timecode"],
                        "duration_seconds": m["duration_seconds"],
                        "scene_text": m["text"],
                        "video_filename": m["video_filename"],
                        "video_drive_id": m["video_drive_id"],
                        "audio_muted": True  # Invariant: audio is always stripped
                    }
                )
        except Exception as e:
            logger.warning(f"[MOVIE_RETRIEVER] SRT scene search error: {e}")

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
        # HARD INVARIANT: Movie footage ONLY. No AI visuals, stock footage, Pexels, or book images.
        self.priority = [SOURCE_MOVIE_CLIP]
        logger.info(f"[VISUAL_ROUTER] Visual source policy: MOVIE FOOTAGE ONLY. Priority: {self.priority}")
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
    ) -> Optional[VisualSourceResult]:
        """
        Resolves the best visual asset for a narration beat.
        HARD INVARIANT: Only movie footage from Harry Potter Films 1-8 is permitted.
        Fallbacks to AI images, stock footage, Pexels, or book images are strictly forbidden.

        Args:
            narration_sentence: The narration text for this beat.
            visual_cue:         A descriptive search query for the visual requirement.
            duration_target_sec: Target clip duration.
            db:                  SQLAlchemy session (optional).

        Returns:
            VisualSourceResult with the matching movie clip (audio muted), or None if no match found.
        """
        query = visual_cue or narration_sentence

        try:
            result = self.movie_retriever.retrieve_clip_for_beat(
                narration_sentence=narration_sentence,
                visual_cue=visual_cue,
                duration_target_sec=duration_target_sec
            )
            if result:
                logger.info(f"[VISUAL_ROUTER] ✅ MOVIE CLIP resolved for: '{query[:50]}'")
                return result
            logger.warning(f"[VISUAL_ROUTER] ⚠️ No movie clip found for: '{query[:50]}' — visual policy forbids non-movie fallbacks.")
        except Exception as e:
            logger.error(f"[VISUAL_ROUTER] Movie clip retrieval error: {e}")

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # --------------------------------------------------------------------------
    # Internal per-source retrieval methods (stubs)
    # --------------------------------------------------------------------------

    def _try_book_image(self, query: str) -> Optional[VisualSourceResult]:
        # Attempt to find book illustration or canonical image
        return None

    def _try_ai_image(self, query: str) -> Optional[VisualSourceResult]:
        # Attempt to generate an AI image via NVIDIA (primary) or Pollinations (fallback)
        return None

    def _try_stock(self, query: str) -> Optional[VisualSourceResult]:
        # Attempt to find archival stock imagery
        return None

    def _try_pexels(self, query: str) -> Optional[VisualSourceResult]:
        # LAST RESORT: Attempt Pexels search
        return None


def get_visual_source_router() -> VisualSourceRouter:
    return VisualSourceRouter()

