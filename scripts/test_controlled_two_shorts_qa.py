import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.hp_script_engine import HarryPotterScriptEngine
from engines.discovery_narrative_engine import DiscoveryNarrativeEngine, DiscoveryEditorialModel

engine = HarryPotterScriptEngine()

# Test A: Discovery (Dueling Club / Parseltongue)
script_a = (
    "The movie completely changes why Harry's Dueling Club scene was so terrifying. "
    "In the film, when Malfoy summons a serpent, Harry appears to coldly command the snake. "
    "But in the novel, Harry was actually screaming in plain English: 'Leave him alone!' "
    "Because Parseltongue bypasses conscious awareness, Harry had no idea he was hissing. "
    "He thought he was being a hero, unaware that to everyone else, he sounded like a dark wizard."
)
beats_a = [
    {"beat_id": "b1", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
    {"beat_id": "b2", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
    {"beat_id": "b3", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
]
qa_a = engine.evaluate_script_qa(script_a, beats_a, candidate_type="discovery_short")
print("TEST A QA:", qa_a.passed, qa_a.score, qa_a.word_count, qa_a.estimated_duration_sec, qa_a.feedback)

# Test B: Novel Story (Ollivander's Wand Selection)
script_b = (
    "Inside the narrow, dusty shop of Mr. Ollivander, thousands of slender wand boxes were stacked from floor to ceiling. "
    "The pale old wandmaker stepped forward quietly and handed Harry a wand of beechwood. "
    "Harry gave it a nervous wave, but it instantly shattered a glass vase into tiny pieces! "
    "The second wand ripped through papers across the counter. "
    "Then Ollivander brought out an unusual wand made of holly and phoenix feather. "
    "The moment Harry took it, warm magic shot through his fingers. "
    "A sudden shower of bright golden sparks lit up the dark room like fireworks. "
    "Ollivander stared in quiet wonder, knowing the wand had chosen its wizard."
)
beats_b = [
    {"beat_id": "b1", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
    {"beat_id": "b2", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
    {"beat_id": "b3", "visual_source_policy": "MOVIE_FOOTAGE_ONLY", "visual_source": "MOVIE_DIRECT"},
]
qa_b = engine.evaluate_script_qa(script_b, beats_b, candidate_type="novel_story")
print("TEST B QA:", qa_b.passed, qa_b.score, qa_b.word_count, qa_b.estimated_duration_sec, qa_b.feedback)
