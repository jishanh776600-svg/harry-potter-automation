"""
STORY FORGE Hybrid Visual Source Resolution Engine
===================================================
Orchestrates truthful visual resolution for every storyboard / narration beat:

1. MOVIE_DIRECT:
   - Evaluates if the exact narrated event exists in Movies 1–8.
   - Leverages MovieRetrievalEngine and EventSemanticVisualEngine.
   - Enforces commit 37b1463 natural framing policy (medium shot preference, no unnecessary zoom).
   - Audio-muted (-an), rapid-fire pacing (1.5s–3.0s).

2. FAN_ART / OFFICIAL_ARTWORK:
   - For novel-only scenes, book-vs-movie differences, or unfilmed events.
   - Executes targeted fan-art search via FanArtRetrievalEngine.
   - Verifies semantic match to the beat.
   - Enforces provenance metadata (creator, source URL, license, rights status).
   - Unverified licenses default to RIGHTS_UNVERIFIED.

3. NO_VALID_VISUAL:
   - If neither an accurate movie shot nor approved artwork can be found:
   - Marks beat as NO_VALID_VISUAL.
   - NEVER forces unrelated movie footage merely to fill time.
   - NEVER uses generic stock imagery (Pexels, Unsplash, generic B-roll permanently forbidden).
   - NEVER generates bespoke AI image scene replacements.
"""
import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from config.settings import PROJECT_ROOT, DB_PATH
from core.hybrid_visual_models import (
    VisualSourceType, RightsStatus, VisualProvenance,
    StoryboardBeatMetadata, FORBIDDEN_SOURCE_PROVIDERS
)
from engines.movie_retrieval_engine import MovieRetrievalEngine, ShotScale
from engines.fan_art_retrieval_engine import FanArtRetrievalEngine

logger = logging.getLogger(__name__)

CLIPS_DIR = PROJECT_ROOT / "data" / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# Minimum movie retrieval score to consider a movie event "directly filmed and matching"
MIN_MOVIE_DIRECT_SCORE = 65.0


class HybridVisualEngine:
    """
    Truthful hybrid visual resolution engine implementing:
    Movie Footage First -> Existing Fan Art / Official Artwork -> No Valid Visual.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        clips_dir: Optional[Path] = None,
        fan_art_engine: Optional[FanArtRetrievalEngine] = None,
        movie_engine: Optional[MovieRetrievalEngine] = None
    ):
        self.db_path = db_path or DB_PATH
        self.clips_dir = clips_dir or CLIPS_DIR
        self.fan_art_engine = fan_art_engine or FanArtRetrievalEngine(clips_dir=self.clips_dir)
        self.movie_engine = movie_engine or MovieRetrievalEngine(db_path=self.db_path, clips_dir=self.clips_dir)

    def resolve_beat_visual(
        self,
        beat: Dict[str, Any],
        script_id: str,
        novel_context: Optional[Dict[str, Any]] = None,
        allow_download: bool = False,
        used_movie_intervals: Optional[List[Tuple[float, float]]] = None
    ) -> Dict[str, Any]:
        """
        Resolves a single narration beat to a truthful visual source:
        Returns dictionary containing:
        - visual_source: VisualSourceType
        - shot_metadata: StoryboardBeatMetadata
        - provenance: Optional[VisualProvenance]
        - clip_file_path: Optional[str]
        - status: ACCEPTED | REJECTED | NO_VALID_VISUAL
        - reason: Optional[str]
        """
        beat_id = beat.get("beat_id", "beat_1")
        narration = beat.get("narration_text") or beat.get("text", "")
        policy = beat.get("visual_source_policy", "HYBRID_TRUTHFUL")

        # Hard guard: reject generic stock providers
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in json.dumps(beat).lower():
                raise ValueError(f"FORBIDDEN VISUAL SOURCE: Beat '{beat_id}' requested '{forbidden}'. Stock is permanently disabled.")

        # Check if beat is explicitly designated as novel-only / fan art
        is_novel_only = beat.get("is_novel_only", False) or beat.get("discovery_type") in ("BOOK_ONLY_DETAIL", "NOVEL_ONLY")

        # ----------------------------------------------------------------------
        # Step A: MOVIE FOOTAGE FIRST (if not novel-only)
        # ----------------------------------------------------------------------
        if not is_novel_only:
            try:
                candidates = self.movie_engine.search_candidates_for_beat(beat)
                for c in candidates:
                    self.movie_engine.expand_candidate_context(c)

                ranked = self.movie_engine.rerank_candidates(
                    beat, candidates, used_intervals=used_movie_intervals or []
                )

                if ranked and ranked[0].get("retrieval_score", 0.0) >= MIN_MOVIE_DIRECT_SCORE:
                    top_cand = ranked[0]
                    target_shots = self.movie_engine.resolve_beat_to_shots(
                        beat, [top_cand], target_shots_per_beat=1, used_intervals=used_movie_intervals or []
                    )
                    if target_shots:
                        sh = target_shots[0]
                        m_num = top_cand["movie_number"]
                        movie_file, source_mode, drive_id = self.movie_engine.resolve_movie_file(
                            m_num, allow_download=allow_download
                        )
                        if movie_file and movie_file.exists():
                            clip_info = self.movie_engine.extract_rapid_shot(
                                shot=sh,
                                script_id=script_id,
                                beat_id=beat_id,
                                movie_path=movie_file
                            )
                            meta = StoryboardBeatMetadata(
                                beat_id=beat_id,
                                visual_source=VisualSourceType.MOVIE_DIRECT,
                                description=f"Movie {m_num} shot @ {sh['clip_start_seconds']:.1f}s ({sh['duration_seconds']:.1f}s)",
                                movie_number=m_num,
                                clip_start_seconds=sh["clip_start_seconds"],
                                clip_end_seconds=sh["clip_end_seconds"],
                                duration_seconds=sh["duration_seconds"],
                                notes=f"Natural framing: {sh.get('framing', 'MEDIUM_SHOT')}"
                            )
                            return {
                                "visual_source": VisualSourceType.MOVIE_DIRECT,
                                "shot_metadata": meta,
                                "provenance": None,
                                "clip_file_path": clip_info["file_path"],
                                "duration_seconds": sh["duration_seconds"],
                                "status": "ACCEPTED",
                                "reason": f"Direct movie match score {top_cand['retrieval_score']:.1f}"
                            }
            except Exception as e:
                logger.debug(f"[HybridVisual] Movie retrieval check failed for {beat_id}: {e}")

        # ----------------------------------------------------------------------
        # Step B: EXISTING RELEVANT FAN ART / OFFICIAL ARTWORK
        # ----------------------------------------------------------------------
        # Search targeted fan art or official artwork
        provenance = self.fan_art_engine.search_artwork_for_beat(
            beat,
            preferred_source=VisualSourceType.FAN_ART,
            novel_context=novel_context
        )

        if provenance and provenance.file_path and Path(provenance.file_path).exists():
            art_path = Path(provenance.file_path)
            clip_name = f"{script_id}_{beat_id}_fanart.mp4"
            out_clip = self.clips_dir / clip_name
            beat_dur = float(beat.get("duration_seconds", 2.5))

            self.fan_art_engine.format_artwork_to_clip(
                artwork_image_path=art_path,
                output_clip_path=out_clip,
                duration_seconds=beat_dur
            )

            meta = StoryboardBeatMetadata(
                beat_id=beat_id,
                visual_source=provenance.source_type,
                description=provenance.visual_description,
                source_url=provenance.source_url,
                original_url=provenance.original_url,
                creator=provenance.creator,
                license=provenance.license,
                license_url=provenance.license_url,
                rights_status=provenance.rights_status.value,
                search_query=provenance.search_query,
                duration_seconds=beat_dur,
                notes=f"Artwork presentation: aspect ratio preserved (no zoom)"
            )

            return {
                "visual_source": provenance.source_type,
                "shot_metadata": meta,
                "provenance": provenance,
                "clip_file_path": str(out_clip),
                "duration_seconds": beat_dur,
                "status": "ACCEPTED",
                "reason": f"Resolved via {provenance.source_type.value}: {provenance.creator or 'curated artwork'}"
            }

        # ----------------------------------------------------------------------
        # Step C: NO_VALID_VISUAL (Truthful Fallback)
        # ----------------------------------------------------------------------
        # Neither movie footage nor approved artwork exists: DO NOT FORCE UNRELATED VISUALS!
        logger.warning(
            f"[HybridVisual] Beat {beat_id} has NO truthful visual. "
            "Marking NO_VALID_VISUAL. Silently substituting unrelated footage is strictly forbidden."
        )

        meta = StoryboardBeatMetadata(
            beat_id=beat_id,
            visual_source=VisualSourceType.NO_VALID_VISUAL,
            description="No truthful visual found for beat narration",
            duration_seconds=float(beat.get("duration_seconds", 2.5)),
            notes="Flagged for script adaptation or candidate review"
        )

        return {
            "visual_source": VisualSourceType.NO_VALID_VISUAL,
            "shot_metadata": meta,
            "provenance": None,
            "clip_file_path": None,
            "duration_seconds": float(beat.get("duration_seconds", 2.5)),
            "status": "NO_VALID_VISUAL",
            "reason": "Neither accurate movie footage nor approved artwork depicts this specific beat."
        }
