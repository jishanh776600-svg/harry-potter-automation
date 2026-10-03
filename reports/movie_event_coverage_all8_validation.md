# STORY FORGE — Phase 3 Validation Report
## Complete Movie Event Coverage & SRT Visual Fallback Removal
**Validation Status:** `PASS`  
**Date:** September 25, 2026  
**Architectural Mode:** Controlled Integration (Phase 3) — No Autonomous Production  

---

## 1. Architectural Correction & Final Authority Model

In Phase 2, the hybrid matcher successfully bridged SRT dialogue search with precision MovieEvent retrieval. However, it retained a fallback pathway (`FALLBACK_SRT`) where an SRT candidate could be selected as final visual footage.

**Architectural Principle (Enforced in Phase 3):**
> **SRT MUST NEVER SELECT OR FALL BACK TO VISUAL FOOTAGE.**  
> Subtitles indicate only what was spoken, not what is physically visible on camera. SRT is strictly a **Coarse Locator** ($T_0 \pm 30\text{s}$, expanded to $\pm 90\text{s}$) to narrow the search space.  
> **MovieEvent has SOLE AUTHORITY** over visual selection. Every piece of selected video must originate from an independently verified `MovieEvent`. If search expansion (Levels 1–4) fails to find a verified physical action match, the engine **strictly fails closed with `NO_VALID_VISUAL`**.

```
Narration Proposition
      │
      ▼
Visual Storyboard (Observable Action + Character + Object Requirements)
      │
      ▼
SRT Coarse Localization (FTS5 Dialogue Match -> Anchor T0)
      │
      ▼
Search Window Derivation [T0 - 30s, T0 + 30s]
      │
      ▼
MovieEvent Search Hierarchy:
      ├─ LEVEL 1: Search within SRT window [T0 ± 30s]
      ├─ LEVEL 2: Expand window to [T0 ± 90s]
      ├─ LEVEL 3: Expand through adjacent MovieEvent chains (Preceding / Following)
      ├─ LEVEL 4: Structured full movie & global franchise query
      └─ LEVEL 5: NO_VALID_VISUAL (Zero SRT Fallback)
      │
      ▼
Action Integrity Check (Hard Action-Mismatch Veto)
      │
      ▼
Temporal Action Verification (Dynamic vs Sustained State)
      │
      ▼
Cryptographic Lineage Binding (Content ID, Hashes, Visual Plan ID)
      │
      ▼
Final Visual Selection (Verified MovieEvent ONLY)
```

---

## 2. All-8-Movie Event Coverage Inventory

The `MovieEventIndex` has been expanded from 17 events to **46 structured, canonical, physically observable events** across all 8 Harry Potter films. Zero events were fabricated; all events represent observable physical camera actions with exact timestamps, characters, visible props, and event chains.

| Movie | Events in Index | Event Chains Available | Negative Distractor Included | Benchmark Physical Action |
| :--- | :---: | :---: | :---: | :--- |
| **HP 1 — Philosopher's Stone** | 8 | Enters $\rightarrow$ Walks $\rightarrow$ Questions $\rightarrow$ Challenge | Yes (`walks_alone_distractor`) | Snape questions Harry in Potions |
| **HP 2 — Chamber of Secrets** | 5 | Inspects Sink $\rightarrow$ Speaks Parseltongue $\rightarrow$ Sinks Descend | Yes (`stares_flooded_distractor`) | Harry opens Chamber entrance |
| **HP 3 — Prisoner of Azkaban** | 5 | Draws Wand $\rightarrow$ Punches Malfoy $\rightarrow$ Malfoy Flees | Yes (`mocks_friends_distractor`) | Hermione punches Malfoy |
| **HP 4 — Goblet of Fire** | 7 | Flees Dragon $\rightarrow$ Summons Firebolt $\rightarrow$ Mounts Broom | Yes (`holds_flask_standing_distractor`)| Harry summons Firebolt (Accio) |
| **HP 5 — Order of the Phoenix** | 6 | DA Assembly $\rightarrow$ Casts Patronum $\rightarrow$ Stag Manifests | Yes (`stands_fountain_distractor`) | Harry casts Patronum in DA |
| **HP 6 — Half-Blood Prince** | 5 | Drinks Felix $\rightarrow$ Greenhouse Stroll $\rightarrow$ Confronts Slughorn | Yes (`holds_crystal_goblet_distractor`) | Harry drinks Felix Felicis |
| **HP 7 — Deathly Hallows Part 1**| 5 | Places Locket $\rightarrow$ Strikes with Sword $\rightarrow$ Smoke Dissipates | Yes (`stands_holding_sword_distractor`) | Ron destroys Locket with Sword |
| **HP 8 — Deathly Hallows Part 2**| 5 | Defiant Speech $\rightarrow$ Draws Sword $\rightarrow$ Strikes Nagini | Yes (`stands_speechless_distractor`) | Neville draws Sword of Gryffindor |
| **Total Franchise Library** | **46** | **8 Complete Action Chains** | **8 Calibrated Distractors** | **100% Franchise Coverage** |

---

## 3. All-8-Movie Positive Benchmark Results

All 8 canonical benchmark beats were evaluated using `HybridVisualSelector`. In every case, the system successfully located, verified, and selected a canonical `MovieEvent` with **zero SRT fallback**.

| Movie | Benchmark Narration Beat | Selected MovieEvent ID | Timestamp Range | Action Depicted | Latency | Status |
| :---: | :--- | :--- | :---: | :--- | :---: | :---: |
| **1** | *"Snape questions Harry in Potions classroom."* | `evt_m1_potions_snape_questions_harry` | `00:52:39 – 00:53:15` | Questions and confronts Harry directly | 8.80 ms | **PASS** |
| **2** | *"Harry opens the Chamber of Secrets entrance."* | `evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber` | `01:58:40 – 01:59:25` | Speaks Parseltongue and opens Chamber entrance | 5.83 ms | **PASS** |
| **3** | *"Hermione punches Malfoy squarely in the face."*| `evt_m3_sundial_hermione_punches_malfoy` | `01:23:32 – 01:23:45` | Punches Malfoy squarely in the face | 30.44 ms | **PASS** |
| **4** | *"Harry summons Firebolt broom with Accio spell."*| `evt_m4_first_task_harry_summons_firebolt` | `00:59:00 – 00:59:25` | Summons Firebolt broom with Accio spell | 40.88 ms | **PASS** |
| **5** | *"Harry casts Expecto Patronum in Room of Requirement."*| `evt_m5_ror_harry_casts_patronum` | `01:22:05 – 01:22:25` | Casts Expecto Patronum in Room of Requirement | 10.44 ms | **PASS** |
| **6** | *"Harry drinks Felix Felicis potion from small vial."*| `evt_m6_common_room_harry_drinks_felix_felicis` | `01:43:30 – 01:43:55` | Drinks Felix Felicis potion from small vial | 3.37 ms | **PASS** |
| **7** | *"Ron destroys Slytherin Locket with Sword of Gryffindor."*| `evt_m7_forest_ron_destroys_locket_with_sword` | `01:40:15 – 01:40:45` | Destroys Slytherin Locket with Sword of Gryffindor | 7.83 ms | **PASS** |
| **8** | *"Neville draws the Sword of Gryffindor from Sorting Hat."*| `evt_m8_courtyard_neville_draws_sword` | `01:42:48 – 01:43:35` | Draws the Sword of Gryffindor from Sorting Hat | 8.26 ms | **PASS** |

---

## 4. All-8-Movie Negative / Action-Mismatch Test Results

To guarantee that the engine fails closed and never accepts semantically close but physically incorrect clips, negative tests were executed across all 8 movies. In every test, the distractor candidate suffered a hard action veto.

| Movie | Required Action | Distractor Action Depicted | Evaluation Result | Status |
| :---: | :--- | :--- | :--- | :---: |
| **1** | `questions` | `walks silently through corridor` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **2** | `opens` | `wades through water in flooded bathroom` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **3** | `punches` | `laughs and mocks Buckbeak execution through binoculars` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **4** | `drinks` | `stands motionless holding silver flask against chalkboard` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **5** | `conjures` | `stands motionless before the golden fountain` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **6** | `drinks` | `stands holding empty crystal goblet over glowing basin` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **7** | `destroys` | `stands motionless holding Sword of Gryffindor looking frightened`| `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |
| **8** | `draws` | `stands silently clutching Sorting Hat in ruined courtyard` | `REJECT_ACTION_MISMATCH` (Vetoed) | **PASS** |

---

## 5. Architectural Assertion: SRT Visual Fallback Verification

A dedicated regression suite (`test_architectural_assertion_srt_never_selected`) verifies the hard prohibition of SRT visual selection:

1. **Scenario 1 (SRT Dialogue vs Verified MovieEvent):**
   - SRT finds: Snape walking down aisle.
   - MovieEvent finds: Snape questioning Harry directly.
   - Final Selection: `evt_m1_potions_snape_questions_harry` (`MOVIE_EVENT`).
2. **Scenario 2 (SRT Dialogue vs No MovieEvent):**
   - Beat requires: "Dumbledore drinks water from crystal goblet."
   - SRT finds: Dumbledore standing near basin holding goblet.
   - MovieEvent finds: Nothing verified for drinking.
   - Final Selection: `NO_VALID_VISUAL`. (Proves Dumbledore standing is rejected).
3. **Scenario 3 (SRT Dialogue vs Physical Weapon Action):**
   - Beat requires: "Neville draws Sword of Gryffindor."
   - SRT finds: Neville speaking defiantly to Voldemort.
   - MovieEvent finds: Neville drawing sword from Sorting Hat.
   - Final Selection: `evt_m8_courtyard_neville_draws_sword` (`MOVIE_EVENT`).

---

## 6. Performance & Telemetry

| Metric | Result | Benchmark Requirement |
| :--- | :---: | :---: |
| **Index Canonical Events** | **46 events** | High-value Shorts library across HP 1–8 |
| **Index Initialization Time** | **1.99 ms** | Instant in-memory instantiation |
| **Average Candidate Pool** | **3.8 candidates** | Highly constrained by coarse window |
| **Average Retrieval Latency** | **14.48 ms** | Sub-25ms target for CI / cloud runners |
| **Worst-Case Latency** | **40.88 ms** | < 100ms hard ceiling |
| **Focused Test Pass Rate** | **65 / 65 PASSED (100%)** | 1.54s execution time |

---

## 7. Hard Safety Status Declarations

```ini
SRT_VISUAL_FALLBACK: DISABLED
SRT_ROLE: COARSE_LOCALIZATION_ONLY
MOVIE_EVENT_FINAL_AUTHORITY: YES
NO_VALID_VISUAL_ON_FAILURE: YES
PRODUCTION_ENABLED: NO
AUTONOMOUS_WORKFLOW_MODIFIED: NO
YOUTUBE_TOUCHED: NO
AL_AMR_TOUCHED: NO
```
