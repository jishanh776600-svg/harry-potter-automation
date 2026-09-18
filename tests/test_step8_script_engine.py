"""
Unit Tests for Step 8: Harry Potter Script Generation & Visual Beat Engine.
================================================================================
Tests QA gate, word count bounds, spoken part numbering rejection,
movie-only visual constraints, and launch batch persistence.
"""

import unittest
import json
from engines.hp_script_engine import HarryPotterScriptEngine
from core.models import HarryPotterScript


class TestHarryPotterScriptEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = HarryPotterScriptEngine()

    def test_word_count_boundaries(self):
        """Scripts under 55 words or over 75 words must fail QA."""
        # 30 words (too short)
        short_text = "Harry Potter walked into the great hall. He saw many students eating. The candles floated high above the tables. Dumbledore smiled quietly."
        beats = [
            {"beat_id": "b1", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b2", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b3", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
        ]
        res_short = self.engine.evaluate_script_qa(short_text, beats)
        self.assertFalse(res_short.passed)
        self.assertTrue(any("TOO SHORT" in f for f in res_short.feedback))

        # 65 words (valid)
        valid_words = ["word"] * 65
        valid_text = " ".join(valid_words)
        res_valid = self.engine.evaluate_script_qa(valid_text, beats)
        self.assertTrue(res_valid.passed)
        self.assertEqual(res_valid.word_count, 65)

    def test_forbidden_spoken_part_patterns(self):
        """Any spoken part, chapter, or episode numbering must be rejected."""
        beats = [
            {"beat_id": "b1", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b2", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b3", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
        ]
        forbidden_samples = [
            "In part one of our story, Harry receives his Hogwarts letter from the fireplace.",
            "Welcome back to episode two where the snake escaped from the zoo cage.",
            "In this part we explore how Dumbledore left Harry on the doorstep.",
            "As we saw in chapter one, Vernon Dursley hated anything strange or unusual.",
        ]
        for sample in forbidden_samples:
            full_60_words = sample + " " + " ".join(["magic"] * (65 - len(sample.split())))
            res = self.engine.evaluate_script_qa(full_60_words, beats)
            self.assertFalse(res.passed, f"Failed to reject: {sample}")
            self.assertTrue(len(res.spoken_parts_detected) > 0)

    def test_forbidden_visual_sources_rejected(self):
        """Visual beats mentioning AI, stock, Pexels, or book screenshots must be rejected."""
        valid_text = " ".join(["magic"] * 65)
        bad_beats = [
            {"beat_id": "b1", "visual_requirement": "AI generated image of castle", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b2", "visual_requirement": "Stock footage of owl", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
            {"beat_id": "b3", "visual_requirement": "Pexels video clip", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
        ]
        res = self.engine.evaluate_script_qa(valid_text, bad_beats)
        self.assertFalse(res.passed)
        self.assertTrue(len(res.forbidden_visuals_detected) > 0)

    def test_launch_batch_persisted_and_retrievable(self):
        """All 4 launch batch scripts must exist in hp_scripts with APPROVED status."""
        with self.engine.Session() as session:
            scripts = session.query(HarryPotterScript).all()
            self.assertGreaterEqual(len(scripts), 4)
            for s in scripts:
                self.assertEqual(s.qa_status, "APPROVED")
                self.assertGreaterEqual(s.word_count, 55)
                self.assertLessEqual(s.word_count, 75)
                self.assertEqual(s.voice_id, "af_sarah")
                self.assertEqual(s.status, "READY_FOR_STEP_9")
                beats = json.loads(s.visual_beats_json)
                self.assertGreaterEqual(len(beats), 3)
                for b in beats:
                    self.assertEqual(b.get("visual_source_policy"), "MOVIE_FOOTAGE_ONLY")

    def test_batch2_persisted_and_distinct(self):
        """Batch 2 scripts (Shorts 5-8) must exist, have 2 novel + 2 discovery, and zero overlap with batch 1."""
        batch2_ids = [
            "hps_ns_b1c02_gc0020_0022",
            "hps_ns_b1c03_gc0029_0031",
            "hps_disc_mirror_of_erised_inscription_b1",
            "hps_disc_neville_remembrall_cloak_b1"
        ]
        with self.engine.Session() as session:
            b2_scripts = session.query(HarryPotterScript).filter(HarryPotterScript.id.in_(batch2_ids)).all()
            self.assertEqual(len(b2_scripts), 4)
            novel_count = sum(1 for s in b2_scripts if s.content_type == "novel_story")
            disc_count = sum(1 for s in b2_scripts if s.content_type == "discovery")
            self.assertEqual(novel_count, 2)
            self.assertEqual(disc_count, 2)

            for s in b2_scripts:
                self.assertEqual(s.qa_status, "APPROVED")
                self.assertGreaterEqual(s.word_count, 55)
                self.assertLessEqual(s.word_count, 75)
                # Verify zero spoken part numbering in narration
                for word in ["part one", "part two", "part three", "part four", "part five", "chapter one"]:
                    self.assertNotIn(word, s.full_text.lower())
                beats = json.loads(s.visual_beats_json)
                self.assertGreaterEqual(len(beats), 3)
                for b in beats:
                    self.assertEqual(b.get("visual_source_policy"), "MOVIE_FOOTAGE_ONLY")


if __name__ == "__main__":
    unittest.main()
