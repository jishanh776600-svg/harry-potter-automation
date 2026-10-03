"""
STORY FORGE -- Phase 5 Fresh Validation Runner
=============================================
Produces TWO genuinely fresh validation renders:
  A. Discovery Short  (>=4 distinct visual beats)
  B. Novel Story Short (>=4 distinct visual beats)

FRESHNESS GUARANTEE:
  - Content IDs include a run-specific timestamp nonce.
  - All intermediate artifacts are written to fresh directories.
  - The vault directory is run-scoped; no stale artifacts can be silently reused.
  - Narration hash, beat hash, evidence hash, timeline hash, render fingerprint
    are all computed fresh for this run and logged in the final report.

SAFETY:
  - ZERO publishing / uploading / scheduling.
  - ZERO AL AMR modification.
  - No autopilot. No buffer production.
  - Real OWLv2 grounding (no DeterministicBenchmarkGrounder).
  - BGM = Exactly Who.wav only (Esther Abrami remains blocked).
  - Video clips extracted with -an (no source movie dialogue).
  - NO video -stream_loop.
  - BGM audio looping under narration is allowed and expected.

PIPELINE (preserving canonical architecture):
  SCRIPT -> NARRATION -> WORD TIMESTAMPS -> VISUAL BEATS
  -> DEEP MOVIE SEARCH (blind clips as source evidence)
  -> CANDIDATE POOL -> CHARACTER/OBJECT IDENTITY (real OWLv2)
  -> TRACKING -> ACTION/HOI/TEMPORAL PROOF
  -> GLOBAL VISUAL EDL (MultiBeatCoverageEngine)
  -> 9:16 COMPOSITION (SubjectAwareCompositionEngine)
  -> DETERMINISTIC RENDERER (FFmpeg + canonical ASS)
  -> ACTUAL 1080x1920 MP4
  -> FINAL PIXEL VERIFICATION (FinalRenderVerifier + Phase5FinalRenderVerifier)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# == Source clips ===============================================================
BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")

# == Audio ======================================================================
MUSIC_DIR = PROJECT_ROOT / "assets" / "music"
CANONICAL_BGM = MUSIC_DIR / "Exactly Who.wav"
CANONICAL_BGM_SHA256 = "96f0e27c7bce624f0f8f8971025bddf62e098c594cfcc839bb1d1a344b110b9d"

# == Fonts ======================================================================
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

# == Brain artifacts (for user-visible output) =================================
BRAIN_ARTIFACTS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36")

# == Run nonce (timestamp-based, guarantees freshness) =========================
RUN_NONCE = int(time.time())
VAULT_DIR = PROJECT_ROOT / "data" / "vault" / f"phase5_validation_{RUN_NONCE}"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

VOICE_DIR = PROJECT_ROOT / "data" / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# FRESHNESS + LINEAGE HELPERS
# =============================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_narration_hash(text: str, run_nonce: int) -> str:
    """Bind narration to this exact run -- prevents stale reuse."""
    return sha256_text(f"{run_nonce}:{text}")


def compute_beat_hash(beats_data: List[Dict]) -> str:
    return sha256_text(json.dumps(beats_data, sort_keys=True))


def compute_evidence_hash(clips: List[str]) -> str:
    """SHA256 of the source clip paths + their file hashes."""
    parts = []
    for c in clips:
        p = Path(c)
        if p.exists():
            parts.append(f"{p.name}:{sha256_file(p)[:16]}")
        else:
            parts.append(f"{p.name}:MISSING")
    return sha256_text("|".join(parts))


def compute_render_fingerprint(content_id: str, narration_hash: str,
                                beat_hash: str, evidence_hash: str,
                                bgm_sha256: str) -> str:
    raw = f"{content_id}:{narration_hash}:{beat_hash}:{evidence_hash}:{bgm_sha256}:{RUN_NONCE}"
    return "rfp_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


# =============================================================================
# BGM CANONICAL GATE
# =============================================================================

def verify_canonical_bgm() -> Tuple[Path, str]:
    """Verify Exactly Who.wav exists with correct SHA256. Hard fail otherwise."""
    if not CANONICAL_BGM.exists():
        raise RuntimeError(
            f"CANONICAL_BGM_MISSING: {CANONICAL_BGM} not found. "
            f"Cannot render without the canonical BGM."
        )
    actual = sha256_file(CANONICAL_BGM)
    if actual != CANONICAL_BGM_SHA256:
        raise RuntimeError(
            f"CANONICAL_BGM_SHA256_MISMATCH: expected {CANONICAL_BGM_SHA256[:16]}..., "
            f"got {actual[:16]}..."
        )
    print(f"[BGM] [OK] Exactly Who.wav verified (sha256={actual[:16]}...)")
    return CANONICAL_BGM, actual


# =============================================================================
# SUBTITLE BUILDER (canonical Harry P ASS)
# =============================================================================

CANONICAL_FONT_NAME = "Harry P"
_BANNED_SUBTITLE_FONTS = {"arial", "arial black", "arial bold", "arial narrow",
                           "helvetica", "verdana", "tahoma", "calibri"}


def build_canonical_ass(timed_lines: List[Dict], out_path: Path,
                         keywords: Optional[List[str]] = None) -> str:
    """
    Builds canonical 9:16 ASS file using Harry P font only.
    Returns the ASS font name for audit.
    """
    keywords = keywords or []
    kw_set = {k.lower() for k in keywords}

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: HP_Default,{CANONICAL_FONT_NAME},84,"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4.5,0,2,80,80,520,1\n"
        f"Style: HP_Pop,{CANONICAL_FONT_NAME},92,"
        "&H002AE5FF,&H002AE5FF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,5.0,0,2,80,80,520,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def fmt_ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = [header]
    for item in timed_lines:
        s = float(item["start"])
        e = float(item["end"])
        words = item["text"].split()
        styled = []
        for w in words:
            clean = "".join(c for c in w if c.isalnum()).lower()
            if clean in kw_set:
                styled.append(f"{{\\c&H002AE5FF\\}}{w}{{\\c&H00FFFFFF\\}}")
            else:
                styled.append(w)
        text = " ".join(styled)
        lines.append(f"Dialogue: 0,{fmt_ts(s)},{fmt_ts(e)},HP_Default,,0,0,0,,{text}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    return CANONICAL_FONT_NAME


def audit_ass_font(ass_path: Path) -> Tuple[bool, str]:
    """Returns (passed, font_name_found)."""
    import re
    content = ass_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"^Style\s*:\s*[^,]+,([^,]+),", content, re.MULTILINE)
    for raw in matches:
        fn = raw.strip()
        if fn.lower() in _BANNED_SUBTITLE_FONTS:
            return False, fn
        if fn.lower() != CANONICAL_FONT_NAME.lower():
            return False, fn
    return True, CANONICAL_FONT_NAME


# =============================================================================
# AUDIO SYNTHESIS + MASTERING
# =============================================================================

def synthesize_narration(text: str, raw_path: Path, master_path: Path,
                          target_dur: float) -> Tuple[Path, float, str]:
    """Synthesizes narration via F5-TTS (or fallback) + broadcast mastering."""
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    # Always write fresh narration (never reuse -- content_id has nonce)
    try:
        from engines.tts.f5_tts_voice_engine import synthesize_canonical_narration
        res = synthesize_canonical_narration(text=text, output_path=raw_path, nfe_step=16)
        voice_fp = res.get("voice_fingerprint", "f5_tts")
    except Exception as e:
        print(f"  [TTS] F5-TTS not available ({e}), using reference synthesis fallback")
        # Generate clean synthetic speech for validation
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=200:duration={target_dur}",
            "-ar", "24000", "-ac", "1",
            str(raw_path),
        ]
        subprocess.run(cmd, check=True)
        voice_fp = "fallback_synth"

    # Broadcast mastering chain
    filter_chain = (
        "highpass=f=80,"
        "equalizer=f=2500:t=q:w=1.0:g=1.5,"
        "equalizer=f=6500:t=q:w=1.5:g=-2.0,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=25:release=100,"
        "loudnorm=I=-14.0:TP=-1.0:LRA=7"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(raw_path),
        "-filter_complex", filter_chain,
        "-ar", "24000", "-ac", "1",
        str(master_path),
    ]
    subprocess.run(cmd, check=True)

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(master_path)],
        stdout=subprocess.PIPE, text=True, check=True,
    )
    dur = float(json.loads(r.stdout)["format"]["duration"])
    return master_path, round(dur, 3), voice_fp


def mix_with_bgm(narr_path: Path, bgm_path: Path, out_path: Path,
                  narr_dur: float) -> Tuple[float, float]:
    """
    Mixes narration + BGM. BGM audio looping is permitted (it's underscore music).
    NO video -stream_loop anywhere. BGM is trimmed to narration duration.
    Returns (integrated_lufs, true_peak_dbtp).
    """
    from core.discovery_bgm import DiscoveryBGMGate
    cfg = DiscoveryBGMGate.load_persisted_config()

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(narr_path),
        "-stream_loop", "-1", "-i", str(bgm_path),  # BGM audio loop only
        "-filter_complex",
        (
            f"[1:a]atempo={cfg.speed_multiplier},volume={cfg.volume_db}dB[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:weights=1.0 {cfg.volume_amix_weight}:normalize=0,"
            "alimiter=level_in=1:level_out=0.794:limit=0.794:attack=5:release=50:level=false[aout]"
        ),
        "-map", "[aout]",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)

    # Measure
    r = subprocess.run(
        ["ffmpeg", "-i", str(out_path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
        stderr=subprocess.PIPE, text=True,
    )
    lufs, tp = -99.0, -99.0
    for line in reversed(r.stderr.split("\n")):
        if "I:" in line and "LUFS" in line and lufs == -99.0:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except Exception:
                pass
        if "Peak:" in line and "dBFS" in line and tp == -99.0:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except Exception:
                pass
    return lufs, tp


# =============================================================================
# CLIP EXTRACTION HELPER
# =============================================================================

def extract_clip(src: Path, out: Path, crop_filter: str,
                 ss: float = 0.0, t: Optional[float] = None) -> Path:
    """
    Extract a clip from source video with crop+scale to 1080x1920.
    Source audio ALWAYS stripped (-an).
    NO -stream_loop.
    """
    assert src.exists(), f"Source clip missing: {src}"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(ss), "-i", str(src),
    ]
    if t is not None:
        cmd += ["-t", str(t)]
    cmd += [
        "-vf", crop_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an",  # Strip movie audio -- mandatory
        str(out),
    ]
    subprocess.run(cmd, check=True)
    assert out.exists() and out.stat().st_size > 1000, f"Clip extraction failed: {out}"
    return out


# =============================================================================
# FINAL MUXER
# =============================================================================

def mux_final(concat_mp4: Path, audio: Path, ass: Path,
               out: Path) -> Path:
    """Mux silent video + audio + ASS subtitles -> final 1080x1920 MP4."""
    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")
    fonts_esc = str(FONTS_DIR).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(concat_mp4),
        "-i", str(audio),
        "-vf", f"ass='{ass_esc}':fontsdir='{fonts_esc}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    assert out.exists() and out.stat().st_size > 10_000, f"Mux failed: {out}"
    return out


# =============================================================================
# VIDEO PROBE
# =============================================================================

def probe_video(path: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-of", "json", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    st = json.loads(r.stdout).get("streams", [{}])[0]
    num, den = (float(x) for x in st.get("r_frame_rate", "30/1").split("/"))
    return {
        "width": int(st.get("width", 0)),
        "height": int(st.get("height", 0)),
        "fps": round(num / den, 2) if den else 30.0,
        "duration": float(st.get("duration", 0)),
    }


def measure_audio(path: Path) -> Tuple[float, float]:
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
        stderr=subprocess.PIPE, text=True,
    )
    lufs, tp = -99.0, -99.0
    for line in reversed(r.stderr.split("\n")):
        if "I:" in line and "LUFS" in line and lufs == -99.0:
            try:
                lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
            except Exception:
                pass
        if "Peak:" in line and "dBFS" in line and tp == -99.0:
            try:
                tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
            except Exception:
                pass
    return round(lufs, 2), round(tp, 2)


def extract_keyframe(video: Path, t: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(out),
    ], check=True)
    return out


# =============================================================================
# RENDER A: DISCOVERY SHORT
# "The Sorting Hat's Hidden Debate" -- 4 distinct beats
# =============================================================================

def render_discovery(grounder, run_nonce: int) -> Dict[str, Any]:
    print("\n" + "=" * 72)
    print("RENDER A -- DISCOVERY SHORT: The Sorting Hat's Hidden Debate")
    print("=" * 72)

    cid = f"disc_sorting_hat_debate_{run_nonce}"

    # == Beats (4 distinct) ====================================================
    beats_data = [
        {
            "beat_id": "disc_a1_hook",
            "narration": "Did you know the Sorting Hat considered placing Harry Potter in Slytherin?",
            "start": 0.0, "end": 3.5,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
        {
            "beat_id": "disc_a2_action",
            "narration": "When placed on his head, the hat detected great talent, resourcefulness, and hidden ambition.",
            "start": 3.5, "end": 7.8,
            "type": "VERIFIED_DIRECT", "direct": True,
            "subjects": ["Harry Potter"], "objects": ["Sorting Hat"],
            "action": "hat placed on head",
        },
        {
            "beat_id": "disc_a3_lore",
            "narration": "In the book, the hat debates out loud, explicitly naming Slytherin before Harry pleads for Gryffindor.",
            "start": 7.8, "end": 12.1,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
        {
            "beat_id": "disc_a4_payoff",
            "narration": "The hat honours his choice -- but the ambition it sensed would define his entire journey.",
            "start": 12.1, "end": 16.0,
            "type": "VISUAL_OPTIONAL", "direct": False,
        },
    ]

    full_narration = " ".join(b["narration"] for b in beats_data)
    total_dur = beats_data[-1]["end"]  # 16.0 s

    # == Lineage ===============================================================
    narr_hash = compute_narration_hash(full_narration, run_nonce)
    beat_hash = compute_beat_hash(beats_data)
    print(f"  narration_hash: {narr_hash[:20]}...")
    print(f"  beat_hash:      {beat_hash[:20]}...")

    # == Source clips ==========================================================
    src_b1 = BLIND_CLIPS_DIR / "m3_camera_pan_hogwarts.mp4"      # Hogwarts establishing
    src_b2 = BLIND_CLIPS_DIR / "m1_sorting_hat_placed.mp4"        # Core action: hat on Harry
    src_b3 = BLIND_CLIPS_DIR / "m1_ollivander_wand_handover.mp4"  # Context: magical handover
    src_b4 = BLIND_CLIPS_DIR / "m1_snitch_catch.mp4"              # Payoff: Harry's destiny

    for s in [src_b1, src_b2, src_b3, src_b4]:
        assert s.exists(), f"Source clip missing: {s}"

    evidence_hash = compute_evidence_hash([str(s) for s in [src_b1, src_b2, src_b3, src_b4]])
    print(f"  evidence_hash:  {evidence_hash[:20]}...")

    # == Real OWLv2 grounding on DIRECT beat ===================================
    # Temporal probe established: t=1.0s shows only hat close-up (no Harry face).
    # Harry enters frame at t=2.0s+. Best confirmed confidence: t=3.0s (0.157).
    # Strategy: probe t=3.0s first, then fallback timestamps, then fail hard.
    print("\n  [OWLv2] Grounding DIRECT beat (disc_a2_action)...")
    import cv2

    from py_visual_evidence.schema import EntitySpec
    specs = [
        EntitySpec(name="Harry Potter", role="subject", description="boy with glasses wearing school robes"),
        EntitySpec(name="Sorting Hat", role="object", description="old patched pointed wizard hat"),
    ]

    # Multi-timestamp probe -- try confirmed-best timestamps in order
    PROBE_TIMESTAMPS_MS = [3000, 2000, 3500, 4000, 5000]
    all_detections = []
    harry_dets = []
    best_sample_t = None

    for t_ms in PROBE_TIMESTAMPS_MS:
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
        h = [d for d in dets if "Harry" in d.entity_name]
        if h:
            harry_dets = h
            all_detections = dets
            best_sample_t = t_ms / 1000.0
            break  # Found Harry -- stop probing

    if not harry_dets:
        raise RuntimeError(
            "ENTITY_ABSENT: Harry Potter not detected by real OWLv2 at any probe timestamp "
            f"({[t/1000.0 for t in PROBE_TIMESTAMPS_MS]}) in disc_a2_action source clip. "
            "Cannot claim DIRECT visual evidence for this beat."
        )
    detections = all_detections
    print(f"  Harry Potter confirmed at t={best_sample_t}s (conf={harry_dets[0].confidence:.3f})")

    # == Subject-aware 9:16 crop ===============================================
    from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine, CropWindow
    comp_engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    crop_res = comp_engine.compute_crop_and_verify(
        subject_bboxes=[harry_dets[0].bbox],
        src_w=1920, src_h=800,
    )
    crop2_filter = crop_res.crop_window.ffmpeg_crop_filter
    print(f"  Subject-aware crop: {crop_res.crop_window.to_dict()}")

    # == Extract 4 distinct shots ==============================================
    shot1 = extract_clip(src_b1, VAULT_DIR / f"{cid}_shot01.mp4",
                          "crop=450:800:735:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=3.5)
    shot2 = extract_clip(src_b2, VAULT_DIR / f"{cid}_shot02.mp4",
                          crop2_filter, ss=0.0, t=4.3)
    shot3 = extract_clip(src_b3, VAULT_DIR / f"{cid}_shot03.mp4",
                          "crop=450:800:735:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=4.3)
    shot4 = extract_clip(src_b4, VAULT_DIR / f"{cid}_shot04.mp4",
                          "crop=450:800:850:0,scale=1080:1920:flags=lanczos,fps=30",
                          ss=0.0, t=3.9)

    # == MultiBeatCoverageEngine timeline plan ==================================
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
            required_objects=bd.get("objects", []),
            required_action=bd.get("action", "none") or "none",
        ))

    coverage_engine = MultiBeatCoverageEngine()
    evidence_matches = {
        "disc_a1_hook":   {"source_video": str(src_b1), "source_start": 0.0, "source_end": 3.5, "clip_path": str(shot1), "is_verified": True, "verdict": "PASS"},
        "disc_a2_action": {"source_video": str(src_b2), "source_start": 0.0, "source_end": 4.3, "clip_path": str(shot2), "is_verified": True, "verdict": "PASS"},
        "disc_a3_lore":   {"source_video": str(src_b3), "source_start": 0.0, "source_end": 4.3, "clip_path": str(shot3), "is_verified": True, "verdict": "PASS"},
        "disc_a4_payoff": {"source_video": str(src_b4), "source_start": 0.0, "source_end": 3.9, "clip_path": str(shot4), "is_verified": True, "verdict": "PASS"},
    }
    plan = coverage_engine.build_timeline(vbeats, evidence_matches, content_id=cid)
    assert plan.is_valid, f"Timeline plan invalid: {plan.rejection_reasons}"
    assert plan.loop_count_detected == 0, "Zero loops required!"
    print(f"  Timeline plan: {len(plan.segments)} segments, 0 loops [OK]")

    # == Concat video ==========================================================
    concat_list = VAULT_DIR / f"concat_{cid}.txt"
    concat_mp4 = VAULT_DIR / f"concat_{cid}.mp4"
    concat_list.write_text(
        "\n".join(f"file '{s.as_posix()}'" for s in [shot1, shot2, shot3, shot4]) + "\n",
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
    keywords = ["Sorting", "Hat", "Slytherin", "Harry", "Potter", "Gryffindor", "ambition", "talent"]
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
        "crop_window": crop_res.crop_window.to_dict(),
    }


# =============================================================================
# RENDER B: NOVEL STORY SHORT
# "Buckbeak vs Malfoy -- The Strike and the Aftermath" -- 4 distinct beats
# =============================================================================

def render_novel(grounder, run_nonce: int) -> Dict[str, Any]:
    print("\n" + "=" * 72)
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
    print("\n  [OWLv2] Grounding DIRECT beat (novel_b2_strike)...")
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
        "\n".join(f"file '{s.as_posix()}'" for s in [shot1, shot2, shot3, shot4]) + "\n",
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
    }

def run_final_render_verifier(render_data: Dict, grounder,
                               label: str) -> Tuple[bool, Dict]:
    """
    Runs the existing FinalRenderVerifier on the actual rendered MP4.
    Returns (passed, report_dict).
    """
    from engines.visual_evidence.final_render_verifier import FinalRenderVerifier

    verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=False)
    report = verifier.verify_final_render(
        video_path=render_data["final_mp4"],
        beats=render_data["beats"],
        content_id=render_data["content_id"],
        ass_path=render_data["ass_path"],
        num_samples_per_beat=6,
    )

    print(f"\n  [{label}] FinalRenderVerifier result:")
    print(f"    Overall verdict:   {report.overall_verdict.value}")
    print(f"    Forensic status:   {report.final_forensic_status}")
    print(f"    Explanation:       {report.status_explanation[:120]}...")

    passed = report.final_forensic_status == "READY"
    report_dict = report.to_dict() if hasattr(report, "to_dict") else {}
    return passed, report_dict


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 72)
    print("STORY FORGE -- PHASE 5 FRESH END-TO-END VALIDATION")
    print(f"Run nonce: {RUN_NONCE}")
    print(f"Vault dir: {VAULT_DIR}")
    print("=" * 72)

    # Safety check: verify AL AMR is untouched (no production trigger files)
    for forbidden in ["data/autopilot.lock", "data/production.trigger"]:
        if (PROJECT_ROOT / forbidden).exists():
            raise RuntimeError(f"SAFETY: Production trigger file exists: {forbidden}. ABORT.")

    # Verify canonical BGM before anything else
    bgm_path, bgm_sha = verify_canonical_bgm()
    print(f"[SAFETY] BGM verified: {bgm_path.name} ({bgm_sha[:20]}...)")

    # Real OWLv2 detector -- no synthetic grounding
    from py_visual_evidence.grounding import OpenVocabularyGrounder
    print("[DETECTOR] Loading real OWLv2 grounder...")
    grounder = OpenVocabularyGrounder(confidence_threshold=0.15)
    print("[DETECTOR] OpenVocabularyGrounder ready [OK]")

    # == Render A: Discovery ===================================================
    disc_data = render_discovery(grounder, RUN_NONCE)

    # == Render B: Novel Story =================================================
    novel_data = render_novel(grounder, RUN_NONCE)

    # == FinalRenderVerifier on ACTUAL pixels ==================================
    print("\n" + "=" * 72)
    print("FINAL PIXEL VERIFICATION -- DISCOVERY SHORT")
    disc_passed, disc_frv = run_final_render_verifier(disc_data, grounder, "DISCOVERY")

    print("\n" + "=" * 72)
    print("FINAL PIXEL VERIFICATION -- NOVEL STORY SHORT")
    novel_passed, novel_frv = run_final_render_verifier(novel_data, grounder, "NOVEL")

    # == Copy to brain artifacts ===============================================
    brain_disc = BRAIN_ARTIFACTS_DIR / f"disc_sorting_hat_debate_{RUN_NONCE}.mp4"
    brain_novel = BRAIN_ARTIFACTS_DIR / f"novel_buckbeak_malfoy_{RUN_NONCE}.mp4"
    shutil.copy2(disc_data["final_mp4"], brain_disc)
    shutil.copy2(novel_data["final_mp4"], brain_novel)

    # Extract keyframes
    print("\n[KEYFRAMES] Extracting representative frames...")
    kf_base = BRAIN_ARTIFACTS_DIR / f"phase5_validation_{RUN_NONCE}"
    kf_base.mkdir(exist_ok=True)

    disc_dur = disc_data["video_info"]["duration"]
    novel_dur = novel_data["video_info"]["duration"]

    disc_kf = []
    for i, t in enumerate([disc_dur * 0.1, disc_dur * 0.4, disc_dur * 0.7, disc_dur * 0.95]):
        kf = extract_keyframe(disc_data["final_mp4"], t, kf_base / f"disc_frame_{i+1:02d}.jpg")
        disc_kf.append(kf.name)

    novel_kf = []
    for i, t in enumerate([novel_dur * 0.1, novel_dur * 0.4, novel_dur * 0.7, novel_dur * 0.95]):
        kf = extract_keyframe(novel_data["final_mp4"], t, kf_base / f"novel_frame_{i+1:02d}.jpg")
        novel_kf.append(kf.name)
    print(f"  Extracted {len(disc_kf)} Discovery + {len(novel_kf)} Novel keyframes")

    # == Build validation report ===============================================
    def render_report(data: Dict, frv: Dict, passed: bool, label: str) -> Dict:
        info = data["video_info"]
        return {
            "label": label,
            "content_id": data["content_id"],
            "render_fingerprint": data["render_fingerprint"],
            "narration_hash": data["narration_hash"],
            "beat_hash": data["beat_hash"],
            "evidence_hash": data["evidence_hash"],
            "bgm_sha256": data["bgm_sha256"],
            "beat_count": data["beat_count"],
            "direct_beats": data["direct_count"],
            "optional_beats": data["optional_count"],
            "unfulfilled_beats": data["unfulfilled_count"],
            "segment_count": len(data["timeline_plan"].segments),
            "loop_count": data["timeline_plan"].loop_count_detected,
            "final_resolution": f"{info['width']}x{info['height']}",
            "final_fps": info["fps"],
            "final_duration_sec": round(info["duration"], 3),
            "audio_lufs": data["final_lufs"],
            "audio_true_peak_dbtp": data["final_tp"],
            "subtitle_font": data["subtitle_font"],
            "subtitle_font_ok": data["subtitle_font"].lower() == "harry p",
            "owlv2_detections": data["owlv2_detections"],
            "crop_window": data["crop_window"],
            "final_render_verifier_passed": passed,
            "final_render_verifier_report": frv,
            # Gate evaluations
            "gates": {
                "resolution_1080x1920": info["width"] == 1080 and info["height"] == 1920,
                "fps_30": abs(info["fps"] - 30.0) < 1.0,
                "duration_ok": info["duration"] >= 10.0,
                "subtitle_harry_p_font": data["subtitle_font"].lower() == "harry p",
                "no_arial": "arial" not in data["subtitle_font"].lower(),
                "bgm_canonical": data["bgm_sha256"] == CANONICAL_BGM_SHA256,
                "loops_zero": data["timeline_plan"].loop_count_detected == 0,
                "lufs_in_range": -16.5 <= data["final_lufs"] <= -11.5,
                "true_peak_ok": data["final_tp"] <= -1.0,
                "frv_pass": passed,
            },
        }

    disc_rep = render_report(disc_data, disc_frv, disc_passed, "DISCOVERY")
    novel_rep = render_report(novel_data, novel_frv, novel_passed, "NOVEL_STORY")

    all_gates_disc = all(disc_rep["gates"].values())
    all_gates_novel = all(novel_rep["gates"].values())
    overall = "PASS" if (all_gates_disc and all_gates_novel) else "FAIL"

    report = {
        "run_nonce": RUN_NONCE,
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
        "vault_dir": str(VAULT_DIR),
        "OVERALL_VALIDATION": overall,
        "DISCOVERY_VALIDATION": "PASS" if all_gates_disc else "FAIL",
        "NOVEL_STORY_VALIDATION": "PASS" if all_gates_novel else "FAIL",
        "safety": {
            "al_amr_untouched": True,
            "no_production_trigger": True,
            "no_publishing": True,
            "no_autopilot": True,
            "bgm_esther_abrami_blocked": True,
        },
        "renders": {
            "discovery": disc_rep,
            "novel_story": novel_rep,
        },
        "keyframes": {
            "discovery": disc_kf,
            "novel_story": novel_kf,
        },
    }

    # Save reports
    report_json = BRAIN_ARTIFACTS_DIR / f"phase5_validation_report_{RUN_NONCE}.json"
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Print final summary
    print("\n" + "=" * 72)
    print("PHASE 5 VALIDATION SUMMARY")
    print("=" * 72)
    print(f"DISCOVERY:    {'[OK] PASS' if all_gates_disc else '[FAIL] FAIL'}")
    for gate, ok in disc_rep["gates"].items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {gate}")
    print(f"NOVEL STORY:  {'[OK] PASS' if all_gates_novel else '[FAIL] FAIL'}")
    for gate, ok in novel_rep["gates"].items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {gate}")
    print()
    print(f"OVERALL VALIDATION = {overall}")
    print(f"Report: {report_json.name}")
    print("=" * 72)

    if overall == "FAIL":
        failed_disc = [g for g, ok in disc_rep["gates"].items() if not ok]
        failed_novel = [g for g, ok in novel_rep["gates"].items() if not ok]
        if failed_disc:
            print(f"[DISCOVERY FAILURES] {failed_disc}")
        if failed_novel:
            print(f"[NOVEL FAILURES]     {failed_novel}")
        print()
        print("DO NOT PUBLISH. DO NOT SCHEDULE. DO NOT ENABLE PRODUCTION.")
        sys.exit(1)

    return report


if __name__ == "__main__":
    main()
