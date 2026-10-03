"""
STORY FORGE — Visual Concept Expansion Engine (Part 5)
======================================================
Expands a narrative visual beat into a rich, structured set of deterministic
search queries and hypotheses across physical entities, actions, and states.
"""

from typing import List, Dict, Any, Optional
import logging

from engines.edl.models import VisualBeat

logger = logging.getLogger("VisualConceptExpander")

# Physical action synonyms and related state concepts
ACTION_SYNONYM_MAP: Dict[str, List[str]] = {
    "PUNCH": ["punching", "punched", "punch", "hitting", "strikes", "fist strike", "blow to face"],
    "HIT": ["strike", "hitting", "struck", "attack", "physical blow"],
    "KICK": ["kicking", "kicked", "foot strike", "sweep"],
    "HANDOVER": ["gives wand", "hands over", "transfer", "passing wand", "receives wand", "presents wand"],
    "THROW": ["throwing", "throws", "tossed", "tossing", "hurls", "cast into distance"],
    "CATCH": ["catching", "catches", "intercepts", "snatches from air"],
    "BREAK": ["snapping", "snaps", "broke", "shattered", "fractured", "broken in half", "pieces"],
    "SNAP": ["snapping", "breaks wand", "fracture", "split into two", "broken wand"],
    "STRIKE_WITH_OBJECT": ["swings sword", "slashes", "beheading", "sword strike", "decapitates"],
    "DRAW": ["draws wand", "unsheathes", "pulls weapon", "whips out wand"],
    "GRAB": ["grabs", "seizes", "snatches", "takes hold"],
    "FALL": ["falls down", "collapses", "drops to ground", "knocked down"],
    "RUN": ["running", "flees", "sprints", "escapes"],
}

# Object state related descriptions
OBJECT_STATE_MAP: Dict[str, List[str]] = {
    "elder_wand": ["Elder Wand", "Deathstick", "Dumbledore's wand", "broken wand", "snapped wand pieces"],
    "wand": ["wand", "magical wand", "wood wand", "wand box"],
    "sword of gryffindor": ["Sword of Gryffindor", "silver sword", "goblin-made blade", "ruby hilt sword"],
    "sorting_hat": ["Sorting Hat", "brown patched hat", "pointed hat on head"],
    "remembrall": ["Remembrall", "glass sphere", "smoke turning red"],
    "golden_snitch": ["Golden Snitch", "snitch with wings", "flying snitch"],
}


class VisualConceptExpander:
    """
    Expands a VisualBeat into structured queries across multiple semantic and
    physical representations, ensuring silent and differently-worded scenes can be found.
    """

    def expand_beat(self, beat: VisualBeat) -> List[str]:
        queries: List[str] = []

        # 1. Exact text span and visual assertion
        if beat.text_span:
            queries.append(beat.text_span)
        if beat.visual_assertion and beat.visual_assertion != beat.text_span:
            queries.append(beat.visual_assertion)

        entities = beat.required_entities
        objects = beat.required_objects
        action = beat.required_action

        # 2. Character + Action combinations
        if entities and action:
            act_variants = ACTION_SYNONYM_MAP.get(action.upper(), [action.lower()])
            for ent in entities:
                for act in act_variants[:3]:
                    queries.append(f"{ent} {act}")

        # 3. Character + Character interactions (e.g. Hermione Draco)
        if len(entities) >= 2:
            queries.append(f"{entities[0]} and {entities[1]}")
            if action:
                queries.append(f"{entities[0]} {action.lower()} {entities[1]}")

        # 4. Character + Object + State combinations
        if entities and objects:
            for ent in entities:
                for obj in objects:
                    queries.append(f"{ent} with {obj}")
                    if action:
                        queries.append(f"{ent} {action.lower()} {obj}")

        # 5. Object + Physical State synonyms (e.g. broken wand, wand pieces)
        if objects:
            for obj in objects:
                queries.append(obj)
                obj_clean = obj.lower().replace(" ", "_")
                if obj_clean in OBJECT_STATE_MAP:
                    queries.extend(OBJECT_STATE_MAP[obj_clean][:3])
                if beat.required_state:
                    queries.append(f"{obj} {beat.required_state.lower()}")

        # 6. Silent Visual Event representations
        if action:
            act_variants = ACTION_SYNONYM_MAP.get(action.upper(), [])
            for act in act_variants[:2]:
                queries.append(f"close up {act}")

        # Deduplicate while preserving rank order
        seen = set()
        deduped: List[str] = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                deduped.append(q_clean)

        return deduped
