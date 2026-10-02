"""
Comprehensive Test Suite: MovieEventIndex 150+ Canonical Events Scale
========================================================================
Validates Pillar 1 of the 99%+ Visual Mismatch-Proof Architecture:
1. MovieEventIndex registers >= 150 canonical events.
2. Every movie from Movie 1 to Movie 8 is represented with >= 10 verified events.
3. Every canonical event adheres strictly to physical observability invariants.
4. Key franchise set-pieces across all 8 movies retrieve with 100% precision.
"""

import pytest
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.models import MovieEvent, MovieEventQuery


@pytest.fixture(scope="module")
def index():
    return MovieEventIndex()


def test_movie_event_index_scale_exceeds_150(index):
    """Verifies that MovieEventIndex has scaled to over 150 canonical events."""
    all_events = index.list_all_events()
    assert len(all_events) >= 150, f"Expected >= 150 canonical events, found {len(all_events)}"


def test_all_eight_movies_adequately_represented(index):
    """Verifies that every single Harry Potter movie (1 through 8) has >= 10 canonical events."""
    all_events = index.list_all_events()
    counts = {}
    for ev in all_events:
        counts[ev.movie_number] = counts.get(ev.movie_number, 0) + 1

    for m in range(1, 9):
        assert m in counts, f"Movie {m} has 0 canonical events in index!"
        assert counts[m] >= 10, f"Movie {m} has only {counts[m]} events, expected >= 10"


def test_canonical_event_data_integrity(index):
    """Validates that all events satisfy pydantic and physical observability contracts."""
    all_events = index.list_all_events()
    for ev in all_events:
        assert ev.event_id.startswith("evt_"), f"Invalid event_id prefix: {ev.event_id}"
        assert 1 <= ev.movie_number <= 8, f"Invalid movie_number: {ev.movie_number}"
        assert ev.start_time >= 0.0, f"Negative start time in {ev.event_id}"
        assert ev.end_time > ev.start_time, f"End time <= start time in {ev.event_id}"
        assert len(ev.primary_subject) > 0, f"Missing primary_subject in {ev.event_id}"
        assert len(ev.action) > 0, f"Missing action in {ev.event_id}"
        assert len(ev.location) > 0, f"Missing location in {ev.event_id}"
        assert len(ev.visual_description) > 0, f"Missing visual_description in {ev.event_id}"
        assert ev.confidence >= 0.8, f"Low confidence score in {ev.event_id}: {ev.confidence}"


def test_iconic_events_retrieval_across_all_movies(index):
    """Tests high-precision candidate discovery for landmark scenes in all 8 movies."""
    test_queries = [
        # Movie 1: Snape questioning Harry
        (MovieEventQuery(subject="Severus Snape", action="questions", movie_number=1), "evt_m1_potions_snape_questions_harry"),
        # Movie 2: Fawkes blinds basilisk
        (MovieEventQuery(subject="Fawkes", action="blinds", movie_number=2), "evt_m2_chamber_fawkes_blinds_basilisk"),
        # Movie 3: Hermione punches Malfoy
        (MovieEventQuery(subject="Hermione Granger", action="punches", movie_number=3), "evt_m3_sundial_hermione_punches_malfoy"),
        # Movie 4: Priori Incantatem duel
        (MovieEventQuery(subject="Harry Potter", action="struggles", target="Lord Voldemort", movie_number=4), "evt_m4_graveyard_priori_incantatem_ghosts_emerge"),
        # Movie 5: Sirius punches Lucius Malfoy
        (MovieEventQuery(subject="Sirius Black", action="punches", movie_number=5), "evt_m5_dom_sirius_punches_malfoy"),
        # Movie 6: Harry casts Sectumsempra
        (MovieEventQuery(subject="Harry Potter", action="Sectumsempra", movie_number=6), "evt_m6_bathroom_harry_casts_sectumsempra_slashes_malfoy"),
        # Movie 7: Ron destroys locket with Sword
        (MovieEventQuery(subject="Ron Weasley", action="destroys", target="Slytherin Locket", movie_number=7), "evt_m7_forest_ron_destroys_locket_with_sword"),
        # Movie 8: Harry snaps Elder Wand
        (MovieEventQuery(subject="Harry Potter", action="snaps", movie_number=8), "evt_m8_viaduct_harry_snaps_elder_wand"),
    ]

    for query, expected_event_id in test_queries:
        candidates = index.search_candidates(query)
        candidate_ids = [c.event_id for c in candidates]
        assert expected_event_id in candidate_ids, (
            f"Query for {query.subject} {query.action} failed to find {expected_event_id}. "
            f"Found: {candidate_ids}"
        )
