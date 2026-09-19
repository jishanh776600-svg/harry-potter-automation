"""
f5_clone.py - F5-TTS voice cloning wrapper (v3 - correct API + correct cfg parsing)
"""
import sys, os, warnings
warnings.filterwarnings("ignore")

# ── Patch torchaudio.load BEFORE any f5_tts import ──────────────────────────
import soundfile as sf
import torch, torchaudio

def _sf_load(path, frame_offset=0, num_frames=-1, normalize=True,
             channels_first=True, format=None, backend=None):
    import soundfile as sf
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    tensor = torch.from_numpy(data.T)
    if frame_offset > 0: tensor = tensor[:, frame_offset:]
    if num_frames > 0:   tensor = tensor[:, :num_frames]
    return tensor, sr

def _sf_save(path, src, sample_rate, *args, **kwargs):
    import soundfile as sf, numpy as np
    data = src.numpy()
    if data.ndim == 2: data = data.T  # (channels, samples) -> (samples, channels)
    sf.write(str(path), data, sample_rate)

torchaudio.load = _sf_load
torchaudio.save = _sf_save
try:
    import torchaudio._torchcodec as _tc
    _tc.load_with_torchcodec = _sf_load
except Exception: pass
print("[patch] torchaudio.load/save -> soundfile OK")

# ── Imports ──────────────────────────────────────────────────────────────────
from f5_tts.infer.utils_infer import (
    load_vocoder, load_model, preprocess_ref_audio_text, infer_process
)
from f5_tts.model import DiT
from omegaconf import OmegaConf
from importlib.resources import files as pkg_files
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REF_CLIP = BASE_DIR / "scratch_ref1_clip.wav"
OUT_DIR  = BASE_DIR / "data" / "voice_audition" / "cloned_voice"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CKPT_PATH = (
    r"C:\Users\jisha\.cache\huggingface\hub"
    r"\models--SWivid--F5-TTS\snapshots"
    r"\84e5a410d9cead4de2f847e7c9369a6440bdfaca"
    r"\F5TTS_v1_Base\model_1250000.safetensors"
)

REF_TEXT = (
    "The Harry Potter movie mistakes that only muggles would actually notice. "
    "When Harry is making breakfast for the Dursleys, Vernon is busy urging Harry to pour him some coffee? "
    "Dudley is busy counting the presents he received, but are you paying attention?"
)
GEN_TEXT = (
    "At the city zoo, Harry stopped in front of a giant sleeping snake. "
    "Suddenly, the snake woke up and winked at him. "
    "Harry whispered to it, and the snake nodded back politely. "
    "His cousin Dudley pushed Harry aside to get closer. "
    "But the moment Dudley touched the tank, the glass vanished into thin air! "
    "Dudley tumbled straight into the cold water pool. "
    "The friendly snake slithered free, leaving Dudley trapped behind the glass."
)
GEN_WORDS = len(GEN_TEXT.split())

SPEEDS = [
    (1.00, "cloned_short5_normal.wav", "Normal"),
    (1.15, "cloned_short5_fast.wav",   "Fast 1.15x"),
    (1.25, "cloned_short5_vfast.wav",  "Very Fast 1.25x"),
]

print("=" * 68)
print("  F5-TTS VOICE CLONING  (F5TTS_v1_Base)")
print("=" * 68)

device = "cpu"

# Load full YAML, extract only model.arch + mel_spec for DiT
full_cfg_path = str(pkg_files("f5_tts").joinpath("configs/F5TTS_v1_Base.yaml"))
full_cfg      = OmegaConf.load(full_cfg_path)

# load_model internally does: DiT(**model_cfg, text_num_embeds=vocab_size, mel_dim=n_mel_channels)
# So model_cfg must be ONLY the arch dict (DiT constructor args)
# We pass the full cfg - load_model itself extracts what it needs via its own logic
# Based on source: it does model_cls(**model_cfg, ...) so model_cfg must be the arch dict
arch_cfg = OmegaConf.to_container(full_cfg.model.arch, resolve=True)
arch_cfg_oc = OmegaConf.create(arch_cfg)

n_mel  = full_cfg.model.mel_spec.n_mel_channels   # 100
target_sr = full_cfg.model.mel_spec.target_sample_rate  # 24000

print(f"  Arch: dim={arch_cfg['dim']}, depth={arch_cfg['depth']}, heads={arch_cfg['heads']}")
print(f"  Mel: {n_mel} channels, {target_sr}Hz")

print("  Loading vocoder...")
vocoder = load_vocoder(vocoder_name="vocos", is_local=False, local_path="", device=device)
print("  Vocoder OK")

print("  Loading model checkpoint...")
ema_model = load_model(
    DiT,
    arch_cfg_oc,
    CKPT_PATH,
    mel_spec_type="vocos",
    vocab_file="",
    ode_method="euler",
    use_ema=True,
    device=device,
)
print("  Model OK")
print()

print("  Preprocessing reference audio...")
ref_audio_proc, ref_text_proc = preprocess_ref_audio_text(str(REF_CLIP), REF_TEXT)
print(f"  Reference ready.")
print()

for speed, filename, label in SPEEDS:
    out_path = OUT_DIR / filename
    print(f"  Generating [{label}]  speed={speed}  ->  {filename}")
    try:
        audio_out, final_sr, _ = infer_process(
            ref_audio_proc,
            ref_text_proc,
            GEN_TEXT,
            ema_model,
            vocoder,
            mel_spec_type="vocos",
            speed=speed,
            nfe_step=32,
            cfg_strength=2.0,
            sway_sampling_coef=-1.0,
            device=device,
        )
        if audio_out.ndim == 1:
            audio_out = audio_out.unsqueeze(0)
        torchaudio.save(str(out_path), audio_out, final_sr)
        dur = audio_out.shape[-1] / final_sr
        wpm = round((GEN_WORDS / dur) * 60, 1)
        kb  = out_path.stat().st_size // 1024
        print(f"    OK  {dur:.1f}s | {wpm} WPM | {kb} KB")
    except Exception as e:
        import traceback
        print(f"    FAILED: {e}")
        traceback.print_exc()
    print()

print("=" * 68)
print("  DONE — Files:")
for _, fn, lbl in SPEEDS:
    p = OUT_DIR / fn
    if p.exists():
        print(f"    {fn}  ({lbl})  {p.stat().st_size//1024} KB")
print(f"  Folder: {OUT_DIR}")
print("  PRODUCTION VOICE UNCHANGED: en-US-AndrewNeural +24Hz +14%")
print("=" * 68)
