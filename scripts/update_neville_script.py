import sqlite3
import json

script_text = (
    "Did you know Neville Longbottom's Remembrall revealed a secret the movie never said out loud? "
    "During morning mail in the Great Hall, an owl drops a magical glass ball that glows bright scarlet "
    "whenever you forget something. Neville stares at the glowing sphere completely bewildered, "
    "admitting he cannot remember what he forgot. But look closely at the breakfast table! "
    "Every single classmate is wearing their black school robes. "
    "Neville is sitting in just his sweater and tie, having completely forgotten his school cloak!"
)

visual_beats = [
    {
        "beat_id": "beat_1",
        "narration_text": "Did you know Neville Longbottom's Remembrall revealed a secret the movie never said out loud?",
        "visual_requirement": "Flock of school owls swooping into the sunny Great Hall carrying letters and packages down to students",
        "characters": ["Hogwarts Students", "Owls"],
        "location": "Great Hall breakfast tables",
        "action": "Owls flying low over long breakfast tables dropping mail",
        "objects": ["Mail packages", "Great Hall tables"],
        "emotional_context": "Morning energy and anticipation",
        "preferred_movie_number": 1,
        "source_grounding": "Movie 1, 00:54:02–00:54:18 / Book 1 Chapter 9",
        "retrieval_hints": ["owls", "Great Hall", "breakfast", "mail", "delivery"],
        "clip_start_seconds": 3242.0,
        "clip_end_seconds": 3249.0,
        "is_novel_only": False,
        "visual_source_policy": "MOVIE_FOOTAGE_ONLY"
    },
    {
        "beat_id": "beat_2",
        "narration_text": "During morning mail in the Great Hall, an owl drops a magical glass ball that glows bright scarlet whenever you forget something. Neville stares at the glowing sphere completely bewildered, admitting he cannot remember what he forgot.",
        "visual_requirement": "Close-up of Neville holding the clear glass ball as glowing red smoke swirls inside, looking bewildered",
        "characters": ["Hermione Granger"],
        "location": "Gryffindor house table",
        "action": "close-up of glass Remembrall ball in Neville hand glowing with swirling red smoke",
        "objects": ["Remembrall", "red smoke", "glass ball"],
        "emotional_context": "Bewilderment and innocent humor",
        "preferred_movie_number": 1,
        "source_grounding": "Movie 1, 00:54:29–00:54:33 / Book 1 Chapter 9",
        "retrieval_hints": ["Remembrall", "red smoke", "confused"],
        "clip_start_seconds": 3269.0,
        "clip_end_seconds": 3273.5,
        "is_novel_only": False,
        "visual_source_policy": "MOVIE_FOOTAGE_ONLY"
    },
    {
        "beat_id": "beat_3",
        "narration_text": "But look closely at the breakfast table! Every single classmate is wearing their black school robes.",
        "visual_requirement": "Medium shot panning across Harry, Ron, Hermione, and Dean, all dressed in standard black Hogwarts robes",
        "characters": ["Harry Potter", "Ron Weasley", "Hermione Granger"],
        "location": "Gryffindor table",
        "action": "Classmates sitting in full uniform black school cloaks watching Neville",
        "objects": ["black Hogwarts robes", "Daily Prophet", "parchment letter"],
        "emotional_context": "Visual evidence and contrast",
        "preferred_movie_number": 1,
        "source_grounding": "Movie 1, 00:54:38–00:54:43 / Book 1 Chapter 9",
        "retrieval_hints": ["students in robes", "Hermione", "black cloaks", "uniform"],
        "clip_start_seconds": 3278.0,
        "clip_end_seconds": 3283.5,
        "is_novel_only": False,
        "visual_source_policy": "MOVIE_FOOTAGE_ONLY"
    },
    {
        "beat_id": "beat_4",
        "narration_text": "Neville is sitting in just his sweater and tie, having completely forgotten his school cloak!",
        "visual_requirement": "Cut back to Neville sitting in just his white collared shirt, vest sweater, and tie, completely missing his black robe",
        "characters": ["Neville Longbottom", "Dean Thomas"],
        "location": "Gryffindor table",
        "action": "close-up of Neville sitting in knit sweater vest and tie admitting he forgot his cloak",
        "objects": ["sweater vest", "Gryffindor tie", "collared shirt", "missing robe"],
        "emotional_context": "Clever realization, laughter, and hidden easter egg",
        "preferred_movie_number": 1,
        "source_grounding": "Movie 1, 00:54:34–00:54:37 / Book 1 Chapter 9",
        "retrieval_hints": ["Neville sweater", "no robe", "Remembrall", "forgotten cloak"],
        "clip_start_seconds": 3274.0,
        "clip_end_seconds": 3277.8,
        "is_novel_only": False,
        "visual_source_policy": "MOVIE_FOOTAGE_ONLY"
    }
]

words = len(script_text.split())

for db in ["data/database/pipeline.db", "data/database/youtube_automation.db"]:
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("""
        UPDATE hp_scripts 
        SET full_text = ?,
            word_count = ?,
            total_beats = 4,
            visual_beats_json = ?,
            status = 'READY_FOR_STEP_9',
            qa_status = 'APPROVED'
        WHERE id = 'hps_disc_neville_remembrall_cloak_b1'
    """, (script_text, words, json.dumps(visual_beats)))
    conn.commit()
    print(f"Successfully updated {db}: word_count = {words}")
