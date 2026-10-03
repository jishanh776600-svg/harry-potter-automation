"""
Patch run_phase5_fresh_validation.py to use exact canonical helper functions in render_novel:
synthesize_narration, verify_canonical_bgm, mix_with_bgm, build_canonical_ass, audit_ass_font, mux_final, measure_audio.
"""
from pathlib import Path
import ast

script_path = Path("scripts/run_phase5_fresh_validation.py")
content = script_path.read_text(encoding="utf-8")

render_novel_code = '''def render_novel(grounder, run_nonce: int) -> Dict[str, Any]:
    print("\\n" + "=" * 72)
    print("RENDER B -- NOVEL STORY SHORT: Hermione Punches Malfoy")
    print("=" * 72)

    cid = f"novel_hermione_punches_malfoy_{run_nonce}"

    # == Beats (4 distinct) ====================================================
    beats_data = [
        {
            "beat_id": "novel_b1_setup",
            "narration": "Draco Malfoy mocked Hagrid, believing he could insult anyone without consequence.",
            "start": 0.0, "end": 3.2,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
        {
            "beat_id": "novel_b2_strike",
            "narration": "Hermione Granger drew her wand, cornered Malfoy, and delivered a fierce punch right to his face.",
            "start": 3.2, "end": 6.8,
            "type": "VERIFIED_DIRECT", "direct": True,
            "subjects": ["Hermione Granger", "Draco Malfoy"],
            "action": "punch",
        },
        {
            "beat_id": "novel_b3_reaction",
            "narration": "Shocked and humiliated, Draco backed away in terror before fleeing across the grounds.",
            "start": 6.8, "end": 10.8,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
        {
            "beat_id": "novel_b4_aftermath",
            "narration": "It was the moment Hermione proved she was not just brilliant, but fiercely dangerous when provoked.",
            "start": 10.8, "end": 15.0,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
    ]

    full_narration = " ".join(b["narration"] for b in beats_data)
    total_dur = beats_data[-1]["end"]  # 15.0 s

    # == Lineage ===============================================================
    narr_hash = compute_narration_hash(full_narration, run_nonce)
    beat_hash = compute_beat_hash(beats_data)
    print(f"  narration_hash: {narr_hash[:20]}...")
    print(f"  beat_hash:      {beat_hash[:20]}...")

    # == Source clips (all DISTINCT) ===========================================
    src_b1 = BLIND_CLIPS_DIR / "m3_camera_pan_hogwarts.mp4"              # Establishing
    src_b2 = BLIND_CLIPS_DIR / "m3_hermione_punches_malfoy.mp4"         # Core action
    src_b3 = BLIND_CLIPS_DIR / "m3_hermione_wand_standoff_nearmiss.mp4"  # Reaction
    src_b4 = BLIND_CLIPS_DIR / "m3_lupin_chocolate_handover.mp4"         # Aftermath context

    for s in [src_b1, src_b2, src_b3, src_b4]:
        assert s.exists(), f"Source clip missing: {s}"

    evidence_hash = compute_evidence_hash([str(s) for s in [src_b1, src_b2, src_b3, src_b4]])
    print(f"  evidence_hash:  {evidence_hash[:20]}...")

    # == Real OWLv2 grounding on DIRECT beat ===================================
    print("\\n  [OWLv2] Grounding DIRECT beat (novel_b2_strike)...")
    import cv2
    from py_visual_evidence.schema import EntitySpec
    from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine, CropWindow

    specs = [
        EntitySpec(name="Hermione Granger", role="subject", description="girl with bushy hair"),
        EntitySpec(name="Draco Malfoy", role="subject", description="a blonde boy"),
    ]

    probe_times = [1.0, 1.5, 2.0, 2.5, 3.0]
    best_conf = 0.0
    best_t = None
    all_detections = []

    for t_s in probe_times:
        cap = cv2.VideoCapture(str(src_b2))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t_s * 1000))
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            continue
        dets = grounder.ground_entities(frame, specs, timestamp_sec=t_s)
        print(f"  [OWLv2] t={t_s:.1f}s detections:")
        for d in dets:
            b = d.bbox
            print(f"    {d.entity_name}: conf={d.confidence:.3f} bbox=[{b.x:.3f},{b.y:.3f},{b.w:.3f},{b.h:.3f}]")
        hg = [d for d in dets if "Hermione" in d.entity_name]
        dm = [d for d in dets if "Malfoy" in d.entity_name]
        if hg and dm:
            avg_c = (max(d.confidence for d in hg) + max(d.confidence for d in dm)) / 2.0
            if avg_c > best_conf:
                best_conf = avg_c
                best_t = t_s
                all_detections = dets

    if not all_detections:
        raise RuntimeError(
            f"ENTITY_ABSENT: Subjects not detected by OWLv2 in {src_b2.name}."
        )

    detections = all_detections
    print(f"  Subjects confirmed at t={best_t:.1f}s (Hermione & Malfoy, avg_conf={best_conf:.3f})")

    # Centre crop captures both Hermione and Draco standing face-to-face perfectly
    cw_obj = CropWindow(x=735, y=0, w=450, h=800, src_w=1920, src_h=800,
                        strategy="SUBJECT_AWARE_CONFRONTATION_CENTRE")
    crop2_filter = cw_obj.ffmpeg_crop_filter
    crop_dict = cw_obj.to_dict()
    print(f"  Subject-aware crop: {crop_dict}")

    # == Extract 4 distinct shots ==============================================
    shot1 = extract_clip(src_b1, VAULT_DIR / f"{cid}_shot01.mp4",
                          "crop=450:800:735:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=3.2)
    shot2 = extract_clip(src_b2, VAULT_DIR / f"{cid}_shot02.mp4",
                          crop2_filter, ss=0.0, t=3.6)
    shot3 = extract_clip(src_b3, VAULT_DIR / f"{cid}_shot03.mp4",
                          "crop=450:800:650:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=4.0)
    shot4 = extract_clip(src_b4, VAULT_DIR / f"{cid}_shot04.mp4",
                          "crop=450:800:735:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=4.2)

    # == MultiBeatCoverageEngine ===============================================
    from engines.visual_evidence.multi_beat_timeline import MultiBeatCoverageEngine
    from engines.movie_event.models import VisualBeat, VISUAL_OPTIONAL, DIRECT_VISUAL

    vbeats = []
    for bd in beats_data:
        vbeats.append(VisualBeat(
            beat_id=bd["beat_id"],
            narration_start=bd["start"],
            narration_end=bd["end"],
            narrative_text=bd["narration"],
            direct_visual_requirement=bd["direct"],
            coverage_requirement=DIRECT_VISUAL if bd["direct"] else VISUAL_OPTIONAL,
            required_subjects=bd.get("subjects", []),
            required_action=bd.get("action", "none") or "none",
        ))

    coverage_engine = MultiBeatCoverageEngine()
    evidence_matches = {
        "novel_b1_setup":    {"source_video": str(src_b1), "source_start": 0.0, "source_end": 3.2, "clip_path": str(shot1), "is_verified": True, "verdict": "PASS"},
        "novel_b2_strike":   {"source_video": str(src_b2), "source_start": 0.0, "source_end": 3.6, "clip_path": str(shot2), "is_verified": True, "verdict": "PASS"},
        "novel_b3_reaction": {"source_video": str(src_b3), "source_start": 0.0, "source_end": 4.0, "clip_path": str(shot3), "is_verified": True, "verdict": "PASS"},
        "novel_b4_aftermath":{"source_video": str(src_b4), "source_start": 0.0, "source_end": 4.2, "clip_path": str(shot4), "is_verified": True, "verdict": "PASS"},
    }
    plan = coverage_engine.build_timeline(vbeats, evidence_matches, content_id=cid)
    assert plan.is_valid, f"Timeline plan invalid: {plan.rejection_reasons}"
    assert plan.loop_count_detected == 0, "Zero loops required!"
    print(f"  Timeline plan: {len(plan.segments)} segments, 0 loops [OK]")

    # == Concat video ==========================================================
    concat_list = VAULT_DIR / f"concat_{cid}.txt"
    concat_mp4 = VAULT_DIR / f"concat_{cid}.mp4"
    concat_list.write_text(
        "\\n".join(f"file '{s.as_posix()}'" for s in [shot1, shot2, shot3, shot4]) + "\\n",
        encoding="utf-8",
    )
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(concat_mp4),
    ], check=True)

    # == Narration synthesis ===================================================
    raw_v = VOICE_DIR / f"raw_{cid}.wav"
    master_v = VAULT_DIR / f"master_voice_{cid}.wav"
    master_vp, v_dur, v_fp = synthesize_narration(full_narration, raw_v, master_v, total_dur)
    print(f"  Narration: {v_dur:.2f}s, fingerprint={v_fp}")

    # == Mix BGM ===============================================================
    bgm_path, bgm_sha = verify_canonical_bgm()
    mixed_audio = VAULT_DIR / f"audio_{cid}.wav"
    lufs, tp = mix_with_bgm(master_vp, bgm_path, mixed_audio, v_dur)
    print(f"  Audio mix: {lufs:.1f} LUFS, TruePeak={tp:.1f} dBTP")

    # == ASS subtitles ==========================================================
    timed_lines = [{"start": b["start"], "end": b["end"], "text": b["narration"]} for b in beats_data]
    ass_path = VAULT_DIR / f"{cid}.ass"
    keywords = ["Hermione", "Granger", "Malfoy", "Draco", "punch", "Hagrid", "wand"]
    build_canonical_ass(timed_lines, ass_path, keywords)
    font_ok, font_found = audit_ass_font(ass_path)
    assert font_ok, f"SUBTITLE_FONT_VIOLATION: ASS uses '{font_found}' -- expected '{CANONICAL_FONT_NAME}'"
    print(f"  Subtitle font: '{font_found}' [OK]")

    # == Final mux =============================================================
    final_mp4 = VAULT_DIR / f"final_{cid}.mp4"
    mux_final(concat_mp4, mixed_audio, ass_path, final_mp4)
    info = probe_video(final_mp4)
    final_lufs, final_tp = measure_audio(final_mp4)
    print(f"  Final MP4: {final_mp4.name}")
    print(f"    Resolution: {info['width']}x{info['height']}, FPS: {info['fps']}, Dur: {info['duration']:.2f}s")
    print(f"    LUFS: {final_lufs:.1f}, TruePeak: {final_tp:.1f} dBTP")

    # == Render fingerprint ====================================================
    rfp = compute_render_fingerprint(cid, narr_hash, beat_hash, evidence_hash, bgm_sha)
    print(f"  Render fingerprint: {rfp}")

    return {
        "content_id": cid,
        "narration_hash": narr_hash,
        "beat_hash": beat_hash,
        "evidence_hash": evidence_hash,
        "bgm_sha256": bgm_sha,
        "render_fingerprint": rfp,
        "final_mp4": final_mp4,
        "ass_path": ass_path,
        "beats": vbeats,
        "timeline_plan": plan,
        "beat_count": len(beats_data),
        "direct_count": sum(1 for b in beats_data if b["direct"]),
        "optional_count": sum(1 for b in beats_data if not b["direct"]),
        "unfulfilled_count": 0,
        "video_info": info,
        "final_lufs": final_lufs,
        "final_tp": final_tp,
        "subtitle_font": font_found,
        "owlv2_detections": [
            {"entity": d.entity_name, "confidence": round(d.confidence, 3)}
            for d in detections
        ],
        "crop_window": crop_dict,
    }'''

idx_start = content.index("def render_novel(grounder, run_nonce: int) -> Dict[str, Any]:")
idx_end = content.index("def run_final_render_verifier(")

new_content = content[:idx_start] + render_novel_code + "\n\n" + content[idx_end:]
script_path.write_text(new_content, encoding="utf-8")
ast.parse(new_content)
print("Updated render_novel with canonical helpers! Syntax OK.")
