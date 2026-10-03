# Implementation Report: Multi-Beat Visual Coverage & Strict Anti-Loop Behavior

**Date**: 2026-09-26  
**Subject**: Multi-Beat Visual Coverage + Strict Anti-Loop Enforcement in STORY FORGE  
**Status**: COMPLETE & VERIFIED  

---

## 1. Overview & Problem Addressed

The forensic diagnostic (`reports/visual_timeline_loop_diagnostic.md`) identified that:
1. Narrative Shorts frequently have multiple distinct propositions / narrative beats (e.g. Hook, Core Visual Action, Book vs. Movie Lore Payoff).
2. Only a single visual assertion was created, and its verified sub-clip was blindly assigned across unrelated subsequent beats.
3. The render pipeline explicitly looped short footage (`loops = int(voice_dur // clip_dur) + 1` in assembly scripts, and `-stream_loop -1` / `deficit` padding in `render_engine.py`), causing 5 consecutive repetitions of the Elder Wand snap while the voiceover explained that in the book Harry *never* breaks it.

This implementation introduces **Multi-Beat Visual Requirements**, **Strict Beat-to-Clip Allocation**, and a **Strict No-Loop Policy** ensuring that missing or unfilmed lore beats are explicitly represented as `VISUAL_OPTIONAL_UNCOVERED` rather than masked with repetitive footage.

---

## 2. Files Changed

| File Path | Type of Change | Purpose |
| :--- | :--- | :--- |
| [`engines/movie_event/models.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/engines/movie_event/models.py) | Model Enhancement | Added multi-beat fields to `VisualBeat`: `narration_start`, `narration_end`, `visual_assertion`, `required_entities`, `visual_state`, `coverage_requirement` (`DIRECT` vs `VISUAL_OPTIONAL`), and bidirectional synchronization validators. |
| [`engines/movie_event/storyboard_generator.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/engines/movie_event/storyboard_generator.py) | Logic Update | Enhanced `ClaimTransformer` to detect unfilmed book canon / comparative claims (`BOOK_CANON_PATTERNS`) and classify them as `VISUAL_OPTIONAL`. Enhanced `generate_beat_from_narration` to populate multi-beat requirements. |
| [`engines/visual_evidence/multi_beat_timeline.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/engines/visual_evidence/multi_beat_timeline.py) | **New Component** | Dedicated timeline engine allocating distinct verified clips to beats. Prevents duplicate clip reuse across beats, clamps duration without looping, and fails closed with `INSUFFICIENT_VISUAL_COVERAGE` on unsatisfied direct beats. |
| [`engines/visual_evidence/__init__.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/engines/visual_evidence/__init__.py) | Package Export | Exported `MultiBeatCoverageEngine`, `MultiBeatTimelinePlan`, `TimelineSegment`, `BeatCoverageStatus`. |
| [`engines/render_engine.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/engines/render_engine.py) | Guard & Anti-Loop | Added `allow_loop: bool = False` to `render_video_shot_clip` and `render_shot_clip` (omits `-stream_loop -1` by default). Added `strict_no_loop: bool = True` to `assemble_short` raising `INSUFFICIENT_VISUAL_COVERAGE` if visual duration is shorter than audio. |
| [`scripts/run_final_human_review_validation.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/scripts/run_final_human_review_validation.py) | Anti-Loop Cleanup | Removed `loops = int(voice_dur // clip_dur) + 1` concat loop padding from Discovery Short and Novel Story paths; writes each distinct verified clip exactly once. |
| [`tests/test_multi_beat_anti_loop.py`](file:///C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/tests/test_multi_beat_anti_loop.py) | **New Test Suite** | 8 focused tests covering multi-beat allocation, anti-loop guards, duration clamping, fail-closed behavior, and book canon distinction. |

---

## 3. Beat Model & Formulation Changes

The `VisualBeat` data contract now guarantees:
- **`beat_id`**: Unique beat identifier.
- **`narration_start` & `narration_end`**: Exact spoken narration time window.
- **`visual_assertion`**: Explicit visual assertion container.
- **`required_entities`**: Consolidated list of all required physical subjects, objects, and targets.
- **`required_action` & `visual_state`**: Observable physical action and state change (e.g. `snaps`, `BROKEN`).
- **`narrative_role`**: Directorial role (e.g. `HOOK`, `CORE_ACTION`, `CLIMAX`, `LORE_COMPARISON`).
- **`direct_visual_requirement`**: Boolean indicating if observable physical movie proof is mandatory.
- **`coverage_requirement`**: `"DIRECT"` or `"VISUAL_OPTIONAL"`.
- **`is_visual_optional`**: Returns `True` for unfilmed book canon, conceptual hooks, or commentary beats.

### Book-Canon Distinction:
Narrative beats comparing book lore (e.g. *"In the book, Harry never breaks it at all..."*) are automatically detected and marked `VISUAL_OPTIONAL`. The system never invents fake movie evidence or reuses prior action clips to fill book lore.

---

## 4. Strict Anti-Loop Enforcement

1. **One Verified Clip Cannot Automatically Satisfy Multiple Beats**:
   - `MultiBeatCoverageEngine` tracks all consumed source clip intervals.
   - If an earlier beat used `m8_elder_wand_snap.mp4` [0.0s – 3.63s], a subsequent beat attempting to reuse that interval is rejected with `BeatCoverageStatus.REUSED_DISALLOWED`.
   - Multi-beat reuse is permissible only when evidence explicitly demonstrates disjoint, non-overlapping source intervals or sustained physical continuity.
2. **Strict No-Loop Duration Clamping**:
   - If a clip provides 3.6s and the beat is 5.0s, the clip is trimmed to 3.6s. It is **never** looped to 5.0s.
   - FFmpeg `-stream_loop -1` is disabled by default in `render_engine.py`.
   - In `assemble_short()`, if visual duration < audio duration under `strict_no_loop=True`, the engine refuses to stretch the final shot and fails closed with `INSUFFICIENT_VISUAL_COVERAGE`.

---

## 5. Verification & Test Results

### A. Focused Test Suite (`tests/test_multi_beat_anti_loop.py`)
Ran `pytest tests/test_multi_beat_anti_loop.py -v`:
- `test_01_three_beats_three_distinct_clips`: **PASSED** (3 separate timeline segments).
- `test_02_only_beat1_valid_prevents_cloning_across_beats`: **PASSED** (Beat 2 rejected as `REUSED_DISALLOWED`; fails closed).
- `test_03_short_clip_is_not_looped`: **PASSED** (2.5s clip assigned to 8.0s beat without looping).
- `test_04_missing_direct_visual_fails_closed`: **PASSED** (`INSUFFICIENT_VISUAL_COVERAGE` returned).
- `test_05_visual_optional_beat_allows_explicit_absence`: **PASSED** (explicit absence marked without fake footage).
- `test_06_legitimate_multi_beat_sharing`: **PASSED** (disjoint contiguous intervals accepted).
- `test_07_real_detector_authority_preserved`: **PASSED** (rejects synthetic grounder, requires real OWLv2).
- `test_08_elder_wand_book_canon_not_filled_with_snap_clip`: **PASSED** (Elder Wand case validated).

**Result: 8 / 8 PASSED in 2.50s.**

### B. Tiny Regression Subset
Ran `pytest tests/test_real_detector_authority.py tests/test_subject_aware_crop.py -v`:
- Real Detector Authority: **5 / 5 PASSED**
- Subject-Aware Crop: **9 / 9 PASSED**

**Result: 14 / 14 PASSED in 93.20s.**

---

## 6. Real Elder Wand Case Validation

Executed timeline allocation on the 3 narrative beats of `disc_elder_wand_snap_v1`:
1. **Beat 1** (`disc_p1_hook`, 0.0s – 3.4s, `HOOK`):
   - Status: `VISUAL_OPTIONAL_UNCOVERED`
   - Clip: `None`
2. **Beat 2** (`disc_p2_visual_core`, 3.4s – 8.5s, `CLIMAX`, `DIRECT_VISUAL`):
   - Status: `VERIFIED_DIRECT`
   - Clip: `clip_disc_elder_wand_snap_v1_shot01.mp4` (Duration: 3.629s)
3. **Beat 3** (`disc_p3_lore_truth`, 8.5s – 16.0s, `PAYOFF`, `VISUAL_OPTIONAL`):
   - Status: `VISUAL_OPTIONAL_UNCOVERED`
   - Clip: `None` (Explicitly NOT filled with Beat 2 wand snap)

**Metrics**:
- `Total Narration Duration`: $16.000\text{s}$
- `Total Verified Visual Duration`: $3.629\text{s}$
- `Loop Count Detected`: **0**
- `Renderable Segments`: **Exactly 1** (Wand snap clip appears once; 5x loop cycle completely eliminated).

---

## 7. Mandatory Commitments & Confirmations

- **No New AI Models**: No LLM, VLM, face-recognition model, SAM2, Grounding DINO, or external AI model was added.
- **AL AMR Untouched**: `intelligence/` and all AL AMR components remain 100% untouched (`git checkout intelligence/visual_evidence.py` verified).
- **No Autonomous Production**: No videos published, no YouTube uploads, no scheduling, no Drive mutations, no READY inventory modifications.
- **Real Detector Authority Preserved**: OWLv2 remains the sole physical evidence authority.
