"""
STORY FORGE — Phase 1 Retrieval Foundation Test Suite
=====================================================
Focused verification of the 14 core capabilities required in Phase 1:
  1. RetrievalQuery schema
  2. Candidate schema
  3. FTS5 adapter
  4. MovieEvent adapter
  5. LanceDB indexing
  6. OpenCLIP embedding
  7. QD-DETR adapter
  8. Candidate fusion
  9. Candidate diversity
  10. Stale index detection
  11. Provenance preservation
  12. No synthetic grounding
  13. Real movie retrieval
  14. Negative retrieval cases
"""

import os
import sys
import pytest
from pathlib import Path
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engines.retrieval.models import (
    RetrievalQuery,
    RetrievalCandidate,
    IRetrievalStage,
)
from engines.retrieval.fts5_stage import L1FTS5DialogueStage
from engines.retrieval.movie_event_stage import L2MovieEventStage
from engines.retrieval.dense_retrieval_stage import L3OpenCLIPDenseStage
from engines.retrieval.temporal_qddetr_stage import L4QDDETRTemporalStage
from engines.retrieval.candidate_fusion import CandidateFusionEngine
from engines.retrieval.vector_index import LanceVectorIndex
from engines.retrieval.clip_encoder import OpenCLIPVisualEncoder
from engines.retrieval.cascade_engine import RetrievalCascadeEngine


# 1. RetrievalQuery schema test
def test_retrieval_query_schema():
    q = RetrievalQuery(
        assertion_id="test_assert_1",
        text_query="Harry casts patronus against dementor",
        required_subjects=["Harry Potter"],
        required_objects=["wand"],
        required_action="casts",
        required_target="dementor",
        required_location="Great Lake",
        preferred_movie_ids=["movie_3"],
    )
    assert q.assertion_id == "test_assert_1"
    prompt = q.build_dense_prompt()
    assert "Harry Potter" in prompt
    assert "wand" in prompt
    assert "casts" in prompt
    assert "Great Lake" in prompt


# 2. Candidate schema & hard invariant test
def test_candidate_schema_invariants():
    cand = RetrievalCandidate(
        candidate_id="cand_test_01",
        movie_id="movie_3",
        start=10.0,
        end=14.5,
        source="L3_OPENCLIP",
        retrieval_score=0.85,
        semantic_score=0.82,
        temporal_score=0.79,
        metadata={"shot_id": "shot_10"},
        retrieval_trace={"model": "vit_b_32"},
    )
    assert cand.duration == 4.5
    assert cand.midpoint == 12.25
    # HARD INVARIANT: is_verified must always default to False at retrieval
    assert cand.is_verified is False
    d = cand.to_dict()
    assert d["is_verified"] is False
    assert d["retrieval_score"] == 0.85


# 3. FTS5 adapter test
def test_fts5_stage_adapter():
    stage = L1FTS5DialogueStage()
    assert stage.stage_name == "L1_FTS5"
    q = RetrievalQuery(
        assertion_id="dialogue_test",
        text_query="Sorting Hat Gryffindor Slytherin",
        preferred_movie_ids=["movie_1"],
    )
    cands = stage.retrieve(q, top_k=3)
    assert isinstance(cands, list)
    for c in cands:
        assert c.source == "L1_FTS5"
        assert c.is_verified is False
        assert "stage" in c.retrieval_trace


# 4. MovieEvent adapter test
def test_movie_event_stage_adapter():
    stage = L2MovieEventStage()
    assert stage.stage_name == "L2_MOVIE_EVENT"
    q = RetrievalQuery(
        assertion_id="event_test",
        text_query="Hermione punches Malfoy",
        required_subjects=["Hermione Granger"],
        required_action="punches",
        required_target="Draco Malfoy",
        preferred_movie_ids=["movie_3"],
    )
    cands = stage.retrieve(q, top_k=3)
    assert isinstance(cands, list)
    for c in cands:
        assert c.source == "L2_MOVIE_EVENT"
        assert c.is_verified is False
        assert c.retrieval_score > 0.0


# 5. LanceDB indexing test (idempotency & vector storage)
def test_lancedb_vector_indexing(tmp_path):
    idx = LanceVectorIndex(db_dir=tmp_path / "lancedb_test")
    vec1 = np.random.randn(512).astype(np.float32)
    vec1 = vec1 / np.linalg.norm(vec1)

    records = [{
        "id": "test_rec_01",
        "vector": vec1,
        "movie_id": "movie_test",
        "shot_id": "shot_01",
        "timestamp": 5.0,
        "frame_index": 120,
    }]

    # First add
    added1 = idx.add_embeddings(records, movie_id="movie_test")
    assert added1 == 1

    # Idempotent second add (must skip duplicate id)
    added2 = idx.add_embeddings(records, movie_id="movie_test")
    assert added2 == 0

    # Search
    hits = idx.search_vectors(vec1, top_k=1)
    assert len(hits) == 1
    assert hits[0]["id"] == "test_rec_01"
    assert hits[0]["similarity_score"] > 0.99


# 6. OpenCLIP embedding test (offline, 512d, normalized)
def test_openclip_embedding_properties():
    enc = OpenCLIPVisualEncoder.get_instance()
    assert enc.fingerprint.startswith("open_clip_vit-b-32")
    t_vec = enc.encode_text("Harry Potter with glasses")
    assert isinstance(t_vec, np.ndarray)
    assert t_vec.shape == (512,)
    # Norm must be ~1.0
    norm = np.linalg.norm(t_vec)
    assert abs(norm - 1.0) < 1e-4


# 7. QD-DETR temporal adapter test
def test_qddetr_temporal_adapter():
    stage = L4QDDETRTemporalStage()
    assert stage.stage_name == "L4_QD_DETR"
    assert "qddetr" in stage.model_version
    q = RetrievalQuery(
        assertion_id="temporal_test",
        text_query="Harry snaps the Elder Wand",
        required_subjects=["Harry Potter"],
        preferred_movie_ids=["movie_8"],
    )
    cands = stage.retrieve(q, top_k=2)
    for c in cands:
        assert c.source == "L4_QD_DETR"
        assert c.is_verified is False
        assert "engine_mode" in c.retrieval_trace


# 8. Candidate fusion test (preserves individual scores & weighted score)
def test_candidate_fusion_engine():
    fusion = CandidateFusionEngine()
    c1 = RetrievalCandidate(
        candidate_id="c1",
        movie_id="movie_1",
        start=10.0,
        end=14.0,
        source="L1_FTS5",
        retrieval_score=0.70,
        metadata={"shot_id": "shot_a"},
        retrieval_trace={"info": "fts5_hit"},
    )
    c2 = RetrievalCandidate(
        candidate_id="c2",
        movie_id="movie_1",
        start=11.0,
        end=15.0,
        source="L3_OPENCLIP",
        retrieval_score=0.80,
        metadata={"shot_id": "shot_a"},
        retrieval_trace={"info": "clip_hit"},
    )

    stage_dict = {"L1_FTS5": [c1], "L3_OPENCLIP": [c2]}
    q = RetrievalQuery(assertion_id="q1", text_query="test query")
    fused = fusion.fuse_and_rank(stage_dict, q, top_k=3)
    assert len(fused) == 1
    top = fused[0]
    assert top.source == "FUSION"
    assert top.is_verified is False
    assert "source_scores" in top.metadata
    assert "L1_FTS5" in top.metadata["source_scores"]
    assert "L3_OPENCLIP" in top.metadata["source_scores"]


# 9. Candidate diversity test
def test_candidate_diversity_enforcement():
    fusion = CandidateFusionEngine(temporal_spacing_sec=4.0)
    # Create 3 candidates very close in time for same shot
    cands = [
        RetrievalCandidate(
            candidate_id=f"c_{i}",
            movie_id="movie_1",
            start=float(i),
            end=float(i + 2),
            source="L3_OPENCLIP",
            retrieval_score=0.80 - i * 0.05,
            metadata={"shot_id": "same_shot"},
        )
        for i in range(3)
    ]
    stage_dict = {"L3_OPENCLIP": cands}
    q = RetrievalQuery(assertion_id="div_test", text_query="test")
    fused = fusion.fuse_and_rank(stage_dict, q, top_k=5)
    # The overlapping frames for the same shot must be clustered, not returning 3 separate identical entries
    assert len(fused) == 1


# 10. Stale index detection test
def test_stale_index_detection(tmp_path):
    idx = LanceVectorIndex(db_dir=tmp_path / "stale_test_db")
    fake_video = tmp_path / "movie_test.mp4"
    fake_video.write_bytes(b"dummy video data 12345")

    records = [{
        "id": "rec_stale_01",
        "vector": np.zeros(512, dtype=np.float32),
        "movie_id": "movie_fake",
        "shot_id": "s1",
        "timestamp": 1.0,
    }]
    idx.add_embeddings(records, video_path=fake_video, movie_id="movie_fake")

    # Check fresh index
    is_stale, reason = idx.check_index_staleness("movie_fake", fake_video)
    assert is_stale is False

    # Simulate video file modification
    new_mtime = fake_video.stat().st_mtime + 50.0
    os.utime(fake_video, (new_mtime, new_mtime))
    is_stale_now, reason_now = idx.check_index_staleness("movie_fake", fake_video)
    assert is_stale_now is True
    assert "mtime changed" in reason_now


# 11. Provenance preservation test
def test_provenance_preservation():
    cascade = RetrievalCascadeEngine()
    q = RetrievalQuery(
        assertion_id="prov_test",
        text_query="Harry snaps Elder Wand",
        required_subjects=["Harry Potter"],
        preferred_movie_ids=["movie_8"],
    )
    cands = cascade.retrieve_candidates(q, top_k=2)
    assert len(cands) > 0
    top = cands[0]
    assert "cascade_total_ms" in top.retrieval_trace
    assert "stages_evaluated" in top.retrieval_trace


# 12. No synthetic grounding test
def test_no_synthetic_grounding_used():
    cascade = RetrievalCascadeEngine()
    # Confirm no SyntheticDetector, MockGrounder, or fake bounding boxes are used
    for name, stage in cascade.stages.items():
        assert not hasattr(stage, "synthetic_boxes")
        assert not hasattr(stage, "mock_detections")


# 13. Real movie retrieval test (Silent scene: Elder Wand snap)
def test_real_movie_silent_retrieval():
    cascade = RetrievalCascadeEngine()
    q = RetrievalQuery(
        assertion_id="real_elder_wand_snap",
        text_query="Harry snaps the Elder Wand in half on the stone bridge",
        required_subjects=["Harry Potter"],
        required_objects=["Elder Wand"],
        required_action="snaps",
        preferred_movie_ids=["movie_8"],
    )
    cands = cascade.retrieve_candidates(q, top_k=3)
    assert len(cands) > 0
    top = cands[0]
    # The Elder Wand snap is in the candidate pool
    assert top.is_verified is False
    assert top.retrieval_score >= 0.50
    # Must contain real footage shot_id or movie_8 candidate
    assert top.movie_id == "movie_8"


# 14. Negative retrieval cases test
def test_negative_retrieval_cases():
    cascade = RetrievalCascadeEngine()
    q_absurd = RetrievalQuery(
        assertion_id="neg_absurd",
        text_query="Spaceship landing on Mars with aliens",
        preferred_movie_ids=["movie_1"],
    )
    cands = cascade.stages["L1_FTS5"].retrieve(q_absurd, top_k=3)
    # Text search for completely unrelated terms must return 0 candidates
    assert len(cands) == 0
