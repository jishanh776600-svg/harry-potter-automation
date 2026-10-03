# Subject-Aware Geometric 9:16 Cropping Implementation & Validation Report

**Date**: 2026-09-26  
**Project**: Story Forge (`harry_potter_automation`) & `py_visual_evidence`  
**Status**: COMPLETE — Subject-Aware Geometric Optimizer Operational & Validated  

---

## 1. Executive Summary

Previously, the rendering pipeline applied an unconditional horizontal center crop (`(iw-1080)/2:(ih-1920)/2`) to widescreen (~2.40:1) footage. This retained only ~23.4% of the source width in the center, causing 0% subject visibility in cinematic rule-of-thirds shots:
- In Case A (`m8_elder_wand_snap.mp4`), Harry Potter on the right was completely omitted (0% retained).
- In Case B (`m3_buckbeak_slash_malfoy.mp4`), Buckbeak on the left was completely omitted (0% retained).

We have implemented a **deterministic, purely geometric subject-aware 9:16 crop optimizer** that positions the vertical 9:16 window based on real bounding boxes detected by OWLv2:
1. **Right-Side Subjects (Case A)**: Crop window dynamically shifts rightward to enclose Harry Potter (100% retained).
2. **Left-Side Subjects (Case B)**: Crop window dynamically shifts leftward to enclose Buckbeak's rearing body, head, neck, and talons (~64% of wide 700px body retained).
3. **Fail-Closed Hard Validation**: Silent fallback to center crop is permanently disabled. If required subjects are missing or completely outside the crop, the system fails closed (`NO_REQUIRED_ENTITY_FOR_CROP` / `CROP_SUBJECT_OUTSIDE`).
4. **No AI / LLM / Face Recognition Added**: Purely deterministic geometry using real bounding boxes already produced by the grounded evidence engine.

---

## 2. Files Changed

1. **`engines/visual_evidence/subject_aware_composition.py`**:
   - Added `_normalize_bbox` supporting `NormalizedBBox`, `BoundingBox`, dictionary formats, and pixel/normalized coordinates.
   - Refactored `SubjectAwareCompositionEngine.compute_crop_and_verify`:
     - Permanently removed synthetic center fallback (`NormalizedBBox(0.38, 0.15, 0.24, 0.75)`).
     - Single subject: maximizes visibility, centers window on subject centroid within frame bounds `[0, src_w - crop_w]`, maintains boundary margins, and prioritizes leading/focal edge for wide entities ($w > \text{crop\_w}$).
     - Multiple subjects: computes union bounding box, centers on union midpoint when fit ($\le \text{crop\_w}$), or rejects with `CROP_MULTI_SUBJECT_LOST` when subjects span beyond usable width.
     - Added rich output metrics to `PostCropVerificationResult`: `is_visible`, `is_clipped`, `crop_position`, `dimensions`, and `crop_fingerprint`.
2. **`py_visual_evidence/crop_validator.py`**:
   - Updated `compute_subject_aware_crop` to raise a `ValueError` if `target_bboxes` is empty, strictly prohibiting silent center-crop fallback.
   - Added wide-entity leading-edge alignment when subject width exceeds 9:16 crop width.
   - Updated `validate_crop` to fail closed with `NO_REQUIRED_ENTITY_FOR_CROP` when required target points are missing.
3. **`tests/test_subject_aware_crop.py`**:
   - Created focused test suite covering all 7 geometric behaviors plus real Case A and Case B validations.

---

## 3. Crop Algorithm Used

The deterministic optimizer executes the following geometric steps:

1. **Crop Dimensions**:
   - Target aspect ratio: 9:16 ($0.5625$).
   - $\text{crop\_h} = \text{src\_h}$.
   - $\text{crop\_w} = \text{round}(\text{src\_h} \times 9 / 16)$ (adjusted to even integer for H.264 encoder compatibility).
   - $\text{crop\_w} = \min(\text{crop\_w}, \text{src\_w})$.

2. **Absence Check (Fail-Closed)**:
   - If `subject_bboxes` is empty or None:
     - Return `is_valid = False`, `retained_subject_ratio = 0.0`, `is_visible = False`, `primary_rejection_reason = "NO_REQUIRED_ENTITY_FOR_CROP"`.
     - Silent fallback to center crop is strictly prohibited.

3. **Single Subject Positioning**:
   - Let subject coordinates in pixels be $[x_1, y_1, x_2, y_2]$, width $w_{\text{subj}} = x_2 - x_1$, centroid $c_x = x_1 + w_{\text{subj}} / 2$.
   - **Case 1 ($w_{\text{subj}} \le \text{crop\_w}$)**:
     - Ideal crop X: $\text{ideal\_x} = c_x - (\text{crop\_w} / 2)$.
     - Clamped crop X: $\text{crop\_x} = \text{round}(\max(0, \min(\text{src\_w} - \text{crop\_w}, \text{ideal\_x})))$.
     - Subject is 100% retained (`retained = 1.0`, `is_clipped = False`).
   - **Case 2 ($w_{\text{subj}} > \text{crop\_w}$)**:
     - Entity is wider than the 9:16 vertical window.
     - If focal region is provided: centers on `focal_region.center_x`.
     - Else if situated on left ($x_1 < 0.25 \times \text{src\_w}$): aligns with leading edge ($\text{crop\_x} = \max(0, \text{round}(x_1))$) to preserve rearing head, neck, and front limbs.
     - Else if situated on right ($x_2 > 0.75 \times \text{src\_w}$): aligns with trailing edge ($\text{crop\_x} = \min(\text{src\_w} - \text{crop\_w}, \text{round}(x_2 - \text{crop\_w}))$).
     - Else: centers on centroid.
     - Retention: $\text{crop\_w} / w_{\text{subj}}$ (e.g. ~64%), `is_clipped = True`.

4. **Multi-Subject Positioning**:
   - Union span: $X_{\min} = \min(x_1), X_{\max} = \max(x_2)$, $W_{\text{union}} = X_{\max} - X_{\min}$.
   - If $W_{\text{union}} \le \text{usable\_crop\_w}$:
     - $\text{crop\_x} = \text{round}(\max(0, \min(\text{src\_w} - \text{crop\_w}, (X_{\min} + X_{\max}) / 2 - \text{crop\_w} / 2)))$.
     - Both entities retained (strategy: `"MULTI_SUBJECT_CO_PRESENCE"`).
   - If $W_{\text{union}} > \text{usable\_crop\_w}$:
     - If letterbox/scale-down permitted: applies supported strategy.
     - Otherwise: fails closed (`is_valid = False`, `primary_reason = "CROP_MULTI_SUBJECT_LOST"`).

5. **Hard Validation & Metrics**:
   - Overlap area calculated via standard 2D axis-aligned bounding box intersection.
   - If $\text{retained} \le 0.001$: rejected with `CROP_SUBJECT_OUTSIDE`.
   - If $\text{retained} < \text{min\_retained\_ratio}$ (and not wide entity with partial retention): rejected with `CROP_SUBJECT_CLIPPED`.
   - Safe zone margins validated.

---

## 4. Focused Test Results

Test command:
```bash
pytest tests/test_subject_aware_crop.py -v
```
**Results**: `9 passed in 29.14s`

| Test | Objective | Result |
| :--- | :--- | :--- |
| `test_01_right_side_subject_shifts_crop_right` | Subject on right third shifts crop window right (`crop_x = 1196 > 735`) | **PASSED** |
| `test_02_left_side_subject_shifts_crop_left` | Subject on left third shifts crop window left (`crop_x = 274 < 735`) | **PASSED** |
| `test_03_centered_subject_remains_near_center` | Centered subject stays at dead center (`crop_x = 735`) | **PASSED** |
| `test_04_subject_outside_center_crop_retained_by_subject_aware` | Subject outside center crop ($x \in [1536, 1728]$, 0% old) gets 100% retention in new crop | **PASSED** |
| `test_05_multi_subject_crop_when_both_fit` | Two subjects within usable width both retained (`MULTI_SUBJECT_CO_PRESENCE`) | **PASSED** |
| `test_06_impossible_full_containment_explicit_failure` | Two wide-spread subjects explicitly rejected (`CROP_MULTI_SUBJECT_LOST`) | **PASSED** |
| `test_07_absent_required_entity_fails_closed` | Empty detection list rejected without center fallback (`NO_REQUIRED_ENTITY_FOR_CROP`) | **PASSED** |
| `test_08_real_case_a_elder_wand_harry_potter_retained` | Real Case A: Harry on right retained in `[730, 1028]` window (100% retention) | **PASSED** |
| `test_09_real_case_b_buckbeak_slash_malfoy` | Real Case B: Buckbeak on left retained in `[3, 453]` window (~64% retention), Draco absent | **PASSED** |

### Regression Safety
- `pytest tests/test_real_detector_authority.py -k "test_guard or test_default"`: **2 PASSED**
- `pytest tests/test_controlled_validation_fixes.py -k "test_08 or test_09 or test_10 or test_11 or test_12"`: **5 PASSED**

---

## 5. Real Case Validation Results

### Case A: `m8_elder_wand_snap.mp4` @ ~1.0s
- **Source Dimensions**: $1280 \times 528$ (~2.42:1 Cinemascope).
- **Old Center Crop**: $[491, 0, 788, 528]$ (retention: **0.00%**, empty stone bridge).
- **Real OWLv2 Detection**: Harry Potter at $[832, 62, 923, 103]$ (confidence: $0.4927$).
- **Subject-Aware Crop**:
  - Crop window: $[730, 0, 298, 528]$ (shifted right by $+239\text{px}$).
  - Subject retention: **100.00%**.
  - Visible: **True**, Clipped: **False**.
  - Head/face/torso fully preserved within the 9:16 vertical canvas.

### Case B: `m3_buckbeak_slash_malfoy.mp4` @ ~6.5s
- **Source Dimensions**: $1920 \times 800$ (2.40:1 Cinemascope).
- **Old Center Crop**: $[735, 0, 1185, 800]$ (retention: **0.00%**, empty grass and Hagrid's back).
- **Real OWLv2 Detection**:
  - Buckbeak at $[3, 123, 703, 799]$ (confidence: $0.3058$).
  - Draco Malfoy: **0 detections** (absent).
- **Subject-Aware Crop**:
  - Crop window: $[3, 0, 450, 800]$ (shifted left by $-732\text{px}$).
  - Subject retention: **64.22%** (due to wide 700px body vs 450px crop width).
  - Visible: **True**, Clipped: **True**.
  - Leading focal region (Buckbeak's rearing head, neck, chest, and front talons from $X = 3$ to $453$) is preserved.
  - Multi-subject check: Draco Malfoy is **not fabricated**. Visual assertion requiring Draco fails closed.

---

## 6. Confirmation of Constraints

1. **Center-Crop Fallback Disabled**:
   - If bounding boxes are missing or empty, `compute_crop_and_verify` immediately returns `is_valid = False`, `retained_subject_ratio = 0.0`, `is_visible = False`, and `primary_rejection_reason = "NO_REQUIRED_ENTITY_FOR_CROP"`.
   - `VerticalCropValidator.compute_subject_aware_crop` raises a fatal `ValueError` if called without target boxes.
2. **No New AI/LLM Model Added**:
   - Zero LLM, VLM, face-recognition, SAM2, Grounding DINO, or external neural networks were introduced.
   - All positions are computed via pure 2D geometry operating on existing OWLv2 bounding boxes.
3. **Untouched Production & AL AMR**:
   - Autonomous production, publishing, scheduling, YouTube, Google Drive, READY inventory, and workflows remain 100% untouched.
   - AL AMR remains completely untouched.
