import sys; sys.path.insert(0, ".")
import cv2
from py_visual_evidence.schema import EntitySpec
from py_visual_evidence.grounding import OpenVocabularyGrounder
from pathlib import Path

brain = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36")

# Use the same alias descriptions FRV resolves for Buckbeak and Draco Malfoy
# (HP_CHARACTER_ALIASES['buckbeak'][0] = 'a creature with wings')
# (HP_CHARACTER_ALIASES['draco malfoy'][0] = 'a blonde boy')
# FRV passes description=aliases[0]
entity_specs = [
    EntitySpec(name="Buckbeak", role="required", description="a creature with wings"),
    EntitySpec(name="Draco Malfoy", role="required", description="a blonde boy"),
    # Also try more descriptive aliases
    EntitySpec(name="Buckbeak_alt", role="required", description="hippogriff"),
    EntitySpec(name="Draco_alt", role="required", description="draco malfoy"),
]

grounder = OpenVocabularyGrounder(confidence_threshold=0.10)

for label, ts in [("b2_sample1", 4.275), ("b2_sample2", 6.425), ("b2_start", 3.2)]:
    frame_path = brain / f"novel_probe_{label}.jpg"
    frame = cv2.imread(str(frame_path))
    print(f"\n=== t={ts}s ({label}) frame={frame.shape} ===")
    dets = grounder.ground_entities(frame, entity_specs, timestamp_sec=ts)
    if dets:
        for d in sorted(dets, key=lambda x: -x.confidence):
            b = d.bbox
            print(f"  {d.entity_name}: conf={d.confidence:.3f} bbox=[{b.x:.3f},{b.y:.3f},{b.w:.3f},{b.h:.3f}]")
    else:
        print("  NO DETECTIONS (threshold=0.10)")
