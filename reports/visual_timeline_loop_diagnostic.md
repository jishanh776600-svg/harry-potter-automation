# Forensic Diagnostic: Story Forge Visual Timeline Construction & Repetitive Looping

**Date**: 2026-09-26  
**Subject**: Visual Timeline & Looping Root Cause Analysis  
**Inspected Render**: `disc_elder_wand_snap_v1` (`final_render_disc_elder_wand_snap_v1.mp4`)  
**Status**: DIAGNOSTIC ONLY — NO CODE MODIFIED — NO TESTS RUN  

---

## 1. Current Timeline

### Narrative Propositions vs. Physical Visual Units

| Timeline Interval | Narration / Proposition | Type | Assigned Visual Unit | Rendered Visual Action | Loop Cycle |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0.00s – 3.40s** | *"The movie completely changed how Harry Potter destroyed the Elder Wand."* (`disc_p1_hook`) | Claim / Hook | `clip_disc_elder_wand_snap_v1_shot01.mp4` | Harry snaps wand on viaduct | **Cycle 1** (0.0s – 3.4s) |
| **3.40s – 8.50s** | *"On screen, Harry grips the Elder Wand with both hands, snaps it cleanly in two pieces..."* (`disc_p2_visual_core`) | Core Physical Evidence | `clip_disc_elder_wand_snap_v1_shot01.mp4` | Harry snaps wand on viaduct | **Cycle 1 remainder** (3.4s – 3.63s)<br>**Cycle 2** (3.63s – 7.26s)<br>**Cycle 3 start** (7.26s – 8.5s) |
| **8.50s – 16.00s** | *"In the book, Harry never breaks it at all. He uses it to repair his original phoenix feather wand..."* (`disc_p3_lore_truth`) | Payoff / Book Lore | `clip_disc_elder_wand_snap_v1_shot01.mp4` | Harry snaps wand on viaduct | **Cycle 3 remainder** (8.5s – 10.89s)<br>**Cycle 4** (10.89s – 14.52s)<br>**Cycle 5 start** (14.52s – 16.0s) |

- **Observed Fact**:
  - The Short duration is $16.00\text{s}$ (governed by narration audio duration).
  - Exactly **1 verified movie clip** was selected: `clip_disc_elder_wand_snap_v1_shot01.mp4` (source interval $0.000\text{s} \dots 3.629\text{s}$, duration = $3.629\text{s}$).
  - `concat_list_disc_elder_wand_snap_v1.txt` contains **5 identical consecutive entries** of `clip_disc_elder_wand_snap_v1_shot01.mp4`.
  - The exact same 3.6-second clip of Harry snapping the wand loops 5 times back-to-back across all 3 beats.
  - While the narrator describes the book where Harry *never* breaks the wand and repairs his phoenix wand, the video is replaying the movie wand break for the 4th and 5th time.

---

## 2. Loop Origin

- **Observed Fact**:
  Repetitive looping is introduced by two distinct, concrete components in the render pipeline:
  1. **Validation / Assembly Runner (`scripts/run_final_human_review_validation.py` lines 376–380 and lines 645–648)**:
     ```python
     loops = int(voice_dur // clip_dur) + 1
     concat_list_p = VAULT_DIR / f"concat_list_{content_id}.txt"
     with open(concat_list_p, "w", encoding="utf-8") as f:
         for _ in range(loops):
             f.write(f"file '{cropped_unit_mp4.as_posix()}'\n")
     ```
     This explicitly generates an $N$-entry concat list repeating the single verified sub-clip until total video duration exceeds `voice_dur`.
  2. **Core Video Render Engine (`engines/render_engine.py` lines 94, 118, and 294–297)**:
     - Lines 94 & 118: FFmpeg is invoked with `-stream_loop -1` directly before input video:
       `[FFMPEG_EXE, "-y", "-stream_loop", "-1", "-ss", "0", "-i", str(video_path), "-t", str(duration), ...]`
     - Line 81 docstring: *"Uses intelligent center-crop scaling and automatic looping for shorter clips."*
     - Lines 294–297: If total visual duration < master audio duration, the deficit is tacked onto the final shot (`shots_data[-1]["duration"] += deficit`), and `-stream_loop -1` loops that final clip continuously.

---

## 3. Trigger Condition

- **Observed Fact**:
  - The loop is triggered when:
    $$\text{Total Audio Duration } (T_{\text{audio}}) > \text{Total Verified Video Duration } (T_{\text{video}})$$
  - In `disc_elder_wand_snap_v1`:
    - $T_{\text{audio}} = 16.000\text{s}$ (`master_voice_disc_elder_wand_snap_v1.wav`)
    - $T_{\text{video}} = 3.629\text{s}$ (`clip_dur = round(ev_res.source_end - ev_res.source_start, 3)`)
    - Deficit calculation: $\text{loops} = \text{int}(16.0 // 3.629) + 1 = 4 + 1 = 5$.
  - The pipeline treats audio duration as an immutable hard master, while treating visual timeline construction as an unconstrained single-clip filler task. When visual coverage is insufficient, rather than pausing, failing closed, or requiring distinct B-roll/editorial units, it blindly duplicates whatever single clip passed verification.

---

## 4. Evidence (Files, Functions, and Metadata)

1. **`reports/final_visual_render_validation.json`**:
   - `narration`: 3 distinct propositions (`disc_p1_hook`, `disc_p2_visual_core`, `disc_p3_lore_truth`).
   - `candidate_id`: `"evt_m8_viaduct_harry_snaps_elder_wand"` (only 1 candidate retrieved and verified across the entire Short).
   - `source_start`: $0.0$, `source_end`: $3.629$ (duration: $3.629\text{s}$).
   - `duration`: $16.0\text{s}$.
2. **`data/vault/controlled_tests/concat_list_disc_elder_wand_snap_v1.txt`**:
   ```
   file 'C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/data/vault/controlled_tests/clip_disc_elder_wand_snap_v1_shot01.mp4'
   file 'C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/data/vault/controlled_tests/clip_disc_elder_wand_snap_v1_shot01.mp4'
   file 'C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/data/vault/controlled_tests/clip_disc_elder_wand_snap_v1_shot01.mp4'
   file 'C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/data/vault/controlled_tests/clip_disc_elder_wand_snap_v1_shot01.mp4'
   file 'C:/Users/jisha/.gemini/antigravity/scratch/harry_potter_automation/data/vault/controlled_tests/clip_disc_elder_wand_snap_v1_shot01.mp4'
   ```
3. **`engines/render_engine.py`**:
   - Function: `render_shot_clip(media_path, duration, output_path, ...)`
   - Command args: `-stream_loop -1 -i {media_path} -t {duration}`
4. **`engines/editorial/editorial_planner.py`**:
   - Function: `EditorialPlanner.plan_timeline(...)`
   - Lines 209–214:
     ```python
     if not match and len(props) == 1 and len(beast_matches) == 1:
         single_m = beast_matches[0]
         prop_meta = single_m.verification_metadata.get("proposition_id")
         if not prop_meta or prop_meta == prop.proposition_id:
             match = single_m
     ```
     When only 1 match exists, it allows that single match to bind to the proposition.

---

## 5. `NO_VALID_VISUAL` Behavior

- **Observed Fact**:
  - In `engines/editorial/editorial_planner.py` lines 215–219:
    ```python
    if not match or match.decision == BeastV2Decision.NO_VALID_VISUAL:
        validation_warnings.append(
            f"NO_VALID_VISUAL on fact {fact.fact_id} proposition {prop.proposition_id}."
        )
    ```
    When a proposition has no valid visual match, `EditorialPlanner` only appends a text warning to `validation_warnings`. It **does not abort**, does not raise an exception, and does not veto the timeline.
  - At line 358, `EditorialPlanner` proceeds to generate an `EditorialUnit` for the ungrounded beat regardless.
  - In `engines/render_engine.py` line 304:
    If an editorial unit has no asset, it falls back to a static generic image:
    `media_path = Path(asset.local_path) if asset else (ASSETS_DIR / "fallback.jpg")`
  - In `scripts/run_final_human_review_validation.py`:
    Propositions 1 and 3 were never even queried against the retrieval engine. The script verified Proposition 2, and then mechanically looped Proposition 2's clip over Propositions 1 and 3.

---

## 6. Pre-existing Anti-Loop Code and Why It Failed

- **Observed Fact**:
  1. **`engines/qa_verification_gate.py` (`_check_08_visual_repetition`)**:
     - Code contains an explicit repetition check (`lines 775–797`):
       `duplicates = {k: v for k, v in seen_sources.items() if len(v) > 2}`
     - **Why it failed**:
       a) The check explicitly permits duplicate reuse up to 2 times (`expected_value_range="<= 2 uses of identical visual asset"`).
       b) The validation runner bypassed `QA_Verification_Gate` entirely during video assembly, executing direct FFmpeg concat commands.
  2. **`engines/editorial/editorial_planner.py`**:
     - Claims in header: *"Enforces strict Anti-Padding (no stretching, no looping, fail-closed on NO_VALID_VISUAL)"*.
     - **Why it failed**:
       At line 234, it clamps unit duration: `unit_dur = max(0.8, match.source_end - match.source_start)`. But it does not ensure that subsequent beats have distinct assets. When total visual timeline duration is shorter than voice audio, downstream consumers (`render_engine.py` or script concat loops) pad or loop the clips to prevent premature video blackouts.

---

## 7. Smallest Next Implementation (Architectural Recommendation Only)

- **Inference**:
  To eliminate repetitive looping permanently without breaking timeline synchronization, the architecture requires:
  1. **Strict 1:1 Beat-to-Clip Allocation**:
     Every narrative beat/proposition requiring visual representation must be assigned a distinct verified visual clip (or distinct sub-shot) with non-overlapping source timestamps.
  2. **Prohibit Clip Duplication at Assembly Gate**:
     Remove `loops = int(voice_dur // clip_dur) + 1` and `-stream_loop -1` from render assembly. If total unique verified visual duration < narration duration:
     $\to$ **Fail closed with `INSUFFICIENT_VISUAL_COVERAGE`** rather than mechanically looping.
  3. **Multi-Beat Visual Planning**:
     Formulate VisualAssertions for each distinct proposition (Hook, Action Core, Payoff) rather than assuming 1 assertion represents an entire 16–25s Short.
