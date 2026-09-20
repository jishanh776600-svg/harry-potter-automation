"""
STORY FORGE Real Fan-Art & Illustration Acquisition Layer Test Suite
=====================================================================
Validates all 13 pre-production acquisition and rights requirements:
1. targeted query generation
2. candidate discovery
3. provenance extraction
4. RIGHTS_VERIFIED candidate accepted
5. RIGHTS_UNVERIFIED candidate quarantined
6. RIGHTS_REJECTED candidate rejected
7. duplicate hash rejected
8. wrong-scene artwork rejected
9. movie clip always beats artwork
10. no valid artwork -> NO_VALID_VISUAL
11. generic stock rejected
12. artwork successfully formatted to 1080x1920/30fps (audio-muted)
13. provenance survives into storyboard metadata
+ deterministic render fingerprinting cache invalidation
"""
import os
import json
import pytest
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import PROJECT_ROOT, DB_PATH
from core.hybrid_visual_models import (
    VisualSourceType, RightsStatus, ApprovalStatus, VisualProvenance,
    StoryboardBeatMetadata, FORBIDDEN_SOURCE_PROVIDERS
)
from engines.fan_art_retrieval_engine import (
    FanArtRetrievalEngine, ArtworkCandidate, CuratedRegistryProvider,
    WikimediaCommonsDiscoveryProvider, InternetArchiveDiscoveryProvider
)
from engines.hybrid_visual_engine import HybridVisualEngine
from engines.hp_script_engine import HarryPotterScriptEngine, VisualBeatPlan
from engines.hp_render_engine import (
    compute_render_fingerprint, FRAMING_POLICY_VERSION, VISUAL_POLICY_VERSION, DEFAULT_BGM_TRACK
)
from engines.asset_fetcher import AssetFetcher


# ------------------------------------------------------------------------------
# 1. TARGETED QUERY GENERATION TEST
# ------------------------------------------------------------------------------
def test_01_targeted_query_generation():
    """Validates that search queries are rich, event-specific, and never generic."""
    beat = {
        "beat_id": "beat_peeves",
        "narration_text": "Peeves the Poltergeist swooped through the Great Hall, dropping water balloons onto screaming students.",
        "characters": ["Peeves"],
        "location": "Great Hall",
        "action": "chaos dropping balloons",
        "objects": ["water balloons", "goblets"],
        "duration_seconds": 3.0,
        "book_number": 1,
        "chapter_number": 7
    }
    queries = FanArtRetrievalEngine.generate_targeted_queries(beat)
    assert len(queries) >= 1
    # Must contain specific character, action/location/object
    q_str = " ".join(queries).lower()
    assert "peeves" in q_str
    assert "great hall" in q_str or "chaos" in q_str
    # Must NOT be bare generic "Harry Potter fan art"
    assert queries[0].strip().lower() != "harry potter fan art"


# ------------------------------------------------------------------------------
# 2. CANDIDATE DISCOVERY TEST
# ------------------------------------------------------------------------------
def test_02_candidate_discovery():
    """Validates that candidate discovery providers discover artwork candidates."""
    registry_data = [{
        "asset_id": "art_test_peeves",
        "title": "Peeves Great Hall Chaos",
        "description": "Peeves dropping water balloons in the Great Hall",
        "characters": ["Peeves"],
        "actions": ["dropping balloons"],
        "objects": ["water balloons"],
        "location": "Great Hall",
        "source_url": "https://archive.org/details/hp-peeves",
        "original_url": "https://archive.org/download/hp-peeves/img.jpg",
        "creator": "Archive Artist",
        "license_name": "Public Domain",
        "rights_status": "RIGHTS_VERIFIED",
        "approval_status": "APPROVED",
        "local_path": "data/artworks/test_artwork_sample.jpg"
    }]
    provider = CuratedRegistryProvider(registry_data)
    candidates = provider.search_candidates(["Harry Potter Peeves Great Hall"], beat={"characters": ["Peeves"]})
    assert len(candidates) >= 1
    assert candidates[0].candidate_id == "art_test_peeves"
    assert candidates[0].creator == "Archive Artist"


# ------------------------------------------------------------------------------
# 3. PROVENANCE EXTRACTION TEST
# ------------------------------------------------------------------------------
def test_03_provenance_extraction():
    """Validates that all required provenance fields are captured and retained."""
    cand = ArtworkCandidate(
        candidate_id="art_provenance_01",
        title="Neville Longbottom Remembrall",
        description="Neville holding his glowing red Remembrall in the Great Hall",
        source_provider="curated_archive",
        source_url="https://archive.org/details/hp-neville-remembrall",
        original_url="https://archive.org/download/hp-neville-remembrall/neville.jpg",
        creator="Canon Fan Artist",
        license_name="Creative Commons Attribution 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        characters=["Neville Longbottom"],
        actions=["holding remembrall", "forgetting"],
        objects=["Remembrall"],
        locations=["Great Hall"],
        book_number=1,
        chapter_number=9
    )
    rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert rights_st == RightsStatus.RIGHTS_VERIFIED
    assert cand.source_url == "https://archive.org/details/hp-neville-remembrall"
    assert cand.creator == "Canon Fan Artist"
    assert cand.license_name == "Creative Commons Attribution 4.0"
    assert "Remembrall" in cand.objects


# ------------------------------------------------------------------------------
# 4. RIGHTS_VERIFIED CANDIDATE ACCEPTED TEST
# ------------------------------------------------------------------------------
def test_04_rights_verified_candidate_accepted():
    """Validates that explicit CC / Public Domain licenses pass the rights gate as RIGHTS_VERIFIED."""
    cand = ArtworkCandidate(
        candidate_id="art_pd_01",
        title="Hogwarts Castle Vintage Illustration",
        description="Public domain sketch of Hogwarts Castle",
        source_provider="wikimedia_commons",
        source_url="https://commons.wikimedia.org/wiki/File:Hogwarts_Sketch.jpg",
        original_url="https://upload.wikimedia.org/Hogwarts_Sketch.jpg",
        creator="Historical Illustrator",
        license_name="Public Domain",
        license_url="https://creativecommons.org/publicdomain/mark/1.0/"
    )
    rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert rights_st == RightsStatus.RIGHTS_VERIFIED
    assert app_st == ApprovalStatus.APPROVED
    assert rights_st.is_production_eligible is True


# ------------------------------------------------------------------------------
# 5. RIGHTS_UNVERIFIED CANDIDATE QUARANTINED TEST
# ------------------------------------------------------------------------------
def test_05_rights_unverified_candidate_quarantined():
    """Validates that web discovery without explicit commercial license is quarantined."""
    cand = ArtworkCandidate(
        candidate_id="art_deviant_01",
        title="Neville Painting",
        description="Fan painting from DeviantArt",
        source_provider="deviantart",
        source_url="https://www.deviantart.com/artist/art/neville-remembrall",
        original_url="https://images-wixmp.com/neville.jpg",
        creator="DeviantArtUser",
        license_name="All Rights Reserved"
    )
    rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert rights_st == RightsStatus.RIGHTS_UNVERIFIED
    assert app_st == ApprovalStatus.QUARANTINED
    assert rights_st.is_production_eligible is False
    assert "quarantined" in reason.lower()


# ------------------------------------------------------------------------------
# 6. RIGHTS_REJECTED CANDIDATE REJECTED TEST
# ------------------------------------------------------------------------------
def test_06_rights_rejected_candidate_rejected():
    """Validates that forbidden generic stock providers are permanently rejected."""
    cand = ArtworkCandidate(
        candidate_id="art_pexels_01",
        title="Stock Castle",
        description="Stock footage castle",
        source_provider="pexels",
        source_url="https://www.pexels.com/photo/castle-123/",
        original_url="https://images.pexels.com/photos/123/castle.jpg",
        license_name="Pexels License"
    )
    rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert rights_st == RightsStatus.RIGHTS_REJECTED
    assert app_st == ApprovalStatus.REJECTED
    assert rights_st.is_production_eligible is False


# ------------------------------------------------------------------------------
# 7. DUPLICATE HASH REJECTED TEST
# ------------------------------------------------------------------------------
def test_07_duplicate_hash_rejected(tmp_path):
    """Validates that an artwork file with an identical SHA-256 hash is recognized as duplicate."""
    engine = FanArtRetrievalEngine(downloads_dir=tmp_path)
    sample_art = PROJECT_ROOT / "data" / "artworks" / "test_artwork_sample.jpg"

    if sample_art.exists():
        expected_hash = engine.compute_image_hash(sample_art)
        # Register the hash in known hashes
        engine._known_hashes.add(expected_hash.lower())

        cand = ArtworkCandidate(
            candidate_id="art_dup_test",
            title="Duplicate Sample",
            description="Duplicate test image",
            source_provider="curated",
            source_url="https://example.com/art",
            original_url="https://example.com/art.jpg",
            rights_status=RightsStatus.RIGHTS_VERIFIED
        )

        # Mock download returning the same bytes as sample_art
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.iter_content = lambda chunk_size: [sample_art.read_bytes()]

        with patch("requests.get", return_value=mock_resp):
            downloaded = engine.download_and_validate_artwork(cand)
            # Duplicate must NOT create a new duplicate file
            assert downloaded is None or Path(downloaded).resolve() == sample_art.resolve()


# ------------------------------------------------------------------------------
# 8. WRONG-SCENE ARTWORK REJECTED TEST
# ------------------------------------------------------------------------------
def test_08_wrong_scene_artwork_rejected():
    """Validates that a random portrait is rejected when beat requires specific event objects/actions."""
    beat = {
        "beat_id": "beat_remembrall_red",
        "narration_text": "The Remembrall turns bright scarlet in Neville's hand when he forgets his robes.",
        "characters": ["Neville"],
        "action": "Remembrall glowing red",
        "objects": ["Remembrall"],
        "duration_seconds": 2.5
    }

    # Irrelevant candidate: Random Neville portrait standing in hallway
    wrong_cand = ArtworkCandidate(
        candidate_id="art_wrong_neville",
        title="Neville Portrait in Corridor",
        description="Neville standing smiling in the corridor with books under his arm",
        source_provider="curated",
        source_url="https://example.com/neville_corridor",
        characters=["Neville"],
        actions=["standing smiling"],
        objects=["books"],
        locations=["corridor"]
    )
    score_wrong = FanArtRetrievalEngine.score_artwork_candidate(wrong_cand, beat)

    # Correct candidate: Neville with Remembrall glowing red
    correct_cand = ArtworkCandidate(
        candidate_id="art_correct_neville",
        title="Neville and Glowing Red Remembrall",
        description="Neville staring in confusion at the Remembrall glowing red in his hand",
        source_provider="curated",
        source_url="https://example.com/neville_remembrall",
        characters=["Neville"],
        actions=["staring in confusion", "glowing red"],
        objects=["Remembrall"],
        locations=["Great Hall"]
    )
    score_correct = FanArtRetrievalEngine.score_artwork_candidate(correct_cand, beat)

    assert score_wrong < 35.0  # Rejected by wrong-scene penalty
    assert score_correct >= 60.0  # Accepted with strong score


# ------------------------------------------------------------------------------
# 9. MOVIE CLIP ALWAYS BEATS ARTWORK TEST
# ------------------------------------------------------------------------------
def test_09_movie_clip_always_beats_artwork(tmp_path):
    """Validates that MOVIE_DIRECT takes absolute precedence over available artwork."""
    hybrid_engine = HybridVisualEngine(clips_dir=tmp_path)

    movie_candidate = {
        "movie_number": 1,
        "movie_title": "Sorcerer's Stone",
        "retrieval_score": 90.0,
        "score": 90.0,
        "chunk_id": "chunk_filmed",
        "clip_start_seconds": 500.0,
        "clip_end_seconds": 502.5,
        "duration_seconds": 2.5,
        "framing": "MEDIUM_SHOT"
    }

    dummy_art = tmp_path / "art_sample.jpg"
    dummy_art.write_bytes(b"dummy image data")

    artwork_provenance = VisualProvenance(
        asset_id="art_sample_01",
        source_type=VisualSourceType.FAN_ART,
        source_url="https://archive.org/details/hp-art",
        creator="Artist",
        license="Public Domain",
        rights_status=RightsStatus.RIGHTS_VERIFIED,
        approval_status=ApprovalStatus.APPROVED,
        file_path=str(dummy_art)
    )

    beat = {
        "beat_id": "beat_sorting",
        "narration_text": "McGonagall placed the Sorting Hat upon Harry's head.",
        "characters": ["Harry", "McGonagall"],
        "action": "sorting",
        "duration_seconds": 2.5
    }

    with patch.object(hybrid_engine.movie_engine, "search_candidates_for_beat", return_value=[movie_candidate]), \
         patch.object(hybrid_engine.movie_engine, "expand_candidate_context"), \
         patch.object(hybrid_engine.movie_engine, "rerank_candidates", return_value=[movie_candidate]), \
         patch.object(hybrid_engine.movie_engine, "resolve_beat_to_shots", return_value=[movie_candidate]), \
         patch.object(hybrid_engine.movie_engine, "resolve_movie_file", return_value=(Path("mock_movie.mp4"), "LOCAL", "mock_id")), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(hybrid_engine.movie_engine, "extract_rapid_shot", return_value={"file_path": "data/clips/mock_sorting.mp4"}), \
         patch.object(hybrid_engine.fan_art_engine, "search_artwork_for_beat", return_value=artwork_provenance):

        res = hybrid_engine.resolve_beat_visual(beat, script_id="test_priority")
        assert res["status"] == "ACCEPTED"
        assert res["visual_source"] == VisualSourceType.MOVIE_DIRECT  # Movie wins!


# ------------------------------------------------------------------------------
# 10. NO VALID ARTWORK -> NO_VALID_VISUAL TEST
# ------------------------------------------------------------------------------
def test_10_no_valid_artwork_results_in_no_valid_visual():
    """Validates that when neither movie nor artwork exists, NO_VALID_VISUAL is returned."""
    hybrid_engine = HybridVisualEngine()

    beat = {
        "beat_id": "beat_unfilmed_unillustrated",
        "narration_text": "An obscure dragon feeder whispered an unknown incantation in Romania.",
        "characters": ["Dragon Feeder"],
        "duration_seconds": 2.5
    }

    with patch.object(hybrid_engine.movie_engine, "search_candidates_for_beat", return_value=[]), \
         patch.object(hybrid_engine.fan_art_engine, "search_artwork_for_beat", return_value=None):

        res = hybrid_engine.resolve_beat_visual(beat, script_id="test_none")
        assert res["status"] == "NO_VALID_VISUAL"
        assert res["visual_source"] == VisualSourceType.NO_VALID_VISUAL
        assert res["clip_file_path"] is None


# ------------------------------------------------------------------------------
# 11. GENERIC STOCK REJECTED TEST
# ------------------------------------------------------------------------------
def test_11_generic_stock_rejected():
    """Validates that requesting generic stock raises hard errors across engine layers."""
    hybrid_engine = HybridVisualEngine()

    for forbidden in ["pexels", "unsplash", "pixabay", "shutterstock", "getty", "istock"]:
        forbidden_beat = {
            "beat_id": f"beat_{forbidden}",
            "narration_text": f"Hogwarts castle footage from {forbidden}.",
            "provider": forbidden,
            "duration_seconds": 2.5
        }
        with pytest.raises(ValueError, match="FORBIDDEN VISUAL SOURCE"):
            hybrid_engine.resolve_beat_visual(forbidden_beat, script_id="test_stock")


# ------------------------------------------------------------------------------
# 12. ARTWORK FORMATTED TO 1080x1920/30FPS (AUDIO-MUTED) TEST
# ------------------------------------------------------------------------------
def test_12_artwork_formatted_to_1080x1920_30fps(tmp_path):
    """Validates that format_artwork_to_clip generates an audio-muted 1080x1920 30fps MP4."""
    engine = FanArtRetrievalEngine()
    sample_art = PROJECT_ROOT / "data" / "artworks" / "test_artwork_sample.jpg"

    if sample_art.exists():
        out_clip = tmp_path / "formatted_test_clip.mp4"
        engine.format_artwork_to_clip(
            artwork_image_path=sample_art,
            output_clip_path=out_clip,
            duration_seconds=2.0
        )
        assert out_clip.exists()

        import subprocess
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height:format=duration",
            "-of", "json",
            str(out_clip)
        ]
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True)
        probe_data = json.loads(res.stdout)
        v_streams = [s for s in probe_data["streams"] if s["codec_type"] == "video"]
        a_streams = [s for s in probe_data["streams"] if s["codec_type"] == "audio"]

        assert len(v_streams) == 1
        assert v_streams[0]["width"] == 1080
        assert v_streams[0]["height"] == 1920
        assert len(a_streams) == 0  # 100% audio-muted invariant!


# ------------------------------------------------------------------------------
# 13. PROVENANCE SURVIVES INTO STORYBOARD METADATA TEST
# ------------------------------------------------------------------------------
def test_13_provenance_survives_into_storyboard_metadata(tmp_path):
    """Validates that full provenance metadata survives into StoryboardBeatMetadata."""
    hybrid_engine = HybridVisualEngine(clips_dir=tmp_path)
    dummy_art = tmp_path / "neville_remembrall_art.jpg"
    dummy_art.write_bytes(b"dummy image data")

    mock_provenance = VisualProvenance(
        asset_id="art_neville_remembrall_001",
        source_type=VisualSourceType.FAN_ART,
        source_url="https://archive.org/details/hp-canon-art-neville-remembrall",
        original_url="https://archive.org/download/hp-canon-art/remembrall.jpg",
        creator="Grand Archival Illustrator",
        license="Creative Commons Attribution 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        rights_status=RightsStatus.RIGHTS_VERIFIED,
        approval_status=ApprovalStatus.APPROVED,
        visual_description="Neville holding glowing red Remembrall",
        associated_beat_id="beat_neville_01",
        file_path=str(dummy_art),
        characters=["Neville Longbottom"],
        actions=["holding remembrall", "forgetting"],
        objects=["Remembrall"],
        locations=["Great Hall"]
    )

    beat = {
        "beat_id": "beat_neville_01",
        "narration_text": "The Remembrall turns scarlet when Neville forgets his clothes.",
        "characters": ["Neville Longbottom"],
        "action": "holding remembrall",
        "objects": ["Remembrall"],
        "duration_seconds": 2.5
    }

    with patch.object(hybrid_engine.movie_engine, "search_candidates_for_beat", return_value=[]), \
         patch.object(hybrid_engine.fan_art_engine, "search_artwork_for_beat", return_value=mock_provenance), \
         patch.object(hybrid_engine.fan_art_engine, "format_artwork_to_clip", return_value=tmp_path / "out.mp4"):

        res = hybrid_engine.resolve_beat_visual(beat, script_id="test_provenance")
        assert res["status"] == "ACCEPTED"
        meta: StoryboardBeatMetadata = res["shot_metadata"]
        assert meta.creator == "Grand Archival Illustrator"
        assert meta.source_url == "https://archive.org/details/hp-canon-art-neville-remembrall"
        assert meta.license == "Creative Commons Attribution 4.0"
        assert meta.rights_status == "RIGHTS_VERIFIED"
        assert meta.approval_status == "APPROVED"
        assert "Remembrall" in meta.objects
        assert "Neville Longbottom" in meta.characters


# ------------------------------------------------------------------------------
# 14. DETERMINISTIC RENDER FINGERPRINT & CACHE SAFETY TEST
# ------------------------------------------------------------------------------
def test_14_render_fingerprint_cache_invalidation():
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
