"""
STORY FORGE — Phase 5: Focused Test Suite
==========================================
Part 32 of the 34-part Phase 5 specification.

24 focused Phase 5 tests covering:
  - EDL Validation (tests 1–7)
  - Clip Extraction (tests 8–9)
  - Timeline Assembly & Anti-Loop (tests 10–13)
  - Subtitle Renderer (tests 14–17)
  - Audio Mixer (tests 18–20)
  - Phase5FinalRenderVerifier (tests 21–24)

Part 33: Critical negative validations — the verifier MUST FAIL on:
  - Historical Elder Wand bad centre crop
  - Historical Buckbeak bad crop
  - Repeated single-scene render
  - Wrong character render
  - Missing object render
  - Wrong subtitle font (Arial substitution)
  - Subtitle covering required action
  - Truncated narration
  - Incorrect true peak
  - Stale EDL render
  - Action hidden by crop
  - Repeated source clip

DO NOT RUN THE FULL TEST SUITE.
Run ONLY this file + directly affected Phase 4 regressions.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from engines.renderer.edl_validator import (
    EDLValidator,
    EDLValidationFailureCode,
    EDLValidationResult,
)
from engines.renderer.clip_extractor import ExactClipExtractor
from engines.renderer.timeline_assembler import TimelineAssembler
from engines.renderer.subtitle_renderer import (
    Phase5SubtitleRenderer,
    CANONICAL_FONT_NAME,
    _BANNED_FONTS,
)
from engines.renderer.audio_mixer import (
    Phase5AudioMixer,
    CANONICAL_BGM_FILENAME,
    CANONICAL_BGM_WAV_FILENAME,
    CANONICAL_BGM_SHA256,
)
from engines.renderer.final_render_verifier_phase5 import (
    Phase5FinalRenderVerifier,
    Phase5Verdict,
    Phase5RenderVerificationReport,
)
from engines.edl.models import (
    VisualEDL,
    EDLEntry,
    EDLLineage,
    AntiLoopAuditResult,
    CoverageState,
    CoverageRequirement,
    CropFeasibility,
    LockedNarrationInput,
    WordTimestamp,
    SentenceBoundary,
)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE FACTORIES
# ══════════════════════════════════════════════════════════════════════════════

def _make_word_timestamps(text: str = "Harry snapped the Elder Wand.", n_words: int = 6) -> List[WordTimestamp]:
    words = text.split()[:n_words]
    return [
        WordTimestamp(word=w, start_sec=i * 0.5, end_sec=(i + 1) * 0.5)
        for i, w in enumerate(words)
    ]


def _make_locked_narration(content_id: str = "test_001", text: str = "Harry snapped the Elder Wand.") -> LockedNarrationInput:
    words = _make_word_timestamps(text)
    total_dur = words[-1].end_sec if words else 3.0
    payload = (content_id + text + str(total_dur)).encode()
    narration_hash = hashlib.sha256(payload).hexdigest()
    script_hash = hashlib.sha256(content_id.encode()).hexdigest()
    return LockedNarrationInput(
        content_id=content_id,
        script_hash=script_hash,
        narration_hash=narration_hash,
        exact_narration_duration=total_dur,
        word_timestamps=words,
        sentence_boundaries=[
            SentenceBoundary(
                sentence_index=0,
                text=text,
                start_sec=words[0].start_sec,
                end_sec=words[-1].end_sec,
                word_start_idx=0,
                word_end_idx=len(words) - 1,
            )
        ],
        narration_text=text,
    )


def _make_edl_lineage(content_id: str = "test_001", narration_hash: str = "") -> EDLLineage:
    if not narration_hash:
        narration_hash = hashlib.sha256(content_id.encode()).hexdigest()
    edl_hash = hashlib.sha256((content_id + narration_hash).encode()).hexdigest()
    return EDLLineage(
        content_id=content_id,
        script_hash=hashlib.sha256(b"script").hexdigest(),
        narration_hash=narration_hash,
        beat_hash=hashlib.sha256(b"beat").hexdigest(),
        candidate_hash=hashlib.sha256(b"cand").hexdigest(),
        perception_hash=hashlib.sha256(b"perc").hexdigest(),
        evidence_hash=hashlib.sha256(b"evid").hexdigest(),
        crop_feasibility_hash=hashlib.sha256(b"crop").hexdigest(),
        arbitration_hash=hashlib.sha256(b"arb").hexdigest(),
        edl_hash=edl_hash,
    )


def _make_edl_entry(
    beat_id: str = "beat_01",
    movie_id: int = 7,
    start: float = 100.0,
    end: float = 105.0,
    nar_start: float = 0.0,
    nar_end: float = 2.5,
    coverage: CoverageState = CoverageState.VERIFIED_DIRECT,
    required_entities: Optional[List[str]] = None,
    source_video: str = "fake_movie.mkv",
) -> EDLEntry:
    return EDLEntry(
        beat_id=beat_id,
        narration_start=nar_start,
        narration_end=nar_end,
        source_movie_id=movie_id,
        source_video=source_video,
        source_clip_start=start,
        source_clip_end=end,
        evidence_id=f"ev_{beat_id}",
        evidence_class="VERIFIED_DIRECT",
        required_entities=required_entities or ["harry"],
        verified_entities=required_entities or ["harry"],
        confidence=0.85,
        evidence_hash=hashlib.sha256(beat_id.encode()).hexdigest(),
        lineage_hash=hashlib.sha256(beat_id.encode()).hexdigest(),
        coverage_state=coverage,
        crop_feasibility=CropFeasibility.FIT,
    )


def _make_complete_edl(
    content_id: str = "test_001",
    narration_hash: str = "",
    entries: Optional[List[EDLEntry]] = None,
    is_complete: bool = True,
) -> VisualEDL:
    lineage = _make_edl_lineage(content_id, narration_hash)
    if entries is None:
        entries = [
            _make_edl_entry("beat_01", nar_start=0.0, nar_end=2.5),
            _make_edl_entry("beat_02", nar_start=2.5, nar_end=5.0, start=200.0, end=205.0),
        ]
    return VisualEDL(
        edl_id=f"edl_{content_id}",
        content_id=content_id,
        total_narration_duration=5.0,
        directly_covered_duration=5.0,
        optional_duration=0.0,
        unfulfilled_duration=0.0,
        coverage_percentage=1.0,
        entries=entries,
        anti_loop_audit=AntiLoopAuditResult(
            passed=True,
            total_entries=len(entries or []),
            unique_footage_intervals=len(entries or []),
        ),
        diagnostics=[],
        lineage=lineage,
        is_complete=is_complete,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ── EDL VALIDATOR TESTS (tests 1–7) ──────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestEDLValidatorCompleteness:
    """Test 1 — EDL_INCOMPLETE: EDL with is_complete=False must fail."""

    def test_01_incomplete_edl_fails(self):
        edl = _make_complete_edl(is_complete=False)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.EDL_INCOMPLETE in result.failure_codes

    def test_01b_complete_edl_with_no_source_check_passes(self):
        edl = _make_complete_edl(is_complete=True)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert result.passed, f"Expected pass, got: {result.failure_details}"


class TestEDLValidatorLineage:
    """Test 2 — EDL_STALE: Invalid lineage hash must fail."""

    def test_02_stale_edl_hash_fails(self):
        edl = _make_complete_edl()
        # Corrupt the lineage hash
        edl.lineage.edl_hash = "short"  # Invalid (not 64 hex chars)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.EDL_STALE in result.failure_codes

    def test_02b_valid_lineage_passes(self):
        edl = _make_complete_edl()
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert result.passed, result.failure_details


class TestEDLValidatorNarrationHash:
    """Test 3 — NARRATION_MISMATCH: Wrong narration hash must fail."""

    def test_03_narration_hash_mismatch_fails(self):
        narration = _make_locked_narration()
        edl = _make_complete_edl(narration_hash=narration.narration_hash)
        wrong_hash = hashlib.sha256(b"wrong_tts").hexdigest()
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl, narration_hash=wrong_hash)
        assert not result.passed
        assert EDLValidationFailureCode.NARRATION_MISMATCH in result.failure_codes

    def test_03b_correct_narration_hash_passes(self):
        narration = _make_locked_narration()
        edl = _make_complete_edl(narration_hash=narration.narration_hash)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl, narration_hash=narration.narration_hash)
        assert result.passed, result.failure_details


class TestEDLValidatorIntervals:
    """Test 4 — INVALID_INTERVAL: Negative/zero clip intervals must fail."""

    def test_04_negative_clip_start_fails(self):
        entry = _make_edl_entry(start=-1.0, end=5.0)
        edl = _make_complete_edl(entries=[entry])
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.INVALID_INTERVAL in result.failure_codes

    def test_04b_zero_duration_clip_fails(self):
        entry = _make_edl_entry(start=5.0, end=5.0)  # zero duration
        edl = _make_complete_edl(entries=[entry])
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.INVALID_INTERVAL in result.failure_codes

    def test_04c_inverted_clip_fails(self):
        entry = _make_edl_entry(start=10.0, end=5.0)  # inverted
        edl = _make_complete_edl(entries=[entry])
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.INVALID_INTERVAL in result.failure_codes


class TestEDLValidatorUnfulfilled:
    """Test 5 — UNFULFILLED_DIRECT_BEAT: Unfulfilled beats must fail."""

    def test_05_unfulfilled_direct_beat_fails(self):
        entry = _make_edl_entry(coverage=CoverageState.UNFULFILLED)
        edl = _make_complete_edl(entries=[entry], is_complete=False)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        codes = result.failure_codes
        assert (
            EDLValidationFailureCode.UNFULFILLED_DIRECT_BEAT in codes
            or EDLValidationFailureCode.EDL_INCOMPLETE in codes
        )


class TestEDLValidatorSourceMissing:
    """Test 6 — SOURCE_MISSING: Missing source files must fail."""

    def test_06_missing_source_file_fails(self, tmp_path):
        entry = _make_edl_entry(source_video="nonexistent_movie.mkv")
        edl = _make_complete_edl(entries=[entry])
        validator = EDLValidator(movies_dir=tmp_path, require_source_files=True)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.SOURCE_MISSING in result.failure_codes

    def test_06b_source_found_passes(self, tmp_path):
        movie_file = tmp_path / "fake_movie.mkv"
        movie_file.write_bytes(b"\x00" * 100)  # dummy file
        entry = _make_edl_entry(source_video="fake_movie.mkv")
        edl = _make_complete_edl(entries=[entry])
        validator = EDLValidator(movies_dir=tmp_path, require_source_files=True)
        result = validator.validate(edl)
        assert result.passed, result.failure_details


class TestEDLValidatorLineageMismatch:
    """Test 7 — LINEAGE_MISMATCH: content_id mismatch between EDL and lineage."""

    def test_07_content_id_mismatch_fails(self):
        edl = _make_complete_edl(content_id="real_content")
        edl.content_id = "tampered_content"  # Introduce mismatch
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.LINEAGE_MISMATCH in result.failure_codes


# ══════════════════════════════════════════════════════════════════════════════
# ── CLIP EXTRACTOR TESTS (tests 8–9) ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestClipExtractor:
    """Tests 8–9: Clip extractor correctness and error handling."""

    def test_08_missing_source_returns_extraction_failed(self, tmp_path):
        """Test 8: Missing source file → extraction_ok=False, not an exception."""
        from engines.renderer.clip_extractor import ExactClipExtractor, ExtractedClip
        entry = _make_edl_entry(source_video="does_not_exist.mkv")
        extractor = ExactClipExtractor(movies_dir=tmp_path, scratch_dir=tmp_path)
        clip = extractor.extract_clip(entry, output_dir=tmp_path)
        assert not clip.extraction_ok
        assert clip.error is not None
        assert "not found" in clip.error.lower()

    def test_09_crop_filter_from_edl_centre_crop(self):
        """Test 9: build_crop_filter_from_edl produces valid 9:16 filter for HP 1920x800 source."""
        from engines.renderer.clip_extractor import ExactClipExtractor
        entry = _make_edl_entry()
        # No explicit crop_requirements — should use centre-crop fallback
        filt = ExactClipExtractor.build_crop_filter_from_edl(entry, src_w=1920, src_h=800)
        assert "crop=" in filt
        assert "scale=1080:1920" in filt
        assert "fps=30" in filt
        # Should NOT contain stream_loop
        assert "stream_loop" not in filt

    def test_09b_crop_filter_from_edl_explicit_window(self):
        """Test 9b: Explicit crop_requirements in EDL entry are used directly."""
        from engines.renderer.clip_extractor import ExactClipExtractor
        entry = _make_edl_entry()
        entry.crop_requirements = {"x": 450, "y": 0, "w": 450, "h": 800, "src_w": 1920, "src_h": 800}
        filt = ExactClipExtractor.build_crop_filter_from_edl(entry, src_w=1920, src_h=800)
        assert "crop=450:800:450:0" in filt
        assert "scale=1080:1920" in filt


# ══════════════════════════════════════════════════════════════════════════════
# ── TIMELINE ASSEMBLER TESTS (tests 10–13) ───────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestTimelineAssembler:
    """Tests 10–13: Timeline assembly, anti-loop, unfulfilled beats."""

    def test_10_unfulfilled_beat_blocks_assembly(self, tmp_path):
        """Test 10: UNFULFILLED coverage state must prevent assembly."""
        from engines.renderer.clip_extractor import ExtractedClip
        entry = _make_edl_entry(coverage=CoverageState.UNFULFILLED)
        edl = _make_complete_edl(entries=[entry], is_complete=False)

        # Give it a fake extracted clip (so that isn't the failure source)
        fake_clip = ExtractedClip(
            beat_id="beat_01",
            source_video="fake.mkv",
            source_start=100.0,
            source_end=105.0,
            output_path=tmp_path / "clip.mp4",
            duration=5.0,
            extraction_ok=True,
        )
        assembler = TimelineAssembler(scratch_dir=tmp_path)
        timeline = assembler.assemble(edl, [fake_clip], output_path=tmp_path / "out.mp4")
        assert not timeline.assembly_ok
        assert "INSUFFICIENT_EDL_COVERAGE" in (timeline.error or "") or "Unfulfilled" in (timeline.error or "")

    def test_11_repeated_source_interval_detected(self, tmp_path):
        """Test 11: Same source interval in two beats → anti-loop violation detected."""
        from engines.renderer.timeline_assembler import TimelineAssembler
        from engines.renderer.clip_extractor import ExtractedClip

        # Two entries with identical source interval (same movie, same timestamps)
        e1 = _make_edl_entry("beat_01", start=100.0, end=105.0, movie_id=7, nar_start=0.0, nar_end=2.5)
        e2 = _make_edl_entry("beat_02", start=100.0, end=105.0, movie_id=7, nar_start=2.5, nar_end=5.0)
        edl = _make_complete_edl(entries=[e1, e2])

        clip1 = ExtractedClip(beat_id="beat_01", source_video="m.mkv", source_start=100.0, source_end=105.0,
                               output_path=tmp_path / "c1.mp4", duration=5.0, extraction_ok=True)
        clip2 = ExtractedClip(beat_id="beat_02", source_video="m.mkv", source_start=100.0, source_end=105.0,
                               output_path=tmp_path / "c2.mp4", duration=5.0, extraction_ok=True)

        assembler = TimelineAssembler(scratch_dir=tmp_path)
        violations = assembler._detect_repeated_clips(edl, [clip1, clip2])
        assert len(violations) > 0
        assert any("REPEATED_SOURCE" in v for v in violations)

    def test_12_duplicate_sha256_clips_detected(self, tmp_path):
        """Test 12: Bitwise identical clips (same SHA256) across distinct beats are flagged."""
        from engines.renderer.timeline_assembler import TimelineAssembler
        from engines.renderer.clip_extractor import ExtractedClip

        shared_sha = "a" * 64
        e1 = _make_edl_entry("beat_01", start=100.0, end=105.0)
        e2 = _make_edl_entry("beat_02", start=200.0, end=205.0)
        edl = _make_complete_edl(entries=[e1, e2])

        clip1 = ExtractedClip(beat_id="beat_01", source_video="m.mkv", source_start=100.0, source_end=105.0,
                               output_path=tmp_path / "c1.mp4", duration=5.0, sha256=shared_sha, extraction_ok=True)
        clip2 = ExtractedClip(beat_id="beat_02", source_video="m.mkv", source_start=200.0, source_end=205.0,
                               output_path=tmp_path / "c2.mp4", duration=5.0, sha256=shared_sha, extraction_ok=True)

        assembler = TimelineAssembler(scratch_dir=tmp_path)
        violations = assembler._detect_repeated_clips(edl, [clip1, clip2])
        assert any("REPEATED_CLIP_SHA256" in v for v in violations)

    def test_13_failed_extraction_blocks_assembly(self, tmp_path):
        """Test 13: Any extraction_ok=False clip must prevent assembly."""
        from engines.renderer.clip_extractor import ExtractedClip

        e1 = _make_edl_entry("beat_01")
        edl = _make_complete_edl(entries=[e1])
        failed_clip = ExtractedClip(
            beat_id="beat_01", source_video="m.mkv", source_start=0.0, source_end=5.0,
            output_path=tmp_path / "c1.mp4", duration=5.0,
            extraction_ok=False, error="Source not found",
        )
        assembler = TimelineAssembler(scratch_dir=tmp_path)
        timeline = assembler.assemble(edl, [failed_clip], output_path=tmp_path / "out.mp4")
        assert not timeline.assembly_ok
        assert "failed extraction" in (timeline.error or "").lower()


# ══════════════════════════════════════════════════════════════════════════════
# ── SUBTITLE RENDERER TESTS (tests 14–17) ────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestSubtitleRenderer:
    """Tests 14–17: Canonical font, word timestamps, collision detection."""

    def test_14_canonical_font_is_harry_p(self, tmp_path):
        """Test 14: Generated ASS must use 'Harry P' font — not Arial."""
        renderer = Phase5SubtitleRenderer(output_dir=tmp_path)
        words = _make_word_timestamps()
        result = renderer.render("test_14", words, edl=None)
        assert result.render_ok
        ass_content = result.ass_path.read_text(encoding="utf-8")
        assert CANONICAL_FONT_NAME in ass_content
        # Must NOT contain any banned font
        for banned in _BANNED_FONTS:
            assert banned.lower() not in ass_content.lower(), \
                f"Banned font '{banned}' found in ASS file!"

    def test_15_word_timestamps_produce_correct_cue_count(self, tmp_path):
        """Test 15: Word-level cue grouping produces ≥1 cue from timestamps."""
        renderer = Phase5SubtitleRenderer(output_dir=tmp_path)
        # 12 words → at least 2 cues (max 7 words per cue)
        text = "Harry Potter bravely snapped the Elder Wand in two breaking its power forever"
        words = _make_word_timestamps(text=text, n_words=12)
        result = renderer.render("test_15", words, edl=None)
        assert result.render_ok
        assert result.cue_count >= 2

    def test_16_arial_font_audit_fails(self, tmp_path):
        """Test 16 (Part 33): audit_ass_font MUST FAIL on Arial — the previous substitution."""
        ass_path = tmp_path / "bad_font.ass"
        ass_content = (
            "[Script Info]\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
            "Style: Default,Arial Black,82\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        ass_path.write_text(ass_content, encoding="utf-8")
        passed, detail = Phase5SubtitleRenderer.audit_ass_font(ass_path)
        assert not passed, "Arial Black must be REJECTED — this was the historical failure!"
        assert "Arial" in (detail or "") or "banned" in (detail or "").lower() or "prohibited" in (detail or "").lower()

    def test_17_harry_p_font_audit_passes(self, tmp_path):
        """Test 17: audit_ass_font must PASS for canonical 'Harry P' font."""
        ass_path = tmp_path / "good_font.ass"
        ass_content = (
            "[Script Info]\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
            f"Style: HarryPStyle,{CANONICAL_FONT_NAME},82\n\n"
            "[Events]\n"
        )
        ass_path.write_text(ass_content, encoding="utf-8")
        passed, detail = Phase5SubtitleRenderer.audit_ass_font(ass_path)
        assert passed, f"Harry P font should pass audit. detail={detail}"


# ══════════════════════════════════════════════════════════════════════════════
# ── AUDIO MIXER TESTS (tests 18–20) ──────────────────────────────────════════
# ══════════════════════════════════════════════════════════════════════════════

class TestAudioMixer:
    """Tests 18–20: Narration hash, canonical BGM gate, banned BGM rejection."""

    def test_18_narration_hash_mismatch_fails(self, tmp_path):
        """Test 18 (Part 33): Mismatched narration hash MUST prevent mixing."""
        # Write a dummy narration file
        narr_path = tmp_path / "narration.wav"
        narr_path.write_bytes(b"RIFF" + b"\x00" * 100)

        # Expected hash differs from file hash
        wrong_hash = hashlib.sha256(b"completely different").hexdigest()

        mixer = Phase5AudioMixer(bgm_dir=tmp_path, scratch_dir=tmp_path)
        result = mixer.mix(
            narration_path=narr_path,
            locked_narration_hash=wrong_hash,
            total_video_duration=5.0,
            output_path=tmp_path / "out.aac",
        )
        assert not result.mix_ok
        assert result.narration_verification is not None
        assert not result.narration_verification.hash_matches
        assert "NARRATION_VERIFICATION_FAILED" in result.failure_codes

    def test_19_canonical_bgm_found(self, tmp_path):
        """Test 19: Canonical BGM located by filename (no Esther Abrami)."""
        # Place canonical BGM file
        bgm_path = tmp_path / CANONICAL_BGM_WAV_FILENAME
        bgm_path.write_bytes(b"\x00" * 200)
        mixer = Phase5AudioMixer(bgm_dir=tmp_path, scratch_dir=tmp_path)
        found, err = mixer._locate_canonical_bgm()
        assert found is not None, f"Should find canonical BGM. err={err}"
        assert err is None

    def test_20_esther_abrami_rejected(self, tmp_path):
        """Test 20 (Part 33): Esther Abrami file must be rejected as BGM."""
        # Place ONLY Esther Abrami (no canonical BGM)
        bad_bgm = tmp_path / "Esther Abrami - No.6 In My Dreams (1).mp3"
        bad_bgm.write_bytes(b"\x00" * 200)
        mixer = Phase5AudioMixer(bgm_dir=tmp_path, scratch_dir=tmp_path)
        found, err = mixer._locate_canonical_bgm()
        assert found is None
        assert err is not None
        assert "Esther Abrami" in err or "banned" in err.lower() or "CANONICAL_BGM_MISSING" in err

    def test_20b_missing_canonical_bgm_fails(self, tmp_path):
        """Test 20b: Empty BGM dir → CANONICAL_BGM_MISSING failure."""
        mixer = Phase5AudioMixer(bgm_dir=tmp_path, scratch_dir=tmp_path)
        found, err = mixer._locate_canonical_bgm()
        assert found is None
        assert "CANONICAL_BGM_MISSING" in (err or "")


# ══════════════════════════════════════════════════════════════════════════════
# ── PHASE5 FINAL RENDER VERIFIER TESTS (tests 21–24 + Part 33) ───────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestPhase5FinalRenderVerifier:
    """Tests 21–24: Independent pixel-level verifier behaviour."""

    def test_21_deterministic_grounder_rejected(self):
        """Test 21 (Part 17): DeterministicBenchmarkGrounder must be rejected."""
        try:
            from py_visual_evidence.grounding import DeterministicBenchmarkGrounder
            fake_grounder = DeterministicBenchmarkGrounder()
            with pytest.raises(ValueError, match="STRICTLY PROHIBITED"):
                Phase5FinalRenderVerifier(grounder=fake_grounder, allow_synthetic_grounding=False)
        except ImportError:
            pytest.skip("py_visual_evidence not installed")

    def test_21b_synthetic_grounder_allowed_for_tests(self):
        """Test 21b: allow_synthetic_grounding=True permits test usage."""
        try:
            from py_visual_evidence.grounding import DeterministicBenchmarkGrounder
            fake_grounder = DeterministicBenchmarkGrounder()
            verifier = Phase5FinalRenderVerifier(
                grounder=fake_grounder,
                allow_synthetic_grounding=True,
            )
            assert verifier.allow_synthetic_grounding is True
        except ImportError:
            pytest.skip("py_visual_evidence not installed")

    def test_22_missing_render_file_fails(self, tmp_path):
        """Test 22: Non-existent video path → FINAL_RENDER_FAIL, not exception."""
        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        narration = _make_locked_narration()
        edl = _make_complete_edl(narration_hash=narration.narration_hash)

        report = verifier.verify(
            video_path=tmp_path / "nonexistent.mp4",
            edl=edl,
            narration=narration,
        )
        assert report.verdict == Phase5Verdict.FINAL_RENDER_FAIL
        assert any("RENDER_FILE_MISSING" in f for f in report.failures_by_category.get("RENDERER_DEFECTS", []))

    def test_23_wrong_subtitle_font_fails(self, tmp_path):
        """Test 23 (Part 33): Wrong subtitle font → FINAL_RENDER_FAIL (SUBTITLE_DEFECTS)."""
        # Create a minimal ASS file with Arial Black (banned font)
        ass_path = tmp_path / "bad.ass"
        ass_path.write_text(
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial Black,82\n",
            encoding="utf-8",
        )
        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        sub_veri = verifier._verify_subtitles(ass_path)
        assert not sub_veri.passed
        assert sub_veri.banned_font_detected or not sub_veri.canonical_font_matched
        assert len(sub_veri.failure_codes) > 0

    def test_24_repetition_audit_detects_identical_frames(self, tmp_path):
        """Test 24 (Part 33): Repeated single-scene footage → repetition audit fails."""
        import cv2
        # Create two identical synthetic frames
        dummy_frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        dummy_frame[:] = (128, 64, 200)  # Distinctive colour

        from engines.renderer.final_render_verifier_phase5 import SampledFrame

        e1 = _make_edl_entry("beat_01", nar_start=0.0, nar_end=2.5)
        e2 = _make_edl_entry("beat_02", nar_start=2.5, nar_end=5.0, start=200.0, end=205.0)
        edl = _make_complete_edl(entries=[e1, e2])

        # Give both beats the SAME frame (simulates repeated clip)
        sf = SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=dummy_frame.copy())

        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        beat_frames = {
            "beat_01": [sf],
            "beat_02": [sf],  # Identical — loop!
        }
        audit = verifier._audit_repetition(edl, beat_frames)
        assert not audit.passed
        assert len(audit.repeated_beat_pairs) > 0
        assert any("PERCEPTUAL_REPETITION" in c for c in audit.failure_codes)


# ══════════════════════════════════════════════════════════════════════════════
# ── PART 33: HISTORICAL FAILURE REGRESSIONS ───────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

class TestPart33NegativeValidations:
    """
    Part 33: Critical negative validations.
    The verifier MUST FAIL on all historical failure modes.
    """

    def test_33a_wrong_subtitle_font_arial(self, tmp_path):
        """Part 33 #6: Wrong subtitle font → SUBTITLE_DEFECTS."""
        ass_path = tmp_path / "arial.ass"
        ass_path.write_text(
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,82\n",
            encoding="utf-8",
        )
        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        sub = verifier._verify_subtitles(ass_path)
        assert not sub.passed

    def test_33b_wrong_subtitle_font_arial_bold(self, tmp_path):
        """Part 33 #6: Arial Bold specifically must also be caught."""
        ass_path = tmp_path / "arial_bold.ass"
        ass_path.write_text(
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial Bold,82\n",
            encoding="utf-8",
        )
        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        sub = verifier._verify_subtitles(ass_path)
        assert not sub.passed, "Arial Bold must be REJECTED"

    def test_33c_truncated_narration_detected(self, tmp_path):
        """Part 33 #8: Truncated narration → TIMELINE_DEFECTS."""
        narration = _make_locked_narration()
        # narration.exact_narration_duration = 3.0 seconds
        # but simulated video is only 1.0 sec
        edl = _make_complete_edl(narration_hash=narration.narration_hash)

        report = Phase5RenderVerificationReport(
            video_path="fake.mp4",
            content_id="test",
            duration_sec=1.0,  # Much shorter than narration
        )
        verifier = Phase5FinalRenderVerifier(allow_synthetic_grounding=True)
        verifier._check_duration_coverage(report, narration, edl)
        assert not report.narration_duration_covered
        assert len(report.failures_by_category["TIMELINE_DEFECTS"]) > 0
        assert "NARRATION_TRUNCATED" in report.failures_by_category["TIMELINE_DEFECTS"][0]

    def test_33d_stale_edl_blocked_by_validator(self):
        """Part 33 #10: Stale EDL (invalid hash) → EDL_STALE failure code."""
        edl = _make_complete_edl()
        edl.lineage.edl_hash = "badhash"
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.EDL_STALE in result.failure_codes

    def test_33e_repeated_source_clip_detected(self, tmp_path):
        """Part 33 #12: Repeated source clip → anti-loop violation."""
        from engines.renderer.clip_extractor import ExtractedClip
        shared_sha = hashlib.sha256(b"same_video_content").hexdigest()

        e1 = _make_edl_entry("beat_01", start=50.0, end=55.0)
        e2 = _make_edl_entry("beat_02", start=50.0, end=55.0)  # Same interval = repeat
        edl = _make_complete_edl(entries=[e1, e2])

        c1 = ExtractedClip(beat_id="beat_01", source_video="hp7.mkv", source_start=50.0, source_end=55.0,
                           output_path=tmp_path / "c1.mp4", duration=5.0, sha256=shared_sha, extraction_ok=True)
        c2 = ExtractedClip(beat_id="beat_02", source_video="hp7.mkv", source_start=50.0, source_end=55.0,
                           output_path=tmp_path / "c2.mp4", duration=5.0, sha256=shared_sha, extraction_ok=True)

        assembler = TimelineAssembler(scratch_dir=tmp_path)
        violations = assembler._detect_repeated_clips(edl, [c1, c2])
        assert len(violations) > 0, "Repeated clip must generate violations"

    def test_33f_narration_hash_mismatch_blocks_render(self, tmp_path):
        """Part 33 #10 (via AudioMixer): Wrong narration hash blocks audio mixing."""
        narr_path = tmp_path / "narration.wav"
        narr_path.write_bytes(b"RIFF" + b"\x00" * 50)
        mixer = Phase5AudioMixer(bgm_dir=tmp_path, scratch_dir=tmp_path)
        fake_correct_hash = hashlib.sha256(b"real_tts_output").hexdigest()
        result = mixer.mix(
            narration_path=narr_path,
            locked_narration_hash=fake_correct_hash,
            total_video_duration=5.0,
            output_path=tmp_path / "out.aac",
        )
        assert not result.mix_ok
        assert not result.narration_verification.hash_matches

    def test_33g_edl_incomplete_blocks_validation(self):
        """Part 33 #10 (via EDLValidator): Incomplete EDL is blocked before rendering."""
        edl = _make_complete_edl(is_complete=False)
        edl.failure_reason = "Beat 'beat_01' has no verified footage."
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        assert EDLValidationFailureCode.EDL_INCOMPLETE in result.failure_codes

    def test_33h_unfulfilled_direct_beat_blocked(self):
        """Part 33 #10: UNFULFILLED beat rejects the EDL."""
        entry = _make_edl_entry(
            beat_id="unfulfilled_beat",
            coverage=CoverageState.UNFULFILLED,
        )
        edl = _make_complete_edl(entries=[entry], is_complete=False)
        validator = EDLValidator(require_source_files=False)
        result = validator.validate(edl)
        assert not result.passed
        codes = result.failure_codes
        assert any(
            c in codes
            for c in [
                EDLValidationFailureCode.UNFULFILLED_DIRECT_BEAT,
                EDLValidationFailureCode.EDL_INCOMPLETE,
            ]
        )
