"""
Franchise Visual Vault Database & Microsecond FTS5 Search Engine
================================================================
Stores rich visual metadata for extracted movie shots and provides
sub-millisecond full-text search across characters, objects, actions, and lore context.
"""
import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("FranchiseClipDB")

DB_DIR = Path(__file__).resolve().parent.parent / "data" / "database"
DB_PATH = DB_DIR / "franchise_visual_vault.db"

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_vault_db(db_path: Path = DB_PATH) -> None:
    """Initializes tables and search indexes."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS franchise_clips (
        clip_id TEXT PRIMARY KEY,
        movie_number INTEGER NOT NULL,
        movie_title TEXT NOT NULL,
        start_seconds REAL NOT NULL,
        end_seconds REAL NOT NULL,
        duration_seconds REAL NOT NULL,
        primary_subject TEXT NOT NULL,
        characters_present TEXT,
        character_expressions TEXT,
        visible_objects_props TEXT,
        spells_magic_actions TEXT,
        action_description TEXT NOT NULL,
        lore_context TEXT,
        location_setting TEXT,
        shot_scale TEXT,
        camera_motion TEXT,
        lighting_and_mood TEXT,
        search_tags TEXT,
        drive_file_id TEXT,
        drive_category TEXT,
        local_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Fast indexes for immediate sub-millisecond retrieval
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_subject ON franchise_clips(primary_subject);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_movie ON franchise_clips(movie_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_category ON franchise_clips(drive_category);")

    # Standalone FTS5 table
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS franchise_clips_fts USING fts5(
        clip_id UNINDEXED,
        primary_subject,
        characters_present,
        visible_objects_props,
        spells_magic_actions,
        action_description,
        lore_context,
        location_setting,
        search_tags
    );
    """)

    conn.commit()
    conn.close()
    logger.info(f"Initialized franchise visual vault database at: {db_path}")

def insert_or_update_clip(clip_data: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    """Inserts or updates a verified clip record in table and FTS index."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    chars = clip_data.get("characters_present", [])
    if isinstance(chars, list):
        chars_str = json.dumps(chars)
    else:
        chars_str = str(chars or "")

    objs = clip_data.get("visible_objects_props", [])
    if isinstance(objs, list):
        objs_str = json.dumps(objs)
    else:
        objs_str = str(objs or "")

    tags = clip_data.get("search_tags", [])
    if isinstance(tags, list):
        tags_str = " ".join(tags)
    else:
        tags_str = str(tags or "")

    clip_id = clip_data["clip_id"]

    expr = clip_data.get("character_expressions", "")
    if isinstance(expr, (list, dict)):
        expr_str = json.dumps(expr)
    else:
        expr_str = str(expr or "")

    spells = clip_data.get("spells_magic_actions", "")
    if isinstance(spells, (list, dict)):
        spells_str = json.dumps(spells)
    else:
        spells_str = str(spells or "")

    cur.execute("""
    INSERT OR REPLACE INTO franchise_clips (
        clip_id, movie_number, movie_title, start_seconds, end_seconds, duration_seconds,
        primary_subject, characters_present, character_expressions, visible_objects_props,
        spells_magic_actions, action_description, lore_context, location_setting,
        shot_scale, camera_motion, lighting_and_mood, search_tags, drive_file_id,
        drive_category, local_path
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        clip_id,
        clip_data.get("movie_number", 1),
        clip_data.get("movie_title", "Harry Potter"),
        clip_data["start_seconds"],
        clip_data["end_seconds"],
        clip_data.get("duration_seconds", round(clip_data["end_seconds"] - clip_data["start_seconds"], 2)),
        str(clip_data.get("primary_subject", "Unknown")),
        chars_str,
        expr_str,
        objs_str,
        spells_str,
        str(clip_data.get("action_description", "")),
        str(clip_data.get("lore_context", "")),
        str(clip_data.get("location_setting", "")),
        str(clip_data.get("shot_scale", "MEDIUM_SHOT")),
        str(clip_data.get("camera_motion", "STATIC")),
        str(clip_data.get("lighting_and_mood", "STANDARD")),
        tags_str,
        str(clip_data.get("drive_file_id", "")),
        str(clip_data.get("drive_category", "CHARACTERS")),
        str(clip_data.get("local_path", ""))
    ))

    # Update FTS
    cur.execute("DELETE FROM franchise_clips_fts WHERE clip_id = ?", (clip_id,))
    cur.execute("""
    INSERT INTO franchise_clips_fts (
        clip_id, primary_subject, characters_present, visible_objects_props,
        spells_magic_actions, action_description, lore_context, location_setting, search_tags
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        clip_id,
        str(clip_data.get("primary_subject", "")),
        chars_str,
        objs_str,
        spells_str,
        str(clip_data.get("action_description", "")),
        str(clip_data.get("lore_context", "")),
        str(clip_data.get("location_setting", "")),
        tags_str
    ))

    conn.commit()
    conn.close()

def search_clips(
    query_str: str,
    movie_number: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 10,
    db_path: Path = DB_PATH
) -> List[Dict[str, Any]]:
    """Performs lightning-fast FTS5 search across all metadata fields."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    words = [w.strip() for w in query_str.split() if w.strip()]
    if not words:
        return []

    # Clean FTS syntax
    clean_q = " ".join(f'"{w}"' for w in words)

    try:
        sql = """
        SELECT c.*, bm25(franchise_clips_fts) as rank
        FROM franchise_clips_fts fts
        JOIN franchise_clips c ON fts.clip_id = c.clip_id
        WHERE franchise_clips_fts MATCH ?
        """
        params = [clean_q]

        if movie_number:
            sql += " AND c.movie_number = ?"
            params.append(movie_number)

        if category:
            sql += " AND c.drive_category LIKE ?"
            params.append(f"%{category}%")

        sql += " ORDER BY rank ASC LIMIT ?"
        params.append(limit)

        cur.execute(sql, params)
        rows = cur.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results
    except Exception as e:
        logger.warning(f"FTS search error: {e}. Falling back to LIKE query...")
        # Fallback to standard SQL LIKE query
        like_sql = "SELECT * FROM franchise_clips WHERE (primary_subject LIKE ? OR action_description LIKE ? OR search_tags LIKE ?)"
        like_params = [f"%{words[0]}%", f"%{words[0]}%", f"%{words[0]}%"]
        cur.execute(like_sql, like_params)
        rows = cur.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results
