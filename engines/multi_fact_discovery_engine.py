"""
STORY FORGE — Multi-Fact Discovery Engine V1
============================================
Rebuilds STORY FORGE's content architecture around Multi-Fact Discovery
as the DEFAULT format (5–7 thematically bound factual payloads in ~75s).

Key Mechanics:
  - 10-Point Multi-Fact Quality Gate
  - Multi-Dimensional Fact Scoring (Canon, Contrast, Curiosity, Feasibility, Coherence)
  - Token/Entity Jaccard Deduplication
  - Zero-Padding Invariant (Refuses to pad < 4 facts; routes to SINGLE_TOPIC_DEEP_DIVE)
  - Escalating Narrative Sequencer (Entry -> Deepening -> Surprise -> Emotion -> Climax)
  - Conversational Transition Synthesizer (Avoids monotonous robotic ordinals)
  - Dynamic Time & Word Budget Allocator (68–78s, ceiling 80.9s, 240–280 words, 3.4–3.7 wps)
  - Anti-Repetition Tracking
  - Novel Story 100% Isolated
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any, Set

from core.discovery_types import HookArchetype, TitlePattern
from core.multi_fact_types import (
    FactType,
    MultiFactFormat,
    MultiFactPayload,
    MultiFactTopicPack,
    RequiredEvidenceType,
    VisualProposition,
)

logger = logging.getLogger("MultiFactDiscoveryEngine")


class MultiFactDiscoveryEngine:
    """
    Orchestrates the selection, scoring, deduplication, narrative sequencing,
    and budget packaging for multi-fact YouTube Shorts.
    """

    def __init__(self, recent_history_limit: int = 50):
        self.recent_history_limit = recent_history_limit
        self._recent_themes: List[str] = []
        self._recent_fact_ids: Set[str] = set()
        self._recent_hooks: List[str] = []

    # ==========================================================================
    # 1. MULTI-DIMENSIONAL FACT SCORING
    # ==========================================================================

    @classmethod
    def score_fact(
        cls,
        fact: MultiFactPayload,
        theme: str,
        coherence_weight: float = 0.20
    ) -> float:
        """
        Calculates a holistic 0.0 - 100.0 score:
          Base (80%): Canon Depth (30%), Movie Contrast (30%), Curiosity (20%), Visual Feasibility (20%)
          Coherence Extension (20%): Semantic overlap between fact claim/details and target theme.
        """
        # Base 4-part score (0-100 scale)
        c_depth = fact.importance * 100.0
        m_contrast = fact.movie_contrast * 100.0
        curiosity = fact.curiosity_score * 100.0
        v_feas = fact.visual_feasibility * 100.0

        base_score = (
            (0.30 * c_depth) +
            (0.30 * m_contrast) +
            (0.20 * curiosity) +
            (0.20 * v_feas)
        )

        # Thematic coherence evaluation
        coherence = cls.calculate_thematic_coherence(fact, theme)
        total_score = ((1.0 - coherence_weight) * base_score) + (coherence_weight * (coherence * 100.0))
        return round(total_score, 2)

    @staticmethod
    def calculate_thematic_coherence(fact: MultiFactPayload, theme: str) -> float:
        """
        Measures semantic relevance between a fact and the Short's overarching theme.
        Returns 0.0 - 1.0.
        """
        if not theme or not theme.strip():
            return 1.0

        if fact.theme and fact.theme.strip().lower() == theme.strip().lower():
            return 1.0

        theme_tokens = set(re.sub(r"[^\w\s]", "", theme.lower()).split())
        # Filter common stopwords
        stopwords = {"the", "a", "an", "and", "or", "in", "of", "to", "for", "that", "this", "these", "there", "are", "is"}
        theme_tokens = {t for t in theme_tokens if t not in stopwords}
        if not theme_tokens:
            return 1.0

        fact_text = f"{fact.theme} {fact.claim} {' '.join(fact.supporting_details)} {fact.canon_source}".lower()
        fact_tokens = set(re.sub(r"[^\w\s]", "", fact_text).split())

        intersection = theme_tokens.intersection(fact_tokens)
        overlap_ratio = len(intersection) / len(theme_tokens)

        # Direct theme match bonus
        if fact.theme.lower() in theme.lower() or theme.lower() in fact.theme.lower():
            overlap_ratio = max(overlap_ratio, 0.90)

        return min(1.0, max(0.0, overlap_ratio))

    # ==========================================================================
    # 2. DEDUPLICATION & OVERLAP PREVENTION
    # ==========================================================================

    @classmethod
    def deduplicate_facts(
        cls,
        facts: List[MultiFactPayload],
        similarity_threshold: float = 0.65
    ) -> List[MultiFactPayload]:
        """
        Filters out exact duplicates and near-duplicate facts using token Jaccard similarity.
        """
        unique_facts: List[MultiFactPayload] = []
        seen_token_sets: List[Set[str]] = []

        for fact in facts:
            # Normalize claim tokens
            tokens = set(re.sub(r"[^\w\s]", "", fact.claim.lower()).split())
            stopwords = {"the", "a", "an", "and", "or", "in", "of", "to", "for", "that", "this", "is", "was"}
            clean_tokens = {t for t in tokens if t not in stopwords}

            # Check similarity against already accepted facts
            is_duplicate = False
            for seen_set in seen_token_sets:
                if not clean_tokens or not seen_set:
                    continue
                intersection = clean_tokens.intersection(seen_set)
                union = clean_tokens.union(seen_set)
                jaccard = len(intersection) / len(union) if union else 0.0
                if jaccard >= similarity_threshold:
                    logger.debug(f"[Deduplication] Dropping near-duplicate fact: '{fact.claim}' (Jaccard: {jaccard:.2f})")
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_facts.append(fact)
                seen_token_sets.append(clean_tokens)

        return unique_facts

    # ==========================================================================
    # 3. SELECTION & ROUTING (ZERO-PADDING GATE)
    # ==========================================================================

    @classmethod
    def select_facts_for_theme(
        cls,
        theme: str,
        candidates: List[MultiFactPayload],
        target_count: int = 5,
        min_coherence: float = 0.25
    ) -> Tuple[List[MultiFactPayload], MultiFactFormat, Optional[str]]:
        """
        Selects candidate facts for a coherent theme.
        ENFORCES CRITICAL INVARIANT:
          If < 4 strong facts exist, STRICTLY REFUSES TO PAD WITH WEAK FILLER.
          Routes to SINGLE_TOPIC_DEEP_DIVE if 1 fact has profound depth, or rejects.
        """
        # Deduplicate first
        deduped = cls.deduplicate_facts(candidates)

        # Score and filter by thematic coherence
        scored_candidates = []
        for f in deduped:
            coherence = cls.calculate_thematic_coherence(f, theme)
            if coherence >= min_coherence:
                score = cls.score_fact(f, theme)
                scored_candidates.append((score, f))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        viable_facts = [f for score, f in scored_candidates if score >= 55.0]

        # Minimum fact gate evaluation
        if len(viable_facts) < 4:
            # Check if one candidate has single-topic depth
            if viable_facts and (viable_facts[0].importance >= 0.85 and viable_facts[0].canon_evidence):
                logger.info(f"Insufficient facts for multi-fact discovery ({len(viable_facts)} < 4). Routing to SINGLE_TOPIC_DEEP_DIVE.")
                return viable_facts[:1], MultiFactFormat.SINGLE_TOPIC_DEEP_DIVE, "ROUTED_TO_SINGLE_TOPIC_DEEP_DIVE"
            else:
                return [], MultiFactFormat.MULTI_FACT_DISCOVERY, f"INSUFFICIENT_STRONG_FACTS: Found {len(viable_facts)}, minimum 4 required. Refusing to pad weak filler."

        # Cap at requested target (5 to 7)
        effective_count = min(max(4, target_count), 7, len(viable_facts))
        selected = viable_facts[:effective_count]
        return selected, MultiFactFormat.MULTI_FACT_DISCOVERY, None

    # ==========================================================================
    # 4. NARRATIVE SEQUENCER (ESCALATING CURIOSITY LADDER)
    # ==========================================================================

    @classmethod
    def order_facts(cls, facts: List[MultiFactPayload]) -> List[MultiFactPayload]:
        """
        Arranges facts into an escalating curiosity ladder rather than arbitrary sorting:
          1. ENTRY: Grounded, accessible, recognizable baseline (verifies hook)
          2. DEEPENING: Canonical lore extension
          3. SURPRISE: Cognitive dissonance / irony
          4. EMOTION: Character reality / human stakes
          5. CLIMAX: Peak reveal / highest payoff value
        """
        if len(facts) <= 2:
            return facts

        # Identify candidate roles
        # 1. Highest payoff_value -> Climax
        climax_fact = max(facts, key=lambda f: (f.payoff_value, f.curiosity_score))
        remaining = [f for f in facts if f.fact_id != climax_fact.fact_id]

        # 2. Emotional peak -> Emotion (if distinct emotional resonance)
        emotion_fact = max(remaining, key=lambda f: f.emotional_value) if remaining else None
        if emotion_fact and emotion_fact.emotional_value >= 0.6:
            remaining = [f for f in remaining if f.fact_id != emotion_fact.fact_id]
        else:
            emotion_fact = None

        # 3. Cognitive surprise -> Surprise (high contrast or curiosity)
        surprise_fact = max(remaining, key=lambda f: (f.movie_contrast, f.curiosity_score)) if remaining else None
        if surprise_fact and (surprise_fact.movie_contrast >= 0.7 or surprise_fact.curiosity_score >= 0.85):
            remaining = [f for f in remaining if f.fact_id != surprise_fact.fact_id]
        else:
            surprise_fact = None

        # 4. Entry fact -> The most grounded, accessible baseline among remaining (accessible / lower payoff / high visual feasibility)
        if remaining:
            entry_fact = min(remaining, key=lambda f: (f.payoff_value, -f.visual_feasibility))
            remaining = [f for f in remaining if f.fact_id != entry_fact.fact_id]
        else:
            entry_fact = None

        # Deepening facts: whatever remains, sorted by importance
        deepening_facts = sorted(remaining, key=lambda f: f.importance, reverse=True)

        # Assemble deliberate ladder
        ordered: List[MultiFactPayload] = []
        if entry_fact:
            entry_fact.narrative_role = "ENTRY"
            ordered.append(entry_fact)

        for df in deepening_facts:
            df.narrative_role = "DEEPENING"
            ordered.append(df)

        if surprise_fact:
            surprise_fact.narrative_role = "SURPRISE"
            ordered.append(surprise_fact)

        if emotion_fact:
            emotion_fact.narrative_role = "EMOTION"
            ordered.append(emotion_fact)

        climax_fact.narrative_role = "CLIMAX"
        ordered.append(climax_fact)

        return ordered

    # ==========================================================================
    # 5. CONVERSATIONAL TRANSITION SYNTHESIZER
    # ==========================================================================

    @classmethod
    def assign_transitions(
        cls,
        facts: List[MultiFactPayload],
        use_conversational_variety: bool = True
    ) -> None:
        """
        Assigns dynamic, contextual spoken bridges to avoid monotonous 'First, second, third' ordinals.
        """
        num_facts = len(facts)
        for idx, fact in enumerate(facts):
            pos = idx + 1
            if pos == 1:
                fact.spoken_transition = "To start," if use_conversational_variety else "First,"
            elif pos == num_facts:
                fact.spoken_transition = "And finally, the one that changes everything:" if use_conversational_variety else "Finally,"
            elif fact.narrative_role == "SURPRISE":
                fact.spoken_transition = "But here's where it gets weird:"
            elif fact.narrative_role == "EMOTION":
                fact.spoken_transition = "Then there's the heartbreaking detail:"
            elif fact.narrative_role == "DEEPENING":
                transitions_pool = ["Next,", "Then there's", "Even more surprising,"]
                fact.spoken_transition = transitions_pool[(idx) % len(transitions_pool)]
            else:
                ordinals = {2: "Second,", 3: "Third,", 4: "Fourth,", 5: "Fifth,", 6: "Sixth,"}
                fact.spoken_transition = ordinals.get(pos, "Next,")

    # ==========================================================================
    # 6. TIME & WORD BUDGET ALLOCATOR
    # ==========================================================================

    @classmethod
    def allocate_duration_and_words(cls, pack: MultiFactTopicPack) -> None:
        """
        Distributes runtime budget (68–78s, ceiling 80.9s, ~240–280 words, 3.4–3.7 wps):
          Hook: ~4.5s (~16 words)
          Epiphany/Payoff: ~5.0s (~18 words)
          Remaining budget dynamically allocated across facts (Climax receives +15% more time).
        """
        total_dur = min(78.0, max(68.0, pack.total_target_duration))
        hook_dur = 4.5
        payoff_dur = 5.0
        remaining_dur = total_dur - hook_dur - payoff_dur

        num_facts = len(pack.facts)
        if num_facts == 0:
            return

        # Weight distribution: Climax gets 1.2x weight, Entry gets 1.0x, others 1.0x
        weights = [1.25 if f.narrative_role == "CLIMAX" else 1.0 for f in pack.facts]
        total_weight = sum(weights)

        speech_rate = pack.target_speech_rate  # ~3.55 wps

        for fact, w in zip(pack.facts, weights):
            fact_dur = round((w / total_weight) * remaining_dur, 1)
            fact.target_duration_sec = fact_dur
            fact.target_word_count = int(round(fact_dur * speech_rate))

            # Update proposition durations to fit allocated fact budget
            if fact.visual_propositions:
                prop_dur = round(fact_dur / len(fact.visual_propositions), 2)
                for vp in fact.visual_propositions:
                    vp.estimated_duration_sec = min(3.5, max(1.5, prop_dur))

        # Recompute total words
        hook_words = int(round(hook_dur * speech_rate))
        payoff_words = int(round(payoff_dur * speech_rate))
        facts_words = sum(f.target_word_count for f in pack.facts)
        pack.total_target_words = hook_words + facts_words + payoff_words

    # ==========================================================================
    # 7. HOOK & TITLE FORMULATION
    # ==========================================================================

    @classmethod
    def generate_thematic_hook(
        cls,
        theme: str,
        fact_count: int,
        archetype: HookArchetype = HookArchetype.COUNTER_INTUITIVE_TRUTH
    ) -> str:
        """
        Synthesizes an overarching promise hook without throat-clearing.
        """
        num_word = {4: "four", 5: "five", 6: "six", 7: "seven"}.get(fact_count, str(fact_count))

        if archetype == HookArchetype.COUNTER_INTUITIVE_TRUTH:
            return f"There are {num_word} details about {theme} that completely change what these scenes actually mean."
        elif archetype == HookArchetype.INCREDULITY_AWARENESS_TEST:
            return f"It took fans over twenty years to notice these {num_word} hidden details about {theme}."
        elif archetype == HookArchetype.DIRECT_CHALLENGE:
            return f"I bet you never noticed these {num_word} massive differences in {theme}."
        elif archetype == HookArchetype.ABSURD_COMIC_REALITY:
            return f"These {num_word} movie changes to {theme} make absolutely zero sense."
        else:
            return f"Did you know these {num_word} insane facts about {theme}?"

    @classmethod
    def generate_suggested_title(
        cls,
        theme: str,
        fact_count: int,
        pattern: TitlePattern = TitlePattern.BOOK_VS_MOVIE
    ) -> str:
        """
        Creates curiosity-driven, non-deceptive title.
        """
        num_word = {4: "Four", 5: "Five", 6: "Six", 7: "Seven"}.get(fact_count, str(fact_count))
        if pattern == TitlePattern.BOOK_VS_MOVIE:
            return f"{num_word} Harry Potter Book Changes That Just Don't Make Sense"
        elif pattern == TitlePattern.HIDDEN_DETAIL:
            return f"It Took Me 18 Years to Notice These {num_word} Harry Potter Details"
        elif pattern == TitlePattern.COUNTER_INTUITIVE_TRUTH:
            return f"{num_word} Insane Facts About {theme} You Definitely Overlooked"
        else:
            return f"{num_word} Things You Never Knew About {theme}"

    # ==========================================================================
    # 8. TOPIC PACK ASSEMBLY & VALIDATION GATE
    # ==========================================================================

    def assemble_topic_pack(
        self,
        topic_id: str,
        theme: str,
        candidate_facts: List[MultiFactPayload],
        target_count: int = 5,
        hook_archetype: HookArchetype = HookArchetype.COUNTER_INTUITIVE_TRUTH,
        title_pattern: TitlePattern = TitlePattern.BOOK_VS_MOVIE,
        target_duration: float = 75.0,
        payoff_text: str = ""
    ) -> MultiFactTopicPack:
        """
        Main entry point for building a production-ready MultiFactTopicPack.
        """
        # 1. Select facts with zero-padding enforcement
        selected_facts, format_decision, routing_note = self.select_facts_for_theme(
            theme=theme,
            candidates=candidate_facts,
            target_count=target_count,
        )

        if format_decision == MultiFactFormat.SINGLE_TOPIC_DEEP_DIVE:
            # Single-topic deep dive fallback
            pack = MultiFactTopicPack(
                topic_id=topic_id,
                theme=theme,
                hook=f"The untold truth behind {theme} that the movies skipped.",
                hook_archetype=hook_archetype,
                facts=selected_facts,
                total_target_duration=target_duration,
                format=MultiFactFormat.SINGLE_TOPIC_DEEP_DIVE,
                payoff_text=payoff_text or "And that changes everything we thought we knew.",
                suggested_title=f"The Real Truth About {theme}",
            )
            pack.validate()
            return pack

        if not selected_facts:
            # Rejection due to insufficient facts
            pack = MultiFactTopicPack(
                topic_id=topic_id,
                theme=theme,
                hook="",
                facts=[],
                validation_errors=[routing_note or "Zero facts selected"],
                is_valid=False,
            )
            return pack

        # 2. Narrative sequencing (escalating curiosity ladder)
        ordered_facts = self.order_facts(selected_facts)

        # 3. Assign natural spoken transitions
        self.assign_transitions(ordered_facts)

        # 4. Generate hook and title
        hook = self.generate_thematic_hook(theme, len(ordered_facts), hook_archetype)
        title = self.generate_suggested_title(theme, len(ordered_facts), title_pattern)

        # 5. Assemble topic pack
        pack = MultiFactTopicPack(
            topic_id=topic_id,
            theme=theme,
            hook=hook,
            hook_archetype=hook_archetype,
            facts=ordered_facts,
            total_target_duration=target_duration,
            format=MultiFactFormat.MULTI_FACT_DISCOVERY,
            payoff_strategy="FINAL_CLIMAX_REVEAL",
            payoff_text=payoff_text or "Once you see these details, you can never watch these movies the same way again.",
            title_pattern=title_pattern,
            suggested_title=title,
            expected_fact_count=len(ordered_facts),
        )

        # 6. Allocate durations & word budgets
        self.allocate_duration_and_words(pack)

        # 7. Anti-repetition registration
        self._recent_themes.append(theme)
        if len(self._recent_themes) > self.recent_history_limit:
            self._recent_themes.pop(0)
        for f in ordered_facts:
            self._recent_fact_ids.add(f.fact_id)

        # 8. Validate quality gates
        pack.validate()
        return pack
