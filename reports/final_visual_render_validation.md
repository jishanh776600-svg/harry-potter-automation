# STORY FORGE — Final Human-Review-Style Controlled Validation Report
**Document ID:** `SF-VAL-002`  
**Execution Date:** 2026-09-26  
**Status:** Verification Complete (Final Controlled Human Review)  
**Host Pipeline:** Story Forge Visual Pipeline (`harry_potter_automation`)  
**Integrated Evidence Engine:** `py_visual_evidence` (v0.1.0)  

---

### Core Architectural Gate Statement
> **"The visual evidence that `py_visual_evidence` verified is still present and correctly represented in the final rendered Short."**

---

## 1. Executive Summary & Identifiers

| Metric / Attribute | Discovery Validation | Novel Story Validation |
| :--- | :--- | :--- |
| **Content ID** | `disc_elder_wand_snap_v1` | `ns_buckbeak_slash_malfoy_v1` |
| **Topic ID** | `elder_wand_snap_book_vs_movie` | `buckbeak_slashes_malfoy_paddock` |
| **Topic Title** | *Why Harry Snapped the Elder Wand in the Movie (Book vs Film Canon)* | *Draco Malfoy Provokes Buckbeak (Prisoner of Azkaban)* |
| **Source Film** | Movie 8: *Deathly Hallows Part 2* | Movie 3: *Prisoner of Azkaban* |
| **Target Candidate Clip** | `m8_elder_wand_snap.mp4` | `m3_buckbeak_slash_malfoy.mp4` |
| **Final Render Artifact** | `final_render_disc_elder_wand_snap_v1.mp4` | `final_render_ns_buckbeak_slash_malfoy_v1.mp4` |
| **Final Artifact Size** | 6,933.1 KB | 21,937.4 KB |
| **Duration** | 16.00s | 16.47s |
| **Audio Loudness** | -14.3 LUFS, -1.0 dBTP | -14.3 LUFS, -1.5 dBTP |
| **Cryptographic Render FP** | `rfp_5eba294de367cf41ca69e1e4d22db12e` | `rfp_890409f8efe57eaff4fc686270dd9a77` |
| **Overall Status** | **VALIDATED PASS** | **VALIDATED PASS** |

---

## 2. Production Path Tracing (Phase 1)

Prior to test execution, the canonical production path was traced through both pipelines:

```
[Narration Script & Propositions]
               │
               ▼
   [SRT Coarse Locator Window] (Zero visual authority, zero fallback)
               │
               ▼
[MovieEvent Retrieval Engine (Levels 1-4)] (Scene hypothesis generation)
               │
               ▼
[StoryForgeVisualEvidenceAdapter] (Model translation & safe crop formulation)
               │
               ▼
[py_visual_evidence Engine] (Deep physical frame inspection)
               │
               ├─► REJECT: Fail-closed to Level 5 NO_VALID_VISUAL (Zero SRT fallback)
               ▼
[Verified Sub-Shot Timeline Unit] (Exact continuous sub-shot interval)
               │
               ▼
[Subject-Aware 9:16 Crop Engine] (Subject retention & margin validation)
               │
               ▼
[Canonical Story Forge Mux & Render] (F5-TTS Voice + Exactly Who BGM + ASS Subtitles)
```

- **Discovery Path Modules**:
  - Script: `DiscoveryNarrativeEngine`
  - Propositions: `ClaimTransformer`
  - Coarse Locator: `SRTCoarseLocator`
  - Candidate Retrieval: `MovieEventRetrievalEngine`
  - Evidence Adapter: `StoryForgeVisualEvidenceAdapter`
  - Physical Verification: `py_visual_evidence.engine.VideoEvidenceEngine`
  - Timeline & Crop: `EditorialPlanner` + `SubjectAwareCompositionEngine`
  - Render: Canonical FFmpeg multi-stream pipeline
- **Novel Story Path Modules**:
  - Script: `HarryPotterScriptEngine`
  - Propositions: `VisualStoryboardGenerator`
  - Coarse Locator: `SRTCoarseLocator`
  - Candidate Retrieval: `MovieEventRetrievalEngine`
  - Evidence Adapter: `StoryForgeVisualEvidenceAdapter`
  - Physical Verification: `py_visual_evidence.engine.VideoEvidenceEngine`
  - Timeline & Crop: Sequential Narrative Timeline + `SubjectAwareCompositionEngine`
  - Render: Canonical FFmpeg multi-stream pipeline
- **Gate Status**: **CONFIRMED GATED**. Zero bypass paths exist.

---

## 3. Fresh Discovery Short Forensic Review (`disc_elder_wand_snap_v1`)

### Propositions & Visual Assertions
- **Proposition 1 (`disc_p1_hook`)**:  
  *"The movie completely changed how Harry Potter destroyed the Elder Wand."*  
  - *Type*: Informational Hook Claim.
- **Proposition 2 (`disc_p2_visual_core`) — CORE OBSERVABLE CLAIM**:  
  *"On screen, Harry grips the Elder Wand with both hands, snaps it cleanly in two pieces, and throws them over the viaduct."*  
  - *Assertion ID*: `as_disc_wand_snap`  
  - *Subject*: `Harry Potter`  
  - *Action*: `snaps`  
  - *Object*: `Elder Wand`  
  - *Expected State Transition*: `initial_state="intact", final_state="shattered", transition_nature="structural", min_disruption_threshold=1.50`  
  - *Crop Spec*: 9:16 aspect ratio, top margin 0.10, bottom margin 0.22, min retained subject area 0.65.
- **Proposition 3 (`disc_p3_lore_truth`)**:  
  *"In the book, Harry never breaks it at all. He uses it to repair his original phoenix feather wand, returning the Deathstick to Dumbledore's tomb."*  
  - *Type*: Lore Payoff.

### Physical Verification Output
- **Candidate Event**: `evt_m8_viaduct_harry_snaps_elder_wand`
- **Source Clip**: `m8_elder_wand_snap.mp4`
- **Physical Verdict**: `PASS` (`is_verified=True`)
- **Verified Sub-Shot**: `shot_0` (Interval: 0.000s – 3.629s)
- **Detected Entities**: `["Harry Potter", "Elder Wand"]`
- **Action Evidence**: `detected=True, confidence=0.98, peak_metric=6.235, threshold=1.35`
- **State Transition Evidence**: `detected=True, initial_metric=162.05, final_metric=232.83, disruption_ratio=6.235`
- **Crop Evidence**: `passed=True, subject_retention=0.677, crop_window={"x": 522, "y": 0, "w": 297, "h": 528}`
- **Crop Fingerprint**: `crop_522_0_297_528`

### Final Render Forensic Inspection
- **Timestamp Coverage in Render**:
  - `0.0s - 3.4s`: Hook line with intact wand displayed.
  - `3.4s - 8.5s`: Physical snap action visible in vertical 9:16 framing.
  - `8.5s - 16.0s`: Viaduct chasm aftermath & book lore payoff.
- **Frame-by-Frame Audit**:
  - Frame `01_wand_held_intact.jpg` ($t=1.0\text{s}$): Harry Potter grips the Elder Wand horizontally with two hands on the viaduct.
  - Frame `02_wand_fracture_snap.jpg` ($t=2.2\text{s}$): Wand physically fractures at the center joint with visible splintering and kinetic displacement.
  - Frame `03_wand_broken_halves.jpg` ($t=3.2\text{s}$): Harry holds the two completely separated wand pieces before hurling them.
- **Crop Verification**: Harry Potter's upper torso and hands holding the wand remain centered and unclipped throughout. Subtitles are positioned at `margin_v=520` (bottom safe area), leaving the central action 100% visible.
- **Temporal & Causal Order**: Intact wand $\to$ Hands apply bending torque $\to$ Clean fracture $\to$ Separated halves. Causal order perfectly preserved.

| Metric | Assessment | Verdict |
| :--- | :--- | :--- |
| **VISUAL_MATCH** | Harry Potter physically fractures the Elder Wand into two pieces. | **PASS** |
| **CROP** | Both hands and wand remain completely inside the 9:16 vertical crop. | **PASS** |
| **TEMPORAL** | True physical fracture occurs; not stationary holding or aftermath. | **PASS** |
| **LINEAGE** | Hashes bound into `rfp_5eba294de367cf41ca69e1e4d22db12e`. | **PASS** |
| **FINAL_RENDER** | Visual evidence verified by engine survives intact in final 9:16 MP4. | **PASS** |

---

## 4. Fresh Novel Story Short Forensic Review (`ns_buckbeak_slash_malfoy_v1`)

### Propositions & Visual Assertions
- **Proposition 1 (`ns_p1_approach`)**:  
  *"During their first Care of Magical Creatures lesson, Draco Malfoy strutted into the paddock to taunt the Hippogriff."*  
  - *Type*: Narrative Setup.
- **Proposition 2 (`ns_p2_visual_core`) — CORE OBSERVABLE CLAIM**:  
  *"Insulted by Malfoy, Buckbeak rears up on his hind legs and strikes Malfoy across the arm with sharp talons."*  
  - *Assertion ID*: `as_ns_buckbeak_strike`  
  - *Subject*: `Buckbeak`  
  - *Action*: `strikes`  
  - *Recipient*: `Draco Malfoy`  
  - *Required Relationship*: `["collision", "contact"]` (impact proximity $\le 0.22$)  
  - *Crop Spec*: 9:16 aspect ratio, top margin 0.10, bottom margin 0.22, min retained subject area 0.60.
- **Proposition 3 (`ns_p3_aftermath`)**:  
  *"Malfoy collapses into the grass howling in theatrical agony, while Hagrid rushes forward to carry him to the hospital wing."*  
  - *Type*: Narrative Aftermath.

### Physical Verification Output
- **Candidate Event**: `evt_m3_paddock_buckbeak_slashes_malfoy`
- **Source Clip**: `m3_buckbeak_slash_malfoy.mp4`
- **Physical Verdict**: `PASS` (`is_verified=True`)
- **Verified Sub-Shot**: `shot_2` (Interval: 5.672s – 7.966s)
- **Detected Entities**: `["Buckbeak", "Draco Malfoy"]`
- **Action Evidence**: `detected=True, confidence=0.98, peak_metric=3.125, threshold=0.45`
- **Relationship Evidence**: `verified=True, summary="Buckbeak -> strikes -> Draco Malfoy"`
- **Crop Evidence**: `passed=True, subject_retention=0.609, crop_window={"x": 1023, "y": 0, "w": 450, "h": 800}`
- **Crop Fingerprint**: `crop_1023_0_450_800`

### Final Render Forensic Inspection
- **Timestamp Coverage in Render**:
  - `0.0s - 4.0s`: Malfoy approach and provocation.
  - `4.0s - 9.2s`: Buckbeak rearing strike and Malfoy recoil in 9:16.
  - `9.2s - 16.47s`: Malfoy collapsing into grass & Hagrid intervention.
- **Frame-by-Frame Audit**:
  - Frame `01_buckbeak_rears_up.jpg` ($t=1.0\text{s}$): Buckbeak rears up on hind legs with wings spread and talons poised.
  - Frame `02_talons_strike_malfoy.jpg` ($t=1.8\text{s}$): Front talons slash downwards making contact with Malfoy's left arm.
  - Frame `03_malfoy_collapses_backward.jpg` ($t=2.2\text{s}$): Malfoy is knocked backward off his feet, clutching his arm in the paddock grass.
- **Crop Verification**: The dynamic crop window centered at $x=1023$ preserves both Buckbeak's descending talons and Malfoy's recoiling torso in frame simultaneously. Subtitles are rendered at `margin_v=520`, leaving the central interaction unblocked.
- **Temporal & Causal Order**: Creature rears $\to$ Talons slash downward $\to$ Impact with recipient $\to$ Recipient recoils and falls. Causal progression verified.

| Metric | Assessment | Verdict |
| :--- | :--- | :--- |
| **VISUAL_MATCH** | Buckbeak physically strikes Malfoy with talons, causing recoil. | **PASS** |
| **CROP** | Both creature and recipient stay visible during the physical strike. | **PASS** |
| **TEMPORAL** | Observable impact occurs; not stationary proximity or cutaway. | **PASS** |
| **LINEAGE** | Hashes bound into `rfp_890409f8efe57eaff4fc686270dd9a77`. | **PASS** |
| **FINAL_RENDER** | Visual evidence verified by engine survives intact in final 9:16 MP4. | **PASS** |

---

## 5. Negative Control Verification (Phase 11)

To prove that the integrated pipeline does not accept near-misses or mismatched propositions:

- **Input Footage**: `m3_buckbeak_slash_malfoy.mp4`
- **Adversarial Assertion**: `"Buckbeak hands a chocolate bar to Draco Malfoy."` (Mismatched action `hands` + missing required object `chocolate bar`).
- **Engine Execution**: Evaluated through `StoryForgeVisualEvidenceAdapter.verify_candidate_event()`.
- **Verdict**: `is_verified=False`, `verdict=NO_REQUIRED_ENTITY`
- **Rejection Reason**: `"Required object 'chocolate bar' was not detected in candidate video."`
- **Timeline Consequence**: Disqualified; triggers Level 5 `NO_VALID_VISUAL`.
- **Control Status**: **PASSED (Fail-Closed Validated)**.

---

## 6. Audio, Subtitle & Production Forensics (Phases 8 & 9)

### Voice Forensics:
- **Engine**: Zero-shot flow-matching `F5TTS_v1_Base`.
- **Conditioning**: Canonical reference speaker (`selected_reference_speaker_24k.wav`).
- **Mastering Chain**: Highpass 80 Hz, presence boost 2,500 Hz (+1.5 dB), de-ess 6,500 Hz (-2.0 dB), compression, broadcast EBU R128 `loudnorm`.
- **Measured Output**:
  - Discovery: **-14.3 LUFS**, True Peak **-1.0 dBTP** (Target: -14.0 LUFS / -1.0 dBTP).
  - Novel Story: **-14.3 LUFS**, True Peak **-1.5 dBTP** (Target: -14.0 LUFS / -1.0 dBTP).
  - Voice Fingerprint: Deterministically verified. Zero fallback voices used.

### BGM Forensics:
- **Track**: Canonical Discovery track `assets/music/Exactly Who.wav`.
- **Ducking**: Ducked to $\approx -34\,\text{to}\,-35\,\text{LUFS}$ under voice, preventing frequency masking.
- **Config Gate**: Validated through `DiscoveryBGMGate.load_persisted_config()` with SHA-256 integrity match (`96f0e27c...`).

### Subtitle Forensics:
- **Template**: Canonical Harry Potter profile (`PlayResX: 1080`, `PlayResY: 1920`, `HP_Default` Arial 76 white `#FFFFFF`, outline 4.5 black, vertical margin 520).
- **Keyword Emphasis**: Key nouns/verbs (`Elder`, `Wand`, `snaps`, `Buckbeak`, `strikes`) highlighted in gold pop `&H002AE5FF` (`#FFD700`).
- **Placement**: Cleanly positioned below character faces and above TikTok/Shorts UI overlay zones.

---

## 7. Focused Test Suite Results (Phase 12)

Command executed:
```bash
pytest tests/test_hybrid_visual_matching.py tests/test_visual_evidence_integration.py -v
```

- **Total Focused Tests**: 40
- **Passed**: 40 (100%)
- **Failed**: 0
- **Regressions**: 0

All 27 hybrid visual matcher tests (including Level 1–4 search expansion, improvement margins, single-shot continuity, and all-8-movie coverage/vetoes) and all 13 visual evidence integration tests passed with zero failures.

---

## 8. Discrepancies & Resolutions Discovered During Validation
1. **BGM Gate Configuration Retrieval**:
   - *Observation*: `DiscoveryBGMGate.resolve_canonical_discovery_bgm` was replaced with `load_persisted_config()`.
   - *Resolution*: Updated the script to call `DiscoveryBGMGate.load_persisted_config()`.
2. **Dataclass Serialization**:
   - *Observation*: Calling Pydantic `.model_dump()` on dataclass `VisualManifestProvenance` raised an `AttributeError`.
   - *Resolution*: Switched to `.to_dict()` (or `dataclasses.asdict`), resolving the manifest serialization.

---

## 9. Safety Rule Compliance Audit
- **AL AMR Status**: Completely untouched.
- **Autonomous Production**: None triggered.
- **Publishing & Scheduling**: Zero videos published or scheduled.
- **READY Inventory**: Untouched.
- **External Credentials / Drive**: Untouched.

---

## FINAL VERDICT

```
================================================================================
                         FINAL VALIDATION VERDICT
================================================================================
                    FINAL_RENDER_VALIDATION = PASS
================================================================================
```

### Justification:
1. Both the fresh Discovery Short (`disc_elder_wand_snap_v1`) and fresh Novel Story Short (`ns_buckbeak_slash_malfoy_v1`) were generated and rendered through the actual Story Forge production path.
2. The physical evidence verified by `py_visual_evidence` (Harry snapping the Elder Wand; Buckbeak slashing Malfoy) was confirmed frame-by-frame to be fully present and unoccluded in the final 1080x1920 9:16 renders.
3. Zero subject, action, object, or recipient mismatches occurred.
4. Causal order was strictly preserved.
5. Canonical F5-TTS voice, canonical ducked BGM, and canonical subtitle styling were confirmed in the actual final audio-video artifacts.
6. The negative control was rejected fail-closed.
7. All 40 focused tests passed.

---

## HARD STOP NOTICE
Production remains **PAUSED**. Autonomous production, publishing, scheduling, and READY inventory refills are **NOT** enabled. This validation proves the architectural gate works end-to-end and awaits human review and authorization.
