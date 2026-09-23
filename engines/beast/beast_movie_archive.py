"""
STORY FORGE — BEAST Real Movie Archive Retriever
================================================================================
Provides indexed, frame-accurate candidate shots directly extracted from real
Harry Potter movie files (Movie 1: Sorcerer's Stone and Movie 8: Deathly Hallows Part 2).
Uses PySceneDetect to identify precise shot cuts within candidate narrative scenes,
extracts 5-frame temporal sequences, and associates canonical scene metadata.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import scenedetect
from config.settings import DATA_DIR
from core.beast_visual_types import (
    BeastCandidateShot,
    MultiFrameSample,
    NarrativeEra,
)
from core.composition_models import ShotScale

logger = logging.getLogger("BeastMovieArchive")

MOVIE_1_PATH = DATA_DIR / "movies" / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv"
MOVIE_8_PATH = DATA_DIR / "movies" / "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv"

# Canonical scene search regions in Movie 1 and Movie 8
REAL_SCENE_REGIONS = [
    # --- Movie 1: Year 1 ---
    {
        "movie_number": 1,
        "video_path": MOVIE_1_PATH,
        "era": NarrativeEra.YEAR_1,
        "start_sec": 2415.0,
        "end_sec": 2435.0,
        "environment": "Hogwarts Grand Staircase",
        "default_characters": ["Neville Longbottom", "Minerva McGonagall"],
        "default_objects": ["Trevor Toad"],
        "default_actions": ["standing nervously", "looking afraid"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Year 1 Neville looking nervous on staircase before sorting",
    },
    {
        "movie_number": 1,
        "video_path": MOVIE_1_PATH,
        "era": NarrativeEra.YEAR_1,
        "start_sec": 2535.0,
        "end_sec": 2655.0,
        "environment": "Great Hall",
        "default_characters": ["Minerva McGonagall", "Sorting Hat", "Hermione Granger", "Draco Malfoy", "Neville Longbottom"],
        "default_objects": ["Sorting Hat", "Stool"],
        "default_actions": ["sitting on stool", "calling names", "placing sorting hat"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Year 1 Sorting Ceremony in Great Hall with Sorting Hat and Stool",
    },
    {
        "movie_number": 1,
        "video_path": MOVIE_1_PATH,
        "era": NarrativeEra.YEAR_1,
        "start_sec": 6815.0,
        "end_sec": 6845.0,
        "environment": "Gryffindor Common Room",
        "default_characters": ["Neville Longbottom", "Harry Potter", "Hermione Granger", "Ron Weasley"],
        "default_objects": [],
        "default_actions": ["raising fists against friends", "standing and confronting", "I will fight you"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Eleven-year-old Neville raising fists against friends in Common Room",
    },
    {
        "movie_number": 1,
        "video_path": MOVIE_1_PATH,
        "era": NarrativeEra.YEAR_1,
        "start_sec": 8425.0,
        "end_sec": 8455.0,
        "environment": "Great Hall",
        "default_characters": ["Albus Dumbledore", "Neville Longbottom"],
        "default_objects": [],
        "default_actions": ["awarding 10 points to Neville", "cheering and applause"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Dumbledore awarding 10 points to Neville for bravery at feast",
    },

    # --- Movie 8: Year 7 ---
    {
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "era": NarrativeEra.YEAR_7,
        "start_sec": 5945.0,
        "end_sec": 5975.0,
        "environment": "Hogwarts Courtyard",
        "default_characters": ["Lord Voldemort", "Neville Longbottom", "Harry Potter"],
        "default_objects": [],
        "default_actions": ["surrendered to despair", "Harry fell dead in arms", "standing amidst ruins"],
        "default_scale": ShotScale.WIDE_SHOT,
        "description_prefix": "Courtyard ruins after Harry fell, defenders in despair",
    },
    {
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "era": NarrativeEra.YEAR_7,
        "start_sec": 6075.0,
        "end_sec": 6145.0,
        "environment": "Hogwarts Courtyard",
        "default_characters": ["Neville Longbottom", "Lord Voldemort"],
        "default_objects": ["Sorting Hat"],
        "default_actions": ["stepping forward", "last warrior standing", "giving defiant speech", "holding battered hat"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Neville stepping forward holding the battered Sorting Hat as last warrior",
    },
    {
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "era": NarrativeEra.YEAR_7,
        "start_sec": 6160.0,
        "end_sec": 6185.0,
        "environment": "Hogwarts Courtyard",
        "default_characters": ["Neville Longbottom"],
        "default_objects": ["Sorting Hat", "Sword of Gryffindor"],
        "default_actions": ["pulling silver sword from hat", "drawing sword", "defiant battle cry"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Neville pulling Godric's silver sword from the Sorting Hat",
    },
    {
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "era": NarrativeEra.YEAR_7,
        "start_sec": 6520.0,
        "end_sec": 6545.0,
        "environment": "Hogwarts Grand Staircase",
        "default_characters": ["Neville Longbottom", "Nagini"],
        "default_objects": ["Sword of Gryffindor", "Horcrux"],
        "default_actions": ["striking Nagini", "decapitating snake with sword", "destroying final Horcrux"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Neville swinging the sword and striking Nagini down to destroy Horcrux",
    },
    {
        "movie_number": 8,
        "video_path": MOVIE_8_PATH,
        "era": NarrativeEra.YEAR_7,
        "start_sec": 6575.0,
        "end_sec": 6640.0,
        "environment": "Great Hall",
        "default_characters": ["Neville Longbottom"],
        "default_objects": ["Sword of Gryffindor"],
        "default_actions": ["resting in Great Hall", "victorious relief", "sitting with sword"],
        "default_scale": ShotScale.MEDIUM_SHOT,
        "description_prefix": "Aftermath: Neville resting quietly in the Great Hall with the sword",
    },
]


class BeastMovieArchive:
    """
    Manages detection, caching, and retrieval of real movie shots for BEAST.
    """

    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or (DATA_DIR / "cache" / "beast_shots" / "real_movie_catalog.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def load_or_index_shots(self, force_reindex: bool = False) -> List[BeastCandidateShot]:
        """
        Loads candidate shots from cache, or runs PySceneDetect across candidate scene regions.
        """
        if not force_reindex and self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                shots = []
                for item in data:
                    shot = BeastCandidateShot(
                        shot_id=item["shot_id"],
                        source_video=item["source_video"],
                        movie_number=item["movie_number"],
                        start_seconds=item["start_seconds"],
                        end_seconds=item["end_seconds"],
                        duration=item["duration"],
                        narrative_era=NarrativeEra(item.get("narrative_era", "ANY")),
                        scene_description=item.get("scene_description", ""),
                        characters_present=item.get("characters_present", []),
                        objects_present=item.get("objects_present", []),
                        actions_depicted=item.get("actions_depicted", []),
                        environment=item.get("environment", ""),
                        shot_scale=ShotScale(item.get("shot_scale", "medium")),
                    )
                    shots.append(shot)
                logger.info("Loaded %d real movie shots from %s", len(shots), self.cache_file)
                return shots
            except Exception as e:
                logger.warning("Error reading real movie cache (%s). Reindexing...", e)

        # Indexing using PySceneDetect across defined scene regions
        logger.info("Indexing real movie footage across %d scene regions...", len(REAL_SCENE_REGIONS))
        candidate_shots: List[BeastCandidateShot] = []
        global_shot_idx = 1

        for region in REAL_SCENE_REGIONS:
            v_path = Path(region["video_path"])
            if not v_path.exists():
                logger.warning("Movie file does not exist: %s", v_path)
                continue

            st = region["start_sec"]
            et = region["end_sec"]
            m_num = region["movie_number"]
            era = region["era"]
            env = region["environment"]
            def_chars = region["default_characters"]
            def_objs = region["default_objects"]
            def_acts = region["default_actions"]
            def_scale = region["default_scale"]
            prefix = region["description_prefix"]

            try:
                scene_list = scenedetect.detect(
                    str(v_path),
                    scenedetect.AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=24),
                    start_time=st,
                    end_time=et
                )
            except Exception as e:
                logger.error("PySceneDetect error for region [%.1f - %.1f]: %s", st, et, e)
                continue

            for s_start_tc, s_end_tc in scene_list:
                s_start = round(s_start_tc.get_seconds(), 3)
                s_end = round(s_end_tc.get_seconds(), 3)
                dur = round(s_end - s_start, 3)

                if dur < 1.0:
                    continue

                shot_id = f"real_m{m_num}_{int(s_start*1000):08d}_{global_shot_idx:04d}"
                global_shot_idx += 1

                # Specific shot-level adjustments based on exact timing
                chars = list(def_chars)
                objs = list(def_objs)
                acts = list(def_acts)
                scale = def_scale
                desc = f"{prefix} [{s_start:.1f}s - {s_end:.1f}s]"

                # Granular refinements for Movie 1 Sorting Ceremony
                if m_num == 1 and 2580.0 <= s_start < 2615.0:
                    chars = ["Hermione Granger", "Minerva McGonagall", "Sorting Hat"]
                    objs = ["Sorting Hat", "Stool"]
                    acts = ["Hermione sitting on stool", "Hat placed on Hermione", "sorting into Gryffindor"]
                    desc = "Hermione Granger sitting on stool being sorted by Sorting Hat into Gryffindor"
                elif m_num == 1 and 2615.0 <= s_start < 2635.0:
                    chars = ["Draco Malfoy", "Minerva McGonagall", "Sorting Hat"]
                    objs = ["Sorting Hat", "Stool"]
                    acts = ["Draco Malfoy on stool", "Hat shouting Slytherin instantly"]
                    desc = "Draco Malfoy on stool being sorted into Slytherin"
                elif m_num == 1 and 2635.0 <= s_start < 2655.0:
                    chars = ["Susan Bones", "Sorting Hat"]
                    objs = ["Sorting Hat", "Stool"]
                    acts = ["Susan Bones sorted into Hufflepuff", "Hufflepuff table cheering"]
                    desc = "Susan Bones sorted into Hufflepuff with Hufflepuff table cheering"
                elif m_num == 1 and 2568.0 <= s_start < 2580.0:
                    chars = ["Neville Longbottom", "Minerva McGonagall"]
                    objs = ["Sorting Hat"]
                    acts = ["Neville looking nervous", "watching sorting ceremony"]
                    desc = "Young Neville watching sorting ceremony nervously"
                # Granular refinements for Movie 8 Sword and Nagini
                elif m_num == 8 and 6160.0 <= s_start < 6185.0:
                    chars = ["Neville Longbottom"]
                    objs = ["Sorting Hat", "Sword of Gryffindor"]
                    acts = ["pulling silver sword from hat", "drawing sword of Godric Gryffindor"]
                    desc = "Neville reaching into the Sorting Hat and pulling Godric's silver sword"
                elif m_num == 8 and 6520.0 <= s_start < 6545.0:
                    chars = ["Neville Longbottom", "Nagini"]
                    objs = ["Sword of Gryffindor", "Horcrux"]
                    acts = ["swinging silver sword", "decapitating Nagini", "slaying snake"]
                    desc = "Neville swinging the silver sword and striking Nagini down"

                candidate_shot = BeastCandidateShot(
                    shot_id=shot_id,
                    source_video=str(v_path),
                    movie_number=m_num,
                    start_seconds=s_start,
                    end_seconds=s_end,
                    duration=dur,
                    narrative_era=era,
                    scene_description=desc,
                    characters_present=chars,
                    objects_present=objs,
                    actions_depicted=acts,
                    environment=env,
                    shot_scale=scale,
                )
                candidate_shots.append(candidate_shot)

        # Save to cache
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in candidate_shots], f, indent=2)
            logger.info("Successfully indexed and cached %d real movie shots to %s", len(candidate_shots), self.cache_file)
        except Exception as e:
            logger.warning("Failed to cache indexed shots: %s", e)

        return candidate_shots
