# STORY FORGE — Real Detector Diagnostic Report

**Date:** 2026-09-26  
**Auditor:** Antigravity Forensic Audit  
**Scope:** Lightweight real-detector evaluation using the native `OpenVocabularyGrounder` (OWLv2: `google/owlv2-base-patch16-ensemble`) without mocks, hardcoded boxes, or benchmark grounders.

---

## 1. Frames Inspected & Real Detections

### Frame 1: `m8_elder_wand_snap.mp4` @ t = 1.0s
- **Resolution:** 1280 x 528 (2.42:1 aspect ratio)
- **Entities Queried:** `Harry Potter`, `Elder Wand`
- **Real Detector Output:**
  - **Entity: `Harry Potter`**
    - Confidence: **0.3545** (Full body) / **0.5927** (Upper body/torso)
    - Normalized BBox: `x = 0.5534, y = 0.0074, w = 0.2616, h = 0.9878`
    - Pixel Span: **`x = [708, 1043], y = [3, 525]`** (Normalized Horizontal Center: **0.6842**)
  - **Entity: `Elder Wand`**
    - Confidence: **< 0.10** (Zero detections at $\ge 0.10$ threshold)

---

### Frame 2: `m3_buckbeak_slash_malfoy.mp4` @ t = 6.5s
- **Resolution:** 1920 x 800 (2.40:1 aspect ratio)
- **Entities Queried:** `Buckbeak`, `Draco Malfoy`
- **Real Detector Output:**
  - **Entity: `Buckbeak`**
    - Confidence: **0.4283**
    - Normalized BBox: `x = 0.0018, y = 0.1539, w = 0.3646, h = 0.8457`
    - Pixel Span: **`x = [3, 703], y = [123, 799]`** (Positioned on the far LEFT edge)
  - **Entity: `Draco Malfoy`**
    - Confidence: **0.0000** (**ZERO DETECTIONS** at any threshold; Malfoy is not in this frame)

---

## 2. Real vs. Synthetic Benchmark Comparison

| Attribute | Frame 1: Harry Potter (`m8`) | Frame 2: Draco Malfoy (`m3`) | Frame 2: Buckbeak (`m3`) |
| :--- | :--- | :--- | :--- |
| **Synthetic / Mock BBox** | `x=0.35, y=0.10, w=0.35, h=0.85` | `x=0.15, y=0.15, w=0.35, h=0.80` | `x=0.40, y=0.10, w=0.50, h=0.85` |
| **Synthetic Confidence** | 0.95 (Mocked) | 0.95 (Mocked) | 0.95 (Mocked) |
| **Real Detector BBox** | `x=0.55, y=0.01, w=0.26, h=0.99` | **None (Zero detections)** | `x=0.00, y=0.15, w=0.36, h=0.85` |
| **Real Detector Confidence** | 0.3545 (Full) / 0.5927 (Torso) | **0.0000** | 0.4283 |
| **Real Pixel Center** | $x \approx 876\,\text{px}$ (68.4% across) | **Absent** | $x \approx 353\,\text{px}$ (18.4% across) |
| **Discrepancy Impact** | Crop centered at $x=516$, severing Harry's body and face at $x=813$. | Malfoy is completely absent, yet mock claimed presence at 95% confidence. | Real Buckbeak is on left ($x < 703$), while crop centered on Hagrid at $x=1023$. |

---

## 3. Answers to Critical Diagnostic Questions

### 1. Does the real detector actually detect Harry in the Elder Wand frame?
- **OBSERVED FACT**: **Yes.** The real OWLv2 neural detector successfully detects Harry Potter at $x \in [0.553, 0.815]$ with 0.3545 to 0.5927 confidence.
- **OBSERVED FACT**: The wand itself was not detected by the open-vocabulary model above the 0.10 threshold.

### 2. Does it actually detect the relevant Buckbeak/Malfoy entities in the second frame?
- **OBSERVED FACT**: For Buckbeak: **Yes**, detected on the far left of the frame ($x \in [0.002, 0.366]$) at 0.4283 confidence.
- **OBSERVED FACT**: For Draco Malfoy: **No. Zero detections.** Draco Malfoy does not exist in this frame.

### 3. Are the real detections materially different from the synthetic benchmark boxes?
- **OBSERVED FACT**: **Yes, drastically different:**
  - Harry is located at $x \in [0.55, 0.81]$ (right side), whereas the synthetic box placed him at $x \in [0.35, 0.70]$ (center). This delta caused the vertical crop window to center on the empty viaduct bridge and amputate Harry's face and upper body.
  - In the Buckbeak clip, the synthetic harness claimed Draco Malfoy was present with 0.95 confidence, while real detector evidence shows Malfoy is completely absent. Furthermore, real Buckbeak is on the left ($x \in [0.00, 0.36]$), while the synthetic box placed him in the center/right ($x \in [0.40, 0.90]$).

### 4. Does current py_visual_evidence have a genuine real-pixel verification path, or is the integration still benchmark-grounded?
- **OBSERVED FACT**: `py_visual_evidence` *does* have a fully functional neural detector (`OpenVocabularyGrounder` with local OWLv2 weights cached on disk).
- **OBSERVED FACT**: The Story Forge validation harness (`run_final_human_review_validation.py`) explicitly instantiated and injected `DeterministicBenchmarkGrounder` with hardcoded bounding boxes, completely bypassing the neural detector.
- **INFERENCE**: The recent validation pass (`FINAL_RENDER_VALIDATION = PASS`) was an artifact of synthetic benchmark grounding. Because the validation script bypassed the real detector, it certified a clip where Malfoy was absent and computed a crop window that decapitated Harry Potter.

---

## 4. Conclusion & Smallest Next Investigation

The visual degradation in the final renders is directly traced to the fact that the integration harness relied on hardcoded synthetic coordinates rather than live real-pixel grounding.

**Smallest next step**:
Do not implement code changes or refactor. The next investigation should simply verify the latency and accuracy of running `OpenVocabularyGrounder` end-to-end inside `StoryForgeVisualEvidenceAdapter` on a single test candidate to measure whether it correctly rejects `m3_buckbeak_slash_malfoy.mp4` fail-closed.
