# Obsidian Architecture Re-Learn

> **Scope:** Comprehensive architectural analysis and knowledge transfer from the Obsidian knowledge vault (`data/knowledge/`) into the Harry Potter automation project (`C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation`).  
> **Mandate:** Zero modifications to AL AMR (`C:\Users\jisha\OneDrive\Desktop\yt automation`), zero code modifications, zero publishing enabled. Pure knowledge acquisition and architectural synthesis.

---

## 1. Source Documents Studied

The following canonical Obsidian Markdown documents within `data/knowledge/` were read, cross-referenced, and analyzed:

### Tier 01 — Project Master
- `data/knowledge/00 - Project Overview.md`
- `data/knowledge/01 — PROJECT MASTER/Operating Principles & Invariants.md`
- `data/knowledge/01 — PROJECT MASTER/Project Overview.md`
- `data/knowledge/01 — PROJECT MASTER/Vision & Editorial Philosophy.md`
- `data/knowledge/01 — PROJECT MASTER/Roadmap & Observation Strategy.md`

### Tier 02 — Architecture
- `data/knowledge/01 - Architecture.md`
- `data/knowledge/02 — ARCHITECTURE/Cloud & Storage Topology.md`
- `data/knowledge/02 — ARCHITECTURE/Distributed Cloud Locking.md`
- `data/knowledge/02 — ARCHITECTURE/Multi-Tier Database Persistence.md`
- `data/knowledge/02 — ARCHITECTURE/Unified Production Controller.md`

### Tier 03 — Autonomous Operations
- `data/knowledge/03 — AUTONOMOUS OPERATIONS/Zero-PC Autonomy Specification.md`
- `data/knowledge/03 — AUTONOMOUS OPERATIONS/Buffer Replenishment Workflow.md`
- `data/knowledge/03 — AUTONOMOUS OPERATIONS/Autonomous Publication Workflow.md`
- `data/knowledge/03 — AUTONOMOUS OPERATIONS/Google Drive Vault Lifecycle.md`

### Tier 04 — Content Production
- `data/knowledge/02 - Production Pipeline.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Production Pipeline Specification.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Duplicate Protection & Fingerprinting.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Audio Mastering & BGM Standards.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Visual Evidence & Composition.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Script Generation & Craftsmanship.md`
- `data/knowledge/04 — CONTENT PRODUCTION/Narration & Bella Voice Specification.md`

### Tier 05 — Publishing
- `data/knowledge/04 - Reserve & Publishing System.md`
- `data/knowledge/05 — PUBLISHING/Forward Horizon Scheduling.md`
- `data/knowledge/05 — PUBLISHING/Publication Safety Gate.md`
- `data/knowledge/05 — PUBLISHING/YouTube Release & Metadata Protocol.md`

### Tier 06 — Intelligence & Decisions
- `data/knowledge/03 - AI Provider Strategy.md`
- `data/knowledge/05 - Analytics & Learning Engine.md`
- `data/knowledge/06 — INTELLIGENCE/Multi-Agent AI Council.md`
- `data/knowledge/06 — INTELLIGENCE/Closed-Loop Telemetry & Learning Engine.md`
- `data/knowledge/06 — INTELLIGENCE/Decommissioned Current-Affairs Architecture.md`
- `data/knowledge/06 — INTELLIGENCE/Historical Topic Discovery & Curated Seeds.md`
- `data/knowledge/10 - Decisions & Engineering Principles.md`

### Tier 07, 08 & 09 — Verification, Incidents & Forensics
- `data/knowledge/07 - Testing & Verification.md`
- `data/knowledge/08 — TESTING/Verification Suite & QA Gates.md`
- `data/knowledge/08 — TESTING/Targeted Test Suites & AST Compliance.md`
- `data/knowledge/08 - Failure Forensics & Fixes.md`
- `data/knowledge/09 — INCIDENTS & FIXES/Incident Register & Forensic Log.md`
- `data/knowledge/09 — INCIDENTS & FIXES/Incident 8 — Cloud Lock Deadlock & Seed Exhaustion.md`

### AL-AMR Historical Archive & Workflows
- `data/knowledge/AL-AMR/11 - Cloud Infrastructure.md`
- `data/knowledge/AL-AMR/12 - Google Drive Vault.md`
- `.github/workflows/produce_buffer.yml`
- `.github/workflows/autopilot.yml`
- `.github/workflows/harvest_analytics.yml`
- `.github/workflows/verify_database_sync.yml`

---

## 2. Core Architecture

The architecture documented in Obsidian operates on a **Strict Three-Tier Segregation Model**:

```
+---------------------------------------------------------------------------------------------------+
| THREE-TIER SYSTEM ARCHITECTURE                                                                    |
+---------------------------------------------------------------------------------------------------+
| [TIER 1: EPHEMERAL CLOUD COMPUTE]  GitHub Actions Runners (ubuntu-latest)                         |
|   - Zero persistent runner disk state; spins up on scheduled cron triggers or workflow_dispatch.  |
|   - Installs FFmpeg, DejaVu fonts, Python 3.11, and pip dependencies.                             |
|   - Synchronizes database from Drive, executes work, and commits updated state back to Drive.     |
|                                                                                                   |
| [TIER 2: DURABLE ASSET VAULT]  Google Drive Cloud Storage                                         |
|   - 00_SYSTEM/         : Canonical SQLite DB, auxiliary DBs, and distributed lock manifests.      |
|   - 01_READY/          : Verified reserve of QA-passed 1080x1920 MP4 Shorts (Target >= 6).        |
|   - 02_PROCESSING/     : In-flight Shorts currently scheduled or uploading to YouTube.            |
|   - 03_PUBLISHED/      : Permanent archive of live, reconciled YouTube Shorts.                    |
|   - 04_FAILED/         : Quarantined assets failing QA or safety checks (never return to READY).    |
|                                                                                                   |
| [TIER 3: KNOWLEDGE BRAIN]  Obsidian Knowledge Vault (data/knowledge)                              |
|   - Human-readable Markdown knowledge records with bi-directional wikilinks.                       |
|   - Maintains operational memory, decision logs, failure forensics, and system invariants.        |
+---------------------------------------------------------------------------------------------------+
```

### Key Architectural Invariants Documented:
1. **Single Canonical Controller:** All video production routes exclusively through `CloudProductionOrchestrator` (`intelligence/cloud_orchestrator.py` or equivalent controller) whether invoked via GitHub Actions, CLI, or daemon.
2. **Sequential Production:** Videos are rendered, verified, and vaulted **strictly one at a time**. Parallel rendering is prohibited to prevent memory exhaustion, race conditions, and uncontrolled API burn.
3. **Dynamic Deficit Replenishment:** Buffer replenishment computes `deficit = max(0, target_buffer - ready_count)`. If `01_READY` meets or exceeds target, the runner exits in under 45 seconds with zero API spend.

---

## 3. Cloud Execution Model

The Obsidian documentation explicitly formalizes the **Zero-PC Autonomy Specification** (`03 — AUTONOMOUS OPERATIONS/Zero-PC Autonomy Specification.md`):

| System Component | Execution Location | Local PC Dependency | Documented Verification |
|---|---|---|---|
| **Topic / Content Selection** | GitHub Actions Runner | **0%** (Headless Python) | `[LIVE VERIFIED]` |
| **Script Generation** | GitHub Actions Runner | **0%** (Cloud AI APIs via secrets) | `[LIVE VERIFIED]` |
| **TTS Narration** | GitHub Actions Runner | **0%** (Cloud runner CPU / edge service) | `[LIVE VERIFIED]` |
| **Visual Retrieval** | GitHub Actions Runner | **0%** (Cloud storage / APIs) | `[LIVE VERIFIED]` |
| **FFmpeg Composition** | GitHub Actions Runner | **0%** (Headless FFmpeg on Linux) | `[LIVE VERIFIED]` |
| **Automated QA Gates** | GitHub Actions Runner | **0%** (Waveform & stream inspection) | `[LIVE VERIFIED]` |
| **State Persistence & Locks** | Google Drive API | **0%** (Cloud durable `00_SYSTEM`) | `[LIVE VERIFIED]` |
| **YouTube Publishing** | GitHub Actions Runner | **0%** (YouTube Data API v3 via secrets) | `[LIVE VERIFIED]` |
| **Telemetry Harvesting** | GitHub Actions Runner | **0%** (YouTube Analytics API) | `[LIVE VERIFIED]` |

### The Role of Developer Hardware
- **Personal PC:** Purely a development terminal, code editor, and emergency administrative console.
- **Personal Browser:** Not required for any production or publishing step.
- **Mobile Device:** Optional administrative review (e.g., viewing GitHub Actions status or YouTube Studio); zero runtime dependency.
- **Personal Internet Connection:** If the developer's internet or power is disconnected for weeks or months, cloud execution proceeds uninterrupted on GitHub Actions and Google Cloud.

---

## 4. GitHub Actions Model

Execution is partitioned across specialized, decoupled workflows in `.github/workflows/`:

1. **`produce_buffer.yml` (The Producer):**
   - **Trigger:** Cron schedule `0 */2 * * *` (or `0 */3 * * *`) + `workflow_dispatch`.
   - **Responsibility:** Restores secrets, downloads canonical DB from Google Drive `00_SYSTEM`, checks `01_READY` reserve stock, calculates deficit, sequentially produces missing Shorts, deposits them to `01_READY`, runs DB WAL checkpoint, and uploads updated DB back to `00_SYSTEM`.
   - **Concurrency:** Single-concurrency group (`buffer-producer`), `cancel-in-progress: false`.

2. **`autopilot.yml` (The Publisher / Releaser):**
   - **Trigger:** Cron schedule aligned with global viewing slots (`0 6,10,14,18 * * *` or `0 6,11,15 * * *`) + `workflow_dispatch`.
   - **Responsibility:** Ultra-fast run (~30–45s). Downloads DB, checks rolling 48-hour forward horizon, claims ready Shorts from `01_READY`, uploads to YouTube as **scheduled private videos** with `publishAt` timestamps, moves Drive files to `02_PROCESSING`, checkpoints DB, and syncs back to Drive.
   - **Concurrency:** Single-concurrency group (`youtube-publisher`), `cancel-in-progress: false`.

3. **`harvest_analytics.yml` (The Telemetry Harvester):**
   - **Trigger:** Daily cron `0 3 * * *` (allowing overnight YouTube metrics to settle).
   - **Responsibility:** Polls YouTube Data and Analytics APIs for published Shorts with $\ge 24\text{h}$ maturity. Inserts immutable `PerformanceSnapshot` records into SQLite.

4. **`verify_database_sync.yml` (Integrity Verification):**
   - **Trigger:** `workflow_dispatch`.
   - **Responsibility:** Non-production verification testing round-trip download $\rightarrow$ integrity $\rightarrow$ upload $\rightarrow$ re-download SHA256 consistency.

---

## 5. Persistent State

Because GitHub Actions runners are ephemeral containers destroyed upon run completion, state cannot live on the runner's scratch disk.

### The Synchronization Lifecycle (`core/database_sync.py`):
1. **Pre-Execution Ingress:**
   - Runner authenticates to Google Drive via service account / OAuth token.
   - Queries `00_SYSTEM/` for `pipeline.db` (or `youtube_automation.db`).
   - Computes local SHA256 checksum and runs `PRAGMA integrity_check;`.
2. **Execution Mutations:**
   - Pipeline reads and writes to SQLite with WAL mode (`journal_mode = WAL`).
3. **Post-Execution Egress:**
   - Pipeline checkpoints WAL: `PRAGMA wal_checkpoint(TRUNCATE);`.
   - Uploads SQLite database back to `00_SYSTEM/` using Drive multipart upload.
   - Re-queries Drive file metadata to confirm byte size and SHA256 integrity match.

### Auxiliary State Files in `00_SYSTEM/`:
- `visual_memory.db` — Stores perceptual hashes (`dHash`) and usage timestamps to prevent visual scene repetition within 45 days.
- `short_fingerprints.db` — Stores 3-gram script shingles and semantic embeddings for duplicate rejection.
- `locks/` — Stores JSON lock manifests for distributed concurrency control.

---

## 6. Storage Model

The storage topology is segmented into:

```
[Google Drive Vault Root]
├── 00_SYSTEM/          # Persistent cloud state, SQLite databases, distributed locks
├── 01_READY/           # Verified reserve stock of QA-passed 1080x1920 MP4 Shorts
├── 02_PROCESSING/      # In-flight Shorts uploaded to YouTube as scheduled private videos
├── 03_PUBLISHED/       # Permanent archive of mature, public YouTube Shorts
└── 04_FAILED/          # Quarantined assets failing QA or rejected (never return to READY)
```

### The Physical `03_PUBLISHED` Barrier:
As documented in `03 — AUTONOMOUS OPERATIONS/Google Drive Vault Lifecycle.md`:
- Direct file moves into `03_PUBLISHED` are prohibited and blocked at the code level (`drive_engine.py` raises `InvariantViolationError` if `_from_gateway=False`).
- An asset can only transition to `03_PUBLISHED` through `core/lifecycle_gateway.py` **after** live YouTube API read-back confirms `privacyStatus == 'public'`.
- Scheduled private uploads remain in `02_PROCESSING`.

---

## 7. Authentication and Secrets

The cloud authentication model documented in Obsidian enforces:

1. **Zero Hardcoded Secrets:** No API keys, client secrets, or refresh tokens exist in git.
2. **GitHub Repository Secrets:** Injected into runner `.env` and JSON token files at runtime:
   - `TOKEN_JSON` — Google OAuth2 refresh & access token (Drive + YouTube scopes).
   - `CLIENT_SECRET_JSON` — Google Cloud Project OAuth2 client registration.
   - LLM Provider keys (`GEMINI_API_KEY`, etc.).
3. **Token Management & Quota Ceilings:**
   - YouTube video upload consumes 1,600 units per video.
   - 3–4 daily uploads consume 4,800–6,400 units, well within YouTube's default 10,000 unit/day free tier quota.

---

## 8. Scheduling and Publishing

Documented in `05 — PUBLISHING/Forward Horizon Scheduling.md`:

1. **Rolling 48-Hour Forward Horizon:**
   - The scheduler scans vacant slots for Day 0 (Today), Day 1 (Tomorrow), and Day 2 (Forward).
   - Evaluates configured daily release slots (e.g., 06:00, 10:00, 14:00, 18:00 UTC).
   - If today's slots are filled, the scheduler claims ready stock to fill tomorrow's vacant slots.
   - If production temporarily halts, the channel buffer prevents going dark for at least 48 hours.
2. **Zero Immediate Public Uploads:**
   - All videos are uploaded as **scheduled private videos** with exact `publishAt` ISO-8601 UTC timestamps.
   - YouTube's backend handles making the video public at the exact second of the scheduled slot.
3. **15-Point Publication Safety Gate (`upload_engine.py`):**
   - Validates resolution (1080x1920), duration bounds, audio levels (-14 LUFS voice / -30 LUFS BGM), zero black frames, non-duplicate story fingerprint, and daily slot ceiling before scheduling.

---

## 9. Failure Recovery and Idempotency

Documented extensively in `08 - Failure Forensics & Fixes.md` and `02 — ARCHITECTURE/Distributed Cloud Locking.md`:

1. **Distributed Concurrency & Deadlock Prevention (`CompositeLock`):**
   - **900s (15m) TTL:** Stale cloud locks automatically expire after 15 minutes.
   - **120s Background Heartbeat:** Active video production threads continuously refresh the lock timestamp.
   - **Dead-Runner Reclamation:** Queries GitHub Actions API (`actions/runs/{run_id}`) to check if the runner holding the lock is dead, cancelled, or completed. If so, reclaims lock immediately.
   - **Non-Crashing Contention Exit:** Lock contention exits cleanly with status `BLOCKED` (exit code 0), avoiding false-positive alerts.
2. **Idempotent Asset Quarantining (`04_FAILED`):**
   - Defective assets are moved to `04_FAILED` and never silently deleted.
   - Assets in `04_FAILED` are permanently excluded from reserve counts and scheduling.
3. **Run-Level Candidate Quarantine:**
   - Evaluated topics or candidates within a run are tracked in an in-memory set (`attempted_candidate_ids`) to prevent reselection storms if a candidate fails validation.
4. **No Side-Effect Status Mutation in Filtering Loops:**
   - Candidate filtering/deduplication checks must never mutate persistent database statuses (e.g., `status = COMPLETED`) as a side effect. Status transitions must be explicit and deliberate.
5. **Corpus Self-Matching Guard:**
   - Deduplication queries must always pass the candidate's own ID (`exclude_topic_id` / `exclude_id`) so candidates are never compared against themselves.

---

## 10. Monitoring and Learning

Documented in `06 — INTELLIGENCE/Closed-Loop Telemetry & Learning Engine.md`:

1. **Live Cloud Truth Only:** Zero fabricated, placeholder, or synthetic telemetry is permitted. If an endpoint returns 0 views, 0 is recorded.
2. **Maturation Gate ($\ge 24\text{h}$):** Telemetry is harvested only after a video has been live for at least 24 hours to allow audience engagement to settle.
3. **Performance Snapshots:** Time-series records in `performance_snapshots` capture views, likes, comments, Average View Duration (AVD), Average Percentage Viewed (APV), and subscriber delta.
4. **Closed-Loop Adaptation:** Historical performance informs subsequent topic selection and hook framing via statistical algorithms (e.g., UCB1 / bandit weights).

---

## 11. Universal Principles to Inherit in Harry Potter Automation

These principles represent proven, production-grade cloud automation engineering and **must be preserved** in the Harry Potter automation:

1. **Zero-PC Autonomy:** Production, scheduling, publishing, and telemetry must run unattended on GitHub Actions runners without requiring the user's PC, browser, or home network.
2. **Three-Tier Architecture:** Ephemeral compute (GitHub Actions), Durable vault (Google Drive), Knowledge documentation (Obsidian Markdown).
3. **Database Cloud Sync:** Bidirectional download $\rightarrow$ integrity check $\rightarrow$ mutate $\rightarrow$ checkpoint $\rightarrow$ upload $\rightarrow$ SHA256 verify.
4. **Distributed Concurrency (`CompositeLock`):** Cloud locks with 900s TTL, 120s background heartbeats, and GitHub Actions API dead-runner reclamation.
5. **Reserve Buffer Pattern:** Maintain target reserve in Drive `01_READY` with dynamic deficit computation `max(0, target - ready)`.
6. **Rolling 48-Hour Forward Horizon:** Scheduled private uploads on YouTube with `publishAt` timestamps across fixed daily slots.
7. **Physical Gateway Barrier:** Strict transition rules where `03_PUBLISHED` requires live YouTube public read-back verification.
8. **Fail-Closed QA Gates:** Programmatic inspection of video container, resolution, audio loudness (LUFS), pause duration, and dead air.
9. **Multi-Tier Deduplication:** Exact and semantic story deduplication + visual frame hashing + self-matching exclusion guards.
10. **Zero Fabricated Telemetry:** Truthful telemetry harvested directly from APIs; missing data remains `None` / `UNAVAILABLE`.
11. **Persistent Failure & Incident Ledger:** Formal logging of all incidents, failure forensic causes, and regression tests.

---

## 12. AL AMR-Specific Components (DO NOT INHERIT)

The following components from AL AMR are **niche-specific** or **outdated** and must **NOT** be applied to Harry Potter automation:

| Component | AL AMR Specification | Harry Potter Canonical Requirement | Rationale |
|---|---|---|---|
| **Content Niche** | Historical mysteries & bizarre real-world events | Harry Potter canonical novels & lore | Completely different universe and subject matter. |
| **Voice & Persona** | `af_bella` (Kokoro-82M ONNX at 1.00x) | `en-US-AndrewNeural` ("Andrew Hype", +24Hz, +14%) | User explicitly auditioned and selected Andrew Hype for HP Shorts. |
| **Visual Sourcing** | Pexels, Wikimedia, public domain archival scans | **100% MOVIE FOOTAGE ONLY** (Movies 1–8) | Hard invariant: NO stock footage, NO Pexels, NO AI images, NO book screenshots. |
| **Audio Muting** | Not applicable (stock/archival footage) | **Hard Audio Muting (`-an`) on all movie clips** | Movie dialogue/sound effects must never bleed into the Short. |
| **Topic Discovery** | Curated historical mystery seeds | **Novel Chapter Chronology + Book-vs-Movie Discoveries** | Grounded in canonical novel PDFs and movie SRTs. |
| **Daily Mix** | 3 historical mystery Shorts/day | **Configurable: 2 Novel Story + 2 Discovery = 4 Shorts/day** | Two distinct formats matching the content strategy. |
| **Target Buffer** | 6 verified Shorts in `01_READY` | 8 verified Shorts in `01_READY` (2 days $\times$ 4/day) | Reflects 4-Short daily publication volume. |
| **Drive Vault** | `YouTube_Shorts_Vault` | `Harry_Potter_Shorts_Vault` (ID: `11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC`) | Strict credential and cloud storage isolation. |
| **Google Account** | AL AMR Google Account | `jishanh760@gmail.com` | Dedicated Harry Potter account. |

---

## 13. Current Harry Potter Compatibility & Gap Analysis

| Principle / Mechanism | Status in HP Project | Current State in Code/Config | Required Future Action |
|---|---|---|---|
| **Zero-PC Autonomy** | Needs adaptation | Local code has runner workflows, but workflows still reference old secrets/voice | Adapt workflows in Step 10+ for HP account & Andrew voice |
| **Storage Hierarchy (00_SYSTEM .. 04_FAILED)** | Needs adaptation | `core/database_sync.py` and `drive_engine.py` exist, configured to HP vault | Verify HP Drive vault folders exist and database sync succeeds |
| **Distributed Locking (`CompositeLock`)** | Already compatible | `core/cloud_lock.py` contains hardened 900s TTL, 120s heartbeat, dead-runner check | Inherited from base; ready for cloud runs |
| **Database Persistence (SQLite + Drive)** | Already compatible | `pipeline.db` with WAL mode and `database_sync.py` present | Ingested Step 6 & 7 models (`nov_story_candidates`, etc.) persist locally |
| **Sequential Production Execution** | Already compatible | `CloudProductionOrchestrator` runs 1-by-1 | Enforced in orchestrator |
| **Visual Sourcing Policy** | Already compatible | `VisualSourceRouter` locked strictly to `SOURCE_MOVIE_CLIP` | Step 6B eliminated all fallbacks (Pexels, stock, AI) |
| **Audio Muting Invariant (`-an`)** | Already compatible | `MovieAssetEngine.extract_muted_clip` verified with `ffprobe` (0 audio streams) | Hard invariant operational |
| **Content Mix Allocation** | Already compatible | `get_content_mix_allocation()` defaults 2 Novel + 2 Discovery | Configurable in `config/settings.py` |
| **Publication Gates Closed** | Already compatible | `PUBLISHING_ENABLED=false`, `UPLOAD_ENABLED=false` | Gates active and safe |
| **Andrew Hype Voice** | Needs adaptation in scripts | `APPROVED_PRODUCTION_VOICES = ["en-US-AndrewNeural"]` in settings; workflow defaults still mention Bella | Update workflow inputs when cloud automation is configured |
| **Movie Footage Availability on Cloud Runners** | Needs later investigation | Movies 1–8 are in Drive (1–3 GB each); cloud runner scratch disk is ~14 GB | In cloud runner, streaming download / targeted clip extraction or caching needed |
| **YouTube Publishing OAuth** | Needs later investigation | OAuth token exists locally (`credentials/hp_token.json`); secret injection for GHA needed later | When publishing is enabled in later steps, configure HP GitHub repository secrets |

---
*Report generated and committed as documentation only. No pipeline code, database schemas, or production settings were modified.*
