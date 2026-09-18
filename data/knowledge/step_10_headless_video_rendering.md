# Step 10: Headless Video Rendering & Audio-Visual Assembly Architecture

## 1. System Overview
Step 10 translates the approved Harry Potter narration scripts (Step 8) and rapid-fire movie shot mappings (Step 9) into broadcast-ready vertical YouTube Shorts (1080x1920 @ 30 FPS).

The engine operates 100% headlessly, suitable for ephemeral execution in GitHub Actions or any server environment without GUI dependencies.

```
       Step 8 Narration Script + Visual Beats
                         ↓
       Edge-TTS Synthesis (en-US-AndrewNeural)
                         ↓
  Word Boundaries Extraction & ASS Subtitle Generation
           (9:16 Safe Zone + PART Marker)
                         ↓
   Step 9 Movie Shot Retrieval & Rapid Clip Extraction
    (8-12+ shots per short, 1.5s-3.0s, -an zero audio)
                         ↓
  Audio Master Mixing (Narration + Ducked BGM @ -14 LUFS)
                         ↓
     FFmpeg Headless Composition & Subtitle Burn-In
                         ↓
      Automated 20-Point Technical QA Verification
                         ↓
       Persist to `hp_renders` Database Table
                         ↓
     STOP AT HUMAN REVIEW GATE (0 Uploads/Publishing)
```

## 2. Invariants & Rules Enforced

1. **Absolute Isolation**:
   - AL AMR project directory (`C:\Users\jisha\OneDrive\Desktop\yt automation`) is never accessed, touched, or inspected.
   - Dedicated Harry Potter vault (`Harry_Potter_Shorts_Vault`) and database (`data/database/pipeline.db`) only.

2. **Movie Footage Exclusively**:
   - Zero AI-generated visuals (no Midjourney, Stable Diffusion, etc.).
   - Zero stock library media (no Pexels, Shutterstock).
   - Zero static book screenshots.
   - Strictly Harry Potter feature films (Movies 1–8).

3. **Zero Movie Audio**:
   - All extracted video clips have their movie audio streams completely stripped (`-an`).
   - The final audio track consists strictly of **Narration + BGM bed**.

4. **Locked Voice Profile**:
   - Voice ID: `en-US-AndrewNeural`
   - Pitch: `+24Hz`
   - Rate: `+14%`
   - Exact script verbatim delivery. Narrator **never** reads the part marker aloud.

5. **Visual Part Marker**:
   - Top-left corner visual marker (e.g. `PART 01`, `PART 02`, `PART 03`, `PART 04`).
   - Sized and placed safely inside the 9:16 vertical viewport (Margin 60px).
   - Present from 0:00 to video completion.

6. **Rapid-Fire Pacing**:
   - 8–12+ shots per Short.
   - Individual shot duration: 1.5s to 3.0s (target 2.0s – 2.5s).
   - Dynamic cuts maintain high viewer retention.

7. **Audio Loudness & Mastering**:
   - BGM ducked by -20 dB under spoken dialogue.
   - Soft fade-in (0.8s) and fade-out (1.5s).
   - EBU R128 integrated loudness target: **-14.0 LUFS** (acceptable broadcast range: -22 to -10 LUFS).

8. **20-Point Technical QA Verification**:
   - File size & container check.
   - Single video stream (H.264 / MP4).
   - Vertical dimensions (1080x1920).
   - Frame rate: 30 FPS.
   - Single stereo audio stream (AAC / 44.1 kHz).
   - Zero movie dialogue leakage.
   - Total duration within bounds (20.0s – 35.0s).
   - No continuous black screen detection (`blackdetect`).
   - EBU R128 loudness verification.

9. **Human Review Gate**:
   - `PUBLISHING_ENABLED = False`, `UPLOAD_ENABLED = False`.
   - Execution halts completely after Step 10. No Step 11, no scheduling.
