# STORY FORGE — Canonical Movie Events Expanded Catalog
import json
import logging
from pathlib import Path
from typing import List
from config.settings import PROJECT_ROOT
from engines.movie_event.models import MovieEvent

logger = logging.getLogger("MovieEventCatalog")

EXPANDED_EVENTS_JSON_PATH = PROJECT_ROOT / "data" / "indices" / "expanded_canonical_events.json"


def load_expanded_canonical_events(json_path: Path = EXPANDED_EVENTS_JSON_PATH) -> List[MovieEvent]:
    """
    Loads all expanded canonical movie events and atmospheric establishing shots
    from the structured JSON catalog on disk.
    """
    if not json_path.exists():
        logger.warning(f"Expanded canonical events JSON not found at: {json_path}")
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        events: List[MovieEvent] = []
        for item in data:
            try:
                events.append(MovieEvent(**item))
            except Exception as e:
                logger.warning(f"Skipping malformed event {item.get('event_id', 'unknown')}: {e}")

        logger.info(f"Loaded {len(events)} expanded canonical events from {json_path}")
        return events
    except Exception as e:
        logger.error(f"Failed to load expanded canonical events from {json_path}: {e}")
        return []


# Cached in-memory list for quick access
EXPANDED_CANONICAL_EVENTS = load_expanded_canonical_events()
