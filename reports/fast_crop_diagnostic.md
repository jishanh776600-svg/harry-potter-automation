# Fast Real-Footage Crop Diagnostic

**Date**: 2026-09-26  
**Tool**: `OpenVocabularyGrounder` (OWLv2 Zero-Shot Detector)  
**Status**: DIAGNOSTIC ONLY — NO CODE MODIFIED  

---

## Compact Metric Table

| Case | Subject | Real BBox (px, norm) | Current Crop (px, norm) | Subject Retained % | Required Shift | Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Case A**<br>`m8_elder_wand_snap.mp4` @ ~1.0s | Harry Potter | `[832, 62, 923, 103]`<br>`[x=0.6506, y=0.1193, w=0.0715, h=0.0784]` | `[491, 0, 788, 528]`<br>`[x=0.3836, y=0.0, w=0.2320, h=1.0]` | **0.00%** | **+135px** min<br>(**+238px** to center) | **TOTAL OMISSION**<br>(Decapitation/Off-screen) |
| **Case B**<br>`m3_buckbeak_slash_malfoy.mp4` @ ~6.5s | Buckbeak | `[3, 123, 703, 799]`<br>`[x=0.0018, y=0.1539, w=0.3646, h=0.8457]` | `[735, 0, 1185, 800]`<br>`[x=0.3828, y=0.0, w=0.2344, h=1.0]` | **0.00%** | **-482px** min<br>(**-735px** to left edge) | **TOTAL OMISSION**<br>(Complete subject miss) |

---

## Multi-Subject Check (Draco Malfoy in Case B)

- **Observed Fact**: When evaluated against `EntitySpec(name="Draco Malfoy", role="recipient", description="a blonde boy")`, the real OWLv2 detector produced **0 detections**.
- **Result**: The real detector does **not** hallucinate or invent absent entities.

---

## 1. Current Crop Behavior

- **Observed Fact**:
  - Production render logic (`hp_render_engine.py` lines 516–517) applies an unconditional horizontal center crop:
    `crop=1080:1920:(iw-1080)/2:(ih-1920)/2`.
  - In source Cinemascope space (~2.40:1), this forces the 9:16 vertical window to occupy the horizontal center ($X = 38.3\% \dots 61.6\%$).
  - In Case A (`1280x528`), the crop covers $X \in [491, 788]$ (center = $639.5$).
  - In Case B (`1920x800`), the crop covers $X \in [735, 1185]$ (center = $960.0$).

---

## 2. Whether the Current Crop is Demonstrably Failing

- **Observed Fact**:
  - **Case A**: Harry Potter's real bounding box is $X \in [832, 923]$. The current crop window ends at $X = 788$. Overlap is **0 px**. Retention is **0.00%**. Unnecessary empty background inside crop: **100.00%** (empty bridge stonework).
  - **Case B**: Buckbeak's real bounding box spans $X \in [3, 703]$. The current crop window begins at $X = 735$. Overlap is **0 px**. Retention is **0.00%**. Unnecessary empty background inside crop: **100.00%** (empty paddock grass / Hagrid's back).
  - **Face/Head Preservation**: In both cases, the head/face of the required subject is **0% visible** in the current 9:16 render.
- **Inference**:
  - The current static center-crop is demonstrably failing to preserve the narrative subject in wide-aspect Cinemascope source footage when subjects are composed according to classical cinematic rule-of-thirds framing.

---

## 3. Whether Subject-Aware Crop Placement Would Technically Solve These Examples

- **Observed Fact**:
  - **Case A**: Harry Potter's width is $91\text{px}$, which is much smaller than the 9:16 crop width of $297\text{px}$.
    - Shifting the crop window rightward by $+135\text{px}$ to $+238\text{px}$ places the window at $X \in [729, 1026]$.
    - Under this subject-aware window, Harry Potter retention is **100.00%**, fully preserving his head, face, and torso.
  - **Case B**: Shifting the crop window leftward to $X \in [0, 450]$ (shift of $-735\text{px}$) captures Buckbeak's rearing head, neck, talons, and core torso ($X \in [3, 450]$), increasing visible retention from **0.00%** to **63.86%** of his total bounding volume without requiring letterboxing.
- **Inference**:
  - Subject-aware horizontal placement directly and technically eliminates the total subject omission in both cases.

---

## 4. Important Limitations Discovered

- **Observed Fact**:
  1. **Subject Wider Than 9:16 Window (Case B)**: Buckbeak's rearing wingspan/body spans $700\text{px}$ ($36.5\%$ of frame width). However, a strict 9:16 vertical window on an $800\text{px}$ high frame is only $450\text{px}$ wide ($800 \times 9 / 16$).
     - No pure horizontal crop translation can contain $100\%$ of a $700\text{px}$ subject inside a $450\text{px}$ window without scale adjustment or aspect ratio letterboxing.
  2. **Motion Over Time**: A static shift calculated on a single keyframe will drift if the subject moves across the cut. Sub-shot tracking is necessary across the clip duration.
- **Inference**:
  - For massive/wide entities (e.g. winged creatures, two-shot interactions), horizontal reframing must be combined with intelligent prioritization (e.g. centering on the head/action focal point) or controlled scale accommodation.
