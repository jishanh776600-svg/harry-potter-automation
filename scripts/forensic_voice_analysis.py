import sys, os, warnings
warnings.filterwarnings('ignore')

import numpy as np
import scipy.io.wavfile as wavfile
import parselmouth
from parselmouth.praat import call
import librosa

WAV_PATH = r'C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation\scratch_ref1_mono.wav'

print('=' * 68)
print('  FORENSIC VOICE ANALYSIS - scratch_ref1.webm')
print('=' * 68)

y, sr = librosa.load(WAV_PATH, sr=None, mono=True)
duration = librosa.get_duration(y=y, sr=sr)
print(f'  Duration   : {duration:.2f}s')
print(f'  Sample rate: {sr} Hz')
print()

# PITCH
snd = parselmouth.Sound(WAV_PATH)
pitch_obj = call(snd, 'To Pitch', 0.0, 50, 600)
pitch_values = pitch_obj.selected_array['frequency']
voiced = pitch_values[pitch_values > 0]

mean_pitch   = float(np.mean(voiced)) if len(voiced) > 0 else 0
median_pitch = float(np.median(voiced)) if len(voiced) > 0 else 0
min_pitch    = float(np.min(voiced)) if len(voiced) > 0 else 0
max_pitch    = float(np.max(voiced)) if len(voiced) > 0 else 0
std_pitch    = float(np.std(voiced)) if len(voiced) > 0 else 0
pitch_range  = max_pitch - min_pitch

print('-- PITCH (F0) -------------------------------------------------------')
print(f'  Mean F0    : {mean_pitch:.1f} Hz')
print(f'  Median F0  : {median_pitch:.1f} Hz')
print(f'  Min F0     : {min_pitch:.1f} Hz')
print(f'  Max F0     : {max_pitch:.1f} Hz')
print(f'  Std Dev F0 : {std_pitch:.1f} Hz')
print(f'  Pitch range: {pitch_range:.1f} Hz')
print()

if median_pitch < 130:   gender_guess = 'MALE (deep)'
elif median_pitch < 165: gender_guess = 'MALE (typical)'
elif median_pitch < 200: gender_guess = 'MALE (high tenor) or FEMALE (low alto)'
elif median_pitch < 255: gender_guess = 'FEMALE (typical)'
else:                    gender_guess = 'FEMALE (high)'
print(f'  Gender estimate: {gender_guess}')
print()

# SPEAKING RATE via Whisper
print('-- SPEAKING RATE ----------------------------------------------------')
try:
    from faster_whisper import WhisperModel
    model = WhisperModel('tiny', device='cpu', compute_type='int8')
    segs_gen, info = model.transcribe(WAV_PATH, beam_size=3, language='en')
    segments = list(segs_gen)
    full_text = ' '.join(s.text.strip() for s in segments)
    total_words = len(full_text.split())
    if segments:
        spoken_dur = segments[-1].end - segments[0].start
        wpm = (total_words / spoken_dur) * 60 if spoken_dur > 0 else 0
    else:
        spoken_dur = duration; wpm = 0
    print(f'  Words          : {total_words}')
    print(f'  Spoken duration: {spoken_dur:.2f}s')
    print(f'  Speaking rate  : {wpm:.1f} WPM')
    if wpm < 120:   rate_class = 'SLOW (audiobook)'
    elif wpm < 155: rate_class = 'MODERATE (conversational)'
    elif wpm < 185: rate_class = 'FAST (storytelling)'
    elif wpm < 210: rate_class = 'VERY FAST (boosted TTS)'
    else:           rate_class = 'EXTREMELY FAST (>210 WPM)'
    print(f'  Rate class     : {rate_class}')
    print()
    print('-- TRANSCRIPT -------------------------------------------------------')
    for s in segments:
        print(f'  [{s.start:6.2f}s-{s.end:5.2f}s] {s.text.strip()}')
    print()
except Exception as e:
    print(f'  [Whisper error: {e}]')
    wpm = 0; full_text = ''
    print()

# SILENCE ANALYSIS
print('-- PAUSE / SILENCE ANALYSIS -----------------------------------------')
frame_len = int(sr * 0.025)
hop_len   = int(sr * 0.010)
rms = librosa.feature.rms(y=y, frame_length=frame_len, hop_length=hop_len)[0]
silence_thr = 0.005
times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_len)
in_sil = False; p_start = 0; pauses = []
for i, r in enumerate(rms):
    if r < silence_thr and not in_sil:
        in_sil = True; p_start = times[i]
    elif r >= silence_thr and in_sil:
        in_sil = False
        pd = times[i] - p_start
        if pd > 0.08: pauses.append(pd)
if pauses:
    avg_p = np.mean(pauses)
    print(f'  Distinct pauses: {len(pauses)}')
    print(f'  Avg pause      : {avg_p*1000:.0f}ms')
    print(f'  Max pause      : {max(pauses)*1000:.0f}ms')
    print(f'  Short (<250ms) : {sum(1 for p in pauses if p<0.25)}')
    print(f'  Long (>=250ms) : {sum(1 for p in pauses if p>=0.25)}')
    if avg_p < 0.18:    pause_style = 'Very tight -> Azure/Edge Neural or ElevenLabs compressed'
    elif avg_p < 0.28:  pause_style = 'Natural tight -> ElevenLabs / OpenAI TTS / Azure Neural'
    else:               pause_style = 'Generous -> Google TTS / audiobook style'
    print(f'  Pause style    : {pause_style}')
else:
    avg_p = 0; print('  No significant pauses.')
print()

# SPECTRAL
print('-- SPECTRAL / TIMBRE -----------------------------------------------')
spec_c = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
mean_c = float(np.mean(spec_c))
zcr = librosa.feature.zero_crossing_rate(y)[0]
mean_zcr = float(np.mean(zcr))
mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
mfcc_m = np.mean(mfccs, axis=1)
print(f'  Spectral centroid: {mean_c:.1f} Hz')
print(f'  Zero crossing    : {mean_zcr:.4f}')
print(f'  MFCC-1..4        : {mfcc_m[0]:.1f}, {mfcc_m[1]:.1f}, {mfcc_m[2]:.1f}, {mfcc_m[3]:.1f}')
if mean_c < 1800:   brightness = 'Dark/warm'
elif mean_c < 2400: brightness = 'Neutral/balanced'
elif mean_c < 3200: brightness = 'Bright/clear (common modern TTS)'
else:               brightness = 'Very bright/thin'
print(f'  Brightness       : {brightness}')
print()

# PROSODY
print('-- PROSODY / EXPRESSIVENESS ----------------------------------------')
pv_pct = (std_pitch / mean_pitch * 100) if mean_pitch > 0 else 0
print(f'  Pitch variation: {pv_pct:.1f}% of mean')
if pv_pct < 10:   prosody = 'FLAT/MONOTONE (robotic early TTS)'
elif pv_pct < 20: prosody = 'MILD variation (standard TTS - Azure, Google)'
elif pv_pct < 30: prosody = 'MODERATE variation (good TTS - ElevenLabs, OpenAI)'
elif pv_pct < 40: prosody = 'HIGH variation (expressive TTS - ElevenLabs turbo)'
else:             prosody = 'VERY HIGH variation (human or very expressive AI)'
print(f'  Prosody class  : {prosody}')
print()

# FORMANT ANALYSIS
print('-- FORMANT ANALYSIS (accent) ----------------------------------------')
try:
    formant = call(snd, 'To Formant (burg)', 0.0, 5, 5500, 0.025, 50)
    f1_v, f2_v = [], []
    for t in np.arange(0.1, duration-0.1, 0.05):
        f1 = call(formant, 'Get value at time', 1, t, 'Hertz', 'Linear')
        f2 = call(formant, 'Get value at time', 2, t, 'Hertz', 'Linear')
        if f1 and not (isinstance(f1, float) and f1 != f1): f1_v.append(f1)
        if f2 and not (isinstance(f2, float) and f2 != f2): f2_v.append(f2)
    mean_f1 = float(np.mean(f1_v)) if f1_v else 0
    mean_f2 = float(np.mean(f2_v)) if f2_v else 0
    print(f'  Mean F1 (height)   : {mean_f1:.1f} Hz')
    print(f'  Mean F2 (front/back): {mean_f2:.1f} Hz')
    if mean_f2 > 1600:   accent_hint = 'Front vowels -> General American / Australian'
    elif mean_f2 > 1350: accent_hint = 'Mid F2 -> British RP / General American'
    else:                accent_hint = 'Back vowels -> non-native or Southern US'
    print(f'  Accent hint        : {accent_hint}')
except Exception as e:
    mean_f1 = mean_f2 = 0
    print(f'  [Formant error: {e}]')
print()

# SCORING
print('=' * 68)
print('  TTS PROVIDER SCORING')
print('=' * 68)
scores = {'ElevenLabs': 0, 'Azure/Edge Neural': 0, 'OpenAI TTS': 0, 'Google TTS': 0, 'Amazon Polly': 0}
if 100 <= median_pitch <= 140:
    scores['Azure/Edge Neural'] += 2; scores['ElevenLabs'] += 2
elif 140 <= median_pitch <= 180:
    scores['ElevenLabs'] += 2; scores['OpenAI TTS'] += 2; scores['Azure/Edge Neural'] += 1
if 155 <= wpm <= 200:
    scores['Azure/Edge Neural'] += 3; scores['ElevenLabs'] += 2
elif wpm > 200:
    scores['Azure/Edge Neural'] += 2; scores['ElevenLabs'] += 1
if pv_pct > 25:
    scores['ElevenLabs'] += 3; scores['OpenAI TTS'] += 2
elif pv_pct > 15:
    scores['Azure/Edge Neural'] += 2; scores['ElevenLabs'] += 1
else:
    scores['Google TTS'] += 2; scores['Amazon Polly'] += 2
if avg_p > 0:
    if avg_p < 0.18:    scores['Azure/Edge Neural'] += 3; scores['ElevenLabs'] += 2
    elif avg_p < 0.28:  scores['ElevenLabs'] += 2; scores['OpenAI TTS'] += 2
    else:               scores['Google TTS'] += 2
if 2000 <= mean_c <= 3000:
    scores['Azure/Edge Neural'] += 2; scores['ElevenLabs'] += 1
elif mean_c > 3000:
    scores['ElevenLabs'] += 2

print()
ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
for prov, sc in ranked:
    print(f'  {prov:<22} {chr(9608)*sc} ({sc})')
top = ranked[0][0]
print(f'\n  MOST LIKELY: {top}')
print()

# FINAL VERDICT
print('=' * 68)
print('  FINAL VERDICT')
print('=' * 68)
print()
print(f'  Gender           : {gender_guess}')
print(f'  Mean Pitch       : {mean_pitch:.1f} Hz')
print(f'  Speaking Rate    : {wpm:.1f} WPM')
print(f'  Prosody          : {prosody}')
print(f'  Spectral bright  : {brightness}')
print(f'  Provider         : {top}')
print()
if 'Azure' in top:
    print('  VOICE CANDIDATES (Azure/Edge Neural):')
    print('    * en-US-AndrewNeural  <- current voice (likely match)')
    print('    * en-US-GuyNeural')
    print('    * en-US-TonyNeural')
    print('    * en-US-DavisNeural')
    print()
    print('  REPRODUCTION: Legal via edge-tts (pip install edge-tts) FREE')
    print()
    print('  RECOMMENDED CONFIG:')
    print('    voice : en-US-AndrewNeural')
    print('    rate  : +14% to +20%')
    print('    pitch : +20Hz to +25Hz')
    print('    style : narration-professional or chat')
elif 'ElevenLabs' in top:
    print('  VOICE CANDIDATES (ElevenLabs):')
    print('    * Adam  (pNInz6obpgDQGcFmaJgB)  <- warm male storyteller')
    print('    * Drew  (29vD33N1CtxCmqQRPOHJ)  <- natural male')
    print('    * Josh  (TxGEqnHWrfWFTfGW9XjX)  <- energetic deep male')
    print()
    print('  REPRODUCTION: Legal via ElevenLabs API (paid)')
    print()
    print('  RECOMMENDED CONFIG:')
    print('    model_id       : eleven_turbo_v2_5')
    print('    stability      : 0.40')
    print('    similarity_boost: 0.80')
    print('    style          : 0.38')
    print('    speed          : 1.20')
print()
if mean_f2 > 1550:
    print('  Accent           : General American English')
elif mean_f2 > 1350:
    print('  Accent           : American English (possible mid-Atlantic or British RP)')
if 100 <= mean_pitch <= 130:
    print('  Age impression   : 30s-50s male (mature, authoritative)')
elif 130 <= mean_pitch <= 165:
    print('  Age impression   : 20s-40s male (neutral adult)')
print()
print('=' * 68)
print('  DONE')
print('=' * 68)
