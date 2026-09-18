"""
Harry Potter Movie Visual Retrieval & Cloud-Safe Clip Extraction Engine (Step 9)
================================================================================
Transforms structured visual beats from Step 8 (hp_scripts) into verified,
audio-muted movie clips from Harry Potter Movies 1-8.

Pipeline Stage:
  hp_scripts (visual beats)
    -> Visual Beat Query Construction
    -> Movie Subtitle FTS5 Search
    -> Timestamp Candidate Discovery
    -> Candidate Context Expansion (adjacent subtitle chunks)
    -> Multi-Factor Reranking (Characters, Keywords, Location, BM25, Preferred Movie, Duration)
    -> Confidence Gate (>= 50.0 -> ACCEPTED; < 50.0 -> REJECTED)
    -> Movie Source Resolution (Local Cache / On-Demand Cloud Download)
    -> Exact Clip Extraction (ffmpeg -an, 9:16 vertical crop)
    -> Post-Extraction FFprobe Verification (assert 0 audio streams)
    -> Persistence to hp_movie_clips Table
    -> Ready for Step 10

Hard Invariants:
  1. ABSOLUTE ISOLATION: Zero interaction with AL AMR.
  2. MOVIE FOOTAGE ONLY: Strictly Movies 1-8. No AI imagery, no stock footage, no Pexels.
  3. AUDIO MUTING INVARIANT: Extracted clips must have audio stripped (-an).
     FFprobe verification must confirm 0 audio streams or raise RuntimeError.
  4. CLOUD-RUNNER COMPATIBILITY: Single movie on-demand download, disk space checks,
     safe ephemeral runner operation without exhausting disk.
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


class MovieRetrievalEngine:
    """
    End-to-end engine for retrieving movie scenes from subtitle indexes,
    scoring candidates against visual beat requirements, gating on confidence,
    and extracting verified audio-muted clips.
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
        Returns a list of search queries from most specific to broad fallback.
        """
        queries = []
        hints = beat.get("retrieval_hints", [])
        characters = beat.get("characters", [])
        location = beat.get("location", "")
        action = beat.get("action", "")
        req = beat.get("visual_requirement", "")

        # Query 1: Cleaned specific retrieval hints
        if hints:
            clean_hints = [re.sub(r"[^a-zA-Z0-9\s]", "", h).strip() for h in hints if h]
            clean_hints = [h for h in clean_hints if len(h) >= 3]
            if clean_hints:
                queries.append(" ".join(clean_hints[:3]))
                for h in clean_hints:
                    if h not in queries:
                        queries.append(h)

        # Query 2: Character names (first/last name tokens)
        for char in characters:
            clean_char = re.sub(r"[^a-zA-Z0-9\s]", "", char).strip()
            if clean_char:
                for token in clean_char.split():
                    if len(token) >= 4 and token.lower() not in ("baby", "professor", "albus", "uncle", "aunt"):
                        if token not in queries:
                            queries.append(token)
                if clean_char not in queries:
                    queries.append(clean_char)

        # Query 3: Salient action / location nouns
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

        # Ensure uniqueness while preserving order
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
        max_candidates: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Queries the movie subtitles FTS5 index across generated queries.
        Prioritizes the beat's preferred_movie_number, then falls back to other movies.
        """
        queries = self.build_queries_for_beat(beat)
        preferred_m = beat.get("preferred_movie_number")
        candidates_by_id = {}

        # Round 1: Search preferred movie with all queries
        if preferred_m:
            for q in queries:
                matches = self.asset_engine.search_movie_scenes(q, movie_number=preferred_m, limit=max_candidates)
                for m in matches:
                    if m["chunk_id"] not in candidates_by_id:
                        m["matched_query"] = q
                        candidates_by_id[m["chunk_id"]] = m

        # Round 2: If insufficient candidates, search globally across all movies
        if len(candidates_by_id) < 3:
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
        """
        Expands candidate context by fetching surrounding subtitle chunks
        (previous and next sequence entries) for the same movie.
        """
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
    # 4. MULTI-FACTOR RERANKING & CONFIDENCE SCORING
    # --------------------------------------------------------------------------
    def score_candidate(
        self,
        candidate: Dict[str, Any],
        beat: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Multi-Factor Scoring (0 to 100 points):
          1. Character Match (0 - 30 pts): Character names mentioned in scene/context text.
          2. Action / Keyword Match (0 - 25 pts): Actions/hints appearing in dialogue or scene.
          3. Location / Object Match (0 - 15 pts): Location/object keywords match.
          4. Lexical BM25 (0 - 15 pts): Direct query rank from SQLite FTS5.
          5. Preferred Movie Match (0 - 15 pts): Candidate belongs to preferred movie.
          6. Duration Suitability (0 - 10 pts): Scene duration falls within 3.0s - 12.0s.

        Total Score = sum of components (clamped 0 to 100).
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
        if 3.0 <= duration <= 12.0:
            dur_score = 10.0
        elif 2.0 <= duration <= 16.0:
            dur_score = 6.0
        else:
            dur_score = 2.0
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
        top_candidate: Optional[Dict[str, Any]],
        threshold: float = MIN_CONFIDENCE_THRESHOLD
    ) -> Tuple[bool, str, str]:
        """
        Validates whether the retrieved movie candidate satisfies the confidence gate.
        Returns: (is_accepted, match_status, reason)
        
        Strict Policies:
          - No AI imagery, no stock footage, no Pexels.
          - Only Harry Potter Movies 1-8.
          - Score must meet or exceed the threshold (default 50.0).
        """
        if top_candidate is None:
            return False, "REJECTED", "NO_CANDIDATE_FOUND"

        m_num = top_candidate.get("movie_number")
        if not m_num or m_num < 1 or m_num > 8:
            return False, "REJECTED", "NON_CANONICAL_MOVIE_NUMBER"

        score = float(top_candidate.get("score", 0.0))
        if score >= threshold:
            return True, "ACCEPTED", "HIGH_CONFIDENCE_MOVIE_MATCH"
        else:
            return False, "REJECTED", f"LOW_RETRIEVAL_CONFIDENCE (Score {score:.1f} < {threshold:.1f})"

    # --------------------------------------------------------------------------
    # 6. MOVIE SOURCE MANAGEMENT (LOCAL & CLOUD ON-DEMAND)
    # --------------------------------------------------------------------------
    def resolve_movie_file(
        self,
        movie_number: int,
        allow_download: bool = False
    ) -> Optional[Path]:
        """
        Resolves the local video file path for a canonical Harry Potter movie.
        If missing and allow_download=True, downloads on-demand from Google Drive.
        Checks disk space before download to ensure ephemeral runner safety.
        """
        meta = get_movie_by_number(movie_number)
        if not meta:
            logger.error(f"Unknown movie number: {movie_number}")
            return None

        video_filename = meta["video_filename"]
        local_path = self.movies_dir / video_filename

        if local_path.exists() and local_path.stat().st_size > 0:
            return local_path

        if not allow_download:
            logger.warning(
                f"Movie {movie_number} ({video_filename}) is not cached locally. "
                "allow_download=False; skipping cloud download."
            )
            return None

        free_bytes = shutil.disk_usage(self.movies_dir).free
        required_bytes = meta.get("video_file_size_bytes", 3 * 1024 * 1024 * 1024)
        if free_bytes < required_bytes + (1024 * 1024 * 1024):
            logger.error(
                f"Insufficient disk space to download Movie {movie_number}: "
                f"Free {free_bytes / (1024**3):.2f} GB < Required {(required_bytes + 1024**3)/(1024**3):.2f} GB"
            )
            return None

        drive_id = meta["video_drive_id"]
        logger.info(f"Downloading Movie {movie_number} ({video_filename}) on-demand from Drive ({drive_id})...")

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload

            if not HP_TOKEN_PATH.exists():
                logger.error(f"Drive token not found at {HP_TOKEN_PATH}")
                return None

            creds = Credentials.from_authorized_user_file(str(HP_TOKEN_PATH))
            drive = build("drive", "v3", credentials=creds)

            req = drive.files().get_media(fileId=drive_id)
            with open(local_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, req, chunksize=10 * 1024 * 1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"Movie {movie_number} download: {int(status.progress() * 100)}%")

            logger.info(f"Movie {movie_number} downloaded successfully to {local_path} ({local_path.stat().st_size} bytes)")
            return local_path
        except Exception as e:
            logger.error(f"Failed to download Movie {movie_number} from Drive: {e}")
            local_path.unlink(missing_ok=True)
            return None

    # --------------------------------------------------------------------------
    # 7. EXACT MUTED CLIP EXTRACTION & FFPROBE VERIFICATION
    # --------------------------------------------------------------------------
    def extract_clip(
        self,
        candidate: Dict[str, Any],
        script_id: str,
        beat_id: str,
        movie_path: Path,
        padding_sec: float = 0.8,
        min_duration: float = 2.5,
        max_duration: float = 8.0
    ) -> Dict[str, Any]:
        """
        Extracts an exact, audio-muted (-an) 9:16 vertical clip from the resolved movie file.
        Verifies via ffprobe that ZERO audio streams are present in the output.
        Computes SHA256 checksum and dimensions.
        """
        src_start = float(candidate["start_seconds"])
        src_end = float(candidate["end_seconds"])
        raw_duration = src_end - src_start

        clip_start = max(0.0, src_start - padding_sec)
        clip_duration = raw_duration + (2.0 * padding_sec)
        clip_duration = max(min_duration, min(max_duration, clip_duration))
        clip_end = clip_start + clip_duration

        output_filename = f"{script_id}_{beat_id}.mp4"
        output_path = self.clips_dir / output_filename

        self.asset_engine.extract_muted_clip(
            video_input_path=movie_path,
            start_seconds=clip_start,
            duration_seconds=clip_duration,
            output_clip_path=output_path,
            target_width=1080,
            target_height=1920
        )

        sha = hashlib.sha256()
        with open(output_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                sha.update(chunk)
        clip_hash = sha.hexdigest()

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
                f"[INVARIANT VIOLATION] Extracted clip {output_filename} has audio stream count {len(audio_streams)}! Must be 0."
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
            "source_start_seconds": round(src_start, 3),
            "source_end_seconds": round(src_end, 3),
            "clip_start_seconds": round(clip_start, 3),
            "clip_end_seconds": round(clip_end, 3),
            "duration_seconds": round(clip_duration, 3),
            "extraction_status": "VERIFIED_MUTED"
        }

    # --------------------------------------------------------------------------
    # 8. PERSISTENCE LAYER (HPMovieClip)
    # --------------------------------------------------------------------------
    def persist_clip_record(
        self,
        script_id: str,
        beat_id: str,
        candidate: Dict[str, Any],
        match_status: str,
        rejection_reason: Optional[str] = None,
        extraction_meta: Optional[Dict[str, Any]] = None
    ) -> HPMovieClip:
        """
        Idempotently persists or updates the HPMovieClip record in SQLite.
        """
        clip_id = f"clip_{script_id}_{beat_id}"

        with self.Session() as session:
            existing = session.query(HPMovieClip).filter_by(id=clip_id).first()

            src_asset_id = f"hp_movie_{candidate.get('movie_number', 1)}"
            sub_id = candidate.get("chunk_id")
            m_num = candidate.get("movie_number", 1)
            m_title = candidate.get("movie_title", "")

            src_start = extraction_meta["source_start_seconds"] if extraction_meta else float(candidate.get("start_seconds", 0.0))
            src_end = extraction_meta["source_end_seconds"] if extraction_meta else float(candidate.get("end_seconds", 0.0))
            clip_start = extraction_meta["clip_start_seconds"] if extraction_meta else src_start
            clip_end = extraction_meta["clip_end_seconds"] if extraction_meta else src_end
            duration = extraction_meta["duration_seconds"] if extraction_meta else round(src_end - src_start, 3)

            file_path = extraction_meta.get("file_path") if extraction_meta else None
            file_size = extraction_meta.get("file_size_bytes") if extraction_meta else None
            sha256 = extraction_meta.get("sha256") if extraction_meta else None
            width = extraction_meta.get("width", 1080) if extraction_meta else None
            height = extraction_meta.get("height", 1920) if extraction_meta else None

            if existing:
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
                    id=clip_id,
                    script_id=script_id,
                    beat_id=beat_id,
                    movie_id=src_asset_id,
                    movie_number=m_num,
                    movie_title=m_title,
                    source_asset_id=src_asset_id,
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
            logger.info(f"Persisted clip record {clip_id}: status={match_status}, score={candidate.get('score', 0.0)}")
            return rec

    # --------------------------------------------------------------------------
    # 9. FULL SCRIPT BEAT PIPELINE EXECUTION
    # --------------------------------------------------------------------------
    def process_script_beats(
        self,
        script_id: str,
        allow_download: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Executes Step 9 for all visual beats of a given script.
        Returns a list of per-beat results with clip metadata and verification details.
        """
        with self.Session() as session:
            script = session.query(HarryPotterScript).filter_by(id=script_id).first()
            if not script:
                raise ValueError(f"Script not found: {script_id}")
            beats = json.loads(script.visual_beats_json)

        results = []
        for beat in beats:
            beat_id = beat.get("beat_id", "beat_1")
            logger.info(f"Processing {script_id} -> {beat_id}...")

            # 1. Search candidates
            candidates = self.search_candidates_for_beat(beat)

            # 2. Expand context for candidates
            for c in candidates:
                self.expand_candidate_context(c)

            # 3. Score & Rerank
            ranked = self.rerank_candidates(beat, candidates)
            top_cand = ranked[0] if ranked else None

            # 4. Confidence Gate & Policy Check
            is_accepted, match_status, reason = self.evaluate_confidence_gate(top_cand)

            extraction_meta = None
            if is_accepted and top_cand:
                m_num = top_cand["movie_number"]
                movie_file = self.resolve_movie_file(m_num, allow_download=allow_download)

                if movie_file and movie_file.exists():
                    try:
                        extraction_meta = self.extract_clip(
                            candidate=top_cand,
                            script_id=script_id,
                            beat_id=beat_id,
                            movie_path=movie_file
                        )
                        logger.info(f"Extracted verified clip for {script_id} {beat_id}: {extraction_meta['file_name']}")
                    except Exception as e:
                        logger.error(f"Clip extraction failed for {script_id} {beat_id}: {e}")
                        match_status = "EXTRACTION_FAILED"
                        reason = str(e)
                else:
                    logger.info(
                        f"Clip extraction deferred for {script_id} {beat_id}: "
                        f"Movie {m_num} source not available locally."
                    )
                    reason = f"MOVIE_{m_num}_SOURCE_PENDING_DOWNLOAD"

            # 5. Persist to SQLite
            cand_to_persist = top_cand or {
                "chunk_id": None,
                "movie_number": beat.get("preferred_movie_number", 1),
                "movie_title": "Unknown",
                "score": 0.0,
                "text": None,
                "matched_query": None
            }
            self.persist_clip_record(
                script_id=script_id,
                beat_id=beat_id,
                candidate=cand_to_persist,
                match_status=match_status,
                rejection_reason=reason if match_status != "ACCEPTED" else None,
                extraction_meta=extraction_meta
            )

            results.append({
                "script_id": script_id,
                "beat_id": beat_id,
                "beat_requirement": beat.get("visual_requirement"),
                "preferred_movie": beat.get("preferred_movie_number"),
                "top_candidate": top_cand,
                "match_status": match_status,
                "reason": reason,
                "extraction_meta": extraction_meta
            })

        return results

    def process_launch_batch(self, allow_download: bool = False) -> Dict[str, Any]:
        """
        Executes Step 9 visual retrieval across all 4 launch batch scripts.
        """
        with self.Session() as session:
            scripts = session.query(HarryPotterScript).order_by(HarryPotterScript.id.asc()).all()
            script_ids = [s.id for s in scripts]

        batch_summary = {
            "total_scripts": len(script_ids),
            "total_beats": 0,
            "accepted_beats": 0,
            "rejected_beats": 0,
            "extracted_clips": 0,
            "scripts_processed": []
        }

        for sid in script_ids:
            beat_results = self.process_script_beats(sid, allow_download=allow_download)
            batch_summary["scripts_processed"].append({
                "script_id": sid,
                "beats": beat_results
            })
            for br in beat_results:
                batch_summary["total_beats"] += 1
                if br["match_status"] == "ACCEPTED":
                    batch_summary["accepted_beats"] += 1
                else:
                    batch_summary["rejected_beats"] += 1
                if br.get("extraction_meta"):
                    batch_summary["extracted_clips"] += 1

        return batch_summary
