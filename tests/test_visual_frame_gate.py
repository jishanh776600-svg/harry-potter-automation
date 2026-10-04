"""
Unit and Regression Tests for Visual Frame Gate & Character Shot Bank
=====================================================================
Ensures that no inanimate object cutaways, blackouts, or character-less
shots can bypass visual extraction and rendering gates.
"""

import pytest
import numpy as np
import cv2
from pathlib import Path
from core.visual_frame_gate import VisualFrameGate
from core.character_shot_bank import CHARACTER_SHOT_BANK, find_curated_character_shots


def test_visual_frame_gate_blackout_rejection(tmp_path):
    """Verifies that pitch-black or near-dark clips are strictly rejected."""
    gate = VisualFrameGate(min_brightness=20.0)

    # Create dummy dark video
    video_path = tmp_path / "dark_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (1080, 1920))
    for _ in range(30):
        dark_frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        out.write(dark_frame)
    out.release()

    is_ok, reason, stats = gate.verify_clip(video_path)
    assert not is_ok
    assert "REJECTED_FRAME_TOO_DARK" in reason
    assert stats["avg_brightness"] < 20.0


def test_visual_frame_gate_inanimate_rejection(tmp_path):
    """Verifies that bright inanimate objects (e.g. wall/curtain) without faces are rejected when character is required."""
    gate = VisualFrameGate()

    # Create dummy inanimate video (e.g. gray textured wall)
    video_path = tmp_path / "wall_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (1080, 1920))
    for _ in range(30):
        wall_frame = np.full((1920, 1080, 3), 120, dtype=np.uint8)
        out.write(wall_frame)
    out.release()

    is_ok, reason, stats = gate.verify_clip(video_path, required_characters=["Albus Dumbledore"])
    assert not is_ok
    assert "REJECTED_NO_CHARACTER_FACE" in reason
    assert stats["any_face_detected"] is False


def test_character_shot_bank_structure():
    """Verifies that CharacterShotBank contains valid, pre-curated entries."""
    assert "albus_dumbledore_privet_drive" in CHARACTER_SHOT_BANK
    assert "petunia_dursley_letters" in CHARACTER_SHOT_BANK
    assert "petunia_dursley_resentment" in CHARACTER_SHOT_BANK

    for key, shots in CHARACTER_SHOT_BANK.items():
        assert len(shots) >= 6
        for s in shots:
            assert s["movie_number"] == 1
            assert s["duration_seconds"] == 1.8
            assert s["end_seconds"] > s["start_seconds"]
            assert len(s["characters"]) > 0


def test_find_curated_character_shots():
    """Verifies query resolution against the CharacterShotBank."""
    dumbledore_shots = find_curated_character_shots(
        query_concept="Dumbledore placing protective letter doorstep",
        characters=["Albus Dumbledore"],
        count=6
    )
    assert dumbledore_shots is not None
    assert len(dumbledore_shots) == 6
    assert "Albus Dumbledore" in dumbledore_shots[0]["characters"]

    petunia_shots = find_curated_character_shots(
        query_concept="Petunia Dursley bitter resentment about Lily",
        characters=["Petunia Dursley"],
        count=6
    )
    assert petunia_shots is not None
    assert len(petunia_shots) == 6
    assert "Petunia Dursley" in petunia_shots[0]["characters"]
