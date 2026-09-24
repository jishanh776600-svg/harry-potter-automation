"""
STORY FORGE — Acquisition Query Generator
==========================================
Translates fine-grained narrative beats and BeastVisualRequirement specifications
into prioritized multi-tier search queries optimized for media APIs and search providers.
"""

import re
from typing import Dict, List, Optional, Any
from core.acquisition_types import AssetAcquisitionRequest, MediaCategory


class AcquisitionQueryGenerator:
    """
    Synthesizes tiered queries from narrative requirements.
    """

    @classmethod
    def generate_queries(
        cls,
        request_or_req: Any,
        target_media: MediaCategory = MediaCategory.IMAGE
    ) -> List[str]:
        """
        Extracts entities, actions, and settings to build tiered search queries:
          Tier 1: [Primary Entity] + [Action / Secondary Entity]
          Tier 2: [Location / Environment] + [Era / Context]
          Tier 3: [Primary Entity / Thematic Subject]
        """
        # Extract fields depending on input object type
        primary_entity = getattr(request_or_req, "primary_subject", None) or getattr(request_or_req, "primary_entity", None)
        secondary_entity = getattr(request_or_req, "secondary_subject", None) or getattr(request_or_req, "secondary_entity", None)
        action = getattr(request_or_req, "required_action", None) or getattr(request_or_req, "action_descriptor", None)
        location = getattr(request_or_req, "required_location", None) or getattr(request_or_req, "location_descriptor", None)
        era = getattr(request_or_req, "narrative_era", None) or getattr(request_or_req, "era", None)
        objects = getattr(request_or_req, "required_objects", []) or []
        narration = getattr(request_or_req, "narration_text", None) or getattr(request_or_req, "query", "")

        queries: List[str] = []

        # 1. Tier 1: Exact Entity + Secondary / Action
        if primary_entity and secondary_entity:
            queries.append(cls._clean(f"{primary_entity} {secondary_entity}"))
        elif primary_entity and action:
            clean_action = cls._simplify_action(action)
            queries.append(cls._clean(f"{primary_entity} {clean_action}"))
        elif primary_entity and objects:
            queries.append(cls._clean(f"{primary_entity} {objects[0]}"))

        # 2. Tier 2: Entity + Location or Location + Action/Context
        if primary_entity and location:
            queries.append(cls._clean(f"{primary_entity} {location}"))
        elif location and objects:
            queries.append(cls._clean(f"{location} {objects[0]}"))
        elif location:
            queries.append(cls._clean(f"{location} Harry Potter Hogwarts"))

        # 3. Tier 3: Primary Entity alone or Thematic Narration Subject
        if primary_entity:
            queries.append(cls._clean(f"{primary_entity} Harry Potter"))

        # 4. Tier 4: Specific Objects & Props
        if objects:
            for obj in objects:
                clean_obj = cls._clean(obj)
                if clean_obj:
                    queries.append(clean_obj)
                    queries.append(cls._clean(f"{clean_obj} Harry Potter"))

        # 5. Tier 5: Split compound entities ("A and B") for high-precision individual searches
        if primary_entity and (" and " in primary_entity.lower() or " / " in primary_entity):
            parts = re.split(r"\s+(?:and|/)\s+", primary_entity, flags=re.IGNORECASE)
            for part in parts:
                clean_part = cls._clean(part.strip())
                if clean_part and len(clean_part) > 2:
                    queries.append(clean_part)
                    queries.append(cls._clean(f"{clean_part} Harry Potter"))

        # 6. Fallback from narration text if no specific entities
        if not queries and narration:
            extracted = cls._extract_key_phrases(narration)
            if extracted:
                queries.append(extracted)

        # Deduplicate while preserving priority order
        seen = set()
        unique_queries = []
        for q in queries:
            normalized = q.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_queries.append(q)

        return unique_queries or ["Harry Potter Hogwarts"]

    @staticmethod
    def _simplify_action(action: str) -> str:
        """Strips auxiliary verbs and simplifies complex action clauses."""
        words = re.sub(r"[^a-zA-Z0-9\s]", " ", action).split()
        stopwords = {"is", "are", "was", "were", "and", "or", "in", "the", "a", "an", "at", "to", "for"}
        filtered = [w for w in words if w.lower() not in stopwords]
        return " ".join(filtered[:3])

    @staticmethod
    def _clean(text: str) -> str:
        """Removes illegal query characters and collapses excess whitespace."""
        cleaned = re.sub(r"[^\w\s-]", " ", text)
        return " ".join(cleaned.split())

    @staticmethod
    def _extract_key_phrases(text: str) -> str:
        """Extracts prominent capitalized words and proper nouns from narration."""
        proper_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        if proper_nouns:
            return " ".join(proper_nouns[:3])
        # Fallback to first 4 meaningful words
        words = [w for w in text.split() if len(w) > 3]
        return " ".join(words[:4])
