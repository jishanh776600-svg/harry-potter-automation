"""
STORY FORGE — Subtitle V2 Focused Test Suite
============================================
FOCUSED TESTS ONLY (Part 13: Tests 8 through 11):
  8. Two-word chunk -> PASS
  9. Three-word chunk -> PASS
  10. Four+ word standard chunk -> REJECT / split
  11. Word timestamps preserved -> PASS
"""

import pytest
from engines.edl.models import WordTimestamp
from engines.renderer.subtitle_renderer import (
    SubtitleChunkerV2,
    Phase5SubtitleRenderer,
    CANONICAL_FONT_NAME,
)


# ------------------------------------------------------------------------------
# TEST 8: Two-word chunk -> PASS
# ------------------------------------------------------------------------------
def test_08_two_word_chunk_passes():
    words = [
        WordTimestamp(word="Harry", start_sec=0.20, end_sec=0.55),
        WordTimestamp(word="grabs", start_sec=0.55, end_sec=0.90),
    ]
    # Validation check: 2-word chunk is valid
    assert SubtitleChunkerV2.validate_chunk(words) is True

    cues = SubtitleChunkerV2.chunk_words(words)
    assert len(cues) == 1
    cue_start, cue_end, text = cues[0]
    assert text == "Harry grabs"
    assert cue_start == 0.20
    assert cue_end == 0.90


# ------------------------------------------------------------------------------
# TEST 9: Three-word chunk -> PASS
# ------------------------------------------------------------------------------
def test_09_three_word_chunk_passes():
    words = [
        WordTimestamp(word="the", start_sec=0.95, end_sec=1.10),
        WordTimestamp(word="golden", start_sec=1.10, end_sec=1.45),
        WordTimestamp(word="snitch", start_sec=1.45, end_sec=1.85),
    ]
    # Validation check: 3-word chunk is valid
    assert SubtitleChunkerV2.validate_chunk(words) is True

    cues = SubtitleChunkerV2.chunk_words(words)
    assert len(cues) == 1
    cue_start, cue_end, text = cues[0]
    assert text == "the golden snitch"
    assert cue_start == 0.95
    assert cue_end == 1.85


# ------------------------------------------------------------------------------
# TEST 10: Four+ word standard chunk -> REJECT / split
# ------------------------------------------------------------------------------
def test_10_four_plus_word_chunk_rejected_and_split():
    words = [
        WordTimestamp(word="Harry", start_sec=0.0, end_sec=0.3),
        WordTimestamp(word="grabs", start_sec=0.3, end_sec=0.6),
        WordTimestamp(word="the", start_sec=0.6, end_sec=0.8),
        WordTimestamp(word="flying", start_sec=0.8, end_sec=1.2),
        WordTimestamp(word="broomstick", start_sec=1.2, end_sec=1.7),
        WordTimestamp(word="tightly", start_sec=1.7, end_sec=2.1),
    ]
    # Validation check: a single 6-word chunk must be rejected
    assert SubtitleChunkerV2.validate_chunk(words) is False

    # Chunker must automatically split into chunks of 2-3 words maximum
    cues = SubtitleChunkerV2.chunk_words(words, max_words_per_cue=3)
    assert len(cues) >= 2

    # Every resulting cue must be <= 3 words
    for cue_start, cue_end, text in cues:
        word_count = len(text.split())
        assert word_count <= 3, f"Cue '{text}' exceeded max 3 words (has {word_count})"
        assert word_count >= 1


# ------------------------------------------------------------------------------
# TEST 11: Word timestamps preserved -> PASS
# ------------------------------------------------------------------------------
def test_11_word_timestamps_strictly_preserved():
    words = [
        WordTimestamp(word="When", start_sec=1.234, end_sec=1.567),
        WordTimestamp(word="Harry", start_sec=1.567, end_sec=1.982),
        WordTimestamp(word="spoke", start_sec=2.100, end_sec=2.450),
    ]
    cues = SubtitleChunkerV2.chunk_words(words)
    assert len(cues) == 1
    cue_start, cue_end, text = cues[0]

    # Exact start matches first word, exact end matches last word
    assert cue_start == 1.234
    assert cue_end == 2.450
    assert text == "When Harry spoke"


# ------------------------------------------------------------------------------
# EXTRA: Typography Invariant Check (Canonical Harry P vs Banned Fonts)
# ------------------------------------------------------------------------------
def test_canonical_font_integrity():
    assert SubtitleChunkerV2.validate_font("Harry P") is True
    assert SubtitleChunkerV2.validate_font("Arial") is False
    assert SubtitleChunkerV2.validate_font("Arial Bold") is False
    assert SubtitleChunkerV2.validate_font("Arial Black") is False
    assert SubtitleChunkerV2.validate_font("generic") is False
    assert CANONICAL_FONT_NAME == "Harry P"
