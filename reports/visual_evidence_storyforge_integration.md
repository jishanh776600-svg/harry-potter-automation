# STORY FORGE — Visual Evidence Engine Integration Report
**Document ID:** `SF-VE-INT-001`  
**Status:** Verification Complete (Awaiting Human Sign-off)  
**Date:** 2026-09-26  
**Engine:** `py_visual_evidence` (v0.1.0)  
**Host System:** Story Forge Visual Pipeline (`harry_potter_automation`)  

---

### Core Architectural Invariant
> **Visual evidence verification is now a mandatory gate before a MovieEvent clip can enter the Story Forge visual timeline.**

Under no circumstances may a MovieEvent candidate or subtitle chunk enter the final timeline as supporting evidence for a narrative assertion unless `py_visual_evidence` has physically inspected and verified that assertion against the underlying video frames.

---

## 1. Executive Summary of Integration
The standalone, domain-agnostic `py_visual_evidence` video verification engine has been fully integrated into Story Forge's hybrid visual retrieval pipeline (`harry_potter_automation`). 

Story Forge previously relied on semantic and lexical alignment between narrative propositions and cataloged `MovieEvent` entries, coupled with coarse temporal localization from SRT subtitle cues. With this integration, semantic hypothesis generation is decoupled from physical verification: `MovieEvent` retrieval generates candidate clips, and `py_visual_evidence` acts as an absolute physical gatekeeper before any clip is granted admittance to the visual timeline.

A comprehensive 40-test verification suite was executed:
- **27/27** existing hybrid visual matcher tests passed with zero regressions.
- **13/13** end-to-end integration tests passed, covering controlled fresh Discovery and Novel Story propositions, multi-proposition timeline independence, 9:16 crop synchronization, cryptographic lineage tamper invalidation, and all 10 negative fail-closed integration scenarios.

---

## 2. Authority Hierarchy
The visual pipeline operates under a strict three-tier authority hierarchy:

```
+-----------------------------------------------------------------------------+
|                                AUTHORITY HIERARCHY                          |
+-----------------------------------------------------------------------------+
| 1. SRT Subtitles                                                            |
|    - Authority: Temporal Coarse Locator ONLY                                |
|    - Visual Authority: ZERO                                                 |
|    - Fallback Authority: ZERO (SRT fallback strictly prohibited)             |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| 2. MovieEvent Retrieval Engine                                              |
|    - Authority: Scene Hypothesis & Candidate Retrieval                      |
|    - Function: Multi-tier index search (Levels 1-4)                         |
|    - Visual Authority: None (generates hypotheses, not physical proof)       |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| 3. py_visual_evidence Engine                                                |
|    - Authority: FINAL PHYSICAL PROOF                                        |
|    - Function: Physical frame inspection (entities, motion, relations,      |
|      state transitions, causal order, shot boundaries, 9:16 safe crop)      |
|    - Rejection: Fails closed to Level 5 NO_VALID_VISUAL                     |
+-----------------------------------------------------------------------------+
```

1. **SRT Subtitles (`SRTCoarseLocator`)**:
   Provides an initial time window based on speech and dialogue. It possesses zero visual authority. If an event cannot be physically grounded, the pipeline never falls back to an SRT-only clip.
2. **MovieEvent Retrieval (`MovieEventRetrievalEngine` / `HybridVisualSelector`)**:
   Formulates candidate visual hypotheses matching characters, actions, and settings across Levels 1–4.
3. **Physical Evidence Engine (`py_visual_evidence` via `StoryForgeVisualEvidenceAdapter`)**:
   Holds sole decision authority. Every candidate event must undergo deep video inspection. If inspection rejects the clip (e.g. action absent, character mismatch, shot cut violation, or crop subject occlusion), the candidate is disqualified. If no candidate passes, the pipeline terminates at Level 5 with `NO_VALID_VISUAL`.

---

## 3. Adapter Design & Domain Translation
To preserve strict separation of concerns, `py_visual_evidence` remains 100% domain-agnostic, containing zero Harry Potter lore or Story Forge data models. All domain mappings reside in:
`engines/visual_evidence/storyforge_adapter.py`

### Key Components:
- **`StoryForgeVisualEvidenceAdapter`**:
  Translates Story Forge data models (`VisualBeat`, Discovery / Novel Story proposition dictionaries) into `py_visual_evidence.schema.VisualAssertion`.
- **Entity & Lore Resolution**:
  Translates narrative references into canonical entity specifications and physical bounding box tracking hints (e.g., resolving "The Boy Who Lived" -> "Harry Potter", "The Headmaster" -> "Albus Dumbledore").
- **Kinematic & State Transition Detection**:
  Parses action strings to identify expected physical state transitions (e.g., words like `snap`, `break`, `split` automatically formulate a `StateTransitionSpec(initial_state="INTACT", final_state="BROKEN")`; words like `shatter`, `disintegrate` map to `final_state="SHATTERED"`).
- **Spatial Relationship Detection**:
  Maps action verbs to physical proximity requirements (e.g., `punches`, `strikes` enforce impact proximity $\le 0.22$; `hands`, `gives` enforce transfer proximity $\le 0.40$).

---

## 4. Candidate Extraction & Micro-Interval Handling
In production, full feature film containers (e.g. 2.5-hour MKVs, ~3GB) cannot be passed directly into full-video PySceneDetect passes without inducing multi-minute delays.

### Solution:
`StoryForgeVisualEvidenceAdapter.verify_candidate_event` implements high-speed candidate extraction:
- Detects video containers exceeding 50 MB.
- Invokes FFmpeg stream copy / ultrafast extraction targeting the candidate interval: `[event.start_time, event.end_time]`.
- Caches micro-clips in `data/clips/evidence_cache/{candidate_id}_{start}_{end}.mp4` (~0.25s execution).
- `py_visual_evidence` operates on the micro-clip with sub-second latency, providing frame-accurate PySceneDetect and Farnebäck optical flow analysis.
- The adapter maps sub-shot timestamps back to master movie container coordinates:
  $$\text{source\_start} = \text{sub\_shot\_start} + \text{extracted\_offset}$$
  $$\text{source\_end} = \text{sub\_shot\_end} + \text{extracted\_offset}$$

---

## 5. Multi-Proposition Independence Findings
To prevent visual "stretching" or silent reuse across narrative beats, each proposition is verified in total isolation:

- **Isolated Verification**: Proposition $P_n$ evaluates candidate footage exclusively against assertion $A_n$.
- **No Cascade Spillover**: If proposition $P_1$ passes with candidate $C_1$ and $P_2$ passes with candidate $C_2$, but proposition $P_3$ fails physical verification, the pipeline **never** stretches $C_1$ or $C_2$ to cover $P_3$.
- **Verified Behavior**: Confirmed by `test_multi_proposition_timeline_independence`. Proposition 3 failed closed as `NO_VALID_VISUAL` with `selected_candidate=None`, leaving $P_1$ and $P_2$ uncompromised.

---

## 6. Sub-Shot Mapping & Visual Beat Boundary Handling
Cinematic movie events frequently span multiple camera angles or cuts. `py_visual_evidence` enforces strict single-shot integrity:

- **PySceneDetect Boundary Detection**: Clips are segmented into atomic sub-shots ($\text{shot\_0}, \text{shot\_1}, \dots$).
- **Atomic Assertion Verification**: Actions, spatial trajectories, and entity tracking are evaluated strictly within continuous camera shots. Physical evidence is never aggregated across a hard cut.
- **Continuous Shot Invariant**: When an assertion requires an uninterrupted shot (`require_uninterrupted_shot=True`), candidates with internal shot boundaries fail closed (`SHOT_BOUNDARY_CONFLICT`).
- **Precision Sub-Shot Trimming**: If a multi-shot candidate contains a verified sub-shot, the timeline unit is trimmed exactly to that sub-shot's start and end timestamps, discarding unverified preceding or succeeding footage.

---

## 7. 9:16 Crop Synchronization Findings
Horizontal 16:9 movie footage must be cropped to 9:16 vertical video for mobile delivery without occluding the physical evidence:

- **Subject-Aware Composition**: The adapter incorporates `CropSpec` configuring 9:16 aspect ratio, safe vertical margins (top 10%, bottom 22% for subtitle/UI clearance), and horizontal safe margins (5%).
- **Crop Retention Validation**: Bounding boxes of all required entities are mapped into the candidate crop window. If a subject or object is pushed outside the crop boundaries or falls below required retention ($<70\%$), the engine returns `CROP_SUBJECT_LOST`.
- **Cryptographic Crop Fingerprinting**: The exact crop window $(x, y, w, h)$ is hashed into a `crop_fingerprint` (e.g. `crop_735_0_450_800`). Any downstream modification to crop coordinates alters this fingerprint and immediately invalidates manifest lineage.

---

## 8. Cryptographic Lineage Changes & Tamper Detection
The cryptographic lineage system in `core/visual_artifact_lineage.py` has been updated to bind physical evidence:

```
+-----------------------------------------------------------------------------+
|                          CRYPTOGRAPHIC MANIFEST LINEAGE                     |
+-----------------------------------------------------------------------------+
| Narration Hash:        SHA256(cleaned_voiceover_script)[:16]                 |
| Proposition Hash:      SHA256(sorted_propositions)[:16]                     |
| Visual Plan ID:        SHA256(narr_hash + prop_hash)[:16]                   |
| Source Evidence Hash:  SHA256(sub_shot_id + engine_version +                |
|                               crop_fingerprint + verdict)[:16]              |
| Timeline Hash:         SHA256(timeline_units)[:16]                          |
| Master Render FP:      SHA256(all upstream hashes combined)[:16]            |
+-----------------------------------------------------------------------------+
```

### Tamper Detection Guarantees:
1. **Crop Tampering**: Changing crop coordinates after verification alters `crop_fingerprint` and triggers render fingerprint mismatch (`test_negative_07`).
2. **Proposition Tampering**: Modifying narrative claims after verification alters `proposition_hash` and triggers `StaleVisualPlanError` (`test_negative_08`).
3. **Stale Evidence Reuse**: Reusing evidence verified against a prior script triggers `StaleVisualPlanError: STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION` (`test_negative_09`).

---

## 9. Evidence Cache Behavior & Performance
- **Directory**: `data/clips/evidence_cache/`
- **Cache Strategy**: Content-addressed keying on `{candidate_id}_{start_sec}_{end_sec}.mp4`.
- **Extraction Overhead**: Ultrafast FFmpeg interval slicing completes in $\approx 220\text{ms} - 350\text{ms}$.
- **Inspection Throughput**: PySceneDetect + Farnebäck optical flow executes across a 3.5s micro-clip in $\approx 1.2\text{s} - 1.8\text{s}$.
- **Storage Management**: Ephemeral candidate clips are cached locally and can be purged safely without affecting finalized assets or source movies.

---

## 10. Test Suite Execution Summary
Executed focused test suite targeting hybrid matching and physical evidence integration:

```
Command: pytest tests/test_hybrid_visual_matching.py tests/test_visual_evidence_integration.py -v
Platform: Windows (Python 3.11.9, pytest 9.1.1)
Total Tests: 40
Passed: 40
Failed: 0
Execution Time: 47.53s
```

- **`tests/test_hybrid_visual_matching.py`**: 27/27 PASSED
- **`tests/test_visual_evidence_integration.py`**: 13/13 PASSED

---

## 11. Controlled Test 1: Fresh Discovery Proposition
- **Proposition**: `"Harry Potter catches the Golden Snitch during the Quidditch match."`
- **Candidate Clip**: `m1_snitch_catch.mp4`
- **Ground Truth Entities**: Harry Potter $[0.30, 0.20, 0.35, 0.60]$, Golden Snitch $[0.45, 0.35, 0.10, 0.10]$
- **Verification Result**:
  - `is_verified`: `True`
  - `verdict`: `PASS`
  - `sub_shot_id`: `shot_0`
  - `crop_fingerprint`: `crop_735_0_450_800`
- **9:16 Render**: Successfully extracted and rendered 9:16 vertical MP4 via FFmpeg Lanczos filter with verified subject containment.
- **Lineage Verification**: Cryptographic evidence hash computed and validated (`test_controlled_fresh_discovery_integration`).

---

## 12. Controlled Test 2: Fresh Novel Story Proposition
- **Proposition**: `"Dudley Dursley falls forward through the vanishing glass into the snake habitat."`
- **Candidate Clip**: `m1_zoo_glass_fall.mp4`
- **Ground Truth Entities**: Dudley Dursley $[0.08, 0.25, 0.20, 0.60]$
- **Verification Result**:
  - `is_verified`: `True`
  - `verdict`: `PASS`
  - `crop_window`: `{"x": 120, "y": 0, "w": 450, "h": 800}`
  - `crop_evidence.subject_retention`: `0.92`
- **Lineage Verification**: `VisualManifestProvenance` verified end-to-end with zero drift (`test_controlled_fresh_novel_story_integration`).

---

## 13. The 10 Negative Integration Scenarios
All 10 negative scenarios failed closed as required, proving that no unverified or tampered clip can pass into the visual timeline:

| Scenario | Test Function | Input Conditions | Expected Verdict | Actual Verdict | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Correct character, wrong action** | `test_negative_01_correct_character_wrong_action` | Hermione & Draco wand standoff; assertion requires punch | `ACTION_ABSENT` / `RELATIONSHIP_ABSENT` | `RELATIONSHIP_ABSENT` | **PASSED** |
| **2. Correct action, wrong object** | `test_negative_02_correct_action_wrong_object` | Lupin hands chocolate; assertion requires golden locket | `OBJECT_MISMATCH` / `NO_REQUIRED_ENTITY` | `NO_REQUIRED_ENTITY` | **PASSED** |
| **3. Correct action, wrong recipient** | `test_negative_03_correct_action_wrong_recipient` | Lupin hands chocolate to Harry; assertion requires Ron | `CHARACTER_MISMATCH` / `NO_REQUIRED_ENTITY` | `NO_REQUIRED_ENTITY` | **PASSED** |
| **4. Correct scene, unsupported narration** | `test_negative_04_correct_source_scene_unsupported_narration` | Quidditch scene; assertion claims drinking Polyjuice | `ACTION_ABSENT` / `NO_REQUIRED_ENTITY` | `NO_REQUIRED_ENTITY` | **PASSED** |
| **5. Continuous shot required, hard cut present** | `test_negative_05_candidate_containing_cuts_when_uninterrupted_required` | Multi-shot clip; assertion sets `require_uninterrupted_shot=True` | `SHOT_BOUNDARY_CONFLICT` | `SHOT_BOUNDARY_CONFLICT` | **PASSED** |
| **6. Source evidence lost in crop** | `test_negative_06_source_evidence_lost_in_crop` | Subject at peripheral edge ($x=0.01$); centered 9:16 crop | `CROP_SUBJECT_LOST` | `CROP_SUBJECT_LOST` | **PASSED** |
| **7. Crop changed after verification** | `test_negative_07_changed_crop_after_verification` | Crop coordinates altered from verified values | Render fingerprint mismatch | Fingerprint divergence | **PASSED** |
| **8. Proposition changed after verification** | `test_negative_08_changed_proposition_after_verification` | Proposition narrative claim modified post-verification | `StaleVisualPlanError` | `StaleVisualPlanError` | **PASSED** |
| **9. Stale evidence from previous render** | `test_negative_09_stale_evidence_from_previous_render` | Prior visual plan paired with modified voiceover | `StaleVisualPlanError` | `StaleVisualPlanError` | **PASSED** |
| **10. No valid visual candidate** | `test_negative_10_movie_event_candidate_no_valid_visual` | Unfulfillable claim ("tames dragon in Great Hall") | `NO_VALID_VISUAL` (Zero SRT fallback) | `NO_VALID_VISUAL` | **PASSED** |

---

## 14. Failure Modes Observed & Resolved During Integration
During integration testing, several real-world failure modes were uncovered and systematically fixed:

1. **Full-Length Movie PySceneDetect Stall**:
   - *Issue*: Passing a 2.5-hour feature film container to `inspect_clip()` triggered a full container scan taking $>60$ seconds.
   - *Fix*: Implemented fast FFmpeg candidate interval micro-extraction ($\le 0.35$s) before passing clips to `inspect_clip()`, preserving sub-second verification.
2. **Regex Substring Collisions on Character Names**:
   - *Issue*: Substring matching for state transitions (e.g. `'snap' in text`) matched inside the name `"Snape"`, erroneously injecting wand-break state transition requirements onto Severus Snape dialogue beats.
   - *Fix*: Enforced strict regex word boundaries `\b(snap|snaps|snapped|break|breaks|split)\b`.
3. **Pydantic Model Completeness**:
   - *Issue*: Synthetic test `MovieEvent` instantiations omitted `location` and `visual_description`, causing Pydantic validation errors.
   - *Fix*: Standardized test fixture definitions with complete model metadata.
4. **Sub-Shot Contact Proximity Calibration**:
   - *Issue*: Evaluating a full multi-shot sequence without temporal bounding evaluated camera cut transitions instead of the active standoff.
   - *Fix*: Properly bounded candidate intervals so spatial relationship verifiers evaluate the specific sub-shot interval.

---

## 15. Absolute Confirmation of Safety Rules
All safety boundaries mandated for this task were strictly maintained:

- **AL AMR Status**: Completely untouched. Zero modifications to AL AMR files, repositories, workflows, or YouTube configurations.
- **Autonomous Production**: Zero autonomous production runs initiated.
- **Publishing & Scheduling**: Zero videos published or scheduled.
- **Inventory**: READY inventory remains completely unmodified.
- **External Services**: Google Drive, YouTube credentials, and external network APIs were not accessed or altered.
- **Scope Isolation**: All edits and tests were strictly restricted between `py_visual_evidence` and `harry_potter_automation`.

---

## 16. Remaining Limitations
1. **Pre-Indexed Grounding Dependency**: The current verification benchmark uses deterministic grounded bounding boxes for high-speed offline testing. Integration with real-time zero-shot open-vocabulary object detectors (e.g. OWL-ViT / Grounding DINO) will require GPU inference during live production.
2. **Audio Track Separation**: The visual engine evaluates pure video streams; audio-visual cross-modal verification (e.g. aligning spell sound effects with wand flashes) is currently handled downstream by Story Forge's audio mastering engine.

---

## 17. Production Readiness Assessment
- **Integration Status**: Code complete and functionally verified across all test fixtures.
- **Regression Status**: 0 regressions across 40 hybrid matching and evidence integration tests.
- **Production Declaration**: **NOT DECLARED PRODUCTION READY.**

In strict accordance with project safety guidelines, this integration is submitted for engineering review. Production deployment will require:
1. Human sign-off on the 10 negative fail-closed integration scenarios.
2. Verification on live movie MKV files in a staged non-production environment.
3. Performance benchmarking under concurrent multi-proposition rendering workloads.
