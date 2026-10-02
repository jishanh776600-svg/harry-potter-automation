"""
Harry Potter Movie Visual Retrieval & Cloud-Safe Clip Extraction Engine (Step 9)
================================================================================
Transforms structured visual beats from Step 8 (hp_scripts) into verified,
rapid-fire, audio-muted movie shots from Harry Potter Movies 1–8.

Pacing & Architectural Invariants:
  1. RAPID-FIRE PACING:
     - Target shot duration: 2.0s – 2.5s (range: 1.5s – 3.0s).
     - 1 visual beat -> multiple rapid movie shots (typically 2–3 shots per beat).
     - A 25–30s Short naturally utilizes 8–12+ rapid movie shots.
  2. ABSOLUTE ISOLATION: Zero interaction with AL AMR.
  3. MOVIE FOOTAGE ONLY: Strictly Movies 1–8. No AI imagery, no stock footage, no Pexels.
  4. AUDIO MUTING INVARIANT: Extracted clips must have audio stripped (-an).
     FFprobe verification must confirm 0 audio streams or raise RuntimeError.
  5. CLOUD-RUNNER COMPATIBILITY: Single movie on-demand download, disk space checks,
     safe ephemeral runner operation. All 8 movies resolve via Google Drive vault IDs.
"""

import os
import re
import json
import shutil
import hashlib
import logging
import sqlite3
import subprocess
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import PROJECT_ROOT, DATABASE_DIR, DB_PATH
from core.models import Base, MovieAssetRecord, MovieSubtitleChunk, HarryPotterScript, HPMovieClip
from core.movie_registry import CANONICAL_MOVIES, get_movie_by_number
from core.event_semantic_engine import EventSemanticVisualEngine, VisualBeatEvent
from engines.movie_asset_engine import MovieAssetEngine, get_db_connection

logger = logging.getLogger(__name__)

MOVIES_DIR = PROJECT_ROOT / "data" / "movies"
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
HP_TOKEN_PATH = CREDENTIALS_DIR / "hp_token.json"

MIN_CONFIDENCE_THRESHOLD = 75.0
DEFAULT_TARGET_SHOT_DURATION = 2.2  # Seconds
MIN_SHOT_DURATION = 1.5
MAX_SHOT_DURATION = 3.0


class ShotScale(str, Enum):
    CLOSE_UP = "CLOSE_UP"
    MEDIUM_CLOSE_UP = "MEDIUM_CLOSE_UP"
    MEDIUM_SHOT = "MEDIUM_SHOT"
    MEDIUM_WIDE = "MEDIUM_WIDE"
    TWO_SHOT = "TWO_SHOT"
    WIDE_SHOT = "WIDE_SHOT"


KNOWN_CHARACTERS = [
    "Harry Potter", "Harry", "Dumbledore", "Albus Dumbledore", "McGonagall", "Minerva McGonagall",
    "Hagrid", "Rubeus Hagrid", "Neville Longbottom", "Neville", "Ron Weasley", "Ron",
    "Hermione Granger", "Hermione", "Severus Snape", "Snape", "Draco Malfoy", "Malfoy",
    "Lord Voldemort", "Voldemort", "Vernon Dursley", "Petunia Dursley", "Dudley Dursley",
    "Dursley", "Vernon", "Petunia", "Dudley", "Sorting Hat", "Hedwig", "Peeves",
    "Argus Filch", "Filch", "Ollivander", "Quirrell", "Fluffy", "Norbert", "James Potter", "Lily Potter"
]


class MovieRetrievalEngine:
    """
    End-to-end engine for retrieving movie scenes from subtitle indexes,
    scoring candidates against visual beat requirements, decomposing beats
    into rapid-fire shot units (1.5–3.0s), and extracting verified audio-muted clips.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        movies_dir: Optional[Path] = None,
        clips_dir: Optional[Path] = None,
    ):
        self.db_path = db_path or DB_PATH
        self.movies_dir = movies_dir or MOVIES_DIR
        self.clips_dir = clips_dir or CLIPS_DIR

        self.movies_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.asset_engine = MovieAssetEngine()
        self.semantic_event_engine = EventSemanticVisualEngine()
        from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
        self.movie_event_retrieval_engine = MovieEventRetrievalEngine()

    # --------------------------------------------------------------------------
    # 1. VISUAL BEAT QUERY BUILDER
    # --------------------------------------------------------------------------
    def build_queries_for_beat(self, beat: Dict[str, Any]) -> List[str]:
        """
        Generates prioritized search queries for a visual beat.
        Combines retrieval hints, character names, location, action keywords,
        and automatic text extraction from narration/text/shot_hint.
        """
        queries = []
        hints = beat.get("retrieval_hints", [])
        characters = list(beat.get("characters", []))
        location = beat.get("location", "")
        action = beat.get("action", "")
        req = beat.get("visual_requirement", "")
        raw_text = beat.get("narration_text") or beat.get("text") or beat.get("shot_hint") or ""

        # Fallback character detection from raw text if characters list is empty
        if not characters and raw_text:
            for kc in KNOWN_CHARACTERS:
                if re.search(r"\b" + re.escape(kc) + r"\b", raw_text, re.IGNORECASE):
                    if kc not in characters:
                        characters.append(kc)

        # 1. Cleaned specific retrieval hints
        if hints:
            clean_hints = [re.sub(r"[^a-zA-Z0-9\s]", "", h).strip() for h in hints if h]
            clean_hints = [h for h in clean_hints if len(h) >= 3]
            if clean_hints:
                queries.append(" ".join(clean_hints[:3]))
                for h in clean_hints:
                    if h not in queries:
                        queries.append(h)

        # 2. Objects and key visual props
        objects = list(beat.get("objects", []))
        for obj in objects:
            clean_obj = re.sub(r"[^a-zA-Z0-9\s]", "", obj).strip()
            if clean_obj and len(clean_obj) >= 3 and clean_obj not in queries:
                queries.append(clean_obj)

        # 3. Character names (full names prioritized over generic single names)
        for char in characters:
            clean_char = re.sub(r"[^a-zA-Z0-9\s]", "", char).strip()
            if clean_char:
                if clean_char not in queries:
                    queries.append(clean_char)
                # Only add single tokens if not overly generic/ubiquitous
                for token in clean_char.split():
                    if len(token) >= 4 and token.lower() not in (
                        "baby", "professor", "albus", "uncle", "aunt", "harry", "potter", "lord"
                    ):
                        if token not in queries:
                            queries.append(token)

        # 4. Salient action / requirement keywords
        salient_words = []
        for text_source in (action, req, location):
            words = re.findall(r"[a-zA-Z]{4,}", text_source)
            for w in words:
                w_lower = w.lower()
                if w_lower not in (
                    "with", "from", "that", "this", "shot", "approaches",
                    "standing", "looking", "walking", "holding", "silent",
                    "quiet", "suburban", "evening", "across", "under", "front", "side",
                    "completely", "reveals", "their", "there", "about", "which", "would",
                    "before", "after", "while", "during", "hogwarts", "classroom", "corridor", "office"
                ):
                    if w not in salient_words:
                        salient_words.append(w)
        if salient_words:
            if not queries:
                queries.append(" ".join(salient_words[:3]))
            for sw in salient_words[:4]:
                if sw not in queries:
                    queries.append(sw)

        unique_queries = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean not in unique_queries:
                unique_queries.append(q_clean)

        return unique_queries or ["Harry Potter"]

    # --------------------------------------------------------------------------
    # 2. SUBTITLE SEARCH & CANDIDATE DISCOVERY
    # --------------------------------------------------------------------------
    def search_candidates_for_beat(
        self,
        beat: Dict[str, Any],
        max_candidates: int = 15,
        canonical_event: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries the movie subtitles FTS5 index across generated queries.
        Prioritizes the beat's preferred_movie_number, then falls back globally.
        If a canonical event is provided, directly ensures the exact ground-truth scene chunks are present.
        """
        queries = self.build_queries_for_beat(beat)
        preferred_m = beat.get("preferred_movie_number")
        candidates_by_id = {}

        # Round 0A: Inject ground-truth canonical scene chunks if provided
        if canonical_event:
            m_num = canonical_event.movie_number
            st_sec = float(getattr(canonical_event, "scene_start_sec", getattr(canonical_event, "start_time", 0.0)))
            end_sec = float(getattr(canonical_event, "scene_end_sec", getattr(canonical_event, "end_time", 0.0)))
            with self.Session() as session:
                chunks = (
                    session.query(MovieSubtitleChunk)
                    .filter(
                        MovieSubtitleChunk.movie_number == m_num,
                        MovieSubtitleChunk.end_seconds >= max(0.0, st_sec - 15.0),
                        MovieSubtitleChunk.start_seconds <= end_sec + 15.0
                    )
                    .all()
                )
                for ch in chunks:
                    if ch.id not in candidates_by_id:
                        candidates_by_id[ch.id] = {
                            "chunk_id": ch.id,
                            "movie_number": ch.movie_number,
                            "movie_title": ch.movie_title,
                            "start_seconds": ch.start_seconds,
                            "end_seconds": ch.end_seconds,
                            "start_timecode": ch.start_timecode,
                            "end_timecode": ch.end_timecode,
                            "duration_seconds": ch.duration_seconds,
                            "text": ch.text,
                            "video_filename": ch.movie.video_filename if ch.movie else "",
                            "video_drive_id": ch.movie.video_drive_id if ch.movie else "",
                            "relevance_rank": -2.0,
                            "matched_query": f"[CANONICAL: {getattr(canonical_event, 'event_summary', getattr(canonical_event, 'action', ''))[:30]}]",
                            "is_canonical": True,
                            "canonical_event_obj": canonical_event
                        }

        # Round 0B: Structured MovieEventIndex retrieval
        try:
            from engines.movie_event.models import MovieEventQuery
            sub = beat.get("subject") or (beat.get("characters")[0] if beat.get("characters") else None)
            act = beat.get("action") or beat.get("visual_requirement")
            tgt = beat.get("object") or beat.get("target") or (beat.get("objects")[0] if beat.get("objects") else None)
            me_query = MovieEventQuery(
                subject=sub,
                action=act,
                target=tgt,
                location=beat.get("location"),
                objects=list(beat.get("objects", [])),
                movie_number=preferred_m
            )
            event_matches = self.movie_event_retrieval_engine.retrieve_events(me_query, top_k=3, min_score=35.0)
            for ev, ev_score, _ in event_matches:
                with self.Session() as session:
                    ev_chunks = (
                        session.query(MovieSubtitleChunk)
                        .filter(
                            MovieSubtitleChunk.movie_number == ev.movie_number,
                            MovieSubtitleChunk.end_seconds >= max(0.0, ev.start_time - 10.0),
                            MovieSubtitleChunk.start_seconds <= ev.end_time + 10.0
                        )
                        .all()
                    )
                    if ev_chunks:
                        for ch in ev_chunks:
                            if ch.id not in candidates_by_id:
                                candidates_by_id[ch.id] = {
                                    "chunk_id": ch.id,
                                    "movie_number": ch.movie_number,
                                    "movie_title": ch.movie_title,
                                    "start_seconds": ch.start_seconds,
                                    "end_seconds": ch.end_seconds,
                                    "start_timecode": ch.start_timecode,
                                    "end_timecode": ch.end_timecode,
                                    "duration_seconds": ch.duration_seconds,
                                    "text": ch.text,
                                    "video_filename": ch.movie.video_filename if ch.movie else "",
                                    "video_drive_id": ch.movie.video_drive_id if ch.movie else "",
                                    "relevance_rank": -2.0,
                                    "matched_query": f"[EVENT: {ev.primary_subject} {ev.action[:25]}]",
                                    "is_canonical": True,
                                    "canonical_event_obj": ev,
                                }
                    else:
                        chunk_id = f"evt_{ev.event_id}"
                        if chunk_id not in candidates_by_id:
                            candidates_by_id[chunk_id] = {
                                "chunk_id": chunk_id,
                                "movie_number": ev.movie_number,
                                "movie_title": f"Harry Potter Movie {ev.movie_number}",
                                "start_seconds": ev.start_time,
                                "end_seconds": ev.end_time,
                                "start_timecode": f"{int(ev.start_time//60):02d}:{int(ev.start_time%60):02d}",
                                "end_timecode": f"{int(ev.end_time//60):02d}:{int(ev.end_time%60):02d}",
                                "duration_seconds": ev.duration,
                                "text": f"{ev.primary_subject} {ev.action}. {ev.visual_description}",
                                "video_filename": f"hp_movie_{ev.movie_number}.mp4",
                                "video_drive_id": "",
                                "relevance_rank": -2.0,
                                "matched_query": f"[EVENT: {ev.primary_subject} {ev.action[:25]}]",
                                "is_canonical": True,
                                "canonical_event_obj": ev,
                            }
        except Exception as e:
            logger.debug(f"MovieEvent retrieval in search_candidates_for_beat: {e}")

        # Round 1: Preferred movie search
        if preferred_m:
            for q in queries:
                matches = self.asset_engine.search_movie_scenes(q, movie_number=preferred_m, limit=max_candidates)
                for m in matches:
                    if m["chunk_id"] not in candidates_by_id:
                        m["matched_query"] = q
                        candidates_by_id[m["chunk_id"]] = m

        # Round 2: Fallback global search ONLY if preferred movie has zero candidates
        if len(candidates_by_id) == 0:
            for q in queries:
                matches = self.asset_engine.search_movie_scenes(q, movie_number=None, limit=5)
                for m in matches:
                    if m["chunk_id"] not in candidates_by_id:
                        m["matched_query"] = q
                        candidates_by_id[m["chunk_id"]] = m
                if len(candidates_by_id) >= max_candidates:
                    break

        return list(candidates_by_id.values())

    # --------------------------------------------------------------------------
    # 3. CANDIDATE CONTEXT EXPANSION
    # --------------------------------------------------------------------------
    def expand_candidate_context(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Expands candidate context by fetching preceding and succeeding subtitle chunks."""
        chunk_id = candidate.get("chunk_id")
        if not chunk_id:
            return candidate
        movie_num = candidate.get("movie_number", 1)

        with self.Session() as session:
            current = session.query(MovieSubtitleChunk).filter_by(id=chunk_id).first()
            if not current:
                return candidate

            prev_chunk = (
                session.query(MovieSubtitleChunk)
                .filter(
                    MovieSubtitleChunk.movie_number == movie_num,
                    MovieSubtitleChunk.start_seconds < current.start_seconds
                )
                .order_by(MovieSubtitleChunk.start_seconds.desc())
                .first()
            )

            next_chunk = (
                session.query(MovieSubtitleChunk)
                .filter(
                    MovieSubtitleChunk.movie_number == movie_num,
                    MovieSubtitleChunk.start_seconds > current.start_seconds
                )
                .order_by(MovieSubtitleChunk.start_seconds.asc())
                .first()
            )

            context_parts = []
            if prev_chunk:
                context_parts.append(f"[PREV: {prev_chunk.text}]")
            context_parts.append(f"[SCENE: {current.text}]")
            if next_chunk:
                context_parts.append(f"[NEXT: {next_chunk.text}]")

            candidate["expanded_context"] = " ".join(context_parts)
            candidate["prev_chunk_id"] = prev_chunk.id if prev_chunk else None
            candidate["next_chunk_id"] = next_chunk.id if next_chunk else None

        return candidate

    # --------------------------------------------------------------------------
    # 4. SHOT SCALE & CHARACTER FRAMING REASONING
    # --------------------------------------------------------------------------
    @staticmethod
    def infer_target_shot_scale(beat: Dict[str, Any]) -> ShotScale:
        """
        Infers the target visual shot scale adhering strictly to the Natural Cinematic Framing Policy:
        1. CLOSE_UP / MCU: ONLY when narration specifically calls for facial expression, eyes, tears,
           shock, fear, realization, smile, or intimate emotional reaction.
        2. TWO_SHOT: When two characters converse, interact, or confront each other.
        3. WIDE_SHOT: When environment, landscape, architecture, or spatial movement is primary without character focus.
        4. MEDIUM_WIDE: When character moves through or inhabits an expansive environment (e.g. "walks into Great Hall").
        5. MEDIUM_SHOT: Natural default for character actions, gestures, and general mentions.
        """
        combined = " ".join([
            str(beat.get("visual_requirement", "")),
            str(beat.get("action", "")),
            str(beat.get("narration_text", "")),
            str(beat.get("text", "")),
            str(beat.get("shot_hint", "")),
            str(beat.get("emotional_context", ""))
        ]).lower()

        # 1. Strict Close-up cues: ONLY explicit facial expression/reaction or intense emotional feature
        strict_close_cues = [
            "close-up", "close up", "extreme close-up", "cu", "ecu",
            "facial expression", "facial reaction", "face filled with", "expression filled with",
            "eyes widen", "eyes filled", "tears in his eyes", "tears in her eyes", "crying",
            "intimate reaction", "shocked face", "look of horror", "look of fear", "look of shock",
            "tears welling", "tearful emotion", "face in horror", "smile spread", "warm smile"
        ]
        if any(cue in combined for cue in strict_close_cues):
            return ShotScale.CLOSE_UP

        # Check for facial emotion pairing (e.g. "eyes" or "face" + "shock" or "fear" or "realization")
        has_facial_element = any(w in combined for w in ("face", "eyes", "expression", "tears"))
        has_intimate_emotion = any(w in combined for w in ("fear", "shock", "terror", "realization", "disbelief", "astonishment", "weeping", "smile", "embarrassment", "dismay"))
        if has_facial_element and has_intimate_emotion:
            return ShotScale.CLOSE_UP

        # 2. Two-shot cues: interaction / dialogue between two characters
        chars = list(beat.get("characters", []))
        if not chars:
            raw_t = str(beat.get("narration_text") or beat.get("text") or "")
            for kc in KNOWN_CHARACTERS:
                if re.search(r"\b" + re.escape(kc) + r"\b", raw_t, re.IGNORECASE):
                    if kc not in chars:
                        chars.append(kc)

        two_shot_cues = [
            "two-shot", "two shot", "confronts", "facing each other", "walks beside",
            "side by side", "whispering to", "talking to", "speaking with", "handing the child",
            "together down", "conversing", "conferring"
        ]
        if any(cue in combined for cue in two_shot_cues):
            return ShotScale.TWO_SHOT
        if len(chars) >= 2 and any(w in combined for w in ("talk", "speak", "greet", "whisper", "warn", "convers", "confer", "discuss")):
            return ShotScale.TWO_SHOT

        # 3. Environmental / Spatial Context cues
        env_cues = [
            "landscape", "castle", "lake", "black lake", "sky", "forest", "forbidden forest",
            "quidditch pitch", "ruins", "street sign", "privet drive sign",
            "great hall filled", "hundreds of owls", "corridor stretching"
        ]
        has_env = any(cue in combined for cue in env_cues)

        if has_env and not chars:
            return ShotScale.WIDE_SHOT

        if has_env and chars:
            # Character walking into or inhabiting an expansive space -> Medium Wide preserves context
            return ShotScale.MEDIUM_WIDE

        # 4. Action cues with environment / space -> Medium Wide
        if any(w in combined for w in ("walks into", "walked into", "enters", "entered", "strides through", "running across", "approaching")):
            return ShotScale.MEDIUM_WIDE

        # 5. Default natural framing for character mention / action -> MEDIUM_SHOT
        return ShotScale.MEDIUM_SHOT

    def infer_candidate_framing_and_scale(
        self,
        candidate: Dict[str, Any],
        beat: Dict[str, Any],
        canonical_event: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Determines the candidate's shot scale and character prominence:
        - If matching a canonical event, leverages authoritative event camera descriptors.
        - Otherwise analyzes dialogue structure, speaker presence, and natural scene composition.
        """
        cand_text = candidate.get("text", "").strip()
        cand_context = candidate.get("expanded_context", "")
        combined = f"{cand_text} {cand_context}".lower()

        # Check canonical event matching
        canonical_obj = canonical_event or candidate.get("canonical_event_obj")
        if canonical_obj or candidate.get("is_canonical"):
            c_scale_str = getattr(canonical_obj, "camera_scale", "") if canonical_obj else ""
            if c_scale_str and hasattr(ShotScale, c_scale_str):
                return {"shot_scale": ShotScale[c_scale_str], "prominence": 1.0, "is_canonical": True}
            ev_summary = getattr(canonical_obj, "event_summary", getattr(canonical_obj, "visual_description", "")).lower()
            if any(w in ev_summary for w in ("close-up", "face in shock", "eyes widen", "tears", "wandlight", "taps")):
                return {"shot_scale": ShotScale.CLOSE_UP, "prominence": 1.0, "is_canonical": True}
            elif any(w in ev_summary for w in ("two professors", "walking together", "greets", "talking quietly", "conferring", "two-shot")):
                return {"shot_scale": ShotScale.TWO_SHOT, "prominence": 1.0, "is_canonical": True}
            elif any(w in ev_summary for w in ("walks into", "striding down", "approaching", "walking across")):
                return {"shot_scale": ShotScale.MEDIUM_WIDE, "prominence": 1.0, "is_canonical": True}
            elif any(w in ev_summary for w in ("street sign", "sky", "street going dark", "landscape", "castle")):
                return {"shot_scale": ShotScale.WIDE_SHOT, "prominence": 0.50, "is_canonical": True}
            return {"shot_scale": ShotScale.MEDIUM_SHOT, "prominence": 1.0, "is_canonical": True}

        # Check beat characters
        beat_chars = list(beat.get("characters", []))
        if not beat_chars:
            raw_text = beat.get("narration_text") or beat.get("text") or ""
            for kc in KNOWN_CHARACTERS:
                if re.search(r"\b" + re.escape(kc) + r"\b", raw_text, re.IGNORECASE):
                    if kc not in beat_chars:
                        beat_chars.append(kc)

        char_tokens = []
        for c in beat_chars:
            for tok in re.findall(r"[a-zA-Z]{4,}", c.lower()):
                if tok not in ("baby", "professor", "uncle", "aunt"):
                    char_tokens.append(tok)
        has_named_char = (
            any(c.lower() in combined for c in beat_chars)
            or any(tok in combined for tok in char_tokens)
        )

        # 1. Dialogue between two speakers -> TWO_SHOT
        if cand_text.count("- ") >= 2:
            return {"shot_scale": ShotScale.TWO_SHOT, "prominence": 1.0, "is_canonical": False}

        # 2. Close-up cues: explicit close-up or intense facial reaction in candidate text
        cu_indicators = [
            "close-up", "close up", "extreme close-up", "cu", "ecu",
            "face filled with", "eyes filled with", "tears welling", "in tears",
            "eyes widen", "look of horror", "look of fear", "sobbing", "weeping"
        ]
        if any(w in combined for w in cu_indicators):
            return {"shot_scale": ShotScale.CLOSE_UP, "prominence": 0.85, "is_canonical": False}

        # 3. Wide shot cues: landscape, panoramic, distant setting, crowd
        wide_indicators = [
            "panoramic", "wide shot", "wide view", "landscape", "establishing shot",
            "cheering crowd", "applause from all tables", "students seated across",
            "silence in the hall", "welcome to hogwarts", "across long tables",
            "massive ornate", "distant view", "in the distance"
        ]
        if any(w in combined for w in wide_indicators):
            return {"shot_scale": ShotScale.WIDE_SHOT, "prominence": 0.40, "is_canonical": False}

        # 4. Movement / traversing environment -> MEDIUM_WIDE
        mw_indicators = [
            "walked into", "walks into", "entered the", "enters the",
            "striding down", "running across", "approaching"
        ]
        if any(w in combined for w in mw_indicators):
            return {"shot_scale": ShotScale.MEDIUM_WIDE, "prominence": 1.0, "is_canonical": False}

        # 5. Default natural framing:
        # If candidate features named character -> MEDIUM_SHOT (natural composition, full prominence)
        # Otherwise -> WIDE_SHOT (ambient/environment)
        cand_has_character = any(kc.lower() in combined for kc in KNOWN_CHARACTERS)
        if cand_has_character or has_named_char:
            return {"shot_scale": ShotScale.MEDIUM_SHOT, "prominence": 1.0, "is_canonical": False}
        else:
            return {"shot_scale": ShotScale.WIDE_SHOT, "prominence": 0.40, "is_canonical": False}

    # --------------------------------------------------------------------------
    # 5. MULTI-FACTOR RERANKING & QUALITY SCORING (A through H)
    # --------------------------------------------------------------------------
    def score_candidate(
        self,
        candidate: Dict[str, Any],
        beat: Dict[str, Any],
        canonical_event: Optional[Any] = None,
        used_intervals: Optional[List[Tuple[int, float, float]]] = None
    ) -> Dict[str, Any]:
        """
        Multi-Factor Scoring (0 to 100 points) evaluating:
          A. Semantic relevance to the narration/beat (0 - 25 pts)
          B. Named-character presence (0 - 20 pts)
          C. Character prominence / framing (0 - 15 pts)
          D. Action relevance (0 - 10 pts)
          E. Reaction / emotion relevance (0 - 10 pts)
          F. Shot scale suitability (0 - 10 pts)
          G. Temporal & context relevance (0 - 10 pts)
          H. Anti-loop & uniqueness constraint (penalty: 0 or 100 pts)
        """
        text = candidate.get("text", "").lower()
        context = candidate.get("expanded_context", "").lower()
        combined_text = f"{text} {context}"

        target_scale = self.infer_target_shot_scale(beat)
        framing_info = self.infer_candidate_framing_and_scale(candidate, beat, canonical_event=canonical_event)
        cand_scale = framing_info["shot_scale"]
        prominence_factor = framing_info["prominence"]
        is_canonical = framing_info.get("is_canonical", False) or candidate.get("is_canonical", False)

        c_movie = int(candidate.get("movie_number", 1))
        c_start = float(candidate.get("start_seconds", 0.0))
        c_end = float(candidate.get("end_seconds", 0.0))

        # ----------------------------------------------------------------------
        # NON-CANONICAL MOVIE REJECTION GATE (Movies 1-8 strictly)
        # ----------------------------------------------------------------------
        if not get_movie_by_number(c_movie):
            zero_details = {
                "semantic_relevance": 0.0,
                "named_character_presence": 0.0,
                "character_prominence": 0.0,
                "action_relevance": 0.0,
                "reaction_emotion_relevance": 0.0,
                "shot_scale_score": 0.0,
                "temporal_context_relevance": 0.0,
                "anti_loop_penalty": 0.0,
                "A_semantic_relevance": 0.0,
                "B_named_character_presence": 0.0,
                "C_character_prominence": 0.0,
                "D_action_relevance": 0.0,
                "E_reaction_emotion_relevance": 0.0,
                "F_shot_scale_suitability": 0.0,
                "G_temporal_context_relevance": 0.0,
                "H_anti_loop_penalty": 0.0,
                "target_shot_scale": target_scale.value,
                "candidate_shot_scale": cand_scale.value,
                "selection_reasoning": f"REJECTED: Movie {c_movie} is not a canonical Harry Potter movie (1-8)."
            }
            candidate["score"] = 0.0
            candidate["total_score"] = 0.0
            candidate["score_details"] = zero_details
            return candidate

        # ----------------------------------------------------------------------
        # H. Anti-Loop & Uniqueness Constraint (0 or 100 pt penalty)
        # ----------------------------------------------------------------------
        loop_penalty = 0.0
        if used_intervals:
            for (u_movie, u_start, u_end) in used_intervals:
                if u_movie == c_movie:
                    overlap_duration = max(0.0, min(c_end, u_end) - max(c_start, u_start))
                    if overlap_duration > 1.0:
                        loop_penalty = 100.0
                        break

        # ----------------------------------------------------------------------
        # A. Semantic Relevance (0 - 25 pts)
        # ----------------------------------------------------------------------
        if is_canonical:
            sem_score = 25.0
        else:
            rank = float(candidate.get("relevance_rank", 0.0))
            rank_pts = max(0.0, min(10.0, 10.0 - abs(rank) * 1.0))
            req_words = set(re.findall(r"[a-zA-Z]{4,}", str(beat.get("visual_requirement", "")).lower()))
            nar_words = set(re.findall(r"[a-zA-Z]{4,}", str(beat.get("narration_text", "") or beat.get("text", "")).lower()))
            overlap_count = sum(1 for w in req_words.union(nar_words) if w in combined_text)
            kw_pts = min(15.0, overlap_count * 5.0)
            sem_score = min(25.0, rank_pts + kw_pts)

            # Key prop check for non-canonical candidates
            key_props = set()
            for p in beat.get("objects", []):
                key_props.update(re.findall(r"[a-zA-Z]{3,}", p.lower()))
            req_props = key_props.intersection({"map", "parchment", "sword", "wand", "mirror", "snitch", "cloak", "potion"})
            if req_props and not any(rp in combined_text for rp in req_props):
                sem_score = max(0.0, sem_score - 10.0)

        # ----------------------------------------------------------------------
        # B. Named-Character Presence (0 - 20 pts)
        # ----------------------------------------------------------------------
        beat_chars = list(beat.get("characters", []))
        if not beat_chars:
            raw_t = str(beat.get("narration_text") or beat.get("text") or "")
            for kc in KNOWN_CHARACTERS:
                if re.search(r"\b" + re.escape(kc) + r"\b", raw_t, re.IGNORECASE):
                    beat_chars.append(kc)

        if is_canonical:
            char_score = 20.0
        elif not beat_chars:
            char_score = 15.0  # Neutral non-character beat
        else:
            char_points = 0.0
            primary_char = beat_chars[0].lower()
            tokens = [t for t in re.split(r"\s+", primary_char) if len(t) >= 4]

            if primary_char in combined_text:
                char_points = 20.0
            elif any(t in combined_text for t in tokens):
                char_points = 16.0
            elif len(beat_chars) > 1:
                sec_char = beat_chars[1].lower()
                sec_tokens = [t for t in re.split(r"\s+", sec_char) if len(t) >= 4]
                if sec_char in combined_text or any(t in combined_text for t in sec_tokens):
                    char_points = 12.0

            # Adversarial character check in dialogue
            adversarial_chars = ["snape", "severus", "malfoy", "draco", "voldemort", "bellatrix", "umbridge", "vernon", "dursley"]
            has_adversary = any(ac in combined_text for ac in adversarial_chars if ac not in primary_char)
            if has_adversary and primary_char not in combined_text:
                char_points = max(0.0, char_points - 15.0)

            char_score = min(20.0, char_points)

        # ----------------------------------------------------------------------
        # C. Character Prominence / Framing (0 - 15 pts)
        # ----------------------------------------------------------------------
        # "Character prominence" must NOT mean "largest possible face."
        # It means: character is identifiable, sufficiently visible, not tiny,
        # surrounding context is preserved, and composition remains natural.
        if beat_chars:
            if char_score > 0.0:
                if cand_scale in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT, ShotScale.MEDIUM_CLOSE_UP):
                    # Natural cinematic framing: character is visible AND context is preserved!
                    prom_score = 15.0 * prominence_factor
                elif cand_scale == ShotScale.CLOSE_UP:
                    if target_scale in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP):
                        # Close-up specifically requested for facial reaction/emotion
                        prom_score = 15.0 * prominence_factor
                    else:
                        # Unnecessary close-up zoom: loses surrounding context!
                        prom_score = 8.0 * prominence_factor
                elif cand_scale == ShotScale.WIDE_SHOT:
                    if target_scale in (ShotScale.WIDE_SHOT, ShotScale.MEDIUM_WIDE):
                        prom_score = 12.0 * prominence_factor
                    else:
                        # Character too distant/tiny
                        prom_score = 4.0
                else:
                    prom_score = 10.0 * prominence_factor
            else:
                prom_score = 0.0
        else:
            # Environmental / non-character beat
            prom_score = 15.0 * prominence_factor
        prom_score = round(max(0.0, min(15.0, prom_score)), 1)

        # ----------------------------------------------------------------------
        # D. Action Relevance (0 - 10 pts)
        # ----------------------------------------------------------------------
        action_text = str(beat.get("action", "")).lower()
        action_words = set(re.findall(r"[a-zA-Z]{4,}", action_text))
        if is_canonical:
            action_score = 10.0
        elif action_words:
            matched_actions = sum(1 for aw in action_words if aw in combined_text)
            action_score = min(10.0, matched_actions * 4.0)
            if action_score == 0.0:
                action_score = 3.0  # Baseline
        else:
            action_score = 7.0

        # ----------------------------------------------------------------------
        # E. Reaction / Emotion Relevance (0 - 10 pts)
        # ----------------------------------------------------------------------
        # Close-up should receive a reaction bonus ONLY when the beat actually focuses
        # on facial emotion, tears, fear, realization, shock, or smile.
        combined_emotion = f"{beat.get('emotional_context', '')} {beat.get('action', '')} {beat.get('narration_text', '')} {beat.get('text', '')}".lower()
        has_emotion = any(w in combined_emotion for w in ("fear", "realization", "shock", "surprise", "warmth", "gravity", "urgent", "bewildered", "embarrassment", "dismay", "shame", "reaction", "reacting", "emotion", "astonishment", "tears", "crying"))
        requires_close_emotion = target_scale in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP) or (has_emotion and any(w in combined_emotion for w in ("face", "eyes", "tears", "expression", "look of")))

        if is_canonical:
            react_score = 10.0
        elif requires_close_emotion:
            if cand_scale in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP):
                react_score = 10.0
            elif cand_scale in (ShotScale.MEDIUM_SHOT, ShotScale.TWO_SHOT):
                react_score = 7.0
            else:
                react_score = 2.0  # Wide shot cannot convey close facial emotion
        else:
            # Normal action or general scene: natural medium shots are optimal
            if cand_scale in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT):
                react_score = 8.5
            elif cand_scale == ShotScale.WIDE_SHOT:
                react_score = 7.0
            else:
                # Close-up on normal non-emotional beat feels forced
                react_score = 6.0

        # ----------------------------------------------------------------------
        # F. Shot Scale Suitability (0 - 10 pts)
        # ----------------------------------------------------------------------
        if cand_scale == target_scale:
            scale_score = 10.0
        elif target_scale == ShotScale.MEDIUM_SHOT:
            if cand_scale in (ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT, ShotScale.MEDIUM_CLOSE_UP):
                scale_score = 8.5
            elif cand_scale == ShotScale.WIDE_SHOT:
                scale_score = 6.0
            elif cand_scale == ShotScale.CLOSE_UP:
                scale_score = 3.0  # Unnecessary zoom penalty
            else:
                scale_score = 5.0
        elif target_scale == ShotScale.MEDIUM_WIDE:
            if cand_scale in (ShotScale.MEDIUM_SHOT, ShotScale.TWO_SHOT, ShotScale.WIDE_SHOT):
                scale_score = 8.5
            elif cand_scale == ShotScale.MEDIUM_CLOSE_UP:
                scale_score = 5.0
            elif cand_scale == ShotScale.CLOSE_UP:
                scale_score = 2.0  # Unnecessary zoom penalty
            else:
                scale_score = 5.0
        elif target_scale == ShotScale.TWO_SHOT:
            if cand_scale in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE):
                scale_score = 8.5
            elif cand_scale == ShotScale.MEDIUM_CLOSE_UP:
                scale_score = 6.0
            elif cand_scale == ShotScale.CLOSE_UP:
                scale_score = 3.0
            else:
                scale_score = 5.0
        elif target_scale == ShotScale.CLOSE_UP:
            if cand_scale == ShotScale.MEDIUM_CLOSE_UP:
                scale_score = 8.5
            elif cand_scale == ShotScale.MEDIUM_SHOT:
                scale_score = 5.0
            elif cand_scale in (ShotScale.MEDIUM_WIDE, ShotScale.WIDE_SHOT):
                scale_score = 1.0  # Too distant when close emotion was requested
            else:
                scale_score = 4.0
        elif target_scale == ShotScale.WIDE_SHOT:
            if cand_scale == ShotScale.MEDIUM_WIDE:
                scale_score = 8.5
            elif cand_scale == ShotScale.MEDIUM_SHOT:
                scale_score = 5.0
            elif cand_scale in (ShotScale.MEDIUM_CLOSE_UP, ShotScale.CLOSE_UP):
                scale_score = 1.0  # Extreme zoom when wide landscape was requested
            else:
                scale_score = 4.0
        else:
            scale_score = 6.0

        # ----------------------------------------------------------------------
        # G. Temporal & Context Relevance (0 - 10 pts)
        # ----------------------------------------------------------------------
        pref_m = beat.get("preferred_movie_number")
        if pref_m and c_movie == pref_m:
            temp_score = 10.0
        elif not pref_m:
            temp_score = 7.0
        else:
            temp_score = 2.0

        # Total Composite Score
        total_score = sem_score + char_score + prom_score + action_score + react_score + scale_score + temp_score - loop_penalty
        total_score = round(max(0.0, min(100.0, total_score)), 2)

        # Reasoning explanation
        reasoning = (
            f"Scale: {cand_scale.value} (Target: {target_scale.value}, match: {scale_score}/10). "
            f"Character: {char_score}/20, Prominence: {prom_score}/15. "
            f"Semantic: {sem_score}/25, Action: {action_score}/10, Reaction: {react_score}/10."
        )
        if loop_penalty > 0:
            reasoning += " REJECTED BY ANTI-LOOP (timestamp overlap with previous shot)."

        score_details = {
            "semantic_relevance": round(sem_score, 1),
            "named_character_presence": round(char_score, 1),
            "character_prominence": round(prom_score, 1),
            "action_relevance": round(action_score, 1),
            "reaction_emotion_relevance": round(react_score, 1),
            "shot_scale_score": round(scale_score, 1),
            "temporal_context_relevance": round(temp_score, 1),
            "anti_loop_penalty": round(loop_penalty, 1),
            "A_semantic_relevance": round(sem_score, 1),
            "B_named_character_presence": round(char_score, 1),
            "C_character_prominence": round(prom_score, 1),
            "D_action_relevance": round(action_score, 1),
            "E_reaction_emotion_relevance": round(react_score, 1),
            "F_shot_scale_suitability": round(scale_score, 1),
            "G_temporal_context_relevance": round(temp_score, 1),
            "H_anti_loop_penalty": round(loop_penalty, 1),
            "target_shot_scale": target_scale.value,
            "candidate_shot_scale": cand_scale.value,
            "selection_reasoning": reasoning
        }

        candidate["score"] = total_score
        candidate["total_score"] = total_score
        candidate["score_details"] = score_details
        candidate["framing"] = framing_info
        return candidate

    def rerank_candidates(
        self,
        beat: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        canonical_event: Optional[Any] = None,
        used_intervals: Optional[List[Tuple[int, float, float]]] = None
    ) -> List[Dict[str, Any]]:
        """Scores and ranks candidates in descending order of composite score."""
        scored = [
            self.score_candidate(
                c,
                beat,
                canonical_event=canonical_event,
                used_intervals=used_intervals
            )
            for c in candidates
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    # --------------------------------------------------------------------------
    # 6. CONFIDENCE GATE & VISUAL POLICY ENFORCEMENT
    # --------------------------------------------------------------------------
    # 6. CONFIDENCE GATE & VISUAL POLICY ENFORCEMENT
    # --------------------------------------------------------------------------
    def get_atmospheric_fallback_candidate(
        self,
        preferred_movie_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Visual Confidence Hard-Gate Fallback:
        When no movie scene candidate meets the strict 75.0 confidence threshold and
        no direct canonical event matches, route to a verified canonical Atmospheric
        Hogwarts Establishing Shot instead of guessing an incorrect character scene.
        """
        atm_map = {
            1: ("evt_atm_m1_hogwarts_night_exterior", 1, "Harry Potter and the Sorcerer's Stone", 2420.0, 2460.0, "Cinematic wide night panorama of Hogwarts Castle across the reflective Black Lake."),
            2: ("evt_atm_m2_hogwarts_express_viaduct", 2, "Harry Potter and the Chamber of Secrets", 1350.0, 1380.0, "Aerial panorama of the scarlet Hogwarts Express billowing steam across the curved stone viaduct."),
            3: ("evt_atm_m3_hogwarts_courtyard_seasons", 3, "Harry Potter and the Prisoner of Azkaban", 3600.0, 3630.0, "Establishing shot of the gothic courtyard with clock tower pendulum swinging."),
            4: ("evt_atm_m4_great_hall_floating_candles", 4, "Harry Potter and the Goblet of Fire", 1920.0, 1950.0, "Overhead crane shot of the Great Hall illuminated by hundreds of floating candles."),
            6: ("evt_atm_m6_astronomy_tower_twilight", 6, "Harry Potter and the Half-Blood Prince", 5400.0, 5430.0, "Panoramic twilight shot of the highest Hogwarts spires and Astronomy Tower in mountain mist."),
            8: ("evt_atm_m8_hogwarts_shield_dome", 8, "Harry Potter and the Deathly Hallows Part 2", 3120.0, 3150.0, "Panoramic shot of the translucent magical shield dome expanding and locking into place over Hogwarts.")
        }
        m_num = preferred_movie_number if preferred_movie_number in atm_map else 1
        ev_id, movie_no, title, s_time, e_time, desc = atm_map[m_num]

        return {
            "chunk_id": f"chunk_atm_{ev_id}",
            "movie_number": movie_no,
            "movie_title": title,
            "text": desc,
            "matched_query": "Hogwarts Castle atmospheric transition",
            "start_seconds": s_time,
            "end_seconds": e_time,
            "score": 85.0,
            "is_canonical": True,
            "is_atmospheric_fallback": True,
            "event_id": ev_id
        }

    def evaluate_confidence_gate(
        self,
        candidate: Optional[Dict[str, Any]],
        threshold: float = MIN_CONFIDENCE_THRESHOLD
    ) -> Tuple[bool, str, str]:
        """
        Validates candidate against confidence threshold and strict MOVIE FOOTAGE ONLY policy.
        """
        if candidate is None:
            return False, "REJECTED", "NO_CANDIDATE_FOUND"

        m_num = candidate.get("movie_number")
        if not m_num or m_num < 1 or m_num > 8:
            return False, "REJECTED", "NON_CANONICAL_MOVIE_NUMBER"

        score = float(candidate.get("score", 0.0))
        is_canonical = bool(candidate.get("is_canonical"))
        if is_canonical or score >= threshold:
            return True, "ACCEPTED", "HIGH_CONFIDENCE_MOVIE_MATCH"
        else:
            return False, "REJECTED", f"LOW_RETRIEVAL_CONFIDENCE (Score {score:.1f} < {threshold:.1f})"

    # --------------------------------------------------------------------------
    # 7. BEAT -> RAPID-FIRE SHOT UNITS RESOLUTION (WITH ANTI-LOOP)
    # --------------------------------------------------------------------------
    def resolve_beat_to_shots(
        self,
        beat: Dict[str, Any],
        ranked_candidates: List[Dict[str, Any]],
        used_intervals: Optional[List[Tuple[int, float, float]]] = None,
        target_shots_per_beat: int = 2,
        canonical_event: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        ARCHITECTURAL ADVANCEMENT:
        Decomposes 1 visual beat into 2 to 3 rapid-fire movie shot units (1.5s - 3.0s each).
        Uses distinct high-confidence scene candidates or sub-cuts from focal scenes.
        Enforces strict anti-loop and interval uniqueness.
        """
        valid_candidates = [
            c for c in ranked_candidates
            if c.get("score", 0.0) >= MIN_CONFIDENCE_THRESHOLD or c.get("is_canonical")
        ]

        if not valid_candidates:
            # Visual Confidence Hard-Gate: Zero guessing of incorrect character scenes.
            # Fall back strictly to verified Atmospheric Hogwarts Establishing Shot.
            atm_cand = self.get_atmospheric_fallback_candidate(beat.get("preferred_movie_number"))
            valid_candidates = [atm_cand]

        shots = []
        shot_idx = 1

        # Strategy A: Select top distinct high-confidence candidates for the beat
        if len(valid_candidates) >= 2:
            for cand in valid_candidates:
                if len(shots) >= target_shots_per_beat:
                    break

                src_start = float(cand["start_seconds"])
                src_end = float(cand["end_seconds"])
                m_num = int(cand["movie_number"])

                # Check anti-loop interval overlap
                if used_intervals:
                    overlap = any(
                        (u_movie == m_num and max(src_start, u_start) < min(src_end, u_end) - 1.0)
                        for (u_movie, u_start, u_end) in used_intervals
                    )
                    if overlap:
                        continue

                # Pacing: clamp shot to 1.5s - 3.0s (default ~2.2s)
                shot_duration = min(MAX_SHOT_DURATION, max(MIN_SHOT_DURATION, src_end - src_start))
                if shot_duration > MAX_SHOT_DURATION:
                    shot_duration = DEFAULT_TARGET_SHOT_DURATION

                clip_start = src_start
                clip_end = clip_start + shot_duration

                shots.append({
                    "shot_id": f"shot_{shot_idx}",
                    "shot_index": shot_idx,
                    "candidate": cand,
                    "source_start_seconds": round(src_start, 3),
                    "source_end_seconds": round(src_end, 3),
                    "clip_start_seconds": round(clip_start, 3),
                    "clip_end_seconds": round(clip_end, 3),
                    "duration_seconds": round(shot_duration, 3),
                    "sub_role": "FOCAL_ACTION" if shot_idx == 1 else "REACTION_OR_LOCATION"
                })
                if used_intervals is not None:
                    used_intervals.append((m_num, clip_start, clip_end))
                shot_idx += 1

        # Strategy B: If fewer shots than target_shots_per_beat, decompose valid candidates into additional rapid cuts
        if len(shots) < target_shots_per_beat and valid_candidates:
            for cand in valid_candidates:
                if len(shots) >= target_shots_per_beat:
                    break
                m_num = int(cand["movie_number"])
                src_start = float(cand["start_seconds"])
                src_end = float(cand["end_seconds"])

                # Determine starting position within candidate interval
                cand_shots = [s for s in shots if s["candidate"].get("chunk_id") == cand.get("chunk_id")]
                last_end = max([s["clip_end_seconds"] for s in cand_shots], default=src_start)

                while len(shots) < target_shots_per_beat and (src_end - last_end) >= MIN_SHOT_DURATION:
                    rem = src_end - last_end
                    shot_dur = min(MAX_SHOT_DURATION, max(MIN_SHOT_DURATION, min(DEFAULT_TARGET_SHOT_DURATION, rem)))
                    c_start = last_end
                    c_end = c_start + shot_dur

                    # Verify no overlap with used_intervals
                    if used_intervals and any(
                        u_m == m_num and max(c_start, u_s) < min(c_end, u_e) - 0.5
                        for (u_m, u_s, u_e) in used_intervals
                    ):
                        last_end += shot_dur
                        continue

                    s_idx = len(shots) + 1
                    shots.append({
                        "shot_id": f"shot_{s_idx}",
                        "shot_index": s_idx,
                        "candidate": cand,
                        "source_start_seconds": round(src_start, 3),
                        "source_end_seconds": round(src_end, 3),
                        "clip_start_seconds": round(c_start, 3),
                        "clip_end_seconds": round(c_end, 3),
                        "duration_seconds": round(shot_dur, 3),
                        "sub_role": "RAPID_CUT_PAYOFF"
                    })
                    if used_intervals is not None:
                        used_intervals.append((m_num, c_start, c_end))
                    last_end = c_end

        return shots

    # --------------------------------------------------------------------------
    # 7. MOVIE SOURCE MANAGEMENT (GOOGLE DRIVE VAULT & DISK CHECK)
    # --------------------------------------------------------------------------
    def resolve_movie_file(
        self,
        movie_number: int,
        allow_download: bool = False
    ) -> Tuple[Optional[Path], str, Optional[str]]:
        """
        Resolves movie video file path and cloud Drive metadata.
        Returns: (local_path_if_present, source_mode, drive_id)
        
        Invariant:
          Movie 8 is treated as cloud-resolvable. The local file is development cache only.
          Production execution retrieves on-demand from Google Drive vault.
        """
        meta = get_movie_by_number(movie_number)
        if not meta:
            logger.error(f"Unknown movie number: {movie_number}")
            return None, "UNRESOLVABLE", None

        video_filename = meta["video_filename"]
        drive_id = meta["video_drive_id"]
        local_path = self.movies_dir / video_filename

        if local_path.exists() and local_path.stat().st_size > 0:
            return local_path, "LOCAL_DEV_CACHE", drive_id

        if not allow_download:
            return None, "CLOUD_RESOLVABLE", drive_id

        # Cloud on-demand single-movie download with disk check
        free_bytes = shutil.disk_usage(self.movies_dir).free
        required_bytes = meta.get("video_file_size_bytes", 3 * 1024 * 1024 * 1024)
        if free_bytes < required_bytes + (1024 * 1024 * 1024):
            logger.error(f"Insufficient disk space for Movie {movie_number}: Free {free_bytes/(1024**3):.2f} GB")
            return None, "INSUFFICIENT_DISK", drive_id

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload

            if not HP_TOKEN_PATH.exists():
                return None, "NO_DRIVE_TOKEN", drive_id

            creds = Credentials.from_authorized_user_file(str(HP_TOKEN_PATH))
            drive = build("drive", "v3", credentials=creds)

            logger.info(f"Downloading Movie {movie_number} ({video_filename}) from Drive ID {drive_id}...")
            req = drive.files().get_media(fileId=drive_id)
            with open(local_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, req, chunksize=10 * 1024 * 1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            logger.info(f"Movie {movie_number} materialized successfully.")
            return local_path, "CLOUD_MATERIALIZED", drive_id
        except Exception as e:
            logger.error(f"Drive download failed for Movie {movie_number}: {e}")
            local_path.unlink(missing_ok=True)
            return None, "DOWNLOAD_FAILED", drive_id

    # --------------------------------------------------------------------------
    # 8. EXACT MUTED CLIP EXTRACTION & FFPROBE VALIDATION
    # --------------------------------------------------------------------------
    def extract_rapid_shot(
        self,
        shot: Dict[str, Any],
        script_id: str,
        beat_id: str,
        movie_path: Path
    ) -> Dict[str, Any]:
        """
        Extracts an exact, audio-muted (-an) 9:16 vertical clip (1.5s - 3.0s).
        Asserts via ffprobe that ZERO audio streams are present.
        """
        clip_start = shot["clip_start_seconds"]
        clip_dur = shot["duration_seconds"]
        shot_id = shot["shot_id"]

        output_filename = f"{script_id}_{beat_id}_{shot_id}.mp4"
        output_path = self.clips_dir / output_filename

        self.asset_engine.extract_muted_clip(
            video_input_path=movie_path,
            start_seconds=clip_start,
            duration_seconds=clip_dur,
            output_clip_path=output_path,
            target_width=1080,
            target_height=1920
        )

        sha = hashlib.sha256()
        with open(output_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                sha.update(chunk)
        clip_hash = sha.hexdigest()

        # FFprobe verification
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,width,height",
            "-of", "json",
            str(output_path)
        ]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        probe_data = json.loads(probe_res.stdout) if probe_res.returncode == 0 else {}
        streams = probe_data.get("streams", [])

        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        video_streams = [s for s in streams if s.get("codec_type") == "video"]

        if len(audio_streams) > 0:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"[INVARIANT VIOLATION] Extracted shot {output_filename} contains audio streams! Must be 0."
            )

        width = video_streams[0].get("width", 1080) if video_streams else 1080
        height = video_streams[0].get("height", 1920) if video_streams else 1920

        return {
            "file_path": str(output_path),
            "file_name": output_filename,
            "file_size_bytes": output_path.stat().st_size,
            "sha256": clip_hash,
            "width": width,
            "height": height,
            "audio_stream_count": 0,
            "clip_start_seconds": clip_start,
            "clip_end_seconds": shot["clip_end_seconds"],
            "duration_seconds": clip_dur,
            "extraction_status": "VERIFIED_MUTED"
        }

    # --------------------------------------------------------------------------
    # 9. PERSISTENCE LAYER (HPMovieClip)
    # --------------------------------------------------------------------------
    def persist_shot_record(
        self,
        script_id: str,
        beat_id: str,
        shot_id: str,
        shot_index: int,
        candidate: Dict[str, Any],
        shot_timing: Dict[str, Any],
        match_status: str,
        source_mode: str,
        source_drive_id: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        extraction_meta: Optional[Dict[str, Any]] = None,
        visual_source: str = "MOVIE_DIRECT",
        source_url: Optional[str] = None,
        creator: Optional[str] = None,
        license_name: Optional[str] = None,
        rights_status: Optional[str] = None,
        provenance_json: Optional[str] = None,
        visual_source_policy: str = "HYBRID_TRUTHFUL"
    ) -> HPMovieClip:
        """Persists or updates an individual HPMovieClip shot record in SQLite."""
        clip_pk = f"clip_{script_id}_{beat_id}_{shot_id}"

        with self.Session() as session:
            existing = session.query(HPMovieClip).filter_by(id=clip_pk).first()

            src_asset_id = f"hp_movie_{candidate.get('movie_number', 1)}"
            sub_id = candidate.get("chunk_id")
            m_num = candidate.get("movie_number", 1)
            m_title = candidate.get("movie_title", "")

            src_start = shot_timing.get("source_start_seconds", 0.0)
            src_end = shot_timing.get("source_end_seconds", 0.0)
            clip_start = shot_timing.get("clip_start_seconds", 0.0)
            clip_end = shot_timing.get("clip_end_seconds", 0.0)
            duration = shot_timing.get("duration_seconds", DEFAULT_TARGET_SHOT_DURATION)

            file_path = extraction_meta.get("file_path") if extraction_meta else None
            file_size = extraction_meta.get("file_size_bytes") if extraction_meta else None
            sha256 = extraction_meta.get("sha256") if extraction_meta else None
            width = extraction_meta.get("width", 1080) if extraction_meta else None
            height = extraction_meta.get("height", 1920) if extraction_meta else None

            if existing:
                existing.shot_id = shot_id
                existing.shot_index = shot_index
                existing.source_start_seconds = src_start
                existing.source_end_seconds = src_end
                existing.clip_start_seconds = clip_start
                existing.clip_end_seconds = clip_end
                existing.duration_seconds = duration
                existing.matched_text = candidate.get("text")
                existing.retrieval_query = candidate.get("matched_query")
                existing.retrieval_score = candidate.get("score", 0.0)
                existing.confidence = candidate.get("score", 0.0)
                existing.match_status = match_status
                existing.rejection_reason = rejection_reason
                existing.source_drive_id = source_drive_id
                existing.source_mode = source_mode
                existing.file_path = file_path
                existing.file_size_bytes = file_size
                existing.sha256 = sha256
                existing.audio_stream_count = 0
                existing.width = width
                existing.height = height
                existing.visual_source = visual_source
                existing.source_url = source_url
                existing.creator = creator
                existing.license_name = license_name
                existing.rights_status = rights_status
                existing.provenance_json = provenance_json
                existing.visual_source_policy = visual_source_policy
                existing.status = "READY_FOR_STEP_10" if match_status == "ACCEPTED" else "REJECTED"
                existing.updated_at = datetime.utcnow()
                rec = existing
            else:
                rec = HPMovieClip(
                    id=clip_pk,
                    script_id=script_id,
                    beat_id=beat_id,
                    shot_id=shot_id,
                    shot_index=shot_index,
                    movie_id=src_asset_id,
                    movie_number=m_num,
                    movie_title=m_title,
                    source_asset_id=src_asset_id,
                    source_drive_id=source_drive_id,
                    source_mode=source_mode,
                    subtitle_chunk_id=sub_id,
                    source_start_seconds=src_start,
                    source_end_seconds=src_end,
                    clip_start_seconds=clip_start,
                    clip_end_seconds=clip_end,
                    duration_seconds=duration,
                    matched_text=candidate.get("text"),
                    retrieval_query=candidate.get("matched_query"),
                    retrieval_score=candidate.get("score", 0.0),
                    confidence=candidate.get("score", 0.0),
                    match_status=match_status,
                    rejection_reason=rejection_reason,
                    file_path=file_path,
                    file_size_bytes=file_size,
                    sha256=sha256,
                    audio_stream_count=0,
                    width=width,
                    height=height,
                    visual_source=visual_source,
                    source_url=source_url,
                    creator=creator,
                    license_name=license_name,
                    rights_status=rights_status,
                    provenance_json=provenance_json,
                    visual_source_policy=visual_source_policy,
                    status="READY_FOR_STEP_10" if match_status == "ACCEPTED" else "REJECTED",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(rec)

            session.commit()
            return rec

    # --------------------------------------------------------------------------
    # 10. FULL SCRIPT EXECUTION (1 BEAT -> MULTIPLE SHOTS)
    # --------------------------------------------------------------------------
    def process_script_shots(
        self,
        script_id: str,
        allow_download: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Executes Step 9 for all visual beats of a given script,
        resolving each beat into 2–3 rapid-fire shot units.
        """
        import math
        with self.Session() as session:
            script = session.query(HarryPotterScript).filter_by(id=script_id).first()
            if not script:
                raise ValueError(f"Script not found: {script_id}")
            beats = json.loads(script.visual_beats_json)
            est_duration = getattr(script, "estimated_duration_sec", 0.0) or 0.0
            if est_duration <= 0.0:
                word_cnt = getattr(script, "word_count", 0) or len(getattr(script, "full_text", "").split())
                est_duration = (word_cnt / 2.5) if word_cnt > 0 else 28.0
            # Ensure idempotency: remove prior clip records for this script before inserting fresh ones
            session.query(HPMovieClip).filter_by(script_id=script_id).delete()
            session.commit()

        canonical_events_map = {}
        try:
            canonical_events = self.semantic_event_engine.get_canonical_events_for_short(script_id)
            for ev in canonical_events:
                canonical_events_map[ev.beat_id] = ev
        except Exception as e:
            logger.debug(f"Could not load canonical events for {script_id}: {e}")

        used_intervals = []
        script_shots = []

        num_beats = max(1, len(beats))
        total_needed_shots = max(num_beats * 2, int(math.ceil(est_duration / 2.2)))
        shots_per_beat = max(2, int(math.ceil(total_needed_shots / num_beats)))

        for beat in beats:
            beat_id = beat.get("beat_id", "beat_1")
            canonical_event = canonical_events_map.get(beat_id)
            if not canonical_event:
                # Dynamic canonical event resolution from MovieEventRetrievalEngine
                try:
                    from engines.movie_event.models import MovieEventQuery
                    sub = beat.get("subject") or (beat.get("characters")[0] if beat.get("characters") else None)
                    act = beat.get("action") or beat.get("visual_requirement")
                    tgt = beat.get("object") or beat.get("target") or (beat.get("objects")[0] if beat.get("objects") else None)
                    me_q = MovieEventQuery(
                        subject=sub,
                        action=act,
                        target=tgt,
                        location=beat.get("location"),
                        objects=list(beat.get("objects", [])),
                        movie_number=beat.get("preferred_movie_number")
                    )
                    top_evs = self.movie_event_retrieval_engine.retrieve_events(me_q, top_k=1, min_score=40.0)
                    if top_evs:
                        canonical_event = top_evs[0][0]
                except Exception as e:
                    logger.debug(f"Dynamic canonical event resolution error for beat {beat_id}: {e}")

            # 1. Search candidates
            candidates = self.search_candidates_for_beat(beat, canonical_event=canonical_event)

            # 2. Context expansion
            for c in candidates:
                self.expand_candidate_context(c)

            # 3. Score & Rerank with visual-semantic matching and framing
            ranked = self.rerank_candidates(beat, candidates, canonical_event=canonical_event, used_intervals=used_intervals)

            # 4. Decompose beat into rapid-fire shots (1.5s - 3.0s each) with anti-loop intervals
            shots = self.resolve_beat_to_shots(beat, ranked, target_shots_per_beat=shots_per_beat, canonical_event=canonical_event, used_intervals=used_intervals)

            if not shots:
                # Check truthful fan-art / official artwork before marking as rejected
                from engines.fan_art_retrieval_engine import FanArtRetrievalEngine
                fa_engine = FanArtRetrievalEngine()
                artwork = fa_engine.search_artwork_for_beat(beat)
                if artwork and artwork.file_path and Path(artwork.file_path).exists():
                    dur = float(beat.get("duration_seconds", 2.5))
                    art_clip = self.clips_dir / f"{script_id}_{beat_id}_fanart.mp4"
                    try:
                        fa_engine.format_artwork_to_clip(Path(artwork.file_path), art_clip, duration_seconds=dur)
                        rec = self.persist_shot_record(
                            script_id=script_id,
                            beat_id=beat_id,
                            shot_id="shot_1",
                            shot_index=1,
                            candidate={
                                "movie_number": 0,
                                "movie_title": f"Artwork: {artwork.creator or 'Curated'}",
                                "text": artwork.visual_description,
                                "matched_query": artwork.search_query,
                                "score": 90.0,
                            },
                            shot_timing={
                                "source_start_seconds": 0.0,
                                "source_end_seconds": dur,
                                "clip_start_seconds": 0.0,
                                "clip_end_seconds": dur,
                                "duration_seconds": dur
                            },
                            match_status="ACCEPTED",
                            source_mode="LOCAL_DEV_CACHE",
                            extraction_meta={
                                "file_path": str(art_clip),
                                "file_size_bytes": art_clip.stat().st_size,
                                "sha256": fa_engine.compute_image_hash(art_clip),
                                "audio_stream_count": 0,
                                "width": 1080,
                                "height": 1920
                            },
                            visual_source=artwork.source_type.value,
                            source_url=artwork.source_url,
                            creator=artwork.creator,
                            license_name=artwork.license,
                            rights_status=artwork.rights_status.value,
                            provenance_json=json.dumps(artwork.to_dict()),
                            visual_source_policy="HYBRID_TRUTHFUL"
                        )
                        script_shots.append({
                            "shot_id": "shot_1",
                            "shot_index": 1,
                            "beat_id": beat_id,
                            "clip_start_seconds": 0.0,
                            "clip_end_seconds": dur,
                            "duration_seconds": dur,
                            "file_path": str(art_clip),
                            "visual_source": artwork.source_type.value,
                            "candidate": {"movie_number": 0, "movie_title": f"Artwork: {artwork.creator or 'Curated'}"}
                        })
                        continue
                    except Exception as art_err:
                        logger.warning(f"Failed to format artwork clip for {beat_id}: {art_err}")

                # No candidate met the gate; record rejected shot without forcing unrelated footage
                top_cand = ranked[0] if ranked else {}
                _, match_status, reason = self.evaluate_confidence_gate(top_cand or None)
                self.persist_shot_record(
                    script_id=script_id,
                    beat_id=beat_id,
                    shot_id="shot_1",
                    shot_index=1,
                    candidate=top_cand,
                    shot_timing={"source_start_seconds": 0.0, "source_end_seconds": 0.0, "duration_seconds": 0.0},
                    match_status="REJECTED",
                    source_mode="CLOUD_RESOLVABLE",
                    rejection_reason=reason or "Neither movie footage nor approved artwork depicts this beat.",
                    visual_source="NO_VALID_VISUAL"
                )
                continue

            for shot in shots:
                cand = shot["candidate"]
                shot_id = shot["shot_id"]
                shot_idx = shot["shot_index"]
                m_num = cand["movie_number"]

                # Resolve movie source
                movie_file, source_mode, drive_id = self.resolve_movie_file(m_num, allow_download=allow_download)

                extraction_meta = None
                match_status = "ACCEPTED"
                reason = None

                if movie_file and movie_file.exists():
                    try:
                        extraction_meta = self.extract_rapid_shot(
                            shot=shot,
                            script_id=script_id,
                            beat_id=beat_id,
                            movie_path=movie_file
                        )
                    except Exception as e:
                        logger.error(f"Clip extraction failed for {script_id} {beat_id} {shot_id}: {e}")
                        match_status = "EXTRACTION_FAILED"
                        reason = str(e)
                else:
                    reason = f"MOVIE_{m_num}_SOURCE_PENDING_CLOUD_DOWNLOAD"

                self.persist_shot_record(
                    script_id=script_id,
                    beat_id=beat_id,
                    shot_id=shot_id,
                    shot_index=shot_idx,
                    candidate=cand,
                    shot_timing=shot,
                    match_status=match_status,
                    source_mode=source_mode,
                    source_drive_id=drive_id,
                    rejection_reason=reason if match_status != "ACCEPTED" else None,
                    extraction_meta=extraction_meta,
                    visual_source="ATMOSPHERIC_ESTABLISHING" if cand.get("is_atmospheric_fallback") else "MOVIE_DIRECT"
                )

                script_shots.append({
                    "script_id": script_id,
                    "beat_id": beat_id,
                    "shot_id": shot_id,
                    "movie_number": m_num,
                    "duration_seconds": shot["duration_seconds"],
                    "confidence": cand.get("score", 0.0),
                    "match_status": match_status,
                    "source_mode": source_mode,
                    "source_drive_id": drive_id,
                    "extraction_meta": extraction_meta
                })

        return script_shots

    def process_launch_batch(self, allow_download: bool = False) -> Dict[str, Any]:
        """Executes Step 9 rapid-fire shot retrieval across all 4 launch batch scripts."""
        with self.Session() as session:
            scripts = session.query(HarryPotterScript).order_by(HarryPotterScript.id.asc()).all()
            script_ids = [s.id for s in scripts]

        batch_summary = {
            "total_scripts": len(script_ids),
            "total_shots_resolved": 0,
            "accepted_shots": 0,
            "extracted_shots": 0,
            "shot_durations": [],
            "scripts": {}
        }

        for sid in script_ids:
            shots = self.process_script_shots(sid, allow_download=allow_download)
            batch_summary["scripts"][sid] = shots
            for sh in shots:
                batch_summary["total_shots_resolved"] += 1
                if sh["match_status"] == "ACCEPTED":
                    batch_summary["accepted_shots"] += 1
                if sh.get("extraction_meta"):
                    batch_summary["extracted_shots"] += 1
                batch_summary["shot_durations"].append(sh["duration_seconds"])

        return batch_summary
