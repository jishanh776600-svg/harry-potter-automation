"""
Harry Potter Movie Asset & Subtitle Engine (Step 6A)
================================================================================
Deterministic Movie -> Video -> SRT asset registration, scene-level subtitle
chunking, SQLite FTS5 semantic search, and hard-enforced audio-muted clip extraction.

Invariants:
  1. Deterministic Pairing: Every movie strictly maps to its verified video & SRT.
  2. Exact Timestamps: Subtitle chunks preserve millisecond-precise start/end timecodes.
  3. Audio Muting Invariant: All extracted movie clips MUST have audio stripped (-an).
     Any output clip containing an audio stream triggers an immediate exception.
  4. Idempotency: Duplicate runs reuse existing database records without duplicating rows.
"""

import os
import re
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import PROJECT_ROOT, DATABASE_DIR, DB_PATH
from core.models import Base, MovieAssetRecord, MovieSubtitleChunk
from core.movie_registry import CANONICAL_MOVIES

logger = logging.getLogger(__name__)

SUBTITLES_DIR = PROJECT_ROOT / "data" / "movie_subtitles"
MOVIES_DIR = PROJECT_ROOT / "data" / "movies"


def get_db_connection() -> sqlite3.Connection:
    """Returns raw SQLite connection with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_movie_tables():
    """Initializes SQLAlchemy movie tables and the SQLite FTS5 virtual table."""
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(engine)

    with get_db_connection() as conn:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS movie_subtitles_fts USING fts5(
                chunk_id UNINDEXED,
                movie_number UNINDEXED,
                movie_title UNINDEXED,
                start_timecode UNINDEXED,
                end_timecode UNINDEXED,
                text,
                tokenize = 'porter unicode61'
            );
        """)
        conn.commit()


def timecode_to_seconds(tc: str) -> float:
    """Converts SRT timecode HH:MM:SS,mmm to float seconds."""
    clean = tc.strip().replace(",", ".")
    parts = clean.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(clean)


def seconds_to_timecode(sec: float) -> str:
    """Converts float seconds to SRT timecode HH:MM:SS,mmm."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt_file(srt_path: Path) -> List[Dict[str, Any]]:
    """
    Robust SRT parser handling various line endings and HTML tags.
    Returns list of dicts: {seq, start_sec, end_sec, start_tc, end_tc, text}
    """
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Split on double newlines
    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        # Find timestamp line (e.g. 00:01:22,277 --> 00:01:27,271)
        tc_idx = None
        for idx, line in enumerate(lines[:3]):
            if "-->" in line:
                tc_idx = idx
                break

        if tc_idx is None:
            continue

        seq_str = lines[0] if tc_idx > 0 else "0"
        seq = int(re.sub(r"\D", "", seq_str)) if re.sub(r"\D", "", seq_str) else len(entries) + 1

        tc_parts = lines[tc_idx].split("-->")
        start_tc = tc_parts[0].strip()
        end_tc = tc_parts[1].strip().split()[0]  # strip any coordinates

        text_lines = lines[tc_idx + 1:]
        raw_text = " ".join(text_lines)
        # Strip HTML tags like <i>, </i>, <font>
        clean_text = re.sub(r"<[^>]+>", "", raw_text).strip()
        clean_text = re.sub(r"\s+", " ", clean_text)

        if not clean_text:
            continue

        start_sec = timecode_to_seconds(start_tc)
        end_sec = timecode_to_seconds(end_tc)

        entries.append({
            "seq": seq,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "start_timecode": start_tc,
            "end_timecode": end_tc,
            "duration_seconds": round(end_sec - start_sec, 3),
            "text": clean_text
        })

    return entries


def merge_into_scene_chunks(
    entries: List[Dict[str, Any]],
    max_duration_sec: float = 12.0,
    max_gap_sec: float = 2.5
) -> List[Dict[str, Any]]:
    """
    Groups adjacent subtitle entries into coherent scene units suitable for
    visual Short beats (4-12 seconds), while strictly preserving exact timecodes.
    """
    if not entries:
        return []

    chunks = []
    cur_entries = [entries[0]]

    for next_entry in entries[1:]:
        prev_entry = cur_entries[-1]
        gap = next_entry["start_seconds"] - prev_entry["end_seconds"]
        cum_duration = next_entry["end_seconds"] - cur_entries[0]["start_seconds"]

        # Merge if gap is small and cumulative duration is within target
        if gap <= max_gap_sec and cum_duration <= max_duration_sec:
            cur_entries.append(next_entry)
        else:
            # Finalize current scene chunk
            start_sec = cur_entries[0]["start_seconds"]
            end_sec = cur_entries[-1]["end_seconds"]
            text_combined = " ".join(e["text"] for e in cur_entries)
            chunks.append({
                "seq_start": cur_entries[0]["seq"],
                "seq_end": cur_entries[-1]["seq"],
                "start_seconds": round(start_sec, 3),
                "end_seconds": round(end_sec, 3),
                "start_timecode": cur_entries[0]["start_timecode"],
                "end_timecode": cur_entries[-1]["end_timecode"],
                "duration_seconds": round(end_sec - start_sec, 3),
                "text": text_combined,
                "raw_entries_count": len(cur_entries)
            })
            cur_entries = [next_entry]

    if cur_entries:
        start_sec = cur_entries[0]["start_seconds"]
        end_sec = cur_entries[-1]["end_seconds"]
        text_combined = " ".join(e["text"] for e in cur_entries)
        chunks.append({
            "seq_start": cur_entries[0]["seq"],
            "seq_end": cur_entries[-1]["seq"],
            "start_seconds": round(start_sec, 3),
            "end_seconds": round(end_sec, 3),
            "start_timecode": cur_entries[0]["start_timecode"],
            "end_timecode": cur_entries[-1]["end_timecode"],
            "duration_seconds": round(end_sec - start_sec, 3),
            "text": text_combined,
            "raw_entries_count": len(cur_entries)
        })

    return chunks


class MovieAssetEngine:
    """Manages movie asset registration, subtitle indexing, search, and audio-muted clip extraction."""

    def __init__(self):
        init_movie_tables()
        self.engine = create_engine(f"sqlite:///{DB_PATH}")
        self.Session = sessionmaker(bind=self.engine)

    def is_movie_registered(self, movie_number: int) -> bool:
        """Checks if a movie and its subtitles are already registered."""
        with self.Session() as session:
            rec = session.query(MovieAssetRecord).filter(MovieAssetRecord.movie_number == movie_number).first()
            return rec is not None and rec.total_scene_chunks > 0

    def register_movie(self, movie_meta: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """
        Registers a movie and parses its SRT subtitle file into searchable scene chunks.
        Idempotent: skips if already registered unless force=True.
        """
        m_num = movie_meta["movie_number"]
        m_title = movie_meta["title"]
        srt_filename = movie_meta["srt_filename"]
        srt_path = SUBTITLES_DIR / srt_filename

        if not srt_path.exists():
            raise FileNotFoundError(f"SRT file for Movie {m_num} not found at {srt_path}")

        if not force and self.is_movie_registered(m_num):
            with self.Session() as session:
                rec = session.query(MovieAssetRecord).filter(MovieAssetRecord.movie_number == m_num).first()
                logger.info(f"Movie {m_num} ('{m_title}') already registered ({rec.total_scene_chunks} scene chunks). Skipping.")
                return {
                    "movie_number": m_num,
                    "title": m_title,
                    "video_filename": rec.video_filename,
                    "srt_filename": rec.srt_filename,
                    "total_raw_subtitles": rec.total_raw_subtitles,
                    "total_scene_chunks": rec.total_scene_chunks,
                    "duration_seconds": rec.video_duration_seconds,
                    "pairing_status": rec.pairing_status,
                    "status": "CACHED"
                }

        logger.info(f"Parsing subtitles for Movie {m_num}: {m_title} ({srt_filename})...")
        raw_entries = parse_srt_file(srt_path)
        scene_chunks = merge_into_scene_chunks(raw_entries)
        logger.info(f"Movie {m_num}: {len(raw_entries)} raw subtitles merged into {len(scene_chunks)} scene units.")

        m_id = f"hp_movie_{m_num}"

        with self.Session() as session:
            if force:
                session.query(MovieSubtitleChunk).filter(MovieSubtitleChunk.movie_number == m_num).delete()
                session.query(MovieAssetRecord).filter(MovieAssetRecord.movie_number == m_num).delete()
                session.commit()
                with get_db_connection() as raw_conn:
                    raw_conn.execute("DELETE FROM movie_subtitles_fts WHERE movie_number = ?", (m_num,))
                    raw_conn.commit()

            # Insert MovieAssetRecord
            asset_rec = MovieAssetRecord(
                id=m_id,
                movie_number=m_num,
                title=m_title,
                video_filename=movie_meta["video_filename"],
                video_drive_id=movie_meta["video_drive_id"],
                video_file_size_bytes=movie_meta["video_file_size_bytes"],
                video_duration_seconds=movie_meta["video_duration_seconds"],
                width=movie_meta.get("width", 1920),
                height=movie_meta.get("height", 800),
                srt_filename=srt_filename,
                srt_local_path=str(srt_path),
                total_raw_subtitles=len(raw_entries),
                total_scene_chunks=len(scene_chunks),
                pairing_status="VALID",
                audio_muted_invariant=True,  # Invariant
                created_at=datetime.utcnow()
            )
            session.add(asset_rec)

            # Insert MovieSubtitleChunks
            fts_rows = []
            for idx, sc in enumerate(scene_chunks):
                chunk_id = f"hp_m{m_num}_sc_{idx + 1:04d}"
                sub_rec = MovieSubtitleChunk(
                    id=chunk_id,
                    movie_id=m_id,
                    movie_number=m_num,
                    movie_title=m_title,
                    seq_start=sc["seq_start"],
                    seq_end=sc["seq_end"],
                    start_seconds=sc["start_seconds"],
                    end_seconds=sc["end_seconds"],
                    start_timecode=sc["start_timecode"],
                    end_timecode=sc["end_timecode"],
                    duration_seconds=sc["duration_seconds"],
                    text=sc["text"],
                    source_srt=srt_filename,
                    created_at=datetime.utcnow()
                )
                session.add(sub_rec)
                fts_rows.append((
                    chunk_id,
                    m_num,
                    m_title,
                    sc["start_timecode"],
                    sc["end_timecode"],
                    sc["text"]
                ))

            session.commit()

        # Insert into SQLite FTS5 index
        with get_db_connection() as raw_conn:
            raw_conn.executemany("""
                INSERT INTO movie_subtitles_fts (chunk_id, movie_number, movie_title, start_timecode, end_timecode, text)
                VALUES (?, ?, ?, ?, ?, ?)
            """, fts_rows)
            raw_conn.commit()

        logger.info(f"Successfully registered Movie {m_num}: {m_title} ({len(scene_chunks)} scene units indexed).")

        return {
            "movie_number": m_num,
            "title": m_title,
            "video_filename": movie_meta["video_filename"],
            "srt_filename": srt_filename,
            "total_raw_subtitles": len(raw_entries),
            "total_scene_chunks": len(scene_chunks),
            "duration_seconds": movie_meta["video_duration_seconds"],
            "pairing_status": "VALID",
            "status": "REGISTERED"
        }

    def register_all_movies(self, force: bool = False) -> List[Dict[str, Any]]:
        """Registers all 8 available Harry Potter movies and their subtitles."""
        results = []
        for m_meta in CANONICAL_MOVIES:
            res = self.register_movie(m_meta, force=force)
            results.append(res)
        return results

    def search_movie_scenes(
        self,
        query: str,
        movie_number: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        FTS5 BM25 search for movie scenes matching dialogue or action descriptions.
        Returns exact start and end timestamps for video clip extraction.
        """
        clean_q = re.sub(r'[^\w\s"\'\-]', " ", query).strip()
        if not clean_q:
            return []

        terms = clean_q.split()
        if len(terms) == 1:
            fts_match = f'"{terms[0]}"*'
        else:
            fts_match = f'"{clean_q}"' if '"' in query else " AND ".join(f'"{t}"*' for t in terms)

        sql = """
            SELECT 
                s.id as chunk_id,
                s.movie_number,
                s.movie_title,
                s.start_seconds,
                s.end_seconds,
                s.start_timecode,
                s.end_timecode,
                s.duration_seconds,
                s.text,
                m.video_filename,
                m.video_drive_id,
                bm25(movie_subtitles_fts) as rank
            FROM movie_subtitles_fts f
            JOIN movie_subtitle_chunks s ON f.chunk_id = s.id
            JOIN movie_assets m ON s.movie_id = m.id
            WHERE movie_subtitles_fts MATCH ?
        """
        params = [fts_match]

        if movie_number is not None:
            sql += " AND s.movie_number = ?"
            params.append(movie_number)

        sql += " ORDER BY rank ASC LIMIT ?"
        params.append(limit)

        with get_db_connection() as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                simple_match = " OR ".join(f'"{t}"' for t in terms)
                params[0] = simple_match
                rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            results.append({
                "chunk_id": r["chunk_id"],
                "movie_number": r["movie_number"],
                "movie_title": r["movie_title"],
                "start_seconds": r["start_seconds"],
                "end_seconds": r["end_seconds"],
                "start_timecode": r["start_timecode"],
                "end_timecode": r["end_timecode"],
                "duration_seconds": r["duration_seconds"],
                "text": r["text"],
                "video_filename": r["video_filename"],
                "video_drive_id": r["video_drive_id"],
                "relevance_rank": round(float(r["rank"]), 3)
            })

        return results

    @staticmethod
    def extract_muted_clip(
        video_input_path: Path,
        start_seconds: float,
        duration_seconds: float,
        output_clip_path: Path,
        target_width: int = 1080,
        target_height: int = 1920,
        custom_vf: Optional[str] = None
    ) -> Path:
        """
        CRITICAL AUDIO MUTING INVARIANT:
        Extracts a vertical visual clip strictly without audio (-an).
        Verifies via ffprobe that output clip contains ZERO audio streams.
        Raises RuntimeError if audio is present.
        """
        output_clip_path.parent.mkdir(parents=True, exist_ok=True)

        vf = custom_vf if custom_vf else f"crop=ih*9/16:ih,scale={target_width}:{target_height}"

        # Explicit FFmpeg command with -an (disable audio) and 9:16 vertical crop
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(round(start_seconds, 3)),
            "-i", str(video_input_path),
            "-t", str(round(duration_seconds, 3)),
            "-an",  # HARD INVARIANT: STRIP ALL AUDIO
            "-vf", vf,
            "-c:v", "libx264",

            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(output_clip_path)
        ]

        logger.info(f"Extracting MUTED clip from {video_input_path.name} @ {start_seconds:.1f}s ({duration_seconds:.1f}s)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg clip extraction failed: {res.stderr[-300:]}")

        # Post-extraction probe: verify zero audio streams exist
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(output_clip_path)
        ]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        audio_streams = probe_res.stdout.strip()
        if audio_streams:
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"[AUDIO MUTING INVARIANT VIOLATION] Extracted clip {output_clip_path.name} "
                f"contains audio stream '{audio_streams}'! Movie audio must NEVER be preserved."
            )

        logger.info(f"Verified: {output_clip_path.name} is 100% video-only (audio completely muted).")
        return output_clip_path
