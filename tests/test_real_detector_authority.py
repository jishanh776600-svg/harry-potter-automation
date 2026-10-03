"""
STORY FORGE — Real Detector Authority & Synthetic Grounding Guard Test Suite
============================================================================
Verifies that:
1. Real visual detector (OpenVocabularyGrounder) is the mandatory authority for real-footage evidence.
2. DeterministicBenchmarkGrounder cannot be silently injected into real-footage paths.
3. Case A: Harry Potter is physically detected on the right side of m8_elder_wand_snap.mp4 @ 1.0s
   (does not fabricate wand detection).
4. Case B: Draco Malfoy is physically absent from m3_buckbeak_slash_malfoy.mp4 @ 6.5s,
   causing assertions requiring Malfoy to fail closed (NO_REQUIRED_ENTITY).
5. Isolated benchmark unit tests can still run if they explicitly declare allow_synthetic_grounding=True.
"""

import pytest
from pathlib import Path

from engines.visual_evidence.storyforge_adapter import (
    StoryForgeVisualEvidenceAdapter,
    StoryForgeEvidenceResult,
)
from engines.movie_event.models import MovieEvent, VisualBeat
from py_visual_evidence.schema import (
    VisualAssertion,
    EntitySpec,
    BoundingBox,
    EvidenceVerdict,
)
from py_visual_evidence.engine import VideoEvidenceEngine
from py_visual_evidence.grounding import (
    DeterministicBenchmarkGrounder,
    OpenVocabularyGrounder,
)

BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")


def test_guard_rejects_synthetic_grounder_in_real_footage_mode():
    """Verify that passing DeterministicBenchmarkGrounder without allow_synthetic_grounding=True raises ValueError."""
    synthetic_grounder = DeterministicBenchmarkGrounder()
    with pytest.raises(ValueError, match="strictly prohibited for real-footage visual evidence"):
        StoryForgeVisualEvidenceAdapter(grounder=synthetic_grounder, allow_synthetic_grounding=False)

    synthetic_engine = VideoEvidenceEngine(grounder=synthetic_grounder)
    with pytest.raises(ValueError, match="strictly prohibited for real-footage visual evidence"):
        StoryForgeVisualEvidenceAdapter(engine=synthetic_engine, allow_synthetic_grounding=False)


def test_default_adapter_uses_real_detector():
    """Verify default StoryForgeVisualEvidenceAdapter initializes OpenVocabularyGrounder in real mode."""
    adapter = StoryForgeVisualEvidenceAdapter()
    assert adapter.allow_synthetic_grounding is False
    assert isinstance(adapter.grounder, OpenVocabularyGrounder)
    assert isinstance(adapter.engine.grounder, OpenVocabularyGrounder)


def test_benchmark_grounder_allowed_when_explicitly_flagged():
    """Verify that isolated unit tests can still use benchmark grounder when explicitly requested."""
    synthetic_grounder = DeterministicBenchmarkGrounder()
    adapter = StoryForgeVisualEvidenceAdapter(grounder=synthetic_grounder, allow_synthetic_grounding=True)
    assert adapter.allow_synthetic_grounding is True
    assert isinstance(adapter.grounder, DeterministicBenchmarkGrounder)


def test_case_a_real_detector_harry_potter_elder_wand():
    """
    CASE A: m8_elder_wand_snap.mp4 @ ~1.0s
    Real detector must find Harry Potter on the RIGHT side of the 2.42:1 cinemascope frame.
    Must NOT require wand or fabricate wand detection.
    """
    clip_path = BLIND_CLIPS_DIR / "m8_elder_wand_snap.mp4"
    assert clip_path.exists(), f"Source clip not found: {clip_path}"

    adapter = StoryForgeVisualEvidenceAdapter(allow_synthetic_grounding=False)
    assert isinstance(adapter.grounder, OpenVocabularyGrounder)

    # Assertion requiring Harry Potter (without requiring wand)
    as_harry = VisualAssertion(
        assertion_id="as_harry_real_detect",
        source_script_line="Harry Potter stands on the Hogwarts viaduct.",
        subject=EntitySpec(name="Harry Potter", role="subject", description="a person with glasses"),
        action="stands",
    )

    ev = MovieEvent(
        event_id="evt_m8_viaduct_harry_presence",
        movie_id="hp_movie_8",
        movie_number=8,
        scene_id="s_viaduct",
        start_time=0.8,
        end_time=2.2,
        primary_subject="Harry Potter",
        action="stands on viaduct",
        location="Hogwarts Viaduct Bridge",
        visual_description="Harry on the viaduct bridge.",
    )

    res: StoryForgeEvidenceResult = adapter.verify_candidate_event(
        event=ev,
        beat_or_prop=as_harry,
        override_video_path=clip_path,
    )

    assert res.is_verified is True, f"Real visual detection failed: {res.rejection_reason}"
    assert res.verdict == EvidenceVerdict.PASS.value
    assert res.detector_type == "REAL_DETECTOR"
    assert "Harry Potter" in res.detected_entities

    # Verify Harry was detected toward the RIGHT side (x > 0.50)
    cw = res.crop_evidence.get("crop_window", {})
    crop_x = cw.get("x", 0)
    # On 1280 wide video, right side starts at 640px; crop_x centered on Harry is > 550px
    assert crop_x > 500, f"Expected crop on right side, got crop_x={crop_x}"


def test_case_b_real_detector_buckbeak_malfoy_fails_closed():
    """
    CASE B: m3_buckbeak_slash_malfoy.mp4 @ ~6.5s
    Real detector detects Buckbeak on the LEFT, but Draco Malfoy is physically absent.
    Therefore any assertion requiring Malfoy as recipient must FAIL CLOSED (NO_REQUIRED_ENTITY).
    """
    clip_path = BLIND_CLIPS_DIR / "m3_buckbeak_slash_malfoy.mp4"
    assert clip_path.exists(), f"Source clip not found: {clip_path}"

    adapter = StoryForgeVisualEvidenceAdapter(allow_synthetic_grounding=False)
    assert isinstance(adapter.grounder, OpenVocabularyGrounder)

    # Assertion requiring Buckbeak (subject) and Draco Malfoy (recipient)
    as_buckbeak_strike = VisualAssertion(
        assertion_id="as_buckbeak_strike_real",
        source_script_line="Buckbeak strikes Draco Malfoy across the arm.",
        subject=EntitySpec(name="Buckbeak", role="subject", description="a creature with wings"),
        action="strikes",
        recipient=EntitySpec(name="Draco Malfoy", role="recipient", description="a blonde boy"),
    )

    ev = MovieEvent(
        event_id="evt_m3_paddock_buckbeak_strike",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s_paddock",
        start_time=5.8,
        end_time=7.5,
        primary_subject="Buckbeak",
        action="strikes Draco Malfoy",
        location="Paddock",
        visual_description="Buckbeak and Malfoy in paddock.",
    )

    res: StoryForgeEvidenceResult = adapter.verify_candidate_event(
        event=ev,
        beat_or_prop=as_buckbeak_strike,
        override_video_path=clip_path,
    )

    # Must FAIL CLOSED because Malfoy is absent in real pixels
    assert res.is_verified is False
    assert res.verdict == EvidenceVerdict.NO_REQUIRED_ENTITY.value
    assert "Draco Malfoy" in (res.rejection_reason or "")
    assert res.detector_type == "REAL_DETECTOR"
    # Buckbeak is detected on the left
    assert "Buckbeak" in res.detected_entities
    # Draco Malfoy must NOT be detected
    assert "Draco Malfoy" not in res.detected_entities
