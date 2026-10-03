"""
Patch run_phase5_fresh_validation.py -- Fix Novel DIRECT beat OWLv2 probe:

The current probe finds Buckbeak in the SOURCE clip (1920x800), picks crop strategy,
but NEVER verifies that the entity is detectable in the CROPPED (1080x1920) frame.
At t=1.593s Buckbeak rears up -- head/wings fill the upper-half, lower body fills
lower-half, crop at x=735 w=450 only captures the lower hindquarters -> OWLv2 fails.

Fix: After crop is decided, simulate the crop on each probe frame and verify OWLv2
can detect the entity in the cropped region. If not, try other timestamps.
Also: Buckbeak's bbox in source has w=0.498 but the rendered frame shows only
lower body -> the bbox was measured at a rearing moment where the WHOLE body spans
0.498 of width but the top portion (eagle head/wings) is cut by the source
frame top edge (y starts at 0.020).

Better fix: use a wider set of probe timestamps (every 0.5s through the clip)
and for each, simulate the crop and run OWLv2 on the simulated crop.
Pick the timestamp+crop_x that maximises detection confidence in the final 9:16 frame.
"""
from pathlib import Path
import ast

script = Path("scripts/run_phase5_fresh_validation.py")
content = script.read_bytes().decode("utf-8")

# ── Replace the Novel DIRECT beat OWLv2 + crop block (L728-L812) ────────────
OLD_BLOCK = '''    import cv2

    from py_visual_evidence.schema import EntitySpec
    specs = [
        EntitySpec(name="Buckbeak", role="subject", description="large hippogriff creature with eagle head and wings"),
        EntitySpec(name="Draco Malfoy", role="subject", description="blonde boy in school robes"),
    ]

    cap_probe = cv2.VideoCapture(str(src_b2))
    total_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_cap = cap_probe.get(cv2.CAP_PROP_FPS) or 25.0
    clip_dur = total_frames / fps_cap
    cap_probe.release()

    # Probe at 20%, 40%, 60%, 80% through the clip
    probe_times_ms = [int(clip_dur * pct * 1000) for pct in [0.2, 0.4, 0.6, 0.8, 0.3]]
    all_detections = []
    malfoy_dets = []
    buckbeak_dets = []
    best_sample_t = None

    for t_ms in probe_times_ms:
        cap = cv2.VideoCapture(str(src_b2))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t_ms))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            continue
        dets = grounder.ground_entities(frame, specs, timestamp_sec=t_ms / 1000.0)
        print(f"  [OWLv2] t={t_ms/1000.0:.1f}s detections:")
        for d in dets:
            b = d.bbox
            print(f"    {d.entity_name}: conf={d.confidence:.3f} bbox=[{b.x:.3f},{b.y:.3f},{b.w:.3f},{b.h:.3f}]")
        m = [d for d in dets if "Malfoy" in d.entity_name]
        bk = [d for d in dets if "Buckbeak" in d.entity_name]
        if m or bk:
            all_detections = dets
            malfoy_dets = m
            buckbeak_dets = bk
            best_sample_t = t_ms / 1000.0
            break  # Found at least one subject -- stop probing

    if not (malfoy_dets or buckbeak_dets):
        raise RuntimeError(
            "ENTITY_ABSENT: Neither Buckbeak nor Draco Malfoy detected by real OWLv2 "
            f"at any probe timestamp in novel_b2_strike source clip ({src_b2.name}). "
            "Cannot claim DIRECT visual evidence for this beat."
        )
    detections = all_detections
    print(f"  Subject confirmed at t={best_sample_t}s "
          f"(Buckbeak: {bool(buckbeak_dets)}, Malfoy: {bool(malfoy_dets)})")

    # Subject-aware crop: focus on strike zone
    from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine, CropWindow
    comp_engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    if malfoy_dets:
        crop_res = comp_engine.compute_crop_and_verify(
            subject_bboxes=[malfoy_dets[0].bbox], src_w=1920, src_h=800,
        )
        crop2_filter = crop_res.crop_window.ffmpeg_crop_filter
        crop_dict = crop_res.crop_window.to_dict()
    elif buckbeak_dets:
        bk = buckbeak_dets[0]
        # If Buckbeak spans >60% of frame width, use centre crop so FRV
        # can detect the entity in the cropped 1080x1920 output.
        if bk.bbox.w > 0.40:  # Buckbeak bbox.w=0.498 triggers centre crop
            from engines.visual_evidence.subject_aware_composition import CropWindow
            cw = CropWindow(x=735, y=0, w=450, h=800, src_w=1920, src_h=800,
                            strategy=\'CENTRE_SUBJECT_WIDE\')
            crop2_filter = cw.ffmpeg_crop_filter
            crop_dict = cw.to_dict()
            crop_res = None
        else:
            crop_res = comp_engine.compute_crop_and_verify(
                subject_bboxes=[bk.bbox], src_w=1920, src_h=800,
            )
            crop2_filter = crop_res.crop_window.ffmpeg_crop_filter
            crop_dict = crop_res.crop_window.to_dict()
    else:
        # Geometrically impossible to reach here -- above assert would have fired
        cw = CropWindow(x=735, y=0, w=450, h=800, src_w=1920, src_h=800, strategy="CENTRE_FALLBACK")
        crop2_filter = cw.ffmpeg_crop_filter
        crop_dict = cw.to_dict()
        crop_res = None
    print(f"  Subject-aware crop: {crop_dict}")'''

NEW_BLOCK = '''    import cv2
    import numpy as np

    from py_visual_evidence.schema import EntitySpec
    from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine, CropWindow

    specs = [
        EntitySpec(name="Buckbeak", role="subject", description="large hippogriff creature with eagle head and wings"),
        EntitySpec(name="Draco Malfoy", role="subject", description="blonde boy in school robes"),
    ]

    cap_probe = cv2.VideoCapture(str(src_b2))
    total_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_cap = cap_probe.get(cv2.CAP_PROP_FPS) or 25.0
    clip_dur = total_frames / fps_cap
    cap_probe.release()

    # Probe every 0.5s through the clip. For each timestamp:
    # 1. Run OWLv2 on the SOURCE frame (1920x800) -- find all subject detections
    # 2. For each detected subject, compute what crop would be used
    # 3. Simulate that crop (extract the region from the source frame)
    # 4. Run OWLv2 on the SIMULATED CROP (as a proxy for the 1080x1920 FRV frame)
    # 5. Pick the timestamp+crop where the CROPPED detection is strongest.
    # This ensures FRV will find the entity in the final rendered 9:16 pixels.
    comp_engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)

    CROP_X, CROP_W, CROP_H = 735, 450, 800  # fixed centre crop for wide entities (>0.40 w)
    # Also try left crop (x=408, w=450) for comparison
    CROP_CANDIDATES = [
        ("centre", 735, 450, 800),
        ("left",   408, 450, 800),
        ("right",  960, 450, 800),
        ("mid",    580, 450, 800),
    ]

    probe_interval = max(0.5, clip_dur / 16)
    probe_times_s = [i * probe_interval for i in range(1, 16) if i * probe_interval < clip_dur]

    best_conf = 0.0
    best_t = None
    best_crop_filter = None
    best_crop_dict = None
    best_entity = None
    all_detections = []

    print(f"  [OWLv2] Scanning {len(probe_times_s)} timestamps in {src_b2.name} (dur={clip_dur:.1f}s)...")
    for t_s in probe_times_s:
        cap = cv2.VideoCapture(str(src_b2))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t_s * 1000))
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            continue

        src_dets = grounder.ground_entities(frame, specs, timestamp_sec=t_s)
        if not src_dets:
            continue

        # For each crop candidate, simulate crop and verify detectability
        for crop_name, cx, cw, ch in CROP_CANDIDATES:
            crop_region = frame[0:ch, cx:cx + cw]
            # Scale to 1080x1920 (same as final render) -- use smaller scale for speed
            cropped_resized = cv2.resize(crop_region, (540, 960))  # half-size proxy
            crop_dets = grounder.ground_entities(cropped_resized, specs, timestamp_sec=t_s)
            for d in crop_dets:
                if d.confidence > best_conf:
                    best_conf = d.confidence
                    best_t = t_s
                    best_entity = d.entity_name
                    all_detections = crop_dets
                    # Build the ffmpeg filter for the winning crop
                    cw_obj = CropWindow(x=cx, y=0, w=cw, h=ch, src_w=1920, src_h=800,
                                        strategy=f"POST_CROP_VERIFIED_{crop_name.upper()}")
                    best_crop_filter = cw_obj.ffmpeg_crop_filter
                    best_crop_dict = cw_obj.to_dict()

        if best_conf >= 0.15 and best_t is not None:
            # Found a crop+timestamp where entity is detectable in cropped frame
            break

    if best_t is None or best_conf < 0.10:
        raise RuntimeError(
            "ENTITY_ABSENT: Neither Buckbeak nor Draco Malfoy detectable in any "
            f"9:16 crop of {src_b2.name} at any probe timestamp (best_conf={best_conf:.3f}). "
            "Cannot claim DIRECT visual evidence for this beat."
        )

    # Detections in crop-verified frame
    buckbeak_dets = [d for d in all_detections if "Buckbeak" in d.entity_name]
    malfoy_dets   = [d for d in all_detections if "Malfoy"   in d.entity_name]
    detections = all_detections
    print(f"  Subject confirmed in cropped frame at t={best_t:.2f}s "
          f"(entity={best_entity}, conf={best_conf:.3f})")
    print(f"  Post-crop verified crop: {best_crop_dict}")

    crop2_filter = best_crop_filter
    crop_dict    = best_crop_dict
    print(f"  Subject-aware crop: {crop_dict}")'''

if OLD_BLOCK in content:
    content = content.replace(OLD_BLOCK, NEW_BLOCK)
    print("[Novel probe] Replaced source-only OWLv2 probe with post-crop-verified probe")
else:
    print("[Novel probe] ERROR: old block not found")
    # Find approximate location
    for i, ln in enumerate(content.splitlines(), 1):
        if "probe_times_ms" in ln or "ENTITY_ABSENT" in ln:
            print(f"  L{i}: {ln.strip()!r}")

script.write_bytes(content.encode("utf-8"))
try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR at L{e.lineno}: {e.msg}")
    lines = content.splitlines()
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        mark = ">>>" if i+1 == e.lineno else "   "
        print(f"{mark} L{i+1}: {lines[i]!r}")
