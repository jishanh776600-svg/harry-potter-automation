import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.multi_fact_types import (
    MultiFactTopicPack,
    MultiFactPayload,
    VisualProposition,
    FactType,
    RequiredEvidenceType,
    MultiFactFormat
)
from core.discovery_types import HookArchetype, TitlePattern

refined_facts = [
    MultiFactPayload(
        fact_id="fact_01_great_hall_duel",
        theme="The Battle of Hogwarts",
        claim="Harry and Voldemort never flew merged in smoke; their confrontation was a psychological trial in the Great Hall, circled in dead silence by hundreds of spectators.",
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Deathly Hallows, Chapter 36, pp. 737-744",
        canon_evidence="They were moving sideways in a circle, both keeping their distance... only Harry and Voldemort facing each other in the center of the hall, with hundreds lining the walls in dead silence.",
        importance=0.95,
        curiosity_score=0.90,
        emotional_value=0.85,
        movie_contrast=0.95,
        visual_feasibility=0.90,
        required_evidence_type=RequiredEvidenceType.DIRECT_FILM_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_01_duel_standoff",
                subject="Harry Potter and Lord Voldemort",
                action="circle each other with wands raised in tense psychological standoff",
                object="Elder Wand and Hawthorn Wand",
                context="Center of Great Hall surrounded by ring of silent spectators",
                visual_role="DIRECT_EVIDENCE",
                estimated_duration_sec=2.4
            )
        ],
        target_duration_sec=11.3,
        target_word_count=40,
        spoken_transition="Starting with the final duel:",
        narrative_role="ENTRY"
    ),
    MultiFactPayload(
        fact_id="fact_02_kreacher_cleaver_charge",
        theme="The Battle of Hogwarts",
        claim="The ground assault that broke the Death Eater lines was led by Kreacher at the head of the Hogwarts house-elves, brandishing carving knives and cleavers while shouting to fight in the name of brave Regulus.",
        claim_type=FactType.OMITTED_SCENE,
        canon_source="Deathly Hallows, Chapter 36, p. 743",
        canon_evidence="...carving knives and cleavers, and at their head, the locket of Regulus Black bouncing on his chest, was Kreacher, shouting 'Fight! Fight! Fight for my Master, defender of the house-elves! Fight the Dark Lord, in the name of brave Regulus!'",
        importance=0.90,
        curiosity_score=0.95,
        emotional_value=0.90,
        movie_contrast=1.00,
        visual_feasibility=0.80,
        required_evidence_type=RequiredEvidenceType.MIXED_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_02_kreacher_army",
                subject="Kreacher and Hogwarts House-Elves",
                action="charge forward brandishing kitchen knives and cleavers",
                object="Carving knives, cleavers, and Regulus Black Horcrux locket",
                context="Hogwarts entrance hall with stone rubble and spell flashes",
                visual_role="OBJECT_PROP",
                estimated_duration_sec=2.2
            )
        ],
        target_duration_sec=11.0,
        target_word_count=39,
        spoken_transition="Next,",
        narrative_role="DEEPENING"
    ),
    MultiFactPayload(
        fact_id="fact_03_centaur_forest_cavalry",
        theme="The Battle of Hogwarts",
        claim="The Forbidden Forest centaurs broke their neutrality, firing heavy arrows and charging straight into the entrance hall alongside Grawp.",
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Deathly Hallows, Chapter 36, pp. 741-743",
        canon_evidence="Then came hooves and the twangs of bows, and arrows were suddenly falling amongst the Death Eaters... The centaurs Bane, Ronan, and Magorian burst into the hall with a great clatter of hooves.",
        importance=0.85,
        curiosity_score=0.85,
        emotional_value=0.75,
        movie_contrast=0.90,
        visual_feasibility=0.85,
        required_evidence_type=RequiredEvidenceType.DIRECT_FILM_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_03_centaur_charge",
                subject="Centaurs (Bane, Ronan, Magorian) and Grawp",
                action="gallop forward releasing heavy bows and charging into entrance hall",
                object="Heavy wooden bows and iron-tipped arrows",
                context="Castle exterior and entrance hall doors during battle",
                visual_role="DIRECT_EVIDENCE",
                estimated_duration_sec=1.8
            )
        ],
        target_duration_sec=6.2,
        target_word_count=22,
        spoken_transition="Right behind them,",
        narrative_role="DEEPENING"
    ),
    MultiFactPayload(
        fact_id="fact_04_molly_bellatrix_lethal_duel",
        theme="The Battle of Hogwarts",
        claim="Molly Weasley's duel with Bellatrix was far more ferocious; the stone floor beneath them cracked from magical heat before Molly struck Bellatrix directly over the heart, toppling her dead.",
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Deathly Hallows, Chapter 36, pp. 735-736",
        canon_evidence="Jets of light flew from both wands, the floor around the witches' feet became hot and cracked... Molly's curse hit her squarely in the chest, directly over her heart... and then she toppled.",
        importance=0.90,
        curiosity_score=0.85,
        emotional_value=0.95,
        movie_contrast=0.80,
        visual_feasibility=0.95,
        required_evidence_type=RequiredEvidenceType.DIRECT_FILM_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_04_molly_duel",
                subject="Molly Weasley and Bellatrix Lestrange",
                action="duel furiously until curse strikes Bellatrix over the heart, toppling her dead",
                object="Wands firing jets of light over cracked stone floor",
                context="Great Hall floor cracking from magical heat",
                visual_role="DIRECT_EVIDENCE",
                estimated_duration_sec=2.0
            )
        ],
        target_duration_sec=8.5,
        target_word_count=30,
        spoken_transition="Even",
        narrative_role="EMOTION"
    ),
    MultiFactPayload(
        fact_id="fact_05_elder_wand_holly_repair",
        theme="The Battle of Hogwarts",
        claim="In the film, Harry snaps the Elder Wand and throws it away. In the book, he uses its power for one single task: repairing his broken phoenix-feather wand, before returning the Elder Wand intact to Dumbledore's tomb so its power will die with him.",
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Deathly Hallows, Chapter 36, pp. 748-749",
        canon_evidence="He laid the broken wand upon the headmaster's desk, touched it with the very tip of the Elder Wand, and said 'Reparo.' ... 'I'm putting the Elder Wand back where it came from. If I die a natural death, its power will be broken.'",
        importance=0.95,
        curiosity_score=0.95,
        emotional_value=0.90,
        movie_contrast=1.00,
        visual_feasibility=0.90,
        required_evidence_type=RequiredEvidenceType.OBJECT_PROP_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_05_wand_repair",
                subject="Harry Potter",
                action="touches broken phoenix wand with Elder Wand, repairing it whole with red sparks",
                object="Elder Wand, broken Holly Wand pieces, mended Holly Wand",
                context="Headmaster's office before Dumbledore's portrait",
                visual_role="OBJECT_PROP",
                estimated_duration_sec=2.5
            )
        ],
        target_duration_sec=14.4,
        target_word_count=51,
        spoken_transition="Then comes the Elder Wand.",
        narrative_role="SURPRISE"
    ),
    MultiFactPayload(
        fact_id="fact_06_voldemort_mundane_corpse",
        theme="The Battle of Hogwarts",
        claim="Voldemort did not dissolve into flakes; his rebounding curse dropped him to the stone floor with a dull, mundane thud, leaving behind an ordinary human corpse that was dragged into a chamber away from the hall.",
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Deathly Hallows, Chapter 36, pp. 744-745",
        canon_evidence="Tom Riddle hit the floor with a mundane finality, his body feeble and shrunken, the white hands empty... They moved Voldemort's body and laid it in a chamber off the Hall, away from the bodies of the fifty who had died.",
        importance=1.00,
        curiosity_score=1.00,
        emotional_value=1.00,
        movie_contrast=1.00,
        visual_feasibility=0.90,
        required_evidence_type=RequiredEvidenceType.DIRECT_FILM_EVIDENCE,
        visual_propositions=[
            VisualProposition(
                proposition_id="prop_06_voldemort_corpse",
                subject="Lord Voldemort / Tom Riddle",
                action="rebounds backward and hits stone floor lifeless with a mundane thud",
                object="Empty pale hands with Elder Wand flying away",
                context="Great Hall floor in morning sunlight, later moved to chamber off the hall",
                visual_role="DIRECT_EVIDENCE",
                estimated_duration_sec=3.0
            )
        ],
        target_duration_sec=14.0,
        target_word_count=50,
        spoken_transition="Which brings us to the biggest betrayal:",
        narrative_role="CLIMAX"
    )
]

refined_pack = MultiFactTopicPack(
    topic_id="mf_battle_of_hogwarts_omitted_truths_v2",
    theme="The Battle of Hogwarts: 6 Book Realities the Movies Got Completely Backwards",
    hook="The movie finale of the Battle of Hogwarts looks incredible, but it actually reversed the book's most important moments.",
    hook_archetype=HookArchetype.COUNTER_INTUITIVE_TRUTH,
    facts=refined_facts,
    total_target_duration=75.8,
    total_target_words=269,
    target_speech_rate=3.55,
    format=MultiFactFormat.MULTI_FACT_DISCOVERY,
    payoff_strategy="FINAL_CLIMAX_REVEAL",
    payoff_text="The filmmakers wanted a fantasy spectacle, but Rowling's entire point was the opposite: after decades of terror, Tom Riddle died just like any other man.",
    title_pattern=TitlePattern.BOOK_VS_MOVIE,
    suggested_title="6 Battle of Hogwarts Truths the Movies Got Completely Backwards"
)

is_valid = refined_pack.validate()
print("Refined Pack Valid?", is_valid)
if not is_valid:
    print("Errors:", refined_pack.validation_errors)
else:
    print(f"Refined Pack Validated! Facts: {len(refined_pack.facts)}, Words: {refined_pack.total_target_words}, Duration: {refined_pack.total_target_duration}s, WPS: {refined_pack.target_speech_rate}")
