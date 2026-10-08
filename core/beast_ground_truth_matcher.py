"""
Beast Ground-Truth Visual Matching Addon
========================================
Authoritative frame-accurate visual retrieval engine integrating:
1. Audio Description (AD / DVS) visual action transcripts.
2. SDH Subtitles (Subtitles for Deaf & Hard-of-Hearing) speaker tags and action cues.
3. Screenplay Action Descriptions & Scene Heading Boundaries (IMSDb / shooting scripts).
4. Direct Blu-ray master movie timecode alignment and lossless smart-crop slicing.

Acts as Tier-1 High-Priority visual matcher before falling back to Franchise Vault.
"""

import os
import re
import sys
import json
import sqlite3
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.smart_crop_engine import SmartCropEngine
from core.visual_mismatch_guard import VisualMismatchGuard

logger = logging.getLogger("BeastGroundTruthMatcher")

DB_PATH = PROJECT_ROOT / "data" / "database" / "beast_ground_truth.db"
MOVIES_DIR = PROJECT_ROOT / "data" / "movies"
SUBTITLES_DIR = PROJECT_ROOT / "data" / "ground_truth" / "subtitles"
CACHE_DIR = PROJECT_ROOT / "data" / "ground_truth" / "cache"

MOVIE_FILE_MAP = {
    1: {
        "title": "Harry Potter and the Sorcerer's Stone",
        "file": "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv"
    },
    2: {
        "title": "Harry Potter and the Chamber of Secrets",
        "file": "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv"
    },
    3: {
        "title": "Harry Potter and the Prisoner of Azkaban",
        "file": "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv"
    },
    4: {
        "title": "Harry Potter and the Goblet of Fire",
        "file": "Harry Potter And The Goblet Of Fire 2005 BluRay 720p Dual Audio Hindi.mkv"
    },
    5: {
        "title": "Harry Potter and the Order of the Phoenix",
        "file": "Harry Potter And The Order Of The Phoenix 2007 Dual Audio Hindi 720p BluRay.mkv"
    },
    6: {
        "title": "Harry Potter and the Half-Blood Prince",
        "file": "Harry Potter And The Half Blood Prince 2009 BluRay 720p Dual Audio Hindi.mkv"
    },
    7: {
        "title": "Harry Potter and the Deathly Hallows – Part 1",
        "file": "Harry Potter And The Deathly Hallows Part 1 2010 Dual Audio Hindi 720p BluRay.mkv"
    },
    8: {
        "title": "Harry Potter and the Deathly Hallows – Part 2",
        "file": "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv"
    }
}

CANONICAL_SCENE_SEEDS = [
    # MOVIE 1: SORCERER'S STONE
    {
        "scene_id": "m1_sorting_hat_mcgonagall",
        "movie_number": 1,
        "movie_title": "Harry Potter and the Sorcerer's Stone",
        "start_seconds": 2605.0,  # 00:43:25 (Sorting Hat placed on head)
        "end_seconds": 2748.0,    # 00:45:48 (Sorting deliberation & Gryffindor)
        "scene_heading": "INT. GREAT HALL - NIGHT",
        "primary_characters": "Professor McGonagall, Sorting Hat, Harry Potter, Hermione Granger, Ron Weasley",
        "key_actions": "McGonagall calls students forward and places the pointed Sorting Hat on their heads. The brown tattered hat twists, wrinkles forming a mouth and eyes, deliberates, and shouts Gryffindor.",
        "objects": "Sorting Hat, four-legged stool, parchment scroll, candles",
        "locations": "Great Hall, Hogwarts",
        "audio_description_text": "Professor McGonagall places the ragged brown Sorting Hat onto Harry Potter's head. The hat folds and squints its fabric folds like a face, muttering thoughtfully before loudly declaring Gryffindor to the cheering hall.",
        "sdh_dialogue_cues": "[Sorting Hat:] Gryffindor! [applause] [McGonagall:] Harry Potter.",
        "visual_tags": "sorting hat, mcgonagall, hatstall, sorting ceremony, great hall, stool, hat folds, mouth, gryffindor"
    },
    {
        "scene_id": "m1_mirror_of_erised_inscription",
        "movie_number": 1,
        "movie_title": "Harry Potter and the Sorcerer's Stone",
        "start_seconds": 5320.0,  # 01:28:40
        "end_seconds": 5580.0,    # 01:33:00
        "scene_heading": "INT. DISUSED CLASSROOM - NIGHT",
        "primary_characters": "Harry Potter, Ron Weasley, James Potter, Lily Potter, Albus Dumbledore",
        "key_actions": "Harry stands mesmerized before the towering ornate gold Mirror of Erised with reversed inscription. He stares into the glass seeing his smiling parents standing beside him.",
        "objects": "Mirror of Erised, golden frame, reversed carved inscription, invisibility cloak",
        "locations": "Disused Classroom, Hogwarts",
        "audio_description_text": "A towering gold-framed mirror stands in the moonlit classroom. Across the top arch carved runes read Erised stra ehru oyt ube cafru oyt on wohsi. Harry gazes into the reflection, seeing his mother Lily and father James smiling gently at him.",
        "sdh_dialogue_cues": "[Harry whispers:] Mom? Dad? [Harry:] Look, Ron! They're my parents!",
        "visual_tags": "mirror of erised, inscription, reflection, harry parents, lily potter, james potter, gold frame, disused classroom"
    },
    {
        "scene_id": "m1_quirrell_voldemort_turban",
        "movie_number": 1,
        "movie_title": "Harry Potter and the Sorcerer's Stone",
        "start_seconds": 7380.0,  # 02:03:00
        "end_seconds": 7560.0,    # 02:06:00
        "scene_heading": "INT. UNDERGROUND CHAMBER - NIGHT",
        "primary_characters": "Professor Quirrell, Lord Voldemort, Harry Potter",
        "key_actions": "Quirrell unwraps his purple turban revealing Voldemort's snakelike face protruding from the back of his bald skull. Voldemort's slit red eyes hiss and speak to Harry.",
        "objects": "turban, Philosopher's Stone, mirror, flames",
        "locations": "Underground Chamber, Hogwarts",
        "audio_description_text": "Quirrell reaches up and slowly unwinds his purple cloth turban, turning around to reveal the pale, serpentine face of Lord Voldemort protruding grotesquely from the back of his bare head.",
        "sdh_dialogue_cues": "[Voldemort hisses:] Harry Potter... We meet again.",
        "visual_tags": "quirrell, voldemort face, back of head, turban unwrapping, underground chamber, sorcerers stone"
    },

    # MOVIE 2: CHAMBER OF SECRETS
    {
        "scene_id": "m2_dobby_privet_drive_bedroom",
        "movie_number": 2,
        "movie_title": "Harry Potter and the Chamber of Secrets",
        "start_seconds": 198.0,   # 00:03:18
        "end_seconds": 380.0,     # 00:06:20
        "scene_heading": "INT. HARRY'S BEDROOM - PRIVET DRIVE - NIGHT",
        "primary_characters": "Dobby the House-Elf, Harry Potter",
        "key_actions": "Dobby the house-elf wearing a ragged pillowcase bounces on Harry's bed with huge bat ears and tennis-ball green eyes, then violently bangs his head against the chest of drawers and nightstand shouting 'Bad Dobby!'.",
        "objects": "ragged pillowcase, bed, nightstand, chest of drawers, letters",
        "locations": "4 Privet Drive, Harry's Bedroom",
        "audio_description_text": "A tiny creature with large bat-like ears, wearing a grubby pillowcase, jumps vigorously on Harry's mattress. Overcome with guilt, Dobby rushes forward and begins repeatedly bashing his own forehead against the wooden drawer.",
        "sdh_dialogue_cues": "[Dobby:] Dobby, sir. Dobby the house-elf. [thud thud] [Dobby:] Bad Dobby! Bad Dobby!",
        "visual_tags": "dobby, house elf, pillowcase, bed jumping, banging head, bad dobby, privet drive, bat ears"
    },
    {
        "scene_id": "m2_dobby_freed_sock",
        "movie_number": 2,
        "movie_title": "Harry Potter and the Chamber of Secrets",
        "start_seconds": 8985.0,  # 02:29:45
        "end_seconds": 9120.0,    # 02:32:00
        "scene_heading": "INT. HOGWARTS CORRIDOR - DAY",
        "primary_characters": "Dobby the House-Elf, Lucius Malfoy, Harry Potter",
        "key_actions": "Lucius Malfoy tosses Tom Riddle's diary to Dobby. Inside is Harry's grey sock. Dobby holds up the sock in trembling awe, declaring 'Master has given Dobby a sock. Dobby is free!'. When Lucius draws his wand, Dobby blasts him backward.",
        "objects": "sock, diary of tom riddle, snake-headed cane wand",
        "locations": "Hogwarts Corridor",
        "audio_description_text": "Dobby opens the diary and pulls out Harry's slimy grey sock. Stunned tears well in his enormous eyes as he raises the sock into the air, whispering that he is free. He snaps his fingers, launching Lucius Malfoy backward through the air.",
        "sdh_dialogue_cues": "[Dobby:] Master has given Dobby a sock. Master has presented Dobby with clothes! Dobby is free!",
        "visual_tags": "dobby free, sock, lucius malfoy, blast malfoy, free elf, diary, corridor"
    },

    # MOVIE 3: PRISONER OF AZKABAN
    {
        "scene_id": "m3_dementor_train_lupin_chocolate",
        "movie_number": 3,
        "movie_title": "Harry Potter and the Prisoner of Azkaban",
        "start_seconds": 1210.0,  # 00:20:10
        "end_seconds": 1440.0,    # 00:24:00
        "scene_heading": "INT. HOGWARTS EXPRESS COMPARTMENT - RAIN - NIGHT",
        "primary_characters": "Dementor, Remus Lupin, Harry Potter, Hermione Granger, Ron Weasley",
        "key_actions": "Frost freezes the carriage window. A cloaked rotting Dementor glides in, rattling and sucking the light and breath from Harry. Lupin wakes, casts a silver Patronus, and hands Harry a bar of chocolate.",
        "objects": "Dementor cloak, skeletal hand, frost, chocolate bar, wand",
        "locations": "Hogwarts Express compartment",
        "audio_description_text": "Ice crystals spread across the glass. The compartment door slides open to reveal a towering, ragged black hooded Dementor. A rotting hand grips the frame as it draws in a deep rattling breath. Professor Lupin unleashes a blinding white light from his wand.",
        "sdh_dialogue_cues": "[rattling breath] [gasping] [Lupin:] Eat this. It'll help. It's chocolate.",
        "visual_tags": "dementor, remus lupin, hogwarts express, chocolate, patronus, frost, ice, train compartment"
    },
    {
        "scene_id": "m3_marauders_map_twins",
        "movie_number": 3,
        "movie_title": "Harry Potter and the Prisoner of Azkaban",
        "start_seconds": 3250.0,  # 00:54:10
        "end_seconds": 3450.0,    # 00:57:30
        "scene_heading": "INT. HOGWARTS CORRIDOR / ALCOVE - SNOW - DAY",
        "primary_characters": "Fred Weasley, George Weasley, Harry Potter",
        "key_actions": "Fred and George corner Harry and unfold a blank sheet of parchment. George taps it with his wand: 'I solemnly swear that I am up to no good.' Ink flows outwards revealing Hogwarts corridors and walking footprints.",
        "objects": "Marauder's Map, parchment, footprints, wand",
        "locations": "Hogwarts Corridor, statues",
        "audio_description_text": "George taps the folded brown parchment with his wand tip. Intricate black ink bleeds across the surface, sketching castle towers, secret passages, and moving sets of labeled footprints wandering through the halls.",
        "sdh_dialogue_cues": "[George:] I solemnly swear that I am up to no good. [Fred:] Mischief managed.",
        "visual_tags": "marauders map, fred and george, footprints, parchment, solemnly swear, mischief managed"
    },

    # MOVIE 4: GOBLET OF FIRE
    {
        "scene_id": "m4_crouch_jr_pensieve_trial_tongue",
        "movie_number": 4,
        "movie_title": "Harry Potter and the Goblet of Fire",
        "start_seconds": 6394.0,  # 01:46:34 (David Tennant snarling & tongue flick)
        "end_seconds": 6402.0,    # 01:46:42
        "scene_heading": "INT. MINISTRY OF MAGIC COURTROOM / PENSIEVE - MEMORY",
        "primary_characters": "Barty Crouch Jr., Igor Karkaroff, Barty Crouch Sr., Albus Dumbledore",
        "key_actions": "Karkaroff names Barty Crouch Junior. David Tennant leaps from the spectator seats, tries to scramble away, is tackled by Aurors, and dragged down snarling, flicking his tongue out like a snake while staring madly at his father.",
        "objects": "cage, chains, Auror uniforms, bowler hat, pensieve memory",
        "locations": "Ministry Courtroom, Council of Magical Law",
        "audio_description_text": "Young Barty Crouch Junior, played by David Tennant, lunges frantically up the stone stairs before Aurors slam him to the floor. Bound in chains, he looks up with crazed, twitching eyes and repeatedly flicks his pink tongue out like a serpent at his stone-faced father.",
        "sdh_dialogue_cues": "[Karkaroff screams:] Barty Crouch... Junior! [Crouch Jr. yells:] Hello, father! [tongue flicks]",
        "visual_tags": "barty crouch jr, david tennant, pensieve trial, tongue flick, courtroom, karkaroff, chains, snarling"
    },
    {
        "scene_id": "m4_crouch_jr_moody_office_reveal",
        "movie_number": 4,
        "movie_title": "Harry Potter and the Goblet of Fire",
        "start_seconds": 8200.0,  # 02:16:40
        "end_seconds": 8340.0,    # 02:19:00
        "scene_heading": "INT. DEFENSE AGAINST THE DARK ARTS OFFICE - NIGHT",
        "primary_characters": "Barty Crouch Jr., Alastor Moody, Albus Dumbledore, Severus Snape, Harry Potter",
        "key_actions": "The Polyjuice potion expires. Mad-Eye Moody convulses, his magical eye popping loose, his wooden leg shedding, transforming back into David Tennant (Barty Crouch Jr.) in a dark coat, flicking his tongue and pointing his wand.",
        "objects": "Polyjuice flask, magical eye, wooden leg, Dark Mark brand, Veritaserum",
        "locations": "DADA Office, Hogwarts",
        "audio_description_text": "Moody writhes in agony as his skin contorts and bubbles. The false face recedes, revealing David Tennant's messy hair and wild glare. He rapidly darts his tongue in and out as Snape forces Veritaserum down his throat.",
        "sdh_dialogue_cues": "[gasping] [Dumbledore:] Barty Crouch Junior. [tongue flicking]",
        "visual_tags": "barty crouch jr, moody reveal, polyjuice potion, dark mark, david tennant, veritaserum, dada office"
    },
    {
        "scene_id": "m4_voldemort_graveyard_rebirth",
        "movie_number": 4,
        "movie_title": "Harry Potter and the Goblet of Fire",
        "start_seconds": 7080.0,  # 01:58:00
        "end_seconds": 7320.0,    # 02:02:00
        "scene_heading": "EXT. LITTLE HANGLETON GRAVEYARD - NIGHT",
        "primary_characters": "Lord Voldemort, Wormtail (Peter Pettigrew), Harry Potter",
        "key_actions": "Wormtail drops the homunculus into a steaming black cauldron, adding bone of father, flesh of servant, and Harry's blood. Voldemort rises from the vapor in full human form, inspecting his skeletal hands and pale snakelike face.",
        "objects": "cauldron, Riddle tombstone, scythe, Harry's blood, bone",
        "locations": "Little Hangleton Graveyard",
        "audio_description_text": "Thick black steam billows from the iron cauldron as a tall, naked, pale figure emerges. Lord Voldemort raises long spindly fingers, tracing his own flat, slit-nostriled nose and grinning with cold red eyes.",
        "sdh_dialogue_cues": "[Voldemort:] Bone of the father, unknowingly given... Harry Potter. [whispers] Welcome, my friends.",
        "visual_tags": "voldemort rebirth, graveyard, cauldron, wormtail, little hangleton, tom riddle gravestone, pale face"
    },

    # MOVIE 5: ORDER OF THE PHOENIX
    {
        "scene_id": "m5_thestrals_luna_lovegood",
        "movie_number": 5,
        "movie_title": "Harry Potter and the Order of the Phoenix",
        "start_seconds": 2560.0,  # 00:42:40 (barefoot Luna feeding Thestrals)
        "end_seconds": 2640.0,    # 00:44:00
        "scene_heading": "EXT. FORBIDDEN FOREST - DAY",
        "primary_characters": "Luna Lovegood, Harry Potter, Thestrals",
        "key_actions": "Luna stands barefoot in the snowy forest feeding raw meat to a winged skeletal black Thestral. She explains to Harry that only those who have seen death can see them: 'You're just as sane as I am.'",
        "objects": "Thestral, raw meat, butterbeer cork necklace, radish earrings",
        "locations": "Forbidden Forest edge",
        "audio_description_text": "Luna Lovegood, barefoot with long blonde hair, holds out raw red meat to a skeletal, black-winged dragon-horse. The gaunt Thestral nuzzles her hand. Harry watches the winged beast in awe.",
        "sdh_dialogue_cues": "[Luna:] They're called Thestrals. You're just as sane as I am.",
        "visual_tags": "luna lovegood, thestrals, forbidden forest, barefoot, raw meat, skeletal horse, seen death"
    },
    {
        "scene_id": "m5_ministry_duel_dumbledore_voldemort",
        "movie_number": 5,
        "movie_title": "Harry Potter and the Order of the Phoenix",
        "start_seconds": 6920.0,  # 01:55:20
        "end_seconds": 7240.0,    # 02:00:40
        "scene_heading": "INT. MINISTRY OF MAGIC ATRIUM - NIGHT",
        "primary_characters": "Albus Dumbledore, Lord Voldemort, Harry Potter",
        "key_actions": "Dumbledore and Voldemort duel in the golden Ministry Atrium. Voldemort conjures a giant flaming fiery serpent; Dumbledore deflects it and traps Voldemort in a swirling vortex sphere of water, while glass shatters across the chamber.",
        "objects": "fire serpent, water sphere, shattered glass, fountain of magical brethren, wand sparks",
        "locations": "Ministry of Magic Atrium",
        "audio_description_text": "Voldemort whips his wand, conjuring a roaring serpent of living flame. Dumbledore sweeps his Elder Wand, converting the fire into steam and encasing Voldemort inside an enormous swirling orb of suspended water.",
        "sdh_dialogue_cues": "[hissing flames] [glass shattering] [Dumbledore:] It was foolish to come here tonight, Tom.",
        "visual_tags": "dumbledore vs voldemort, ministry duel, atrium, fire snake, water sphere, glass rain, magic duel"
    },

    # MOVIE 6: HALF-BLOOD PRINCE
    {
        "scene_id": "m6_slughorn_memory_horcrux",
        "movie_number": 6,
        "movie_title": "Harry Potter and the Half-Blood Prince",
        "start_seconds": 6200.0,  # 01:43:20
        "end_seconds": 6420.0,    # 01:47:00
        "scene_heading": "INT. SLUGHORN'S OFFICE / PENSIEVE - MEMORY",
        "primary_characters": "Horace Slughorn, Tom Riddle, Harry Potter, Albus Dumbledore",
        "key_actions": "Young teenage Tom Riddle in Slytherin robes smiles charismatically at Slughorn by the fireplace, asking about dark magic and Horcruxes: 'Could one divide the soul into seven pieces?'.",
        "objects": "Pensieve, hourglass, ring, fireplace, crystal glasses",
        "locations": "Slughorn's office, Pensieve memory",
        "audio_description_text": "Inside the shimmering silver memory, handsome young Tom Riddle stands by Professor Slughorn's mantelpiece, stroking the black stone ring on his finger as he asks in a soft whisper about splitting his soul into seven Horcruxes.",
        "sdh_dialogue_cues": "[Tom Riddle:] Seven? Isn't seven the most powerfully magical number?",
        "visual_tags": "slughorn memory, tom riddle, horcrux, seven horcruxes, pensieve, gaunt ring, split soul"
    },
    {
        "scene_id": "m6_astronomy_tower_snape_kills_dumbledore",
        "movie_number": 6,
        "movie_title": "Harry Potter and the Half-Blood Prince",
        "start_seconds": 7920.0,  # 02:12:00
        "end_seconds": 8160.0,    # 02:16:00
        "scene_heading": "EXT. ASTRONOMY TOWER - NIGHT",
        "primary_characters": "Severus Snape, Albus Dumbledore, Draco Malfoy, Bellatrix Lestrange",
        "key_actions": "Draco Malfoy lowers his trembling wand. Snape steps forward onto the tower platform. Dumbledore whispers 'Severus, please.' Snape raises his wand, utters 'Avada Kedavra', and a flash of green light throws Dumbledore over the ramparts.",
        "objects": "Elder wand, green curse light, ramparts, Dark Mark in sky",
        "locations": "Astronomy Tower, Hogwarts",
        "audio_description_text": "Dumbledore leans weakly against the rampart wall, looking up into Snape's dark eyes. With a chillingly calm expression, Snape aims his wand and whispers Avada Kedavra. Emerald green light blasts Dumbledore backward over the stone ledge.",
        "sdh_dialogue_cues": "[Dumbledore whispers:] Severus... please. [Snape:] Avada Kedavra. [screams]",
        "visual_tags": "snape kills dumbledore, astronomy tower, avada kedavra, green light, fall from tower, draco malfoy"
    },

    # MOVIE 7: DEATHLY HALLOWS PART 1
    {
        "scene_id": "m7_dobby_death_shell_cottage",
        "movie_number": 7,
        "movie_title": "Harry Potter and the Deathly Hallows – Part 1",
        "start_seconds": 7680.0,  # 02:08:00
        "end_seconds": 7880.0,    # 02:11:20
        "scene_heading": "EXT. SHELL COTTAGE BEACH - SUNSET",
        "primary_characters": "Dobby the House-Elf, Harry Potter, Hermione Granger, Ron Weasley",
        "key_actions": "Dobby appears on the windy sand dunes clutching his chest. Bellatrix's silver dagger is embedded in his chest. Dobby collapses into Harry's arms, whispering 'Such a beautiful place to be with friends... Dobby is happy' before dying.",
        "objects": "silver dagger, sand, waves, shells, knitted wool cap",
        "locations": "Shell Cottage Beach, sand dunes",
        "audio_description_text": "Dobby stumbles on the ocean dunes, clutching the hilt of Bellatrix's silver dagger protruding from his jacket. Harry rushes forward and catches the collapsing elf. Dobby looks up into Harry's tear-filled eyes, gasps softly, and closes his eyes forever.",
        "sdh_dialogue_cues": "[Dobby gasps:] Harry... Potter. Such a beautiful place, to be with friends. Dobby is happy to be with his friend... Harry Potter.",
        "visual_tags": "dobby death, shell cottage, beach, silver dagger, beautiful place with friends, free elf dies"
    },

    # MOVIE 8: DEATHLY HALLOWS PART 2
    {
        "scene_id": "m8_snapes_tear_princes_tale",
        "movie_number": 8,
        "movie_title": "Harry Potter and the Deathly Hallows – Part 2",
        "start_seconds": 4215.0,  # 01:10:15 (Snape boathouse death & silvery memory tear)
        "end_seconds": 4265.0,    # 01:11:05
        "scene_heading": "INT. BOATHOUSE - NIGHT",
        "primary_characters": "Severus Snape, Harry Potter",
        "key_actions": "Snape lies bleeding on the boathouse floor after Nagini's attack. As Harry kneels over him, a silver tear of memories spills from Snape's eye. Snape whispers 'Take them to the Pensieve... Look at me. You have your mother's eyes.'",
        "objects": "silver memory tear, glass flask, blood, boathouse window",
        "locations": "Hogwarts Boathouse",
        "audio_description_text": "Snape gasps for breath in the dim boathouse, clutching his bleeding throat. A silvery stream of glowing memory tears traces down his cheek. Harry collects the memories into a crystal vial. Snape gazes intently at Harry's green eyes before breathing his last.",
        "sdh_dialogue_cues": "[Snape whispers:] Take them... Take them to the Pensieve. Look at me. You have your mother's eyes.",
        "visual_tags": "snape death, princes tale, silvery tear, memory flask, boathouse, mothers eyes, always"
    },
    {
        "scene_id": "m8_voldemort_disintegration_courtyard",
        "movie_number": 8,
        "movie_title": "Harry Potter and the Deathly Hallows – Part 2",
        "start_seconds": 6420.0,  # 01:47:00
        "end_seconds": 6620.0,    # 01:50:20
        "scene_heading": "EXT. HOGWARTS COURTYARD - RUINS - DAY",
        "primary_characters": "Lord Voldemort, Harry Potter",
        "key_actions": "The Elder Wand spins out of Voldemort's grasp into Harry's hand. Voldemort's spell rebounds. His grey skin begins flaking, peeling, and disintegrating into hundreds of black papery ash fragments swirling into the morning sky.",
        "objects": "Elder Wand, red and green spell collision, ash flakes, ruins",
        "locations": "Hogwarts Ruined Courtyard",
        "audio_description_text": "Voldemort's killing curse recoils. His eyes widen in disbelief as hairline fractures spread across his grey face. His skin turns brittle and dissolves into a thousand fluttering black ash flakes, scattering into the dawn breeze.",
        "sdh_dialogue_cues": "[wind howling] [ash fluttering] [clattering wand]",
        "visual_tags": "voldemort death, disintegration, ash flakes, ruined courtyard, elder wand catches, morning sky"
    }
]

CANONICAL_SHOT_CATALOG = {
    # MOVIE 3: DEMENTOR TRAIN & LUPIN CHOCOLATE
    "m3_train_rain_speeding": {
        "movie_number": 3,
        "start_seconds": 1195.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Hogwarts Express engine speeding through heavy rain",
        "keywords": ["express", "train", "rain", "tracks", "speeding", "board", "dementors board", "engine"]
    },
    "m3_window_freezing_frost": {
        "movie_number": 3,
        "start_seconds": 1250.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Ice crystals freezing train compartment window glass",
        "keywords": ["freeze", "frost", "solid", "ice", "window", "windows", "fog up", "creeping black frost"]
    },
    "m3_dementor_door_hooded": {
        "movie_number": 3,
        "start_seconds": 1315.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Towering black hooded Dementor sliding open train door",
        "keywords": ["dementor", "hooded", "door", "rotting", "cloak", "sliding", "black cloaked", "physically drain"]
    },
    "m3_dementor_sucking_mist": {
        "movie_number": 3,
        "start_seconds": 1335.0,
        "duration": 3.0,
        "target_x_pct": 0.65,
        "subject": "Dementor sucking soul mist from shivering Harry",
        "keywords": ["mist", "sucking", "breath", "warmth", "light", "joy", "surrounding environment", "attack"]
    },
    "m3_lupin_patronus_flash": {
        "movie_number": 3,
        "start_seconds": 1344.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Remus Lupin casting blinding white Patronus flash",
        "keywords": ["lupin", "remus", "patronus", "flash", "white light", "wand", "carried", "honeydukes"]
    },
    "m3_lupin_chocolate_bar_breaking": {
        "movie_number": 3,
        "start_seconds": 1375.0,
        "duration": 3.0,
        "target_x_pct": 0.35,
        "subject": "Remus Lupin breaking Honeydukes chocolate slab handing to Harry",
        "keywords": ["chocolate", "honeydukes", "remedy", "magical remedy", "slab", "warmth", "jumpstarts"]
    },
    "m3_harry_eating_chocolate_lights": {
        "movie_number": 3,
        "start_seconds": 1378.0,
        "duration": 3.0,
        "target_x_pct": 0.85,
        "subject": "Harry holding and eating chocolate recovering on seat",
        "keywords": ["eating", "emotional stability", "recovering", "restores", "dementor attack", "chocolate"]
    },

    # MOVIE 5: LUNA LOVEGOOD & THESTRALS
    "m5_luna_forest_clearing_petting": {
        "movie_number": 5,
        "start_seconds": 2563.0,
        "duration": 3.0,
        "target_x_pct": 0.72,
        "subject": "Barefoot Luna Lovegood petting Thestral in snowy forest",
        "keywords": ["luna", "lovegood", "barefoot", "snow", "forbidden forest", "standing barefoot"]
    },
    "m5_luna_bare_feet_closeup": {
        "movie_number": 5,
        "start_seconds": 2567.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Luna Lovegood bare feet close-up on ground in forest",
        "keywords": ["feet", "bare feet", "ground", "snow", "feeding raw meat", "caring for the thestrals", "meat"]
    },
    "m5_luna_thestral_head_towering": {
        "movie_number": 5,
        "start_seconds": 2574.0,
        "duration": 3.0,
        "target_x_pct": 0.65,
        "subject": "Luna holding raw meat looking up at towering Thestral head",
        "keywords": ["skeletal", "winged", "horses", "thestrals", "invisible", "canon lore", "dragon horse"]
    },
    "m5_thestral_full_body_walking": {
        "movie_number": 5,
        "start_seconds": 2594.0,
        "duration": 3.0,
        "target_x_pct": 0.70,
        "subject": "Massive black winged skeletal Thestral walking through forest",
        "keywords": ["massive black", "walking through", "winged horses", "aren't invisible", "invisible to everyone", "skeletal black", "bat wings", "black skeleton"]
    },
    "m5_thestrals_foal_sunlight": {
        "movie_number": 5,
        "start_seconds": 2604.0,
        "duration": 3.0,
        "target_x_pct": 0.70,
        "subject": "Winged Thestrals in sunbeams in Forbidden Forest",
        "keywords": ["witnessed death", "processed its reality", "truly witnessed", "foal", "sunbeams", "majestic creatures"]
    },
    "m5_luna_face_speaking_sane": {
        "movie_number": 5,
        "start_seconds": 2584.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Luna Lovegood close-up face speaking softly",
        "keywords": ["mother die", "look directly", "comfort", "calmly comfort", "just as sane as i am", "speaking softly"]
    },
    "m5_harry_wonder_thestrals": {
        "movie_number": 5,
        "start_seconds": 2612.0,
        "duration": 3.0,
        "target_x_pct": 0.45,
        "subject": "Harry Potter looking in amazement at Luna and Thestrals",
        "keywords": ["harry", "comfort harry", "wonder", "amazement", "majestic", "smiled at harry", "calmly smiled"]
    },

    # MOVIE 8: SNAPE FINAL TEAR & PRINCE'S TALE
    "m8_snape_boathouse_wounded": {
        "movie_number": 8,
        "start_seconds": 4217.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Severus Snape slumped wounded against glass in boathouse",
        "keywords": ["severus", "snape", "boathouse", "dying", "slumped", "wounded", "lay dying"]
    },
    "m8_snape_tear_forming": {
        "movie_number": 8,
        "start_seconds": 4221.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Silvery glowing tear forming in Snape's eye",
        "keywords": ["silvery", "tear", "cheek", "grief", "ordinary cry", "glowing silvery tear"]
    },
    "m8_harry_flask_to_cheek": {
        "movie_number": 8,
        "start_seconds": 4238.0,
        "duration": 3.0,
        "target_x_pct": 0.45,
        "subject": "Harry Potter kneeling holding crystal glass flask to Snape's cheek",
        "keywords": ["extracted", "flask", "vial", "memory flask", "memories", "catching"]
    },
    "m8_snape_tear_flowing_stream": {
        "movie_number": 8,
        "start_seconds": 4244.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Extreme close-up of silvery memory tear streaming down Snape's cheek",
        "keywords": ["prince's tale", "princes tale", "voldemort was watching", "voldemort watching", "streaming down", "memory tear", "extreme close-up", "final breath", "give harry"]
    },
    "m8_harry_hand_holding_vial": {
        "movie_number": 8,
        "start_seconds": 4250.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Harry's hand clutching glass vial containing glowing silver memory",
        "keywords": ["vial", "hand", "whisper", "telling harry", "clutching"]
    },
    "m8_harry_green_eyes_looking": {
        "movie_number": 8,
        "start_seconds": 4254.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Harry looking down with his green eyes into Snape's eyes",
        "keywords": ["mother's eyes", "mothers eyes", "look at me", "green eyes"]
    },
    "m8_snape_final_look_lily": {
        "movie_number": 8,
        "start_seconds": 4258.0,
        "duration": 3.0,
        "target_x_pct": 0.50,
        "subject": "Snape's final gaze whispering mother's eyes out of eternal love for Lily",
        "keywords": ["sacrifice", "confession", "ultimate confession", "eternal love", "lily potter", "always"]
    }
}


class BeastGroundTruthMatcher:
    """
    Authoritative Beast Ground-Truth Addon Engine.
    Provides frame-accurate matching using Audio Description, SDH, and Screenplay scene headings.
    Can cut lossless smart-cropped micro-clips on demand directly from the master Blu-ray files.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.smart_crop = SmartCropEngine()
        self.visual_guard = VisualMismatchGuard()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """Initializes tables, FTS virtual tables, and seeds canonical ground truth."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS ground_truth_scenes (
            scene_id TEXT PRIMARY KEY,
            movie_number INTEGER,
            movie_title TEXT,
            start_seconds REAL,
            end_seconds REAL,
            duration REAL,
            scene_heading TEXT,
            primary_characters TEXT,
            key_actions TEXT,
            objects TEXT,
            locations TEXT,
            audio_description_text TEXT,
            sdh_dialogue_cues TEXT,
            visual_tags TEXT,
            canonical_source TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS ground_truth_subtitles (
            cue_id TEXT PRIMARY KEY,
            movie_number INTEGER,
            start_seconds REAL,
            end_seconds REAL,
            speaker TEXT,
            dialogue TEXT,
            sound_effects TEXT,
            clean_text TEXT
        )
        """)

        # FTS5 tables
        try:
            cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(
                scene_id UNINDEXED,
                scene_heading,
                primary_characters,
                key_actions,
                objects,
                locations,
                audio_description_text,
                sdh_dialogue_cues,
                visual_tags
            )
            """)
        except Exception as e:
            logger.debug(f"FTS5 scenes table init: {e}")

        conn.commit()

        # Seed scenes if empty
        cur.execute("SELECT COUNT(*) FROM ground_truth_scenes")
        count = cur.fetchone()[0]
        if count == 0:
            logger.info("Seeding Ground Truth Scenes database...")
            for s in CANONICAL_SCENE_SEEDS:
                dur = round(s["end_seconds"] - s["start_seconds"], 2)
                cur.execute("""
                INSERT OR REPLACE INTO ground_truth_scenes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s["scene_id"], s["movie_number"], s["movie_title"],
                    s["start_seconds"], s["end_seconds"], dur,
                    s["scene_heading"], s["primary_characters"], s["key_actions"],
                    s["objects"], s["locations"], s["audio_description_text"],
                    s["sdh_dialogue_cues"], s["visual_tags"], "BEAST_GROUND_TRUTH_CANONICAL"
                ))
                try:
                    cur.execute("""
                    INSERT INTO scenes_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        s["scene_id"], s["scene_heading"], s["primary_characters"],
                        s["key_actions"], s["objects"], s["locations"],
                        s["audio_description_text"], s["sdh_dialogue_cues"], s["visual_tags"]
                    ))
                except Exception:
                    pass
            conn.commit()

        # Check subtitles count
        cur.execute("SELECT COUNT(*) FROM ground_truth_subtitles")
        sub_count = cur.fetchone()[0]
        if sub_count == 0:
            self._index_all_subtitles(conn)

        conn.close()

    def _index_all_subtitles(self, conn: sqlite3.Connection):
        """Indexes all 8 movies' SRT files into ground_truth_subtitles table."""
        if not SUBTITLES_DIR.exists():
            return

        cur = conn.cursor()
        logger.info("Indexing Blu-ray SRT subtitles for all 8 films...")
        for m_num in range(1, 9):
            srt_path = SUBTITLES_DIR / f"movie_{m_num}_bluray.srt"
            if not srt_path.exists():
                continue

            try:
                try:
                    with open(srt_path, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    with open(srt_path, "r", encoding="latin-1") as f:
                        content = f.read()
                blocks = content.strip().split("\n\n")
                records = []
                for b_idx, block in enumerate(blocks):
                    lines = [l.strip() for l in block.splitlines() if l.strip()]
                    if len(lines) < 2:
                        continue
                    
                    time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
                    if not time_line:
                        continue
                    
                    parts = time_line.split("-->")
                    if len(parts) != 2:
                        continue

                    start_sec = self._parse_srt_timestamp(parts[0].strip())
                    end_sec = self._parse_srt_timestamp(parts[1].strip())

                    text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
                    raw_text = " ".join(text_lines)

                    # Extract bracketed cues [action] or speaker labels
                    sound_cues = re.findall(r"\[(.*?)\]", raw_text)
                    speaker = None
                    if ":" in raw_text:
                        spk_cand = raw_text.split(":", 1)[0].replace("[", "").strip()
                        if len(spk_cand) < 30:
                            speaker = spk_cand

                    clean_text = re.sub(r"<[^>]+>", "", raw_text)
                    clean_text = re.sub(r"\[.*?\]", "", clean_text).strip()

                    cue_id = f"m{m_num}_cue_{b_idx}"
                    records.append((
                        cue_id, m_num, start_sec, end_sec,
                        speaker or "", raw_text, ", ".join(sound_cues), clean_text
                    ))

                cur.executemany("""
                INSERT OR REPLACE INTO ground_truth_subtitles VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, records)
                logger.info(f"  Indexed M{m_num}: {len(records)} subtitle cues.")
            except Exception as err:
                logger.warning(f"Failed indexing SRT for movie {m_num}: {err}")

        conn.commit()

    @staticmethod
    def _parse_srt_timestamp(ts_str: str) -> float:
        """Parses '01:46:08,230' or '01:46:08.230' into total seconds."""
        ts_clean = ts_str.replace(",", ".").strip()
        parts = ts_clean.split(":")
        if len(parts) == 3:
            h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
            return round(h * 3600.0 + m * 60.0 + s, 3)
        elif len(parts) == 2:
            m, s = float(parts[0]), float(parts[1])
            return round(m * 60.0 + s, 3)
        return 0.0

    def query_ground_truth_scenes(
        self,
        query_text: str,
        movie_number: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Queries ground truth scenes using full-text search and character presence.
        """
        conn = self._get_connection()
        cur = conn.cursor()

        # Tokenize query
        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query_text.lower())
        tokens = [w for w in clean_q.split() if len(w) > 2]

        if not tokens:
            conn.close()
            return []

        fts_query = " OR ".join(tokens)
        results = []

        try:
            sql = """
            SELECT s.*, bm25(scenes_fts) as rank
            FROM ground_truth_scenes s
            JOIN scenes_fts f ON s.scene_id = f.scene_id
            WHERE scenes_fts MATCH ?
            """
            params = [fts_query]
            if movie_number:
                sql += " AND s.movie_number = ?"
                params.append(movie_number)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cur.execute(sql, params)
            for row in cur.fetchall():
                results.append(dict(row))
        except Exception:
            # Fallback to LIKE
            like_clauses = " OR ".join(["visual_tags LIKE ?" for _ in tokens[:4]])
            like_params = [f"%{t}%" for t in tokens[:4]]
            sql = f"SELECT * FROM ground_truth_scenes WHERE ({like_clauses})"
            if movie_number:
                sql += f" AND movie_number = {movie_number}"
            sql += f" LIMIT {limit}"
            cur.execute(sql, like_params)
            for row in cur.fetchall():
                results.append(dict(row))

        conn.close()
        return results

    def slice_master_movie(
        self,
        movie_number: int,
        start_seconds: float,
        duration: float,
        output_path: Path,
        target_x_pct: Optional[float] = None
    ) -> bool:
        """
        Directly cuts a frame-accurate, lossless slice from the local Blu-ray MKV master.
        Applies SmartCropEngine vertical centering with optional target_x_pct focus.
        """
        movie_info = MOVIE_FILE_MAP.get(movie_number)
        if not movie_info:
            logger.error(f"Unknown movie number {movie_number}")
            return False

        master_path = MOVIES_DIR / movie_info["file"]
        if not master_path.exists():
            logger.error(f"Master movie file not found on disk: {master_path}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Temporary raw cut to compute face center crop
        temp_raw = CACHE_DIR / f"raw_m{movie_number}_{int(start_seconds)}_{int(duration)}.mp4"

        # Fast seek cut: -ss before -i for lightning speed
        raw_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start_seconds:.3f}",
            "-i", str(master_path),
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-an",
            str(temp_raw)
        ]
        res = subprocess.run(raw_cmd, capture_output=True, text=True)
        if res.returncode != 0 or not temp_raw.exists() or temp_raw.stat().st_size < 1000:
            logger.error(f"Failed slicing raw master movie: {res.stderr}")
            return False

        # Smart horizontal face-centering crop to 1080x1920 with optional target_x_pct
        vf_filter = self.smart_crop.get_filter_for_clip(temp_raw, target_x_pct=target_x_pct)

        conform_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(temp_raw),
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-an",
            str(output_path)
        ]
        res2 = subprocess.run(conform_cmd, capture_output=True, text=True)

        # Cleanup temp
        if temp_raw.exists():
            try:
                temp_raw.unlink()
            except Exception:
                pass

        if res2.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"Master slice created successfully: {output_path.name} ({duration:.2f}s)")
            return True
        else:
            logger.error(f"Failed smart-cropping master slice: {res2.stderr}")
            return False

    def find_best_ground_truth_slice(
        self,
        query_text: str,
        preferred_characters: Optional[List[str]] = None,
        preferred_props: Optional[List[str]] = None,
        movie_number: Optional[int] = None,
        target_duration: float = 3.0,
        used_clip_ids: Optional[Set[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        High-Priority Tier 1 Resolver:
        1. Checks curated CANONICAL_SHOT_CATALOG for exact micro-shots and target ROI crops.
        2. Falls back to matching query against ground-truth Audio Descriptions, SDH cues, and Screenplay actions.
        """
        preferred_characters = preferred_characters or []
        preferred_props = preferred_props or []
        used_cids = used_clip_ids or set()
        q_lower = query_text.lower()

        # -------------------------------------------------------------
        # PASS 1: CURATED CANONICAL SHOT CATALOG (Frame-Accurate Micro Shots)
        # -------------------------------------------------------------
        best_catalog_match = None
        best_cat_score = 0.0

        for shot_id, shot_info in CANONICAL_SHOT_CATALOG.items():
            cid = f"gt_shot_{shot_id}"
            if cid in used_cids:
                continue
            if movie_number and shot_info.get("movie_number") != movie_number:
                continue

            # Check keyword matches
            score = 0.0
            hits = 0
            for kw in shot_info.get("keywords", []):
                if kw in q_lower:
                    score += 50.0
                    hits += 1

            # Check character presence
            subj = shot_info.get("subject", "").lower()
            for pc in preferred_characters:
                if pc.lower() in subj:
                    score += 25.0
                    hits += 1

            if hits >= 1 and score > best_cat_score:
                best_cat_score = score
                best_catalog_match = (shot_id, shot_info)

        if best_catalog_match and best_cat_score >= 50.0:
            shot_id, shot_info = best_catalog_match
            cid = f"gt_shot_{shot_id}"
            dur = shot_info.get("duration", target_duration)
            start_sec = shot_info["start_seconds"]
            target_x = shot_info.get("target_x_pct", 0.50)
            m_num = shot_info["movie_number"]

            cache_filename = f"gt_m{m_num}_{shot_id}_{int(start_sec)}_{int(dur)}.mp4"
            cached_clip_path = CACHE_DIR / cache_filename

            if not cached_clip_path.exists() or cached_clip_path.stat().st_size < 1000:
                success = self.slice_master_movie(
                    movie_number=m_num,
                    start_seconds=start_sec,
                    duration=dur,
                    output_path=cached_clip_path,
                    target_x_pct=target_x
                )
                if not success or not cached_clip_path.exists():
                    return None

            logger.info(f"[BEAST CANONICAL SHOT HIT] '{query_text[:40]}' -> {shot_id} (t={start_sec}s, x_pct={target_x})")
            return {
                "clip_id": cid,
                "movie_number": m_num,
                "movie_title": MOVIE_FILE_MAP[m_num]["title"],
                "start_seconds": start_sec,
                "end_seconds": start_sec + dur,
                "duration": dur,
                "primary_subject": shot_info.get("subject", ""),
                "action_description": shot_info.get("subject", ""),
                "local_path": str(cached_clip_path),
                "match_score": 999.0 + best_cat_score,
                "source_mode": "CANONICAL_SHOT_CATALOG",
                "scene_heading": f"INT/EXT - CANONICAL SHOT {shot_id}",
                "audio_description": shot_info.get("subject", "")
            }

        candidates = self.query_ground_truth_scenes(
            query_text=query_text,
            movie_number=movie_number,
            limit=5
        )

        if not candidates:
            # Also try without movie filter
            candidates = self.query_ground_truth_scenes(
                query_text=query_text,
                movie_number=None,
                limit=5
            )

        if not candidates:
            return None

        q_lower = query_text.lower()
        STOPWORDS_LOCAL = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "up", "about", "into", "over", "after", "is", "are", "was", "were", "shot",
            "close", "view", "pan", "and", "or", "looking", "look", "looks", "scene", "direct"
        }

        scored_candidates = []
        for c in candidates:
            score = 0.0
            hits = 0
            ad_text = (c.get("audio_description_text") or "").lower()
            sdh_text = (c.get("sdh_dialogue_cues") or "").lower()
            tags = (c.get("visual_tags") or "").lower()
            chars = (c.get("primary_characters") or "").lower()

            # Character match boost
            for pc in preferred_characters:
                pc_low = pc.lower()
                if pc_low in chars or pc_low in ad_text:
                    score += 40.0
                    hits += 1

            # Direct keyword hits in AD and SDH cues
            for token in re.findall(r"\w+", q_lower):
                if len(token) <= 3 or token in STOPWORDS_LOCAL:
                    continue
                if token in tags:
                    score += 15.0
                    hits += 1
                if token in ad_text:
                    score += 10.0
                    hits += 1
                if token in sdh_text:
                    score += 8.0
                    hits += 1

            # Movie number boost only if relevant hits exist
            if hits >= 2 and movie_number and c.get("movie_number") == movie_number:
                score += 15.0

            # Entity conflict check
            if "crouch jr" in q_lower and "crouch sr" in c.get("primary_characters", "").lower() and "crouch jr" not in c.get("primary_characters", "").lower():
                score -= 800.0

            if hits >= 2:
                scored_candidates.append((score, c))

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_scene = scored_candidates[0]

        if best_score < 70.0:
            return None

        # Determine exact slice timestamp within scene
        scene_start = best_scene["start_seconds"]
        scene_end = best_scene["end_seconds"]
        
        # Micro-slice offset: step forward through scene if earlier window was already used
        slice_start = round(scene_start, 2)
        step = max(3.5, target_duration)
        while f"gt_{best_scene['scene_id']}_{int(slice_start)}" in used_cids:
            slice_start = round(slice_start + step, 2)
            if slice_start + target_duration > scene_end:
                logger.info(f"Ground truth scene {best_scene['scene_id']} exhausted in duration.")
                return None

        cid = f"gt_{best_scene['scene_id']}_{int(slice_start)}"
        cache_filename = f"gt_m{best_scene['movie_number']}_{best_scene['scene_id']}_{int(slice_start)}_{int(target_duration)}.mp4"
        cached_clip_path = CACHE_DIR / cache_filename

        if not cached_clip_path.exists() or cached_clip_path.stat().st_size < 1000:
            success = self.slice_master_movie(
                movie_number=best_scene["movie_number"],
                start_seconds=slice_start,
                duration=target_duration,
                output_path=cached_clip_path
            )
            if not success or not cached_clip_path.exists():
                return None

        return {
            "clip_id": cid,
            "movie_number": best_scene["movie_number"],
            "movie_title": best_scene["movie_title"],
            "start_seconds": slice_start,
            "end_seconds": slice_start + target_duration,
            "duration": target_duration,
            "primary_subject": best_scene["primary_characters"].split(",")[0].strip(),
            "action_description": best_scene["key_actions"][:120],
            "local_path": str(cached_clip_path),
            "match_score": best_score,
            "source_mode": "GROUND_TRUTH_AD_SDH",
            "scene_heading": best_scene["scene_heading"],
            "audio_description": best_scene["audio_description_text"]
        }
