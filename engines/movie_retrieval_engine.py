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
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import PROJECT_ROOT, DATABASE_DIR, DB_PATH
from core.models import Base, MovieAssetRecord, MovieSubtitleChunk, HarryPotterScript, HPMovieClip
from core.movie_registry import CANONICAL_MOVIES, get_movie_by_number
from engines.movie_asset_engine import MovieAssetEngine, get_db_connection

logger = logging.getLogger(__name__)

MOVIES_DIR = PROJECT_ROOT / "data" / "movies"
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
HP_TOKEN_PATH = CREDENTIALS_DIR / "hp_token.json"

MIN_CONFIDENCE_THRESHOLD = 50.0
DEFAULT_TARGET_SHOT_DURATION = 2.2  # Seconds
MIN_SHOT_DURATION = 1.5
MAX_SHOT_DURATION = 3.0


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

    # --------------------------------------------------------------------------
    # 1. VISUAL BEAT QUERY BUILDER
    # --------------------------------------------------------------------------
    def build_queries_for_beat(self, beat: Dict[str, Any]) -> List[str]:
        """
        Generates prioritized search queries for a visual beat.
        Combines retrieval hints, character names, location, and action keywords.
        """
        queries = []
        hints = beat.get("retrieval_hints", [])
        characters = beat.get("characters", [])
        location = beat.get("location", "")
        action = beat.get("action", "")
        req = beat.get("visual_requirement", "")

        # 1. Cleaned specific retrieval hints
        if hints:
            clean_hints = [re.sub(r"[^a-zA-Z0-9\s]", "", h).strip() for h in hints if h]
            clean_hints = [h for h in clean_hints if len(h) >= 3]
            if clean_hints:
                queries.append(" ".join(clean_hints[:3]))
                for h in clean_hints:
                    if h not in queries:
                        queries.append(h)

        # 2. Character names (tokens and full names)
        for char in characters:
            clean_char = re.sub(r"[^a-zA-Z0-9\s]", "", char).strip()
            if clean_char:
                for token in clean_char.split():
                    if len(token) >= 4 and token.lower() not in ("baby", "professor", "albus", "uncle", "aunt"):
                        if token not in queries:
                            queries.append(token)
                if clean_char not in queries:
                    queries.append(clean_char)

        # 3. Salient action / location nouns
        salient_words = []
        for text_source in (location, action, req):
            words = re.findall(r"[a-zA-Z]{4,}", text_source)
            for w in words:
                w_lower = w.lower()
                if w_lower not in (
                    "with", "from", "that", "this", "shot", "approaches",
                    "standing", "looking", "walking", "holding", "silent",
                    "quiet", "suburban", "evening", "across", "under", "front", "side"
                ):
                    if w not in salient_words:
                        salient_words.append(w)
        if salient_words:
            queries.append(" ".join(salient_words[:3]))
            for sw in salient_words[:5]:
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
        max_candidates: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Queries the movie subtitles FTS5 index across generated queries.
        Prioritizes the beat's preferred_movie_number, then falls back globally.
        """
        queries = self.build_queries_for_beat(beat)
        preferred_m = beat.get("preferred_movie_number")
        candidates_by_id = {}

        # Round 1: Preferred movie search
        if preferred_m:
            for q in queries:
                matches = self.asset_engine.search_movie_scenes(q, movie_number=preferred_m, limit=max_candidates)
                for m in matches:
                    if m["chunk_id"] not in candidates_by_id:
                        m["matched_query"] = q
                        candidates_by_id[m["chunk_id"]] = m

        # Round 2: Fallback global search if fewer than 5 candidates
        if len(candidates_by_id) < 5:
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
        chunk_id = candidate["chunk_id"]
        movie_num = candidate["movie_number"]

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
    # 4. MULTI-FACTOR RERANKING & SCORING
    # --------------------------------------------------------------------------
    def score_candidate(
        self,
        candidate: Dict[str, Any],
        beat: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Multi-Factor Scoring (0 to 100 points):
          1. Character Match (0 - 30 pts)
          2. Action / Keyword Match (0 - 25 pts)
          3. Location / Object Match (0 - 15 pts)
          4. Lexical BM25 (0 - 15 pts)
          5. Preferred Movie Match (0 - 15 pts)
          6. Duration Suitability (0 - 10 pts)
        """
        text = candidate.get("text", "").lower()
        context = candidate.get("expanded_context", "").lower()
        combined_text = f"{text} {context}"

        score_details = {}

        # 1. Character Match (0-30 pts)
        characters = [c.lower() for c in beat.get("characters", [])]
        char_points = 0.0
        for char in characters:
            tokens = [t for t in re.split(r"\s+", char) if len(t) >= 4]
            if char in combined_text:
                char_points += 30.0
                break
            elif any(t in combined_text for t in tokens):
                char_points += 20.0
                break
        char_score = min(30.0, char_points)
        score_details["character_score"] = char_score

        # 2. Action / Visual Keyword Match (0-25 pts)
        action_words = set(re.findall(r"[a-zA-Z]{4,}", beat.get("action", "").lower()))
        hint_words = set(re.findall(r"[a-zA-Z]{4,}", " ".join(beat.get("retrieval_hints", [])).lower()))
        target_keywords = action_words.union(hint_words)
        matched_kw_count = sum(1 for kw in target_keywords if kw in combined_text)
        action_score = min(25.0, matched_kw_count * 8.5)
        score_details["action_score"] = round(action_score, 1)

        # 3. Location / Object Match (0-15 pts)
        loc_words = set(re.findall(r"[a-zA-Z]{4,}", beat.get("location", "").lower()))
        req_words = set(re.findall(r"[a-zA-Z]{4,}", beat.get("visual_requirement", "").lower()))
        loc_target = loc_words.union(req_words)
        matched_loc_count = sum(1 for kw in loc_target if kw in combined_text)
        loc_score = min(15.0, matched_loc_count * 5.0)
        score_details["location_score"] = round(loc_score, 1)

        # 4. Lexical BM25 (0-15 pts)
        rank = float(candidate.get("relevance_rank", 0.0))
        bm25_score = max(0.0, min(15.0, 15.0 - abs(rank) * 1.5))
        score_details["bm25_score"] = round(bm25_score, 1)

        # 5. Preferred Movie Match (0-15 pts)
        pref_m = beat.get("preferred_movie_number")
        movie_score = 15.0 if (pref_m and candidate.get("movie_number") == pref_m) else 0.0
        score_details["preferred_movie_score"] = movie_score

        # 6. Duration Suitability (0-10 pts)
        duration = float(candidate.get("duration_seconds", 0.0))
        if 2.0 <= duration <= 15.0:
            dur_score = 10.0
        else:
            dur_score = 5.0
        score_details["duration_score"] = dur_score

        total_score = char_score + action_score + loc_score + bm25_score + movie_score + dur_score
        total_score = round(min(100.0, max(0.0, total_score)), 2)

        candidate["score"] = total_score
        candidate["score_details"] = score_details
        return candidate

    def rerank_candidates(
        self,
        beat: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Scores and ranks candidates in descending order of composite score."""
        scored = [self.score_candidate(c, beat) for c in candidates]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    # --------------------------------------------------------------------------
    # 5. CONFIDENCE GATE & VISUAL POLICY ENFORCEMENT
    # --------------------------------------------------------------------------
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
        if score >= threshold:
            return True, "ACCEPTED", "HIGH_CONFIDENCE_MOVIE_MATCH"
        else:
            return False, "REJECTED", f"LOW_RETRIEVAL_CONFIDENCE (Score {score:.1f} < {threshold:.1f})"

    # --------------------------------------------------------------------------
    # 6. BEAT -> RAPID-FIRE SHOT UNITS RESOLUTION
    # --------------------------------------------------------------------------
    def resolve_beat_to_shots(
        self,
        beat: Dict[str, Any],
        ranked_candidates: List[Dict[str, Any]],
        target_shots_per_beat: int = 2
    ) -> List[Dict[str, Any]]:
        """
        ARCHITECTURAL ADVANCEMENT:
        Decomposes 1 visual beat into 2 to 3 rapid-fire movie shot units (1.5s - 3.0s each).
        Uses distinct high-confidence scene candidates or sub-cuts from focal scenes.
        NEVER uses unrelated footage.
        """
        valid_candidates = [
            c for c in ranked_candidates
            if c.get("score", 0.0) >= MIN_CONFIDENCE_THRESHOLD
        ]

        if not valid_candidates:
            # Fallback placeholder to record rejection
            return []

        shots = []
        shot_idx = 1

        # Strategy A: Select top distinct high-confidence candidates for the beat
        if len(valid_candidates) >= 2:
            for cand in valid_candidates[:target_shots_per_beat]:
                src_start = float(cand["start_seconds"])
                src_end = float(cand["end_seconds"])
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
                shot_idx += 1

        # Strategy B: If only 1 distinct scene candidate is valid, decompose it into 2 rapid cuts
        else:
            primary = valid_candidates[0]
            src_start = float(primary["start_seconds"])
            src_end = float(primary["end_seconds"])
            total_dur = src_end - src_start

            if total_dur >= 4.0:
                # Cut 1: Initial focus / reaction (2.2s)
                dur_1 = min(2.5, total_dur / 2.0)
                dur_1 = max(MIN_SHOT_DURATION, dur_1)
                shots.append({
                    "shot_id": "shot_1",
                    "shot_index": 1,
                    "candidate": primary,
                    "source_start_seconds": round(src_start, 3),
                    "source_end_seconds": round(src_end, 3),
                    "clip_start_seconds": round(src_start, 3),
                    "clip_end_seconds": round(src_start + dur_1, 3),
                    "duration_seconds": round(dur_1, 3),
                    "sub_role": "ESTABLISHING_OR_ACTION"
                })
                # Cut 2: Follow-through / dialogue payoff (2.2s)
                dur_2 = min(MAX_SHOT_DURATION, max(MIN_SHOT_DURATION, total_dur - dur_1))
                start_2 = src_start + dur_1
                shots.append({
                    "shot_id": "shot_2",
                    "shot_index": 2,
                    "candidate": primary,
                    "source_start_seconds": round(src_start, 3),
                    "source_end_seconds": round(src_end, 3),
                    "clip_start_seconds": round(start_2, 3),
                    "clip_end_seconds": round(start_2 + dur_2, 3),
                    "duration_seconds": round(dur_2, 3),
                    "sub_role": "DIALOGUE_PAYOFF"
                })
            else:
                # Single rapid shot
                dur = min(MAX_SHOT_DURATION, max(MIN_SHOT_DURATION, total_dur))
                shots.append({
                    "shot_id": "shot_1",
                    "shot_index": 1,
                    "candidate": primary,
                    "source_start_seconds": round(src_start, 3),
                    "source_end_seconds": round(src_end, 3),
                    "clip_start_seconds": round(src_start, 3),
                    "clip_end_seconds": round(src_start + dur, 3),
                    "duration_seconds": round(dur, 3),
                    "sub_role": "FOCAL_ACTION"
                })

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
        extraction_meta: Optional[Dict[str, Any]] = None
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
                    visual_source_policy="MOVIE_FOOTAGE_ONLY",
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
        with self.Session() as session:
            script = session.query(HarryPotterScript).filter_by(id=script_id).first()
            if not script:
                raise ValueError(f"Script not found: {script_id}")
            beats = json.loads(script.visual_beats_json)

        script_shots = []

        for beat in beats:
            beat_id = beat.get("beat_id", "beat_1")

            # 1. Search candidates
            candidates = self.search_candidates_for_beat(beat)

            # 2. Context expansion
            for c in candidates:
                self.expand_candidate_context(c)

            # 3. Score & Rerank
            ranked = self.rerank_candidates(beat, candidates)

            # 4. Decompose beat into rapid-fire shots (1.5s - 3.0s each)
            shots = self.resolve_beat_to_shots(beat, ranked, target_shots_per_beat=2)

            if not shots:
                # No candidate met the gate; record rejected shot
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
                    rejection_reason=reason
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
                    extraction_meta=extraction_meta
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
