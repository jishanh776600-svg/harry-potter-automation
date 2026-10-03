# STORY FORGE — Fresh End-to-End Controlled Validation Report

**Execution Timestamp:** 2026-09-26 17:37:23  
**Evaluator:** Blind `FinalRenderVerifier` (Real OWLv2 Open-Vocabulary Authority)  
**Safety Status:** AL AMR completely untouched (`intelligence/` clean). Autonomous workflows disabled. Zero upload to YouTube/Drive. Zero production state mutated.

---

## 1. Executive Summary & Status Declarations

```ini
FRESH_DISCOVERY_STATUS = PASS
FRESH_NOVEL_STORY_STATUS = FAIL
FINAL_RENDER_PIPELINE_STATUS = NOT_READY
```

The fresh controlled validation experiment tested the complete integrated Story Forge pipeline on two genuine, non-historical test cases:
1. **Fresh Discovery Short (`fresh_validation_discovery_v1`)**: **PASS** (`READY`). Successfully verified across all narrative, visual, subject-aware composition, anti-loop, typography, and broadcast audio gates.
2. **Fresh Novel Story Short (`fresh_validation_novel_v1`)**: **FAIL** (`NOT_READY`). Correctly failed closed by the blind `FinalRenderVerifier` due to temporal action concentration in the source clip (`m3_hermione_punches_malfoy.mp4`), where Hermione's visual evidence drops below the 40% retention threshold at the uniform sampling boundaries (1.25s and 3.75s).

The pipeline strictly enforces failure-closed integrity: **neither synthetic boxes nor fabricated evidence can slip through the real OWLv2 detector**.

---

## 2. Controlled Case A: Fresh Discovery Short (`fresh_validation_discovery_v1`)

### 2.1 Narrative & Multi-Beat Structure
- **Title:** The Sorting Hat's Secret Choice
- **Topic:** `sorting_hat_secret_choice` (Movie 1: Philosopher's Stone / Book 1)
- **Beats:**
  1. `disc_b1_hook` (0.0s – 3.0s): *"Why did the Sorting Hat almost place Harry Potter into Slytherin?"* — Role: `HOOK`, Coverage: `VISUAL_OPTIONAL`.
  2. `disc_b2_action` (3.0s – 6.8s): *"When placed on his head, the magical hat saw great talent and ambition."* — Role: `CORE_ACTION`, Coverage: `DIRECT_VISUAL`, Subjects: `["Harry Potter"]`, Objects: `["Sorting Hat"]`, Action: `"placed"`.
  3. `disc_b3_lore` (6.8s – 10.36s): *"In the book, the hat openly debated Slytherin, until Harry begged for Gryffindor."* — Role: `PAYOFF`, Coverage: `VISUAL_OPTIONAL`.

### 2.2 Timeline Allocation & Anti-Loop Validation
`MultiBeatCoverageEngine` allocated three distinct, non-overlapping visual segments without repeating or looping any media:
- **Segment 1 (0.0s – 3.0s):** Establishing shot of Hogwarts Castle (`m3_camera_pan_hogwarts.mp4`, 3.0s) — `VISUAL_OPTIONAL_COVERED`.
- **Segment 2 (3.0s – 6.8s):** Sorting Hat placed on Harry (`m1_sorting_hat_placed.mp4`, 3.8s) — `VERIFIED_DIRECT`.
- **Segment 3 (6.8s – 10.36s):** Book lore contextual shot (`m1_ollivander_wand_handover.mp4`, 3.56s) — `VISUAL_OPTIONAL_COVERED`.
- **Repetitive Loop Count Detected:** `0` (Frame difference across beats: $\Delta > 35.0$).

### 2.3 Real OWLv2 Detector Grounding & Subject-Aware 9:16 Crop
- **Source Clip:** `m1_sorting_hat_placed.mp4` (1920x800, ~2.40:1).
- **OWLv2 Grounding (Pre-Crop):**
  - `Harry Potter`: confidence `0.619`, bbox `[x=0.463, y=0.316, w=0.184, h=0.100]`
  - `Sorting Hat`: confidence `0.426`, bbox `[x=0.451, y=0.002, w=0.229, h=0.282]`
- **Subject-Aware Crop Window:** `[x=840, y=0, w=450, h=800]` (normalized center: `0.5547`).
- **Post-Crop Result:** Centered on Harry and the Sorting Hat. Zero border clipping. Zero amputation.

### 2.4 Blind Pixel Verification on Final 1080x1920 MP4
- **Video Path:** `data/vault/controlled_tests/final_render_fresh_validation_discovery_v1.mp4`
- **Resolution:** 1080x1920 (Canonical 9:16 vertical).
- **OWLv2 Pixel Inspection on Final Render:**
  - `Harry Potter`: Retention rate `100.0%`, status `PASS`.
  - `Sorting Hat`: Retention rate `100.0%`, status `PASS`.
  - Observable Action (`placed`): `PASS`.
- **Subtitle Composition & Typography:**
  - Font: `Harry P` (Canonical match confirmed).
  - Safe-Zone Clearance: `PASS` (MarginV = 520, zero character collision).
- **Broadcast Audio Loudness (EBU R128):**
  - Integrated Loudness: `-14.4 LUFS` (Target: -14.0 LUFS $\pm 2.5$).
  - True Peak: `-2.0 dBTP` (Threshold: $\le -1.0$ dBTP).
- **Final Status:** **`READY`** (Overall Verdict: `PASS`).

---

## 3. Controlled Case B: Fresh Novel Story Short (`fresh_validation_novel_v1`)

### 3.1 Narrative & Multi-Beat Structure
- **Title:** Hermione Confronts and Punches Malfoy
- **Topic:** `hermione_punches_malfoy` (Movie 3: Prisoner of Azkaban)
- **Beats:**
  1. `novel_b1_punch` (0.0s – 5.0s): *"Hermione lowered her wand, spun around, and delivered a devastating right punch squarely into Malfoy's nose."* — Role: `CORE_ACTION`, Coverage: `DIRECT_VISUAL`, Subjects: `["Hermione Granger", "Draco Malfoy"]`, Action: `"punch"`.

### 3.2 Real OWLv2 Detector Grounding & Subject-Aware 9:16 Crop
- **Source Clip:** `m3_hermione_punches_malfoy.mp4` (1920x800).
- **OWLv2 Grounding at Punch Setup (2.0s):**
  - `Hermione Granger`: confidence `0.325`, bbox `[x=0.555, y=0.091, w=0.193, h=0.476]`
  - `Draco Malfoy`: confidence `0.367`, bbox `[x=0.471, y=0.094, w=0.399, h=0.915]`
- **Subject-Aware Crop Window:** `[x=985, y=0, w=450, h=800]` (normalized center: `0.6302`).
  - *Note:* Shifting from dead center (735) to 985 successfully prevented center-crop amputation of Hermione and Malfoy.

### 3.3 Blind Pixel Verification on Final 1080x1920 MP4 & Root-Cause Failure Analysis
- **Video Path:** `data/vault/controlled_tests/final_render_fresh_validation_novel_v1.mp4`
- **Resolution:** 1080x1920.
- **Audio & Subtitle Checks:**
  - Integrated Loudness: `-14.6 LUFS` (`PASS`).
  - True Peak: `-2.7 dBTP` (`PASS`).
  - Subtitle Font: `Harry P` (`PASS`).
  - Safe-Zone Collision: `PASS`.
- **EVIDENCE_DEFECTS Detected by `FinalRenderVerifier`:**
  - `Beat 'novel_b1_punch': Entity 'Hermione Granger' absent from final render.`
  - `Beat 'novel_b1_punch': Action 'punch' failed: primary subject 'Hermione Granger' is missing from final render.`
- **Forensic Diagnosis:**
  - While Hermione is present at the impact moment ($t \approx 2.0\text{s} - 2.8\text{s}$), uniform beat sampling at $t=1.25\text{s}$ (pre-turn standoff) and $t=3.75\text{s}$ (post-punch Malfoy collapse) captures frames where Hermione's visual confidence falls below the 0.15 threshold or her body is occluded by motion blur during the rapid punch turn.
  - As a result, detected retention was $0.0\% < 40\%$, causing the verifier to strictly fail closed.
- **Final Status:** **`NOT_READY`** (Overall Verdict: `FAIL`).

---

## 4. Verification Evidence Matrix

| Check / Gate | Discovery Short (`fresh_disc_v1`) | Novel Story Short (`fresh_novel_v1`) | Pipeline Compliance Requirement |
| :--- | :---: | :---: | :---: |
| **Mandatory Real OWLv2 Detector** | `PASS` (Real detector used) | `PASS` (Real detector used) | No DeterministicBenchmarkGrounder |
| **Subject-Aware Geometric 9:16 Crop** | `PASS` (x=840, center 0.555) | `PASS` (x=985, center 0.630) | Non-centered subjects preserved |
| **Subject Amputation / Clipping** | `PASS` (0 frames amputated) | `PASS` (0 frames amputated) | Edge boundary distance $\ge 0.015$ |
| **Timeline Anti-Loop Enforcement** | `PASS` (0 loops, 3 distinct clips) | `PASS` (0 loops, 1 distinct clip) | Stream-loop disabled, $\Delta > 12.0$ |
| **Book Lore / VISUAL_OPTIONAL** | `PASS` (Explicit absence, 0 fake) | N/A | No fabricated movie evidence |
| **Subtitles Canonical Font** | `PASS` (`Harry P`) | `PASS` (`Harry P`) | Exact font profile match |
| **Subtitle Safe-Zone Collisions** | `PASS` (MarginV 520, clear) | `PASS` (MarginV 520, clear) | Bottom safe-zone overlap = 0 |
| **EBU R128 Audio Loudness** | `PASS` (-14.4 LUFS, -2.0 dBTP) | `PASS` (-14.6 LUFS, -2.7 dBTP) | $-16.5 \le \text{LUFS} \le -11.5$, $\text{TP} \le -1.0$ |
| **Pixel-Level Subject Retention** | `PASS` (100% Harry & Hat) | **`FAIL`** (Hermione retention $< 40\%$) | $\ge 40\%$ retention across sampled frames |
| **Action Survival in Final Frames** | `PASS` (`placed` verified) | **`FAIL`** (Action absent at sample pts) | Observable action verified |
| **Overall Forensic Gate Status** | **`READY`** | **`NOT_READY`** | All categories must pass |

---

## 5. Artifact & Keyframe Audit Trail

All rendered MP4 videos and visual inspection keyframes are saved in the artifact vault:

- **Discovery Short Render:**
  - `data/vault/controlled_tests/final_render_fresh_validation_discovery_v1.mp4`
  - Brain Artifact: `fresh_validation_discovery_v1.mp4`
  - Keyframe 1 (t=1.5s, Hogwarts Castle): `fresh_validation_discovery_v1_01_hogwarts_pan.jpg`
  - Keyframe 2 (t=5.0s, Sorting Hat on Harry): `fresh_validation_discovery_v1_02_sorting_hat_harry.jpg`
  - Keyframe 3 (t=10.0s, Book Lore Payoff): `fresh_validation_discovery_v1_03_book_lore_payoff.jpg`
- **Novel Story Short Render:**
  - `data/vault/controlled_tests/final_render_fresh_validation_novel_v1.mp4`
  - Brain Artifact: `fresh_validation_novel_v1.mp4`
  - Keyframe 1 (t=1.0s, Standoff): `fresh_validation_novel_v1_01_standoff.jpg`
  - Keyframe 2 (t=2.5s, Punch Impact): `fresh_validation_novel_v1_02_punch_impact.jpg`
  - Keyframe 3 (t=3.8s, Malfoy Reaction): `fresh_validation_novel_v1_03_malfoy_reaction.jpg`
- **Machine-Readable Forensic Log:** `fresh_validation_summary.json`

---

## 6. Focused Regression Test Suite Results

The full suite of 36 focused regression tests was executed and passed with 100% success:

```text
tests/test_final_render_verifier.py      14 / 14 PASSED
tests/test_multi_beat_anti_loop.py         8 / 8  PASSED
tests/test_real_detector_authority.py      5 / 5  PASSED
tests/test_subject_aware_crop.py           9 / 9  PASSED
============================= 36 passed in 121.89s =============================
```

---

## 7. Forensic Conclusions & Production Readiness

1. **Discovery Short Pipeline is Verified & Fully Functional:**
   - Multi-beat narrative beats are accurately partitioned without artificial footage looping.
   - Non-filmed book canon is handled cleanly under `VISUAL_OPTIONAL` without fabricating fake clips.
   - Real OWLv2 verifies subjects directly in the final 1080x1920 pixels.
   - Subject-aware geometric cropping maintains safe margins without center-crop decapitation or amputation.
   - Canonical `Harry P` typography and broadcast audio loudness (-14.0 LUFS) are fully satisfied.

2. **Novel Story Short Pipeline Failure-Closed Protection Verified:**
   - The blind `FinalRenderVerifier` successfully caught a temporal action misalignment where rapid motion and shot framing resulted in low entity retention at the uniform sampling timestamps.
   - Rather than creating a false positive, the verifier correctly raised `EVIDENCE_DEFECTS` and blocked release.

3. **Status:**
   - `FRESH_DISCOVERY_STATUS = PASS`
   - `FRESH_NOVEL_STORY_STATUS = FAIL`
   - `FINAL_RENDER_PIPELINE_STATUS = NOT_READY`
