import json
import subprocess
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MP4_PATH = PROJECT_ROOT / "data" / "renders" / "validation" / "battle_of_hogwarts_assembly_v1.mp4"
REMOTION_PROPS_PATH = PROJECT_ROOT / "data" / "renders" / "remotion_props" / "battle_of_hogwarts_remotion_props.json"
ASS_PATH = PROJECT_ROOT / "data" / "renders" / "validation" / "battle_of_hogwarts_v1.ass"
MANIFEST_PATH = PROJECT_ROOT / "data" / "cache" / "beast_shots" / "battle_of_hogwarts_beast_v2_grounding_manifest.json"

def test_rendered_mp4_container_and_dimensions():
    assert MP4_PATH.exists(), f"Rendered MP4 not found at {MP4_PATH}"
    assert MP4_PATH.stat().st_size > 20_000_000, f"File size too small: {MP4_PATH.stat().st_size}"

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,codec_type,sample_rate,channels:format=duration",
        "-of", "json",
        str(MP4_PATH)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    data = json.loads(res.stdout)
    
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next(s for s in data["streams"] if s["codec_type"] == "audio")
    dur = float(data["format"]["duration"])

    assert v["width"] == 1080
    assert v["height"] == 1920
    assert v["codec_name"] == "h264"
    assert a["codec_name"] == "aac"
    assert int(a["sample_rate"]) == 44100
    assert int(a["channels"]) == 2
    assert 68.0 <= dur <= 78.5, f"Duration {dur} outside 68-78.5s"

def test_remotion_props_contract():
    assert REMOTION_PROPS_PATH.exists()
    with open(REMOTION_PROPS_PATH, "r", encoding="utf-8") as f:
        props = json.load(f)

    assert props["compositionId"] == "BattleOfHogwartsShort"
    assert props["width"] == 1080
    assert props["height"] == 1920
    assert props["fps"] == 30
    assert len(props["clips"]) == 21
    assert len(props["sfxCues"]) == 4

    # Verify all evidence classes are declared
    evidence_classes = {c["evidenceClass"] for c in props["clips"]}
    assert "DIRECT_EVIDENCE" in evidence_classes
    assert "CONTRAST_EVIDENCE" in evidence_classes
    assert "CONTEXTUAL_EVIDENCE" in evidence_classes
    assert "OBJECT_EVIDENCE" in evidence_classes

def test_ass_subtitles_validity():
    assert ASS_PATH.exists()
    content = ASS_PATH.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Dialogue:" in content
    # Discovery package must NOT have part marker dialogue events
    assert "PartMarker,," not in content

def test_beast_v2_manifest_integrity():
    assert MANIFEST_PATH.exists()
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    assert m["topic_id"] == "mf_battle_of_hogwarts_omitted_truths_v2"
    assert m["summary"]["total_facts"] == 6
    assert m["summary"]["rejected_intervals"] == 0
    assert m["summary"]["accepted_intervals"] >= 20

def test_audio_loudness_and_true_peak():
    measure_cmd = [
        "ffmpeg", "-i", str(MP4_PATH),
        "-filter:a", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    res = subprocess.run(measure_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import re
    m_lufs = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", res.stderr)
    m_tp = re.search(r"True peak:\s+Peak:\s+([-\d.]+)\s+dBFS", res.stderr)
    assert m_lufs is not None
    assert m_tp is not None
    lufs = float(m_lufs.group(1))
    tp = float(m_tp.group(1))

    assert -20.0 <= lufs <= -12.0, f"LUFS {lufs} out of broadcast bounds"
    assert tp <= -1.0, f"True peak {tp} exceeds ceiling -1.0 dBTP"
