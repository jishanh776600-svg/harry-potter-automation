import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engines.visual_source_router import VisualSourceRouter, SOURCE_MOVIE_CLIP

router = VisualSourceRouter()

# Test 1: Query that matches Movie 3
res1 = router.resolve(
    narration_sentence="Harry muttered the spell Lumos Maxima under his bedsheet.",
    visual_cue="Lumos Maxima"
)
print("=== TEST 1: Lumos Maxima ===")
print("Source Type:", res1.source_type)
print("Is Movie Clip:", res1.source_type == SOURCE_MOVIE_CLIP)
print("Movie Title:", res1.movie_title)
print("Timecodes:", res1.metadata.get("start_timecode"), "-->", res1.metadata.get("end_timecode"))
print("Scene Text:", res1.metadata.get("scene_text"))
print("Audio Muted Invariant:", res1.metadata.get("audio_muted"))

# Test 2: Query that matches Movie 2
res2 = router.resolve(
    narration_sentence="The house-elf warned Harry about the mortal danger awaiting him.",
    visual_cue="Dobby warning Harry"
)
print("\n=== TEST 2: Dobby warning Harry ===")
print("Source Type:", res2.source_type)
print("Is Movie Clip:", res2.source_type == SOURCE_MOVIE_CLIP)
print("Movie Title:", res2.movie_title)
print("Timecodes:", res2.metadata.get("start_timecode"), "-->", res2.metadata.get("end_timecode"))
print("Scene Text:", res2.metadata.get("scene_text"))

assert res1.source_type == SOURCE_MOVIE_CLIP, "Movie footage must be attempt #1!"
assert res2.source_type == SOURCE_MOVIE_CLIP, "Movie footage must be attempt #1!"
assert res1.metadata.get("audio_muted") is True, "Audio must be muted!"
print("\nALL VISUAL ROUTER TESTS PASSED: MOVIE FOOTAGE IS ATTEMPT #1!")
