import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engines.tts.f5_tts_voice_engine import F5TTSVoiceEngine

ref_audio = "data/voice_cloning/f5_tts/reference/selected_reference_speaker_24k.wav"
ref_text = "To put that into perspective, even Hermione only got 10. After graduation, he began following Voldemort."

t0 = time.time()
engine = F5TTSVoiceEngine(device="cpu", nfe_step=16)
engine.load_model()
t1 = time.time()
print(f"Model loaded in {t1 - t0:.2f}s")

t2 = time.time()
res = engine.generate(
    text="Did you know why the Mandrake cry is fatal?",
    reference_audio=ref_audio,
    reference_text=ref_text,
    output_path="data/voice/test_f5_speed.wav",
    speed=1.06,
    seed=101
)
t3 = time.time()
print(f"Inference completed in {t3 - t2:.2f}s, generated audio duration: {res['duration_s']}s")
