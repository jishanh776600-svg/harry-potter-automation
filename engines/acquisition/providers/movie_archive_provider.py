"""
STORY FORGE — Movie Archive Media Provider
===========================================
Acquires frame-accurate video evidence directly extracted from canonical
movie archives (Sorcerer's Stone and Deathly Hallows Part 2) with strict
FFmpeg sub-clip extraction, temporal grounding metadata, and rights classification.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Any
import urllib.parse

from config.settings import DATA_DIR
from core.acquisition_types import (
    AssetCandidate,
    AssetProvenance,
    MediaCategory,
    RightsClassification,
    RightsMetadata,
    SourceCategory,
)
from engines.acquisition.providers.base_provider import (
    AssetSourceProvider,
    ProviderDownloadError,
)

logger = logging.getLogger("AssetAcquisition.MovieArchive")

MOVIE_1_PATH = DATA_DIR / "movies" / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv"
MOVIE_8_PATH = DATA_DIR / "movies" / "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv"

CANONICAL_MOVIE_SCENES: List[Dict[str, Any]] = [
    {
        "id": "dh2_harry_voldemort_duel_standoff",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 6420.0,
        "end_sec": 6465.0,
        "title": "Harry Potter and Voldemort Courtyard Wand Standoff and Duel Clash",
        "characters": ["Harry Potter", "Lord Voldemort", "Tom Riddle"],
        "actions": ["circle each other", "wands raised in tense standoff", "spell clash", "duel standoff"],
        "objects": ["Elder Wand", "Hawthorn Wand", "Wands"],
        "location": "Hogwarts Courtyard",
        "evidence_type": "DIRECT_EVIDENCE",
        "notes": "Courtyard duel standoff and spell clash in Deathly Hallows Part 2. Contrasts book Great Hall duel.",
    },
    {
        "id": "dh2_great_hall_crowd_aftermath",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 6580.0,
        "end_sec": 6625.0,
        "title": "Hogwarts Great Hall Silent Crowd and Defenders Gathering",
        "characters": ["Hogwarts Survivors", "Defenders of Hogwarts", "Harry Potter"],
        "actions": ["gathered in Great Hall in dead silence", "watching in silence", "mourning fallen"],
        "objects": ["Great Hall tables", "torches"],
        "location": "Great Hall",
        "evidence_type": "CONTEXTUAL_EVIDENCE",
        "notes": "Great Hall interior crowd framing after the battle, survivors lining the walls in silent aftermath.",
    },
    {
        "id": "dh2_molly_bellatrix_lethal_duel",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 6374.0,
        "end_sec": 6405.0,
        "title": "Molly Weasley vs Bellatrix Lestrange Lethal Great Hall Duel",
        "characters": ["Molly Weasley", "Bellatrix Lestrange"],
        "actions": ["duel furiously", "wand clash", "strike over heart", "freeze and shatter toppling", "cast lethal spell"],
        "objects": ["Wands", "Cracked stone floor"],
        "location": "Great Hall",
        "evidence_type": "DIRECT_EVIDENCE",
        "notes": "Exact duel sequence where Molly steps forward, duels Bellatrix furiously over cracking stone floor until striking Bellatrix over the heart.",
    },
    {
        "id": "dh2_grawp_giants_battle",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 5695.0,
        "end_sec": 5725.0,
        "title": "Grawp Battling Death Eater Giants at Hogwarts Castle Exterior",
        "characters": ["Grawp", "Death Eater Giants"],
        "actions": ["fighting giants", "brawling in battle", "charging", "defending castle"],
        "objects": ["boulders", "wooden clubs"],
        "location": "Hogwarts Castle Exterior",
        "evidence_type": "DIRECT_EVIDENCE",
        "notes": "Grawp engaging giant attackers during the exterior assault on Hogwarts.",
    },
    {
        "id": "m1_centaur_firenze_forest_archer",
        "movie_number": 1,
        "video_path": MOVIE_1_PATH,
        "start_sec": 6512.0,
        "end_sec": 6530.0,
        "title": "Centaur Firenze in Forbidden Forest",
        "characters": ["Centaurs", "Firenze", "Harry Potter"],
        "actions": ["rearing up", "forest archers", "protecting Harry", "galloping"],
        "objects": ["Bow", "Arrows"],
        "location": "Forbidden Forest",
        "evidence_type": "CONTEXTUAL_EVIDENCE",
        "notes": "Contextual centaur footage from Sorcerer's Stone; classified as CONTEXTUAL since it depicts centaurs in Forbidden Forest rather than Battle of Hogwarts entrance hall.",
    },
    {
        "id": "dh2_elder_wand_viaduct_bridge",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 6738.0,
        "end_sec": 6765.0,
        "title": "Harry Potter Holding Elder Wand on Viaduct Bridge",
        "characters": ["Harry Potter", "Ron Weasley", "Hermione Granger"],
        "actions": ["holding Elder Wand", "inspecting wand", "snapping wand", "conversing"],
        "objects": ["Elder Wand"],
        "location": "Viaduct Bridge",
        "evidence_type": "OBJECT_PROP_EVIDENCE",
        "notes": "Movie sequence showing the Elder Wand prop in detail before Harry snaps it. Contrasts book repair.",
    },
    {
        "id": "dh2_voldemort_spell_rebound_fall",
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "start_sec": 6512.0,
        "end_sec": 6526.0,
        "title": "Voldemort Killing Curse Rebounding and Collapsing Backward",
        "characters": ["Lord Voldemort", "Harry Potter", "Tom Riddle"],
        "actions": ["curse rebounds", "Elder Wand flies away", "falls backward lifeless", "collapsing to stone floor"],
        "objects": ["Elder Wand"],
        "location": "Hogwarts Courtyard Stone Floor",
        "evidence_type": "DIRECT_EVIDENCE",
        "notes": "Rebounding curse and falling backward motion. Contrasts book mortal corpse in Great Hall with film ash flaking.",
    }
]


class MovieArchiveProvider(AssetSourceProvider):
    """
    Extracts frame-accurate video candidates from canonical Harry Potter movie files.
    """

    def __init__(self, enabled: bool = True):
        super().__init__(
            name="movie_archive",
            enabled=enabled,
            rate_limit_delay=0.1,
            max_retries=1,
        )

    def is_available(self) -> bool:
        """Returns True if at least one movie file exists on disk."""
        return self.enabled and (MOVIE_8_PATH.exists() or MOVIE_1_PATH.exists())

    def search(
        self,
        query: str,
        requirements: Optional[Dict[str, Any]] = None,
        limit: int = 5
    ) -> List[AssetCandidate]:
        """
        Searches canonical scenes matching the query or requirements.
        """
        if not self.is_available() or not query.strip():
            return []

        q_lower = query.lower().strip()
        tokens = set(q_lower.split())

        candidates: List[AssetCandidate] = []

        for scene in CANONICAL_MOVIE_SCENES:
            v_path = Path(scene["video_path"])
            if not v_path.exists():
                continue

            # Compute match score based on character, object, action, and location overlap
            score = 0.0
            searchable_text = (
                f"{scene['title']} "
                f"{' '.join(scene['characters'])} "
                f"{' '.join(scene['actions'])} "
                f"{' '.join(scene['objects'])} "
                f"{scene['location']} "
                f"{scene['notes']}"
            ).lower()

            for token in tokens:
                if len(token) > 2 and token in searchable_text:
                    score += 0.25

            # Exact character or object boost
            for char in scene["characters"]:
                if char.lower() in q_lower:
                    score += 0.5
            for obj in scene["objects"]:
                if obj.lower() in q_lower:
                    score += 0.5
            for act in scene["actions"]:
                if act.lower() in q_lower:
                    score += 0.4

            if score > 0.3:
                start_sec = scene["start_sec"]
                end_sec = scene["end_sec"]
                duration = round(end_sec - start_sec, 2)
                url = f"movie://{scene['movie_number']}/{start_sec}/{end_sec}"

                cand = AssetCandidate(
                    candidate_id=f"movie_{scene['id']}",
                    title=scene["title"],
                    download_url=url,
                    preview_url=None,
                    media_category=MediaCategory.VIDEO,
                    source_category=SourceCategory.ARCHIVAL,
                    provenance=AssetProvenance(
                        source_url=url,
                        provider_name=self.name,
                        search_query=query,
                        retrieved_at_iso=datetime.now(timezone.utc).isoformat(),
                        rights=RightsMetadata(
                            classification=RightsClassification.EDITORIAL_FAIR_USE,
                            license_name="Warner Bros. Entertainment (Editorial Fair Use Reference / Critical Commentary)",
                            author="Warner Bros. Pictures",
                            attribution_text=f"Harry Potter and the {'Deathly Hallows Part 2' if scene['movie_number']==8 else 'Sorcerer Stone'}",
                            commercial_cleared=False,
                            notes=scene["notes"],
                        ),
                        external_id=scene["id"],
                    ),
                    score=min(score, 1.0),
                    estimated_size_bytes=int(duration * 250_000),  # Approx 250KB/sec at crf 20
                    description=scene["notes"],
                    extra_attributes={
                        "movie_number": scene["movie_number"],
                        "source_start": start_sec,
                        "source_end": end_sec,
                        "duration_sec": duration,
                        "characters_present": scene["characters"],
                        "objects_present": scene["objects"],
                        "actions_depicted": scene["actions"],
                        "environment": scene["location"],
                        "evidence_type": scene["evidence_type"],
                    }
                )
                candidates.append(cand)

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    def download(self, candidate: AssetCandidate, dest_path: Path) -> Path:
        """
        Extracts sub-clip using FFmpeg with frame-accurate seek and h264 re-encoding.
        """
        extra = candidate.extra_attributes or {}
        m_num = extra.get("movie_number", 8)
        start_sec = extra.get("source_start")
        end_sec = extra.get("source_end")

        if start_sec is None or end_sec is None:
            # Parse from URL movie://{movie_number}/{start_sec}/{end_sec}
            parsed = urllib.parse.urlparse(candidate.download_url)
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                start_sec = float(parts[0])
                end_sec = float(parts[1])
            else:
                raise ProviderDownloadError(f"Cannot determine timestamps from candidate: {candidate.download_url}")

        source_movie = MOVIE_8_PATH if m_num == 8 else MOVIE_1_PATH
        if not source_movie.exists():
            raise ProviderDownloadError(f"Canonical movie file missing: {source_movie}")

        # Ensure output filename ends with .mp4
        output_file = dest_path.with_suffix(".mp4")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", str(source_movie),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "128k",
            str(output_file)
        ]

        logger.info(f"[MovieArchive] Extracting clip {candidate.candidate_id} [{start_sec}s - {end_sec}s] to {output_file.name}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise ProviderDownloadError(f"FFmpeg extraction failed: {e.stderr}")

        if not output_file.exists() or output_file.stat().st_size < 1000:
            raise ProviderDownloadError(f"FFmpeg produced invalid or empty file: {output_file}")

        return output_file
