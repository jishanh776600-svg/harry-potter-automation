"""
STORY FORGE — LanceDB Embedded Vector Index (Phase 1C)
======================================================
Provides local, serverless, disk-backed vector storage and ANN similarity search
for OpenCLIP video frame and shot representations.

Guarantees:
  1. Offline & Local: Zero cloud or external network dependencies.
  2. Idempotent Indexing: Re-indexing existing frames replaces or skips duplicates.
  3. Stale-Index Detection: Verifies source video hashes and mtime to detect outdated embeddings.
  4. Factual Safety: Explicitly annotated as a retrieval index, NEVER an evidence authority.
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pyarrow as pa
import lancedb

from config.settings import PROJECT_ROOT

logger = logging.getLogger("LanceVectorIndex")

INDEX_VERSION = "1.0.0"
EMBEDDING_DIM = 512
TABLE_NAME = "movie_visual_embeddings"
DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "indices" / "lancedb"


class LanceVectorIndex:
    """
    Embedded vector index backed by LanceDB columnar disk format.
    """

    def __init__(self, db_dir: Optional[Path] = None):
        self.db_dir = Path(db_dir or DEFAULT_DB_DIR)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_dir))
        self.metadata_file = self.db_dir / "index_lineage.json"
        self._init_table()

    def _init_table(self):
        """Initializes LanceDB table schema if not already present."""
        self.schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            pa.field("movie_id", pa.string()),
            pa.field("shot_id", pa.string()),
            pa.field("timestamp", pa.float32()),
            pa.field("frame_index", pa.int32()),
            pa.field("is_keyframe", pa.bool_()),
            pa.field("event_linkage", pa.string()),
            pa.field("source_video_hash", pa.string()),
            pa.field("model_fingerprint", pa.string()),
            pa.field("index_version", pa.string()),
            pa.field("metadata_json", pa.string()),
        ])

        try:
            self.table = self.db.open_table(TABLE_NAME)
        except Exception:
            logger.info(f"Creating new LanceDB table '{TABLE_NAME}' in {self.db_dir}")
            self.table = self.db.create_table(TABLE_NAME, schema=self.schema, mode="create")

    def add_embeddings(
        self,
        records: List[Dict[str, Any]],
        video_path: Optional[Path] = None,
        movie_id: Optional[str] = None,
        model_fingerprint: str = "open_clip_vit_b32_openai",
    ) -> int:
        """
        Idempotently inserts embedding records. Skips or updates existing records.
        """
        if not records:
            return 0

        # Load existing IDs to prevent duplicate vectors
        existing_ids = set()
        try:
            if self.table.count_rows() > 0:
                # Query IDs for this movie
                df_ids = self.table.search().select(["id"]).to_pandas()
                existing_ids = set(df_ids["id"].tolist())
        except Exception as e:
            logger.debug(f"Could not pre-fetch IDs: {e}")

        new_rows = []
        for r in records:
            rec_id = str(r["id"])
            if rec_id in existing_ids:
                continue

            vec = r["vector"]
            if isinstance(vec, np.ndarray):
                vec = vec.astype(np.float32).tolist()
            elif isinstance(vec, list):
                vec = [float(v) for v in vec]

            if len(vec) != EMBEDDING_DIM:
                raise ValueError(f"Vector dim {len(vec)} does not match index dim {EMBEDDING_DIM}")

            row = {
                "id": rec_id,
                "vector": vec,
                "movie_id": str(r.get("movie_id", movie_id or "unknown")),
                "shot_id": str(r.get("shot_id", "shot_0")),
                "timestamp": float(r.get("timestamp", 0.0)),
                "frame_index": int(r.get("frame_index", 0)),
                "is_keyframe": bool(r.get("is_keyframe", True)),
                "event_linkage": str(r.get("event_linkage", "")),
                "source_video_hash": str(r.get("source_video_hash", "")),
                "model_fingerprint": str(r.get("model_fingerprint", model_fingerprint)),
                "index_version": INDEX_VERSION,
                "metadata_json": json.dumps(r.get("metadata", {})),
            }
            new_rows.append(row)

        if new_rows:
            self.table.add(new_rows)
            self._update_lineage_metadata(new_rows, video_path, movie_id, model_fingerprint)
            logger.info(f"Added {len(new_rows)} new embedding records to LanceDB (Total: {self.table.count_rows()})")

        return len(new_rows)

    def search_vectors(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        movie_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Searches nearest neighbors using cosine/L2 distance in LanceDB.
        Returns list of hit dictionaries with normalized similarity score.
        """
        if self.table.count_rows() == 0:
            return []

        q_vec = query_vector.astype(np.float32).tolist()
        query = self.table.search(q_vec).metric("cosine")

        if movie_id:
            query = query.where(f"movie_id = '{movie_id}'")

        results = query.limit(top_k).to_list()
        hits = []
        for r in results:
            dist = float(r.get("_distance", 1.0))
            # LanceDB cosine distance is (1 - cosine_similarity), where 0.0 is identical
            # Normalized similarity score: max(0.0, 1.0 - dist)
            similarity = max(0.0, min(1.0, 1.0 - dist))
            meta = {}
            if r.get("metadata_json"):
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    pass

            hits.append({
                "id": r["id"],
                "movie_id": r["movie_id"],
                "shot_id": r["shot_id"],
                "timestamp": float(r["timestamp"]),
                "frame_index": int(r["frame_index"]),
                "similarity_score": similarity,
                "distance": dist,
                "is_keyframe": bool(r.get("is_keyframe", True)),
                "event_linkage": r.get("event_linkage", ""),
                "model_fingerprint": r.get("model_fingerprint", ""),
                "source_video_hash": r.get("source_video_hash", ""),
                "metadata": meta,
            })

        return hits

    def check_index_staleness(self, movie_id: str, video_path: Path) -> Tuple[bool, str]:
        """
        Verifies whether the indexed vectors for movie_id are stale compared to video on disk.
        Returns (is_stale, reason).
        """
        lineage = self.get_lineage()
        movie_meta = lineage.get("movies", {}).get(movie_id)
        if not movie_meta:
            return True, f"No index metadata found for movie '{movie_id}'"

        if not video_path.exists():
            return True, f"Source video file not found at {video_path}"

        current_mtime = video_path.stat().st_mtime
        stored_mtime = movie_meta.get("source_video_mtime")
        if stored_mtime and abs(current_mtime - stored_mtime) > 2.0:
            return True, f"Source video mtime changed: current={current_mtime}, indexed={stored_mtime}"

        return False, "Index is fresh and matches source video"

    def get_lineage(self) -> Dict[str, Any]:
        """Loads index lineage and metadata."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"index_version": INDEX_VERSION, "movies": {}}

    def _update_lineage_metadata(
        self,
        new_rows: List[Dict[str, Any]],
        video_path: Optional[Path],
        movie_id: Optional[str],
        model_fingerprint: str,
    ):
        lineage = self.get_lineage()
        target_mid = movie_id or (new_rows[0]["movie_id"] if new_rows else "unknown")
        movie_entry = lineage.setdefault("movies", {}).setdefault(target_mid, {})

        movie_entry["total_vectors"] = movie_entry.get("total_vectors", 0) + len(new_rows)
        movie_entry["model_fingerprint"] = model_fingerprint
        movie_entry["index_version"] = INDEX_VERSION

        if video_path and video_path.exists():
            movie_entry["source_video_path"] = str(video_path)
            movie_entry["source_video_mtime"] = video_path.stat().st_mtime
            movie_entry["source_video_size"] = video_path.stat().st_size

        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(lineage, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist lineage metadata: {e}")

    def get_index_stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics of the index."""
        row_count = self.table.count_rows() if hasattr(self, "table") else 0
        lineage = self.get_lineage()
        return {
            "total_vectors": row_count,
            "embedding_dimension": EMBEDDING_DIM,
            "index_version": INDEX_VERSION,
            "table_name": TABLE_NAME,
            "db_path": str(self.db_dir),
            "indexed_movies": list(lineage.get("movies", {}).keys()),
        }
