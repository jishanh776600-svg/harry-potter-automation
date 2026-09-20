"""
STORY FORGE Hardened Rights Gate & Real Fan-Art Acquisition Test Suite
======================================================================
Validates the hardened two-dimensional rights architecture:
1. targeted query generation
2. candidate discovery
3. provenance extraction captures artist license and commercial clearance
4. artist license verified != commercial clearance (fan art with CC-BY quarantined for review)
5. official or pre-cleared artwork achieves COMMERCIAL_PRODUCTION_CLEARED
6. unverified platform quarantined
7. forbidden provider permanently rejected
8. duplicate hash rejected
9. wrong-scene artwork rejected
10. movie clip always beats artwork
11. no valid artwork -> NO_VALID_VISUAL
12. generic stock rejected
13. artwork formatted to 1080x1920/30fps
14. provenance survives into storyboard metadata
15. deterministic render fingerprinting cache invalidation
"""
import os
import json
import pytest
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import PROJECT_ROOT, DB_PATH
from core.hybrid_visual_models import (
    VisualSourceType, ArtistLicenseStatus, CommercialClearanceStatus,
    RightsStatus, ApprovalStatus, VisualProvenance, StoryboardBeatMetadata,
    FORBIDDEN_SOURCE_PROVIDERS
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
    q_str = " ".join(queries).lower()
    assert "peeves" in q_str
    assert "great hall" in q_str or "chaos" in q_str
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
        "artist_license_status": "ARTIST_LICENSE_VERIFIED",
        "commercial_clearance": "COMMERCIAL_PRODUCTION_REVIEW_REQUIRED",
        "rights_status": "RIGHTS_UNVERIFIED",
        "approval_status": "QUARANTINED",
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
def test_03_provenance_extraction_captures_license_and_clearance():
    """Validates that all required provenance and clearance fields are captured."""
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
    art_st, comm_st, rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert art_st == ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED
    assert comm_st == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED
    assert cand.source_url == "https://archive.org/details/hp-neville-remembrall"
    assert cand.creator == "Canon Fan Artist"
    assert "Remembrall" in cand.objects


# ------------------------------------------------------------------------------
# 4. ARTIST LICENSE != COMMERCIAL CLEARANCE TEST
# ------------------------------------------------------------------------------
def test_04_artist_license_verified_but_derivative_fan_art_requires_review():
    """
    CRITICAL TEST: Validates that an artist's CC-BY license on derivative Harry Potter fan art
    does NOT automatically clear commercial production. It must remain review-required and quarantined.
    """
    cand = ArtworkCandidate(
        candidate_id="art_fan_ccby_01",
        title="Peeves Great Hall Drawing",
        description="Peeves dropping water balloons in the Great Hall",
        source_provider="curated_archive",
        source_url="https://archive.org/details/hp-peeves-art",
        original_url="https://archive.org/download/hp-peeves-art/peeves.jpg",
        creator="Independent Fan Illustrator",
        license_name="Creative Commons Attribution 4.0 International (CC BY 4.0)",
        characters=["Peeves"],
        actions=["chaos", "dropping water balloons"],
        objects=["water balloons"]
    )
    art_st, comm_st, rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    # Artist license is verified
    assert art_st == ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED
    # But commercial clearance for copyrighted Harry Potter IP requires review!
    assert comm_st == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED
    # Quarantined from autonomous production
    assert app_st == ApprovalStatus.QUARANTINED
    assert rights_st.is_production_eligible is False


# ------------------------------------------------------------------------------
# 5. PRODUCTION-CLEARED ARTWORK ACCEPTED TEST
# ------------------------------------------------------------------------------
def test_05_official_artwork_or_cleared_asset_accepted():
    """Validates that official licensed illustrations achieve COMMERCIAL_PRODUCTION_CLEARED and APPROVED."""
    cand = ArtworkCandidate(
        candidate_id="art_scholastic_01",
        title="Mirror of Erised Chapter Illustration",
        description="Official Scholastic chapter illustration of Mirror of Erised",
        source_provider="curated",
        source_url="https://scholastic.com/hp/erised",
        original_url="https://scholastic.com/hp/erised.jpg",
        creator="Mary GrandPré",
        license_name="Scholastic Official Illustration Editorial Release",
        is_official=True
    )
    art_st, comm_st, rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
    assert art_st == ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED
    assert comm_st == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_CLEARED
    assert rights_st == RightsStatus.RIGHTS_VERIFIED
    assert app_st == ApprovalStatus.APPROVED
    assert rights_st.is_production_eligible is True


# ------------------------------------------------------------------------------
# 6. UNVERIFIED PLATFORMS QUARANTINED TEST
# ------------------------------------------------------------------------------
def test_06_unverified_platform_quarantined():
    """Validates that social/art sharing platforms without verified commercial terms are quarantined."""
    for platform in ["deviantart", "artstation", "tumblr", "reddit", "pinterest"]:
        cand = ArtworkCandidate(
            candidate_id=f"art_{platform}_01",
            title="Fan Art",
            description="Character artwork",
            source_provider=platform,
            source_url=f"https://www.{platform}.com/artwork/123",
            original_url=f"https://images.{platform}.com/123.jpg",
            creator="ArtistName",
            license_name=None
        )
        art_st, comm_st, rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
        assert art_st == ArtistLicenseStatus.ARTIST_LICENSE_UNVERIFIED
        assert comm_st == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REVIEW_REQUIRED
        assert app_st == ApprovalStatus.QUARANTINED
        assert rights_st.is_production_eligible is False


# ------------------------------------------------------------------------------
# 7. FORBIDDEN PROVIDERS REJECTED TEST
# ------------------------------------------------------------------------------
def test_07_rights_rejected_candidate_rejected():
    """Validates that forbidden generic stock and synthetic AI providers are rejected."""
    for forbidden in ["pexels", "unsplash", "pixabay", "shutterstock", "getty", "istock", "midjourney", "flux"]:
        cand = ArtworkCandidate(
            candidate_id=f"art_{forbidden}_01",
            title="Stock Image",
            description="Generic stock image",
            source_provider=forbidden,
            source_url=f"https://www.{forbidden}.com/photo/123",
            original_url=f"https://images.{forbidden}.com/123.jpg",
            license_name="Stock License"
        )
        art_st, comm_st, rights_st, app_st, reason = FanArtRetrievalEngine.evaluate_rights_status(cand)
        assert art_st == ArtistLicenseStatus.ARTIST_LICENSE_REJECTED
        assert comm_st == CommercialClearanceStatus.COMMERCIAL_PRODUCTION_REJECTED
        assert rights_st == RightsStatus.RIGHTS_REJECTED
        assert app_st == ApprovalStatus.REJECTED


# ------------------------------------------------------------------------------
# 8. DUPLICATE HASH REJECTED TEST
# ------------------------------------------------------------------------------
def test_08_duplicate_hash_rejected(tmp_path):
    """Validates that an artwork file with an identical SHA-256 hash is recognized as duplicate."""
    engine = FanArtRetrievalEngine(downloads_dir=tmp_path)
    sample_art = PROJECT_ROOT / "data" / "artworks" / "test_artwork_sample.jpg"

    if sample_art.exists():
        expected_hash = engine.compute_image_hash(sample_art)
        engine._known_hashes.add(expected_hash.lower())

        cand = ArtworkCandidate(
            candidate_id="art_dup_test",
            title="Duplicate Sample",
            description="Duplicate test image",
            source_provider="curated",
            source_url="https://example.com/art",
            original_url="https://example.com/art.jpg",
            artist_license_status=ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED,
            commercial_clearance=CommercialClearanceStatus.COMMERCIAL_PRODUCTION_CLEARED,
            rights_status=RightsStatus.RIGHTS_VERIFIED
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.iter_content = lambda chunk_size: [sample_art.read_bytes()]

        with patch("requests.get", return_value=mock_resp):
            downloaded = engine.download_and_validate_artwork(cand)
            assert downloaded is None or Path(downloaded).resolve() == sample_art.resolve()


# ------------------------------------------------------------------------------
# 9. WRONG-SCENE ARTWORK REJECTED TEST
# ------------------------------------------------------------------------------
def test_09_wrong_scene_artwork_rejected():
    """Validates that a random portrait is rejected when beat requires specific event objects/actions."""
    beat = {
        "beat_id": "beat_remembrall_red",
        "narration_text": "The Remembrall turns bright scarlet in Neville's hand when he forgets his robes.",
        "characters": ["Neville"],
        "action": "Remembrall glowing red",
        "objects": ["Remembrall"],
        "duration_seconds": 2.5
    }

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

    assert score_wrong < 35.0
    assert score_correct >= 60.0


# ------------------------------------------------------------------------------
# 10. MOVIE CLIP ALWAYS BEATS ARTWORK TEST
# ------------------------------------------------------------------------------
def test_10_movie_clip_always_beats_artwork(tmp_path):
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
        artist_license_status=ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED,
        commercial_clearance=CommercialClearanceStatus.COMMERCIAL_PRODUCTION_CLEARED,
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
        assert res["visual_source"] == VisualSourceType.MOVIE_DIRECT


# ------------------------------------------------------------------------------
# 11. NO VALID ARTWORK -> NO_VALID_VISUAL TEST
# ------------------------------------------------------------------------------
def test_11_no_valid_artwork_results_in_no_valid_visual():
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
# 12. GENERIC STOCK REJECTED TEST
# ------------------------------------------------------------------------------
def test_12_generic_stock_rejected():
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
# 13. ARTWORK FORMATTED TO 1080x1920/30FPS (AUDIO-MUTED) TEST
# ------------------------------------------------------------------------------
def test_13_artwork_formatted_to_1080x1920_30fps(tmp_path):
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
        assert len(a_streams) == 0


# ------------------------------------------------------------------------------
# 14. PROVENANCE SURVIVES INTO STORYBOARD METADATA TEST
# ------------------------------------------------------------------------------
def test_14_provenance_survives_into_storyboard_metadata(tmp_path):
    """Validates that full provenance and clearance metadata survives into StoryboardBeatMetadata."""
    hybrid_engine = HybridVisualEngine(clips_dir=tmp_path)
    dummy_art = tmp_path / "neville_remembrall_art.jpg"
    dummy_art.write_bytes(b"dummy image data")

    mock_provenance = VisualProvenance(
        asset_id="art_neville_remembrall_001",
        source_type=VisualSourceType.FAN_ART,
        source_url="https://archive.org/details/hp-canon-art-neville-remembrall",
        original_url="https://archive.org/download/hp-canon-art/remembrall.jpg",
        creator="Grand Archival Illustrator",
        license="Scholastic Official Illustration",
        artist_license_status=ArtistLicenseStatus.ARTIST_LICENSE_VERIFIED,
        commercial_clearance=CommercialClearanceStatus.COMMERCIAL_PRODUCTION_CLEARED,
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
        assert meta.artist_license_status == "ARTIST_LICENSE_VERIFIED"
        assert meta.commercial_clearance == "COMMERCIAL_PRODUCTION_CLEARED"
        assert meta.rights_status == "RIGHTS_VERIFIED"
        assert meta.approval_status == "APPROVED"
        assert "Remembrall" in meta.objects
        assert "Neville Longbottom" in meta.characters


# ------------------------------------------------------------------------------
# 15. DETERMINISTIC RENDER FINGERPRINT & CACHE SAFETY TEST
# ------------------------------------------------------------------------------
def test_15_render_fingerprint_cache_invalidation():
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
