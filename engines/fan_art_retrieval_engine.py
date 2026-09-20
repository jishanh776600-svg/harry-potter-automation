"""
STORY FORGE Fan-Art & Official Artwork Retrieval Engine
======================================================
Coordinates targeted retrieval of existing Harry Potter illustrations and artwork
for novel-only scenes, book-vs-movie differences, and scenes unfilmed in Movies 1–8.

Invariants:
1. TARGETED SEARCH: Queries must be semantically rich (character + action + object + location + event).
   Never broad "Harry Potter fan art".
2. PROVENANCE & RIGHTS: Every asset captures creator, source URL, license, and rights status.
   Unverified licenses default to RIGHTS_UNVERIFIED.
3. NEVER GENERIC STOCK: Pexels, Unsplash, generic B-roll are permanently forbidden.
4. NO BESPOKE AI GENERATION: Searches existing artwork rather than generating new synthetic scenes.
5. CLEAN PRESENTATION: Artwork is formatted to 1080x1920 30fps audio-muted MP4 clips
   using subtle aspect-preserving presentation (no aggressive cropping or artificial zoom).
"""
import os
import re
import json
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

from config.settings import PROJECT_ROOT
from core.hybrid_visual_models import (
    VisualSourceType, RightsStatus, VisualProvenance, FORBIDDEN_SOURCE_PROVIDERS
)

logger = logging.getLogger(__name__)

ARTWORKS_DIR = PROJECT_ROOT / "data" / "artworks"
FAN_ART_DIR = PROJECT_ROOT / "data" / "fan_art"
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"

ARTWORKS_DIR.mkdir(parents=True, exist_ok=True)
FAN_ART_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)


class FanArtRetrievalEngine:
    """
    Manages targeted query generation, artwork search, provenance verification,
    and video clip generation for fan art and official illustrations.
    """

    def __init__(
        self,
        artworks_dir: Optional[Path] = None,
        fan_art_dir: Optional[Path] = None,
        clips_dir: Optional[Path] = None
    ):
        self.artworks_dir = artworks_dir or ARTWORKS_DIR
        self.fan_art_dir = fan_art_dir or FAN_ART_DIR
        self.clips_dir = clips_dir or CLIPS_DIR
        self.curated_index_path = self.artworks_dir / "curated_artwork_index.json"
        self._curated_registry = self._load_curated_registry()

    def _load_curated_registry(self) -> List[Dict[str, Any]]:
        """Loads curated artwork metadata from disk if present."""
        if self.curated_index_path.exists():
            try:
                with open(self.curated_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load curated artwork index: {e}")
        return []

    # --------------------------------------------------------------------------
    # 1. TARGETED QUERY GENERATION
    # --------------------------------------------------------------------------
    @staticmethod
    def generate_targeted_queries(
        beat: Dict[str, Any],
        novel_context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Generates event-specific, semantically rich search queries from a narration beat.
        Never outputs generic 'Harry Potter fan art'.

        Incorporates:
        - Characters (Harry, Peeves, Neville, etc.)
        - Specific action / verb (chaos, sorting, riddle, execution, etc.)
        - Specific object (Remembrall, potion bottles, sorting hat, etc.)
        - Location (Great Hall, corridors, trapdoor, Shrieking Shack, etc.)
        - Book/chapter reference when relevant
        """
        characters = beat.get("characters", [])
        if isinstance(characters, str):
            characters = [c.strip() for c in characters.split(",") if c.strip()]

        char_str = " ".join(characters) if characters else ""
        location = beat.get("location", "")
        action = beat.get("action", "")
        objects = beat.get("objects", [])
        if isinstance(objects, str):
            objects = [o.strip() for o in objects.split(",") if o.strip()]
        obj_str = " ".join(objects) if objects else ""

        narration = beat.get("narration_text", "") or beat.get("text", "")
        book_num = beat.get("book_number") or (novel_context.get("book_number") if novel_context else None)
        chapter_num = beat.get("chapter_number") or (novel_context.get("chapter_number") if novel_context else None)

        queries = []

        # 1. Highly specific event query: Character + Location + Action + Object
        specific_parts = [p for p in [char_str, location, action, obj_str] if p]
        if specific_parts:
            q1 = f"Harry Potter {' '.join(specific_parts)} illustration"
            q1 = re.sub(r"\s+", " ", q1).strip()
            queries.append(q1)

        # 2. Fan art specific query with event/action
        if char_str and (action or location):
            q2 = f"Harry Potter {char_str} {action or location} fan art"
            q2 = re.sub(r"\s+", " ", q2).strip()
            queries.append(q2)

        # 3. Book/chapter grounded query
        if book_num and (char_str or action):
            chapter_info = f"chapter {chapter_num}" if chapter_num else ""
            q3 = f"Harry Potter book {book_num} {chapter_info} {char_str} {action} illustration"
            q3 = re.sub(r"\s+", " ", q3).strip()
            queries.append(q3)

        # 4. Fallback targeted query extracted from narration key terms
        if not queries and narration:
            key_words = [w for w in re.findall(r"[a-zA-Z]{4,}", narration) if w.lower() not in {"this", "that", "with", "from", "were", "they", "there", "every", "scene", "movie"}]
            q4 = f"Harry Potter {' '.join(key_words[:5])} fan art"
            queries.append(q4)

        # Deduplicate while preserving order
        unique_queries = list(dict.fromkeys(queries))
        return unique_queries

    # --------------------------------------------------------------------------
    # 2. ARTWORK RETRIEVAL & CURATED LOOKUP
    # --------------------------------------------------------------------------
    def search_artwork_for_beat(
        self,
        beat: Dict[str, Any],
        preferred_source: VisualSourceType = VisualSourceType.FAN_ART,
        novel_context: Optional[Dict[str, Any]] = None
    ) -> Optional[VisualProvenance]:
        """
        Searches for an existing, relevant illustration matching the narration beat.
        Checks curated library first, then registered artwork records.
        Validates semantic relevance and captures full provenance.
        """
        queries = self.generate_targeted_queries(beat, novel_context=novel_context)
        logger.info(f"[FanArtEngine] Generated targeted queries for {beat.get('beat_id')}: {queries}")

        beat_id = beat.get("beat_id", "beat_1")
        narration = (beat.get("narration_text") or beat.get("text", "")).lower()
        characters = [c.lower() for c in (beat.get("characters") or [])]
        action = (beat.get("action") or "").lower()

        # Check curated registry for matches
        for item in self._curated_registry:
            # Enforce provider check: NO generic stock
            provider = (item.get("provider") or item.get("source") or "").lower()
            if any(f in provider for f in FORBIDDEN_SOURCE_PROVIDERS):
                continue

            # Semantic match scoring
            tags = [t.lower() for t in item.get("tags", [])]
            desc = (item.get("description") or "").lower()
            title = (item.get("title") or "").lower()
            combined_meta = f"{desc} {title} {' '.join(tags)}"

            # Check character and action match
            char_matched = any(c in combined_meta for c in characters) if characters else True
            action_matched = any(w in combined_meta for w in action.split()) if action else True

            if char_matched and action_matched:
                # Found matching artwork in curated library
                file_path = item.get("file_path")
                img_hash = item.get("image_hash")
                if file_path and Path(file_path).exists() and not img_hash:
                    img_hash = self.compute_image_hash(Path(file_path))

                rights_status = item.get("rights_status", RightsStatus.RIGHTS_UNVERIFIED.value)
                if not item.get("license") or rights_status == RightsStatus.RIGHTS_UNVERIFIED.value:
                    rights_status = RightsStatus.RIGHTS_UNVERIFIED
                else:
                    try:
                        rights_status = RightsStatus(rights_status)
                    except ValueError:
                        rights_status = RightsStatus.RIGHTS_UNVERIFIED

                source_type = preferred_source
                if item.get("is_official"):
                    source_type = VisualSourceType.OFFICIAL_ARTWORK

                return VisualProvenance(
                    asset_id=item.get("id", f"art_{hashlib.sha256(combined_meta.encode()).hexdigest()[:12]}"),
                    source_type=source_type,
                    source_url=item.get("source_url", "https://archive.org/details/harrypotter-curated-art"),
                    original_url=item.get("original_url"),
                    creator=item.get("creator", "Unknown Illustrator"),
                    license=item.get("license", "Unverified - Editorial Review Required"),
                    license_url=item.get("license_url"),
                    rights_status=rights_status,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    image_hash=img_hash,
                    search_query=queries[0] if queries else "",
                    visual_description=item.get("description", title),
                    associated_beat_id=beat_id,
                    notes=item.get("notes"),
                    file_path=file_path
                )

        # Check local files directly in artworks or fan_art directory
        for search_dir in [self.artworks_dir, self.fan_art_dir]:
            for img_file in search_dir.glob("*.[jJ][pP][gG]"):
                fname_lower = img_file.name.lower()
                if any(c in fname_lower for c in characters) and (not action or any(w in fname_lower for w in action.split())):
                    img_hash = self.compute_image_hash(img_file)
                    return VisualProvenance(
                        asset_id=f"local_{img_file.stem}",
                        source_type=preferred_source,
                        source_url=f"file://{img_file.resolve()}",
                        original_url=None,
                        creator="Local Curated Repository",
                        license="Curated Editorial Selection",
                        license_url=None,
                        rights_status=RightsStatus.RIGHTS_UNVERIFIED,
                        retrieved_at=datetime.now(timezone.utc).isoformat(),
                        image_hash=img_hash,
                        search_query=queries[0] if queries else img_file.stem,
                        visual_description=f"Local illustration for {img_file.stem}",
                        associated_beat_id=beat_id,
                        file_path=str(img_file)
                    )

        # No truthful visual found
        return None

    # --------------------------------------------------------------------------
    # 3. ARTWORK-TO-VIDEO PRESENTATION FORMATTER
    # --------------------------------------------------------------------------
    @staticmethod
    def compute_image_hash(image_path: Path) -> str:
        """Computes SHA-256 of image file."""
        h = hashlib.sha256()
        with open(image_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def format_artwork_to_clip(
        self,
        artwork_image_path: Path,
        output_clip_path: Path,
        duration_seconds: float,
        target_width: int = 1080,
        target_height: int = 1920
    ) -> Path:
        """
        Converts a still artwork image into an audio-muted (-an) 1080x1920 30 FPS MP4 clip.
        
        Natural Presentation Invariants:
        - NO aggressive zoom/cropping: The full artwork subject must remain visible.
        - Uses classic broadcast vertical layout:
          Blurred, darkened ambient background scaled to fill 1080x1920,
          overlaid with the sharp, correctly proportioned original artwork centered.
        - Strict audio muting: 0 audio streams guaranteed.
        - 30 FPS, H.264 video.
        """
        output_clip_path.parent.mkdir(parents=True, exist_ok=True)
        img_str = str(artwork_image_path.resolve()).replace("\\", "/")
        out_str = str(output_clip_path.resolve()).replace("\\", "/")

        # FFmpeg filter:
        # 1. Background [bg]: scale to fill 1080x1920, crop center, blur, darken slightly
        # 2. Foreground [fg]: scale to fit within 1080x1920 preserving exact aspect ratio
        # 3. Overlay [fg] onto [bg] centered
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
            f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,colorlevels=rimin=0.1:gimin=0.1:bimin=0.1[bg];"
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[vout]"
        )

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1",
            "-i", str(artwork_image_path),
            "-t", f"{duration_seconds:.3f}",
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-an",  # Audio-muted invariant
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            str(output_clip_path)
        ]

        logger.info(f"Formatting artwork {artwork_image_path.name} -> clip {output_clip_path.name} ({duration_seconds:.2f}s)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg artwork formatting failed: {res.stderr[-300:]}")

        # Probe output clip to verify invariants: single video stream, 0 audio streams, 1080x1920
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height",
            "-of", "json",
            str(output_clip_path)
        ]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        probe_data = json.loads(probe_res.stdout) if probe_res.returncode == 0 else {}
        streams = probe_data.get("streams", [])

        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        video_streams = [s for s in streams if s.get("codec_type") == "video"]

        if len(audio_streams) > 0:
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(f"[INVARIANT VIOLATION] Formatted artwork clip contains audio: {output_clip_path.name}")

        if not video_streams or video_streams[0].get("width") != target_width or video_streams[0].get("height") != target_height:
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(f"[INVARIANT VIOLATION] Formatted artwork clip dimensions != {target_width}x{target_height}")

        return output_clip_path
