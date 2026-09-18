# STEP 9: MOVIE VISUAL RETRIEVAL & CLOUD-SAFE CLIP EXTRACTION

## 1. System Overview & Objective
Step 9 bridges narrative script planning (Step 8) and audio-visual rendering (Step 10). It takes the structured visual beats produced by `HPScriptEngine` in table `hp_scripts` and grounds them in genuine, canonical movie footage from **Harry Potter Movies 1–8**.

```
VISUAL BEAT (Step 8)
        ↓
QUERY BUILDER (Hints, Characters, Actions, Locations)
        ↓
SQLITE FTS5 SUBTITLE SEARCH
        ↓
TIMESTAMP CANDIDATE DISCOVERY
        ↓
CANDIDATE CONTEXT EXPANSION (Surrounding Subtitle Chunks)
        ↓
MULTI-FACTOR RERANKING (0-100 Score)
        ↓
CONFIDENCE GATE (>= 50.0 Threshold & Visual Source Policy)
        ↓
MOVIE SOURCE RESOLUTION (Local Cache / On-Demand Cloud Download)
        ↓
EXACT CLIP EXTRACTION (FFmpeg -an, 9:16 Vertical 1080x1920)
        ↓
POST-EXTRACTION FFPROBE VERIFICATION (0 Audio Streams Asserted)
        ↓
PERSISTENCE (hp_movie_clips Table)
        ↓
READY FOR STEP 10
```

---

## 2. Hard Invariants & Policies

### A. Non-Negotiable Project Isolation
- **Zero AL AMR Dependency**: The `yt automation` project is completely untouched, unopened, and unreferenced.
- All operations run inside `C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation` using the isolated database `pipeline.db` and dedicated credentials `credentials/hp_token.json`.

### B. Visual Source Policy: MOVIE FOOTAGE ONLY
- **Strictly Allowed**: Harry Potter Movies 1 through 8 only.
- **Strictly Prohibited**:
  - AI generated images (Midjourney, DALL-E, Imagen)
  - AI generated video (Sora, Runway, Pika, Kling, Luma)
  - Consistory / face swapping / character hallucination
  - Stock footage (Pexels, Pixabay, Shutterstock, Storyblocks)
  - Book screenshots / PDF page renders
  - External YouTube or fan video rips
- **Fallback Action**: If a beat cannot be matched to canonical movie subtitles with confidence $\ge 50.0$, the candidate is marked as `REJECTED` with reason `LOW_RETRIEVAL_CONFIDENCE` or `NO_CANDIDATE_FOUND`. The system NEVER falls back to generic images or external providers.

### C. Audio Muting Invariant
- **Invariant**: All extracted movie clips must have their audio stripped (`-an`).
- **Enforcement**:
  1. FFmpeg is invoked with explicit flag `-an`.
  2. Post-extraction validation runs `ffprobe -select_streams a -show_entries stream=codec_type` on the output file.
  3. If any audio stream is detected, the file is immediately unlinked (deleted) and a `RuntimeError` is raised.

### D. Cloud-Runner / Zero-PC Compatibility
- Designed for ephemeral `ubuntu-latest` GitHub Actions runners (~14 GB total disk).
- **Single-Movie On-Demand Download**: Never downloads all 8 movies simultaneously (~16 GB combined).
- **Pre-flight Disk Check**: Verifies free disk space using `shutil.disk_usage()` before any download.
- **Post-Extraction Cleanup**: Source movie files can be purged after extracting the required clips in resource-constrained environments.

---

## 3. Query Construction & Subtitle Retrieval

The `MovieRetrievalEngine.build_queries_for_beat()` method parses each visual beat and extracts:
1. **Retrieval Hints**: Pre-curated keywords (e.g. `['Neville', 'sword', 'courage', 'hero']`).
2. **Character Names**: Recognized tokens (e.g. `Dumbledore`, `McGonagall`, `Vernon`, `Neville`).
3. **Salient Action/Location Words**: Filtered nouns and descriptive terms.

Queries are executed against the SQLite virtual table `movie_subtitles_fts` using BM25 ranking. The engine searches the beat's `preferred_movie_number` first, and falls back to global movie search if fewer than 3 candidates are found.

---

## 4. Candidate Context Expansion

Individual subtitle lines are often short fragments. `expand_candidate_context()` looks up the preceding chunk (`seq - 1`) and succeeding chunk (`seq + 1`) within the same movie to assemble full conversational context:
$$\text{expanded\_context} = [\text{PREV: } \dots] + [\text{SCENE: } \dots] + [\text{NEXT: } \dots]$$

This enables the multi-factor scoring engine to detect character presence and narrative context even when the focal subtitle line itself only contains a brief exclamation.

---

## 5. Multi-Factor Reranking & Scoring (0–100 Scale)

Each candidate scene is evaluated against 6 deterministic criteria:

| Factor | Weight | Evaluation Logic |
| :--- | :---: | :--- |
| **Character Match** | 0 – 30 pts | Exact match with character name in text/context (30 pts) or token match (20 pts). |
| **Action / Keyword Match** | 0 – 25 pts | Overlap with action and retrieval hint keywords ($8.5 \times \text{count}$, capped at 25 pts). |
| **Location / Object Match** | 0 – 15 pts | Overlap with location and visual requirement nouns ($5.0 \times \text{count}$, capped at 15 pts). |
| **Lexical BM25 Rank** | 0 – 15 pts | FTS5 relevance score ($15.0 - 1.5 \times |\text{rank}|$, bounded $[0, 15]$). |
| **Preferred Movie Match** | 0 – 15 pts | 15 pts if candidate movie matches beat's `preferred_movie_number`, else 0 pts. |
| **Duration Suitability** | 0 – 10 pts | 10 pts for $3.0\text{s} \le \text{duration} \le 12.0\text{s}$; 6 pts for $2.0\text{s} - 16.0\text{s}$; 2 pts otherwise. |

**Total Score**: $\sum \text{factors}$, bounded $[0.0, 100.0]$.

### Confidence Gate
- $\text{Score} \ge 50.0 \implies \mathbf{ACCEPTED}$ (`HIGH_CONFIDENCE_MOVIE_MATCH`)
- $\text{Score} < 50.0 \implies \mathbf{REJECTED}$ (`LOW_RETRIEVAL_CONFIDENCE`)

---

## 6. Exact Clip Extraction Specifications

When extracting clips from a movie video file:
1. **Padded Timestamps**:
   - $\text{clip\_start} = \max(0.0, \text{source\_start} - 0.8\text{s})$
   - $\text{clip\_duration} = \text{clamp}(2.5\text{s}, 8.0\text{s}, \text{raw\_duration} + 1.6\text{s})$
2. **FFmpeg Command**:
   ```bash
   ffmpeg -y \
     -ss <clip_start> \
     -i <movie_video_file> \
     -t <clip_duration> \
     -an \
     -vf "crop=ih*9/16:ih,scale=1080:1920" \
     -c:v libx264 \
     -preset fast \
     -crf 20 \
     -pix_fmt yuv420p \
     <output_path.mp4>
   ```
3. **Verification**:
   ```bash
   ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 <output_path.mp4>
   ```
   Must return an empty string. If non-empty, file is deleted and exception raised.

---

## 7. Launch Batch Audit Trail (16 Beats Evaluated)

Across the 4 launch batch scripts from Step 8, all 16 visual beats were matched, scored, confidence-gated, and persisted to `hp_movie_clips`:

| Script ID | Beat ID | Movie | Subtitle Chunk | Timecode Range | Confidence | Match Status | Verification |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `hps_ns_b1c01_gc0001_0003` | `beat_1` | M1 | `hp_m1_sc_0017` | 00:05:05 – 00:05:15 | 50.9 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0001_0003` | `beat_2` | M1 | `hp_m1_sc_0465` | 01:52:27 – 01:52:37 | 70.1 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0001_0003` | `beat_3` | M1 | `hp_m1_sc_0135` | 00:31:09 – 00:31:20 | 77.5 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0001_0003` | `beat_4` | M1 | `hp_m1_sc_0063` | 00:15:27 – 00:15:36 | 88.1 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0004_0006` | `beat_1` | M1 | `hp_m1_sc_0018` | 00:05:17 – 00:05:28 | 68.4 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0004_0006` | `beat_2` | M1 | `hp_m1_sc_0256` | 00:59:53 – 01:00:04 | 62.1 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0004_0006` | `beat_3` | M1 | `hp_m1_sc_0294` | 01:07:32 – 01:07:42 | 52.4 / 100 | ACCEPTED | Pending M1 download |
| `hps_ns_b1c01_gc0004_0006` | `beat_4` | M1 | `hp_m1_sc_0072` | 00:17:15 – 00:17:26 | 82.2 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_peeves_poltergeist_b1` | `beat_1` | M1 | `hp_m1_sc_0579` | 02:19:43 – 02:19:55 | 78.2 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_peeves_poltergeist_b1` | `beat_2` | M1 | `hp_m1_sc_0205` | 00:47:44 – 00:47:55 | 70.0 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_peeves_poltergeist_b1` | `beat_3` | M1 | `hp_m1_sc_0181` | 00:42:27 – 00:42:39 | 92.3 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_peeves_poltergeist_b1` | `beat_4` | M1 | `hp_m1_sc_0178` | 00:41:48 – 00:41:55 | 76.5 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_neville_hufflepuff_sorting_b1` | `beat_1` | M1 | `hp_m1_sc_0583` | 02:20:31 – 02:20:42 | 100.0 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_neville_hufflepuff_sorting_b1` | `beat_2` | M1 | `hp_m1_sc_0183` | 00:42:49 – 00:43:01 | 89.6 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_neville_hufflepuff_sorting_b1` | `beat_3` | M1 | `hp_m1_sc_0581` | 02:20:10 – 02:20:15 | 84.4 / 100 | ACCEPTED | Pending M1 download |
| `hps_disc_neville_hufflepuff_sorting_b1` | `beat_4` | M8 | `hp_m8_sc_0375` | 01:41:35 – 01:41:43 | 77.2 / 100 | ACCEPTED | **Extracted & Verified** (3.50 MB, 0 Audio Streams) |

---

## 8. Verified Physical Movie Clip Artifact

- **File**: `data/clips/hps_disc_neville_hufflepuff_sorting_b1_beat_4.mp4`
- **Source Movie**: Movie 8 (*Harry Potter and the Deathly Hallows – Part 2*)
- **Scene**: Neville stepping forward in courtyard ruins facing Voldemort
- **Size**: 3,500,340 bytes (~3.50 MB)
- **SHA-256**: `f0f67fda2299d6e60b299e5330335e2363198083c27e8201b1784eb9aa6bb4d4`
- **Resolution**: 1080 × 1920 (9:16 vertical crop)
- **Streams**: Exactly 1 video stream (`h264`), 0 audio streams.
- **Audio Muting Invariant**: 100% verified via `ffprobe`.
