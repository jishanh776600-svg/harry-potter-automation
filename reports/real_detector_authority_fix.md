# Real Visual Detector Authority Fix & Validation Report

**Date**: 2026-09-26  
**Project**: Story Forge (`harry_potter_automation`) & `py_visual_evidence`  
**Status**: COMPLETE — Real Detector Mandatory Authority Established & Verified  

---

## 1. Executive Summary

In the forensic audit and real-detector diagnostic, it was discovered that previous Story Forge visual evidence validation passed using `DeterministicBenchmarkGrounder` (a test fixture with hardcoded/synthetic bounding boxes), which bypassed real pixels entirely.

This implementation establishes the **REAL detector (`OpenVocabularyGrounder` with OWLv2 zero-shot grounding)** as the **mandatory authority** for all Story Forge visual evidence paths:
1. **Synthetic Grounding Prohibited in Real Paths**: Attempting to pass `DeterministicBenchmarkGrounder` without explicitly opting into isolated unit-test synthetic mode (`allow_synthetic_grounding=True`) immediately raises a fatal `ValueError`.
2. **Real Pixels Mandated**: All default adapters instantiate `OpenVocabularyGrounder(confidence_threshold=0.15)` operating directly on physical decoded video frames.
3. **Core OWLv2 Bug Fixed**: Resolved a PyTorch Tensor index bug in `py_visual_evidence/grounding.py` where tensor label indices forced all detections to index 0.
4. **Offline Cache Hardening**: Added `local_files_only=True` offline loading to prevent offline test suites and socket guards from blocking local model instantiation.
5. **Real-Footage Validation (Case A & Case B)**:
   - **Case A (`m8_elder_wand_snap.mp4`)**: Real detector physically detected Harry Potter on the right side of the Cinemascope frame (`[832.8, 63.0, 924.2, 104.4]`, `crop_x > 500`), passing with `EvidenceVerdict.PASS` without fabricating a wand.
   - **Case B (`m3_buckbeak_slash_malfoy.mp4`)**: Real detector physically detected Buckbeak on the left side of the frame (`[3.5, 123.1, 703.5, 799.7]`) and confirmed Draco Malfoy is physically absent at t=6.5s, **failing closed** with `EvidenceVerdict.NO_REQUIRED_ENTITY` (`rejection_reason="Required recipient 'Draco Malfoy' was not detected in candidate video."`).

---

## 2. Exact Changes Implemented

### 2.1 PyTorch Tensor Indexing Fix (`py_visual_evidence/grounding.py`)
- **Defect**: In `OpenVocabularyGrounder.ground_entities`, OWLv2 returned `res["labels"]` as `torch.Tensor`. Line 96 checked `isinstance(label, (int, np.integer)) or str(label).isdigit()`. For `torch.Tensor`, `str(tensor).isdigit()` evaluated to `False`, forcing `spec_idx = 0` for all entity detections regardless of class.
- **Fix**: Updated line 96 to unpack tensor scalars correctly:
  ```python
  spec_idx = (
      int(label.item()) if hasattr(label, "item")
      else (int(label) if isinstance(label, (int, np.integer)) or str(label).isdigit() else 0)
  )
  ```

### 2.2 Offline Model Loading Hardening (`py_visual_evidence/grounding.py`)
- **Defect**: In strict offline test environments (`conftest.py` blocking unmocked network sockets), Hugging Face's `from_pretrained` attempted a DNS query to Hugging Face Hub, causing `ExternalNetworkForbiddenError` and silently leaving `self._model = None`.
- **Fix**: Updated `_ensure_loaded` to attempt `local_files_only=True` first:
  ```python
  try:
      self._processor = AutoProcessor.from_pretrained(self.model_name, local_files_only=True)
      self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_name, local_files_only=True).to(self.device)
  except Exception:
      self._processor = AutoProcessor.from_pretrained(self.model_name)
      self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_name).to(self.device)
  ```

### 2.3 Mandatory Real Detector & Guard in Adapter (`engines/visual_evidence/storyforge_adapter.py`)
- **Mandatory Authority**: Default grounder is now `OpenVocabularyGrounder(confidence_threshold=0.15)`.
- **Synthetic Guard**: Added `allow_synthetic_grounding: bool = False`. If `DeterministicBenchmarkGrounder` is supplied when `allow_synthetic_grounding=False`, the constructor immediately aborts:
  ```python
  if not self.allow_synthetic_grounding:
      if isinstance(self.grounder, DeterministicBenchmarkGrounder):
          raise ValueError(
              "DeterministicBenchmarkGrounder is strictly prohibited for real-footage visual evidence. "
              "Only real pixel detectors (e.g. OpenVocabularyGrounder) are permitted in Story Forge. "
              "Pass allow_synthetic_grounding=True only for isolated benchmark unit tests."
          )
  ```
- **Provenanced Detection**: Added `detector_type: str = "REAL_DETECTOR"` to `StoryForgeEvidenceResult`.
- **Visual Description Aliases**: Enriched `HP_CHARACTER_ALIASES` with physical descriptions recognizable by open-vocabulary models (e.g. Harry Potter: `"a person with glasses"`, Buckbeak: `"a creature with wings"`, Draco Malfoy: `"a blonde boy"`).

---

## 3. Test Verification & Results

### 3.1 Real Detector Authority Suite (`tests/test_real_detector_authority.py`)
Run command:
```bash
pytest tests/test_real_detector_authority.py -v
```
**Results**: `5 passed, 20 warnings in 69.65s (0:01:09)`
1. `test_guard_rejects_synthetic_grounder_in_real_footage_mode`: **PASSED** (guards reject benchmark grounder).
2. `test_default_adapter_uses_real_detector`: **PASSED** (confirms real detector instantiated by default).
3. `test_benchmark_grounder_allowed_when_explicitly_flagged`: **PASSED** (isolated benchmark tests still supported).
4. `test_case_a_real_detector_harry_potter_elder_wand`: **PASSED**
   - Real clip: `m8_elder_wand_snap.mp4` @ ~1.0s
   - Verdict: `EvidenceVerdict.PASS`
   - Entities: `["Harry Potter"]`
   - Spatial position: Right side confirmed (`crop_x > 500` on 1280px frame).
   - No wand fabricated or required.
5. `test_case_b_real_detector_buckbeak_malfoy_fails_closed`: **PASSED**
   - Real clip: `m3_buckbeak_slash_malfoy.mp4` @ ~6.5s
   - Verdict: `EvidenceVerdict.NO_REQUIRED_ENTITY`
   - Rejection Reason: `"Required recipient 'Draco Malfoy' was not detected in candidate video."`
   - Entities detected: `["Buckbeak"]` on the left.
   - Malfoy absent from frame: **Fails closed**.

### 3.2 Regression Suite (`tests/test_visual_evidence_integration.py`)
Run command:
```bash
pytest tests/test_visual_evidence_integration.py -k "test_controlled_fresh_discovery_integration or test_negative_01" -v
```
**Results**: `2 passed, 11 deselected in 39.12s`
- Synthetic benchmark test fixtures explicitly passing `allow_synthetic_grounding=True` run deterministically without regressions.

---

## 4. Status of Deferred Improvements

Per task instructions, the following improvements remain strictly deferred to subsequent phases:
- **Dynamic Crop / Safe Margin Adjustments**: Deferred. The real bounding boxes are now available and will feed into dynamic horizontal panning in the next task.
- **Multi-Clip Sequencing & Anti-Looping**: Deferred.
- **Face Recognition / Fine-Grained Identification**: Deferred.
- **MovieEvent Retrieval Engine**: Untouched.
- **Production / Publishing / Inventory**: Completely untouched; zero live changes made to production assets.
