# STORY FORGE — Blind Visual Forensic Audit Report

**Date:** 2026-09-26  
**Auditor:** Antigravity Forensic Audit  
**Scope:** Lightweight independent forensic inspection of recent final Story Forge video renders:
- `final_render_disc_elder_wand_snap_v1.mp4`
- `final_render_ns_buckbeak_slash_malfoy_v1.mp4`

---

## 1. Observed Failures

1. **Severe Subject Truncation / Edge Amputation (Discovery Short)**:
   Harry Potter is severed by the right crop boundary. His face, head, and eyes are completely excluded from the 9:16 frame. Only his left shoulder, torso, and partial hands are visible at the extreme right edge; approximately 75% of the frame is empty background rocks.

2. **Complete Entity Absence / Wrong Character Focus (Novel Story Short)**:
   Neither Draco Malfoy nor Buckbeak is visible in the final rendered video. The frame displays Hagrid's back and dark coat as he moves through trees. The characters named in the narration never appear on screen.

3. **Jarring Short-Clip Looping Across Unrelated Narrative Claims (Both Shorts)**:
   A single short clip (3.6s for Discovery; 2.3s for Novel Story) is looped 5 to 8 times back-to-back to pad out a ~16-second narration.

4. **Narrative-Visual Semantic Contradiction (Both Shorts)**:
   - In Discovery, while the narrator explains that in the original book *Harry never breaks the wand at all*, the video continues to loop Harry breaking the wand.
   - In Novel Story, while the narrator describes Malfoy strutting, being struck by talons, and collapsing into the grass, the video shows Hagrid's back repeatedly.

5. **Subtitle-on-Action Collision (Discovery Short)**:
   The ASS subtitles at vertical margin 520 directly overlay the small remaining visible area containing Harry's hands and the wand, further obscuring the action.

---

## 2. Evidence

### Case A: Discovery Short (`final_render_disc_elder_wand_snap_v1.mp4`)
- **Total Duration:** 16.00s | **Source Clip:** `m8_elder_wand_snap.mp4` (1280x528, 5.005s)
- **Sub-shot Used:** `shot_0` (0.000s – 3.629s)

| Timestamp | Frame Ref | Narration Claim | What Final Frame Actually Shows | Defect |
| :--- | :--- | :--- | :--- | :--- |
| **t = 1.0s** | `disc_render_t01.jpg` | *"The movie completely changed how Harry Potter destroyed the Elder Wand."* | Blurry stone bridge pillars occupy 75% of frame; Harry's dark shoulder and arm are cut off at the right edge; face is absent. | Subject truncation; empty frame center; hook has no unique footage. |
| **t = 4.5s** | `disc_render_t04_5.jpg` | *"On screen, Harry grips the Elder Wand with both hands, snaps it cleanly in two pieces..."* | Disembodied hands and torso on right edge; wand snap occurs against right border; subtitle text sits directly over hands. | Action obscured at frame boundary; subtitle collision; head completely off-screen. |
| **t = 6.0s** | `disc_render_t06.jpg` | *"...and throws them over the viaduct."* | Hard cut restart of the exact same 3.6s clip back to Harry holding the unbroken wand; hands reset abruptly. | Temporal loop artifact; action does not show throwing pieces over the viaduct. |
| **t = 10.0s** | `disc_render_t10.jpg` | *"In the book, Harry never breaks it at all. He uses it to repair his original phoenix feather wand..."* | Replaying the movie snap animation for the third time; Harry's arm is visible snapping the wand. | Direct contradiction: audio claims Harry does not break it; visual shows Harry breaking it. |
| **t = 14.0s** | `disc_render_t14.jpg` | *"...returning the Deathstick to Dumbledore's tomb."* | Replaying the snap animation for the fourth time. | Infinite loop padding; zero visual evidence of repair or Dumbledore's tomb. |

### Case B: Novel Story Short (`final_render_ns_buckbeak_slash_malfoy_v1.mp4`)
- **Total Duration:** 16.47s | **Source Clip:** `m3_buckbeak_slash_malfoy.mp4` (1920x800, 8.008s)
- **Sub-shot Used:** `shot_2` (5.672s – 7.966s, duration 2.294s)

| Timestamp | Frame Ref | Narration Claim | What Final Frame Actually Shows | Defect |
| :--- | :--- | :--- | :--- | :--- |
| **t = 1.0s** | `ns_render_t01.jpg` | *"During their first Care of Magical Creatures lesson, Draco Malfoy strutted into the paddock to taunt the Hippogriff."* | Close-up of Hagrid's back and matted hair as he runs past a pine tree. Neither Malfoy nor Buckbeak is visible. | Complete absence of subject (Malfoy), target (Buckbeak), and action (strutting/taunting). |
| **t = 5.0s** | `ns_render_t05.jpg` | *"Insulted by Malfoy, Buckbeak rears up on his hind legs and strikes Malfoy across the arm with sharp talons."* | Same clip of Hagrid's back on its third loop cycle. Dark silhouette fills center; forest background. | Complete absence of Buckbeak, talons, and Malfoy; strike action does not occur in frame. |
| **t = 7.0s** | `ns_render_t07.jpg` | *"...strikes Malfoy across the arm with sharp talons."* | Hagrid's back on its fourth loop cycle. | Zero action visibility; loop glitch. |
| **t = 10.0s** | `ns_render_t10.jpg` | *"Malfoy collapses into the grass howling in theatrical agony..."* | Hagrid's back on its fifth loop cycle. | Malfoy is not visible; grass/ground where Malfoy fell is not framed. |
| **t = 14.0s** | `ns_render_t14.jpg` | *"...while Hagrid rushes forward to carry him to the hospital wing."* | Hagrid's back on its seventh loop cycle. | Repetitive loop; no continuation of Hagrid carrying Malfoy. |

---

## 3. Root-Cause Hypotheses

### Hypothesis 1: The Verification Gate Relied on Synthetic / Mock Grounding
- **OBSERVED FACT**: In the validation harness (`run_final_human_review_validation.py`), entity grounding was handled by `DeterministicBenchmarkGrounder` initialized with manual `register_ground_truth` bounding boxes:
  - Harry Potter: `BoundingBox(x=0.35, y=0.10, w=0.35, h=0.85)`
  - Elder Wand: `BoundingBox(x=0.42, y=0.30, w=0.20, h=0.15)`
  - Buckbeak: `BoundingBox(x=0.40, y=0.10, w=0.50, h=0.85)`
  - Draco Malfoy: `BoundingBox(x=0.15, y=0.15, w=0.35, h=0.80)`
- **OBSERVED FACT**: No neural object detector (such as OWLv2 or YOLO-World) processed the actual video frames during validation.
- **INFERENCE**: The engine returned `PASS` and `is_verified=True` because the verification pipeline validated against the hardcoded mock coordinates rather than the physical pixels of the footage. In `shot_2` of the Buckbeak clip, Draco Malfoy does not exist in the frame, yet the mock grounder reported Malfoy present at 95% confidence.

### Hypothesis 2: Static / Decoupled Crop Calculation Truncates Off-Center Subjects
- **OBSERVED FACT**: Source footage is widescreen cinemascope:
  - `m8_elder_wand_snap.mp4` is 1280x528 (2.42:1 aspect ratio). A 9:16 crop box has a width of only 297px (23.2% of the frame).
  - In `m8_src_t00_5.jpg`, Harry is positioned on the right half ($x \approx 650 \dots 1050$, center $\approx 850$).
  - The render script applied a static filter: `crop=297:528:516:0`, capturing $x \in [516, 813]$.
  - In `m3_buckbeak_slash_malfoy.mp4` (1920x800, 2.40:1), 9:16 crop width is 450px (23.4% of the frame).
  - In `shot_2`, Buckbeak is positioned at $x \in [0, 800]$ and Hagrid is at $x \in [800, 1600]$.
  - The render script applied a static filter: `crop=450:800:1023:0`, capturing $x \in [1023, 1473]$.
- **INFERENCE**: Because the crop calculation was computed from synthetic centroid estimates rather than real subject pixel boundaries, the 9:16 window anchored on the wrong coordinates:
  - For Harry: Centered on the empty gorge ($x=516$), bisecting Harry at $x=813$ and severing his head and wand.
  - For Buckbeak: Centered on Hagrid's back ($x=1023$), completely cropping out Buckbeak on the left ($x < 800$).

### Hypothesis 3: Single-Sub-Shot Timeline Construction & Loop-Padding
- **OBSERVED FACT**: In both validations:
  - Only one candidate sub-shot was retrieved (Discovery: `shot_0`, 3.63s; Novel Story: `shot_2`, 2.29s).
  - Neither the hook proposition (Beat 1) nor the payoff/context proposition (Beat 3) was assigned a separate visual clip.
  - The single sub-shot was concatenated via `concat_list` using `loops = int(voice_dur // clip_dur) + 1` to fill the 16-second narration.
- **INFERENCE**: The pipeline does not build a multi-clip storyboard matching each proposition in the narration script. When a claim has 3 distinct narrative beats, the current render assembly repeats the single verified sub-shot in an infinite loop, creating visual stutter and semantic contradictions.

### Hypothesis 4: Candidate Clip Retrieval Boundaries Mismatched to Action Verb
- **OBSERVED FACT**: In `m3_buckbeak_slash_malfoy.mp4`:
  - At t=1.0s, Malfoy is already lying on the ground clutching his arm; Hagrid is holding Buckbeak back; students are fleeing.
  - At t=5.67s to 7.96s (`shot_2`), Buckbeak is settling down and turning to run away while Hagrid turns around.
  - The physical strike (where Buckbeak rears and cuts Malfoy's arm) occurred *prior* to t=0.0s of this candidate clip.
- **INFERENCE**: The source clip in the candidate database does not contain the actual strike event. The retrieval index matched on text/event metadata (`evt_m3_paddock_buckbeak_slashes_malfoy`), but the clip itself covers only the aftermath.

---

## 4. Cross-Case Pattern

| Pattern Element | Present in Discovery (`elder_wand`) | Present in Novel Story (`buckbeak`) | Diagnostic Significance |
| :--- | :--- | :--- | :--- |
| **Short-clip loop padding** | **Yes** (3.6s looped 5x) | **Yes** (2.3s looped 8x) | Systemic timeline defect: lack of multi-clip editorial sequencing. |
| **Semantic contradiction on Beat 3** | **Yes** (Snap shown while audio says "never breaks") | **Yes** (Hagrid's back shown while audio says Malfoy howls/carried) | Systemic defect: non-core propositions receive zero visual coverage. |
| **9:16 cinemascope crop amputation** | **Yes** (Harry's face/wand severed at right edge) | **Yes** (Buckbeak completely excluded on left edge) | Systemic defect: 9:16 crop window misaligned with actual subject position in 2.40:1 footage. |
| **Subject completely missing from frame** | No (Harry's torso is partially in frame) | **Yes** (Neither Malfoy nor Buckbeak is in frame) | Severe grounding/selection failure in Novel Story. |
| **Subtitle occlusion on active zone** | **Yes** (Subtitles cover Harry's hands/wand) | Minor (Subtitles cover Hagrid's back) | Discovery-specific layout collision due to off-center subject positioning. |

---

## 5. Unknowns

The following cannot be determined from this lightweight inspection:
1. **Behavior of Real Open-Vocabulary Detectors**: It is unknown whether `OpenVocabularyGrounder` (OWLv2) would correctly reject `shot_2` of the Buckbeak clip or find Harry's true bounding box in the wand clip, because only `DeterministicBenchmarkGrounder` was invoked in the validation script.
2. **MovieEvent Temporal Annotation Accuracy**: It is unknown whether the source file `m3_buckbeak_slash_malfoy.mp4` was cut too late at ingestion time, or if earlier frames containing the strike exist in the raw movie cut.
3. **Full EditorialPlanner Integration**: It is unknown why the validation script bypassed the full `EditorialPlanner` (which contains anti-padding and multi-beat scheduling logic) in favor of a raw FFmpeg loop concat.

---

## 6. Recommended Next Investigation

**Smallest single next step**:
Run a 1-frame diagnostic script using `OpenVocabularyGrounder` (or direct OpenCV/YOLO/OWLv2 inference) without any mocks or registered ground truth on:
1. `m8_elder_wand_snap.mp4` at t=1.0s to detect Harry Potter's real bounding box.
2. `m3_buckbeak_slash_malfoy.mp4` at t=6.5s to see what entities are actually detected.

Compare the real detector bounding boxes against the hardcoded mock coordinates to confirm Hypothesis 1 and Hypothesis 2.
