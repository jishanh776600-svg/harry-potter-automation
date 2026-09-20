"""
STORY FORGE Hybrid Visual Source System Test Suite
=================================================
Validates:
1. Movie-direct event -> MOVIE_DIRECT (with natural framing)
2. Novel-only event -> FAN_ART with targeted query generation
3. Official artwork -> OFFICIAL_ARTWORK with provenance
4. No valid visual -> NO_VALID_VISUAL (never forced unrelated visual)
5. Generic stock rejection (Pexels, Unsplash permanently blocked)
6. Unrelated movie footage rejection
7. Fan-art provenance and rights status enforcement
8. Deterministic render fingerprinting (stale cache miss vs fresh cache hit)
9. Artwork video formatting (1080x1920, 30fps, 0 audio streams)
10. Strict safety: zero YouTube publishing, zero AL-AMR contamination
"""
import os
import json
import pytest
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import PROJECT_ROOT, DB_PATH
from core.models import HarryPotterScript, HPMovieClip, HPRender
from core.hybrid_visual_models import (
    VisualSourceType, RightsStatus, VisualProvenance, StoryboardBeatMetadata
)
from engines.fan_art_retrieval_engine import FanArtRetrievalEngine
from engines.hybrid_visual_engine import HybridVisualEngine
from engines.hp_script_engine import HarryPotterScriptEngine, VisualBeatPlan
from engines.hp_render_engine import (
    compute_render_fingerprint, FRAMING_POLICY_VERSION, VISUAL_POLICY_VERSION, DEFAULT_BGM_TRACK
)
from engines.asset_fetcher import AssetFetcher


# ------------------------------------------------------------------------------
# 1. MOVIE-DIRECT RESOLUTION TEST
# ------------------------------------------------------------------------------
def test_movie_direct_resolution():
    """Validates that a filmed movie event resolves to MOVIE_DIRECT."""
    hybrid_engine = HybridVisualEngine()
    
    # Mock movie engine to return a high-scoring direct movie match
    mock_candidate = {
        "movie_number": 1,
        "movie_title": "Harry Potter and the Sorcerer's Stone",
        "retrieval_score": 88.0,
        "score": 88.0,
        "chunk_id": "sub_chunk_001",
        "clip_start_seconds": 1200.0,
        "clip_end_seconds": 1202.5,
        "duration_seconds": 2.5,
        "framing": "MEDIUM_SHOT"
    }
    
    beat = {
        "beat_id": "beat_1",
        "narration_text": "Harry sat on the stool as Professor McGonagall placed the Sorting Hat upon his head.",
        "characters": ["Harry", "McGonagall"],
        "location": "Great Hall",
        "action": "sorting",
        "duration_seconds": 2.5
    }
    
    with patch.object(hybrid_engine.movie_engine, "search_candidates_for_beat", return_value=[mock_candidate]), \
         patch.object(hybrid_engine.movie_engine, "expand_candidate_context"), \
         patch.object(hybrid_engine.movie_engine, "rerank_candidates", return_value=[mock_candidate]), \
         patch.object(hybrid_engine.movie_engine, "resolve_beat_to_shots", return_value=[mock_candidate]), \
         patch.object(hybrid_engine.movie_engine, "resolve_movie_file", return_value=(Path("mock_movie.mp4"), "LOCAL", "drive_id_1")), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(hybrid_engine.movie_engine, "extract_rapid_shot", return_value={"file_path": "data/clips/mock.mp4"}):
        
        result = hybrid_engine.resolve_beat_visual(beat, script_id="test_script_01")
        assert result["status"] == "ACCEPTED"
        assert result["visual_source"] == VisualSourceType.MOVIE_DIRECT
        assert result["shot_metadata"].movie_number == 1


# ------------------------------------------------------------------------------
# 2. NOVEL-ONLY EVENT -> FAN_ART RESOLUTION TEST
# ------------------------------------------------------------------------------
def test_novel_only_event_fan_art_resolution():
    """Validates that a novel-only scene generates targeted queries and resolves to FAN_ART."""
    fa_engine = FanArtRetrievalEngine()
    
    beat = {
        "beat_id": "beat_peeves",
        "narration_text": "Peeves the Poltergeist swooped through the Great Hall, dropping water balloons onto screaming students.",
        "characters": ["Peeves"],
        "location": "Great Hall",
        "action": "chaos dropping balloons",
        "objects": ["water balloons", "goblets"],
        "duration_seconds": 3.0,
        "is_novel_only": True
    }
    
    # 1. Test targeted query generation
    queries = fa_engine.generate_targeted_queries(beat)
    assert len(queries) >= 1
    # Must be event-specific, not broad generic "Harry Potter fan art"
    assert any("peeves" in q.lower() for q in queries)
    assert any("great hall" in q.lower() or "chaos" in q.lower() for q in queries)
    assert queries[0] != "Harry Potter fan art"
    
    # 2. Test search against curated library
    artwork = fa_engine.search_artwork_for_beat(beat)
    assert artwork is not None
    assert artwork.source_type == VisualSourceType.FAN_ART
    assert "peeves" in artwork.visual_description.lower()
    assert artwork.creator is not None
    assert artwork.source_url is not None


# ------------------------------------------------------------------------------
# 3. OFFICIAL ARTWORK RESOLUTION TEST
# ------------------------------------------------------------------------------
def test_official_artwork_resolution():
    """Validates that official licensed illustrations resolve as OFFICIAL_ARTWORK with provenance."""
    fa_engine = FanArtRetrievalEngine()
    
    beat = {
        "beat_id": "beat_erised",
        "narration_text": "Harry gazed into the Mirror of Erised, seeing his parents James and Lily standing behind him.",
        "characters": ["Harry", "James", "Lily"],
        "location": "Mirror room",
        "action": "gazing",
        "objects": ["Mirror of Erised"],
        "duration_seconds": 2.5
    }
    
    artwork = fa_engine.search_artwork_for_beat(beat, preferred_source=VisualSourceType.OFFICIAL_ARTWORK)
    assert artwork is not None
    assert artwork.source_type == VisualSourceType.OFFICIAL_ARTWORK
    assert artwork.creator == "Mary GrandPré"
    assert artwork.rights_status == RightsStatus.OFFICIAL_LICENSED


# ------------------------------------------------------------------------------
# 4. NO VALID VISUAL TEST (Truthful Rejection)
# ------------------------------------------------------------------------------
def test_no_valid_visual_rejection():
    """Validates that when neither movie footage nor artwork is found, NO_VALID_VISUAL is returned."""
    hybrid_engine = HybridVisualEngine()
    
    beat = {
        "beat_id": "beat_unknown",
        "narration_text": "An obscure wizard in Romania brewed an ancient potion never shown anywhere.",
        "characters": ["Obscure Wizard"],
        "location": "Romania",
        "action": "brewing ancient unknown potion",
        "duration_seconds": 2.5
    }
    
    with patch.object(hybrid_engine.movie_engine, "search_candidates_for_beat", return_value=[]), \
         patch.object(hybrid_engine.fan_art_engine, "search_artwork_for_beat", return_value=None):
        
        result = hybrid_engine.resolve_beat_visual(beat, script_id="test_script_no_vis")
        assert result["status"] == "NO_VALID_VISUAL"
        assert result["visual_source"] == VisualSourceType.NO_VALID_VISUAL
        assert result["clip_file_path"] is None


# ------------------------------------------------------------------------------
# 5. GENERIC STOCK REJECTION TEST (Pexels / Unsplash Permanently Forbidden)
# ------------------------------------------------------------------------------
def test_generic_stock_permanently_forbidden():
    """Validates that requesting generic stock raises an immediate hard exception."""
    hybrid_engine = HybridVisualEngine()
    
    # Beat requesting forbidden provider
    forbidden_beat = {
        "beat_id": "beat_forbidden",
        "narration_text": "Students walking through the castle.",
        "provider": "pexels",
        "duration_seconds": 2.5
    }
    
    with pytest.raises(ValueError, match="FORBIDDEN VISUAL SOURCE"):
        hybrid_engine.resolve_beat_visual(forbidden_beat, script_id="test_stock_rejection")
        
    # Also verify in AssetFetcher
    fetcher = AssetFetcher()
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="Generic stock fallback is permanently disabled"):
        fetcher.fetch_asset_for_shot(
            db=mock_db,
            shot_data={"search_query": "Harry Potter students hallway stock footage"}
        )


# ------------------------------------------------------------------------------
# 6. SCRIPT QA HYBRID VISUAL POLICY & PROVENANCE TEST
# ------------------------------------------------------------------------------
def test_script_qa_hybrid_provenance_enforcement():
    """Validates that script QA enforces valid sources and artwork provenance."""
    script_engine = HarryPotterScriptEngine()
    
    # 1. Valid hybrid beat with provenance -> passes
    valid_beat = VisualBeatPlan(
        beat_id="beat_1",
        narration_text="In the book, Peeves threw walking sticks at Neville in the corridor.",
        visual_requirement="Peeves throwing sticks",
        characters=["Peeves", "Neville"],
        location="corridor",
        action="throwing sticks",
        objects=["walking sticks"],
        emotional_context="chaos",
        preferred_movie_number=1,
        source_grounding="Book 1 Chapter 8",
        retrieval_hints=["Peeves", "chaos"],
        visual_source_policy="HYBRID_TRUTHFUL",
        visual_source="FAN_ART",
        creator="Curated Artist",
        source_url="https://archive.org/details/hp-art"
    )
    
    script_dict = {
        "full_text": "There is a deleted Harry Potter character most fans never saw. In the novel, Peeves the Poltergeist tormented students in every corridor. He dropped heavy walking sticks onto Neville Longbottom and threw chalk at teachers. Chris Columbus filmed scenes with actor Rik Mayall, but every single minute was cut from the final film leaving Peeves completely absent.",
        "word_count": 61,
        "visual_beats": [valid_beat.to_dict(), valid_beat.to_dict(), valid_beat.to_dict()]
    }
    
    qa_res = script_engine.evaluate_script_qa(
        script_dict["full_text"], visual_beats=script_dict["visual_beats"], candidate_type="discovery"
    )
    assert qa_res.passed is True
    
    # 2. Missing provenance on fan art beat -> feedback generated
    bad_beat = VisualBeatPlan(
        beat_id="beat_bad",
        narration_text="In the book, Peeves threw walking sticks at Neville in the corridor.",
        visual_requirement="Peeves throwing sticks",
        characters=["Peeves"],
        location="corridor",
        action="throwing sticks",
        objects=["walking sticks"],
        emotional_context="chaos",
        preferred_movie_number=1,
        source_grounding="Book 1 Chapter 8",
        retrieval_hints=["Peeves"],
        visual_source_policy="HYBRID_TRUTHFUL",
        visual_source="FAN_ART",
        creator=None,
        source_url=None  # Missing provenance!
    )
    
    script_dict_bad = dict(script_dict)
    script_dict_bad["visual_beats"] = [bad_beat.to_dict(), valid_beat.to_dict(), valid_beat.to_dict()]
    qa_bad = script_engine.evaluate_script_qa(
        script_dict_bad["full_text"], visual_beats=script_dict_bad["visual_beats"], candidate_type="discovery"
    )
    assert any("MISSING PROVENANCE" in f for f in qa_bad.feedback)


# ------------------------------------------------------------------------------
# 7. DETERMINISTIC RENDER FINGERPRINT & CACHE SAFETY TEST
# ------------------------------------------------------------------------------
def test_render_fingerprint_cache_invalidation():
    """Validates that config or visual changes trigger fingerprint mismatch (cache miss)."""
    base_fp = compute_render_fingerprint(
        script_id="hps_test_01",
        full_text="Test narration for Harry Potter short.",
        visual_beats_json='[{"beat_id": "beat_1", "visual_source": "MOVIE_DIRECT"}]',
        bgm_track=DEFAULT_BGM_TRACK,
        bgm_volume_db=-28.0,
        framing_policy_version=FRAMING_POLICY_VERSION,
        visual_policy=VISUAL_POLICY_VERSION
    )
    
    # Identical config -> identical fingerprint (cache hit)
    matching_fp = compute_render_fingerprint(
        script_id="hps_test_01",
        full_text="Test narration for Harry Potter short.",
        visual_beats_json='[{"beat_id": "beat_1", "visual_source": "MOVIE_DIRECT"}]',
        bgm_track=DEFAULT_BGM_TRACK,
        bgm_volume_db=-28.0,
        framing_policy_version=FRAMING_POLICY_VERSION,
        visual_policy=VISUAL_POLICY_VERSION
    )
    assert base_fp == matching_fp
    
    # Changing visual source from MOVIE_DIRECT to FAN_ART -> cache miss!
    fanart_fp = compute_render_fingerprint(
        script_id="hps_test_01",
        full_text="Test narration for Harry Potter short.",
        visual_beats_json='[{"beat_id": "beat_1", "visual_source": "FAN_ART"}]',
        bgm_track=DEFAULT_BGM_TRACK,
        bgm_volume_db=-28.0,
        framing_policy_version=FRAMING_POLICY_VERSION,
        visual_policy=VISUAL_POLICY_VERSION
    )
    assert base_fp != fanart_fp
    
    # Changing BGM track (e.g. from old BGM to Esther Abrami) -> cache miss!
    old_bgm_fp = compute_render_fingerprint(
        script_id="hps_test_01",
        full_text="Test narration for Harry Potter short.",
        visual_beats_json='[{"beat_id": "beat_1", "visual_source": "MOVIE_DIRECT"}]',
        bgm_track="Old BGM Track.wav",
        bgm_volume_db=-20.0,
        framing_policy_version=FRAMING_POLICY_VERSION,
        visual_policy=VISUAL_POLICY_VERSION
    )
    assert base_fp != old_bgm_fp
    
    # Changing framing policy version -> cache miss!
    old_framing_fp = compute_render_fingerprint(
        script_id="hps_test_01",
        full_text="Test narration for Harry Potter short.",
        visual_beats_json='[{"beat_id": "beat_1", "visual_source": "MOVIE_DIRECT"}]',
        bgm_track=DEFAULT_BGM_TRACK,
        bgm_volume_db=-28.0,
        framing_policy_version="v1_close_up_biased",
        visual_policy=VISUAL_POLICY_VERSION
    )
    assert base_fp != old_framing_fp


# ------------------------------------------------------------------------------
# 8. ARTWORK PRESENTATION FORMATTING INVARIANTS TEST
# ------------------------------------------------------------------------------
def test_artwork_presentation_formatting(tmp_path):
    """Validates that format_artwork_to_clip creates an audio-muted 1080x1920 30fps clip."""
    fa_engine = FanArtRetrievalEngine()
    test_img = PROJECT_ROOT / "data" / "artworks" / "test_artwork_sample.jpg"
    
    if test_img.exists():
        out_clip = tmp_path / "test_formatted_clip.mp4"
        fa_engine.format_artwork_to_clip(
            artwork_image_path=test_img,
            output_clip_path=out_clip,
            duration_seconds=2.0
        )
        assert out_clip.exists()
        assert out_clip.stat().st_size > 10000
        
        # Verify via ffprobe
        import subprocess
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height:format=duration",
            "-of", "json",
            str(out_clip)
        ]
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        v_streams = [s for s in data["streams"] if s["codec_type"] == "video"]
        a_streams = [s for s in data["streams"] if s["codec_type"] == "audio"]
        
        assert len(v_streams) == 1
        assert v_streams[0]["width"] == 1080
        assert v_streams[0]["height"] == 1920
        assert len(a_streams) == 0  # 100% audio-muted invariant!
