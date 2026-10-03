"""
STORY FORGE — Benchmark Movie Footage LanceDB Indexer (Phase 1)
================================================================
Indexes real Harry Potter movie clips into the local LanceDB vector database.
Extracts multi-frame keyframe representations per shot to enable dense semantic
retrieval and temporal moment proposals.
"""

import os
import sys
import time
import hashlib
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np
from engines.retrieval.vector_index import LanceVectorIndex
from engines.retrieval.clip_encoder import OpenCLIPVisualEncoder

BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")


def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:16]


def index_all_benchmark_clips():
    print(f"Connecting to LanceDB in {PROJECT_ROOT / 'data' / 'indices' / 'lancedb'}...")
    index = LanceVectorIndex()
    encoder = OpenCLIPVisualEncoder.get_instance()

    clip_files = sorted(list(BLIND_CLIPS_DIR.glob("*.mp4")))
    print(f"Found {len(clip_files)} real movie clips to index.")

    total_indexed_frames = 0
    t0 = time.time()

    for clip_path in clip_files:
        if clip_path.stat().st_size < 1000:
            print(f"Skipping corrupt/tiny clip: {clip_path.name}")
            continue

        clip_name = clip_path.stem
        # Extract movie id from filename prefix (e.g. m8_elder_wand_snap -> movie_8)
        prefix = clip_name.split("_")[0]
        movie_num = prefix.replace("m", "") if prefix.startswith("m") else "1"
        movie_id = f"movie_{movie_num}"

        file_hash = compute_file_hash(clip_path)

        # Inspect clip duration and frame count
        cap = cv2.VideoCapture(str(clip_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if frame_count > 0 else 5.0
        cap.release()

        # Multi-frame sampling strategy:
        # Sample keyframes at 0.5s intervals or start, quarter, midpoint, three-quarter, end
        num_samples = max(3, min(8, int(duration * 1.5)))
        sample_timestamps = np.linspace(0.2, max(0.3, duration - 0.2), num_samples)

        extracted_frames = []
        cap = cv2.VideoCapture(str(clip_path))
        for ts in sample_timestamps:
            f_idx = int(round(ts * fps))
            if f_idx >= frame_count:
                f_idx = max(0, frame_count - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                extracted_frames.append((float(ts), f_idx, frame))
        cap.release()

        if not extracted_frames:
            print(f"Warning: No frames extracted from {clip_path.name}")
            continue

        # Encode frames in batch with OpenCLIP
        bgr_images = [f[2] for f in extracted_frames]
        embeddings = encoder.encode_batch_images(bgr_images)

        # Prepare records for LanceDB
        records = []
        for (ts, f_idx, _), emb in zip(extracted_frames, embeddings):
            rec_id = f"{clip_name}_f{f_idx}"
            records.append({
                "id": rec_id,
                "vector": emb,
                "movie_id": movie_id,
                "shot_id": clip_name,
                "timestamp": round(ts, 3),
                "frame_index": f_idx,
                "is_keyframe": True,
                "event_linkage": clip_name,
                "source_video_hash": file_hash,
                "model_fingerprint": encoder.fingerprint,
                "metadata": {
                    "clip_name": clip_name,
                    "clip_duration": round(duration, 2),
                    "fps": round(fps, 2),
                    "relative_pos": round(ts / max(1e-3, duration), 3),
                },
            })

        added = index.add_embeddings(
            records=records,
            video_path=clip_path,
            movie_id=movie_id,
            model_fingerprint=encoder.fingerprint,
        )
        total_indexed_frames += added
        print(f"Indexed {clip_path.name}: {added} keyframes (duration: {duration:.2f}s)")

    elapsed = time.time() - t0
    stats = index.get_index_stats()
    print("\n" + "=" * 60)
    print("LANCEDB INDEXING COMPLETE")
    print(f"Total Keyframes in Index: {stats['total_vectors']}")
    print(f"Indexed Movies: {stats['indexed_movies']}")
    print(f"Total Time: {elapsed:.2f}s ({elapsed/max(1, total_indexed_frames):.3f}s per frame)")
    print("=" * 60)


if __name__ == "__main__":
    index_all_benchmark_clips()
