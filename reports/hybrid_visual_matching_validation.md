# STORY FORGE — Phase 2: Hybrid SRT + Movie Event Visual Matching Validation Report
**Phase 2: Controlled Integration (Visual Intelligence Only — No Autonomous Production)**
**Date:** September 25, 2026

---

## 1. Hybrid Architecture

Phase 2 couples SRT dialogue indexing with precision observable movie event verification:

$$\text{Narration} \longrightarrow \text{SRT Coarse Scene Window} \longrightarrow \text{Movie Event Precision Matching} \longrightarrow \text{Objective Candidate Comparison} \longrightarrow \text{"Only If Better" Selection} \longrightarrow \text{Temporal Action Verification} \longrightarrow \text{Lineage Binding} \longrightarrow \text{Controlled Output}$$

This architecture ensures:
1. **SRT is NOT the visual brain:** SRT does not select the final visual clip; it provides coarse spatial and temporal localization to narrow the search space.
2. **MovieEvent provides precision:** Matches observable physical actions, subjects, targets, and settings.
3. **Objective Comparison:** Both candidates (SRT vs MovieEvent) are evaluated under the same verification framework.
4. **"Only If Better" Gate:** Configured via `MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN = 10.0 pts`.
5. **Fail-Closed Fallback Hierarchy:** Prevents forced or random footage if no verified evidence exists.

---

## 2. SRT Localization Behavior
The `SRTCoarseLocator` queries SQLite FTS5 across 4,470 subtitle chunks:
- Derives an `SRTTimeWindow`:
  - `scene_window_start`: $\max(0.0, t_{\text{pref}} - 30.0\text{s})$
  - `scene_window_end`: $t_{\text{pref}} + 30.0\text{s}$
  - `preferred_timestamp`: Timestamp of top dialogue match
  - `nearby_scene_context`: Subtitle dialogue snippet
- **Hierarchical Search Progression:**
  - **Level 1 (Tight Window):** $\pm 30.0\text{s}$ padding around preferred timestamp.
  - **Level 2 (Adjacent Expansion):** $\pm 90.0\text{s}$ window expansion to capture contiguous scene units.
  - **Level 3 (Franchise Search):** Wider franchise-level search when local dialogue yields zero events.

---

## 3. MovieEvent Precision Behavior
Once localized to an SRT window, the `MovieEventRetrievalEngine` queries candidate events using:
- `primary_subject` and `secondary_subjects`
- `action` (physical action verbs clustered by stem)
- `target` (character or object recipient)
- `location` (physical environment)
- `forbidden_elements` (elements that disqualify candidates)

Candidate events inside the SRT window receive temporal priority, avoiding full-movie brute force scans.

---

## 4. Candidate Comparison Logic
The `HybridVisualSelector` evaluates Candidate A (SRT dialogue cue) and Candidate B (MovieEvent index candidate) using the same 9 verification dimensions:
- `subject_match` (Weight 30 pts)
- `action_match` (Weight 35 pts — **Hard Veto**)
- `target_match` (Weight 15 pts)
- `location_match` (Weight 10 pts)
- `interaction_match` (Weight 10 pts)
- `forbidden_absent` (Disqualifier: $-50\text{ pts}$ if violated)
- `temporal_alignment` & `proximity`

**Action Mismatch is an Insurmountable Veto:** If a candidate depicts a different physical action (e.g. walking instead of questioning), verification fails with `REJECT_ACTION_MISMATCH` regardless of character presence or dialogue proximity.

---

## 5. Improvement-Margin Behavior
To prevent unnecessary churn or replacing optimal clips, the selector enforces the named configuration constant:
$$\text{MOVIE\_EVENT\_MIN\_IMPROVEMENT\_MARGIN} = 10.0\text{ pts}$$

- **Rule 1 (MovieEvent Wins):** MovieEvent verified, free of action mismatch, and $\text{Score}_{\text{ME}} - \text{Score}_{\text{SRT}} \ge 10.0\text{ pts}$.
- **Rule 2 (Unconditional Action Override):** MovieEvent verified, SRT failed verification (e.g. `REJECT_ACTION_MISMATCH`) $\rightarrow$ MovieEvent wins unconditionally.
- **Rule 3 (SRT Retained):** SRT verified, and MovieEvent delta does not satisfy the $10.0\text{ pt}$ margin $\rightarrow$ SRT candidate retained as verified fallback (`FALLBACK_SRT`).

---

## 6. Fallback Hierarchy
The selector enforces a 4-tier fallback:
1. **Verified MovieEvent Candidate** with improvement $\ge 10.0\text{ pts}$.
2. **Existing SRT Candidate** if independently verified and stronger/equal.
3. **Expanded MovieEvent Search** (Level 2 / Level 3).
4. **`NO_VALID_VISUAL`**: When neither candidate demonstrates the required physical action, the system strictly returns `NO_VALID_VISUAL`. Random or unrelated clips are never forced.

---

## 7. Event-Chain Behavior
When a narrative proposition requires sequential coverage:
$$\text{Preceding Context (Approach)} \longrightarrow \text{Core Action} \longrightarrow \text{Following Reaction (Payoff)}$$
The hybrid selector binds neighboring event IDs to ensure coherent shot-to-shot flow rather than disjointed cuts across unrelated scenes.

---

## 8. Temporal Action Engine Integration
The selected candidate is evaluated by the `TemporalActionEngine`:
- Verifies dynamic action transitions (e.g. drawing sword, punching, opening entrance) versus continuous states (e.g. standing, looking, listening).
- Flags temporal state: `TRANSITION_VERIFIED` or `SUSTAINED_STATE_VERIFIED`.

---

## 9. Lineage Integration
Every selection is cryptographically bound into the visual plan:
- `content_id`
- `narration_hash` ($\text{SHA-256}_{16}$)
- `proposition_hash` ($\text{SHA-256}_{16}$)
- `source_evidence_hash` ($\text{SHA-256}_{16}$)
- `timeline_hash` ($\text{SHA-256}_{16}$)
- `visual_plan_id` (`vp_<hash>`)

Any modification to narration or propositions changes the visual plan ID and forces a clean rebuild, preventing stale visual artifact reuse.

---

## 10. All-8-Movie Coverage Status

| Movie | Title | Subtitle Chunks in DB | Structured MovieEvents | Status |
| :---: | :--- | :---: | :---: | :--- |
| **Movie 1** | *Sorcerer's Stone* | 594 | 6 | **Complete (Benchmark 1 Coverage)** |
| **Movie 2** | *Chamber of Secrets* | 646 | 4 | **Complete (Benchmark 3 Coverage)** |
| **Movie 3** | *Prisoner of Azkaban* | 534 | 4 | **Complete (Benchmark 4 Coverage)** |
| **Movie 4** | *Goblet of Fire* | 583 | 0 | **Coverage Gap Identified** (Subtitles indexed; 0 structured events) |
| **Movie 5** | *Order of the Phoenix* | 538 | 0 | **Coverage Gap Identified** (Subtitles indexed; 0 structured events) |
| **Movie 6** | *Half-Blood Prince* | 566 | 0 | **Coverage Gap Identified** (Subtitles indexed; 0 structured events) |
| **Movie 7** | *Deathly Hallows – Part 1* | 606 | 0 | **Coverage Gap Identified** (Subtitles indexed; 0 structured events) |
| **Movie 8** | *Deathly Hallows – Part 2* | 403 | 3 | **Complete (Benchmark 2 Coverage)** |
| **TOTAL** | **Franchise (1–8)** | **4,470 chunks** | **17 events** | **Controlled Offline Hybrid Functional** |

**Audit Findings:**
- All 8 movies have complete subtitle chunking (4,470 chunks) and can provide coarse time windows via FTS5.
- Movies 4, 5, 6, and 7 currently have 0 structured observable physical events in `MovieEventIndex`.
- The hybrid matcher handles this gap gracefully: queries targeting Movies 4–7 either localize via SRT and fallback to `FALLBACK_SRT` if verified, or return `NO_VALID_VISUAL`. Zero events were fabricated.

---

## 11. Controlled Benchmark Results (Categories A – H)

| Category | Benchmark Narration | SRT Search Window | Candidate A (SRT) | Candidate B (MovieEvent) | Delta | Selected Source | Reason | Status |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |
| **A** | *"Snape questions Harry in Potions classroom."* | Movie 1 `00:54:15 – 00:55:15` | `srt_cue_hp_m1_sc_0234` (25.0) | `evt_m1_potions_snape_questions_harry` (80.0) | $+55.0$ | `MOVIE_EVENT` | MovieEvent verified; exceeded margin $+55.0$ pts | `VERIFIED` |
| **B** | *"Neville draws the Sword of Gryffindor."* | Movie 8 `00:37:21 – 00:38:21` | `srt_cue_hp_m8_sc_0158` (25.0) | `evt_m8_courtyard_neville_draws_sword` (80.0) | $+55.0$ | `MOVIE_EVENT` | MovieEvent verified; exceeded margin $+55.0$ pts | `VERIFIED` |
| **C** | *"Harry opens the Chamber of Secrets entrance."* | Movie 2 `02:05:21 – 02:06:21` | `srt_cue_hp_m2_sc_0554` (25.0) | `evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber` (80.0) | $+55.0$ | `MOVIE_EVENT` | MovieEvent verified; exceeded margin $+55.0$ pts | `VERIFIED` |
| **D** | *"Hermione punches Malfoy."* | Movie 3 `01:48:54 – 01:49:54` | `srt_cue_hp_m3_sc_0456` (25.0) | `evt_m3_sundial_hermione_punches_malfoy` (80.0) | $+55.0$ | `MOVIE_EVENT` | MovieEvent verified; exceeded margin $+55.0$ pts | `VERIFIED` |
| **E** | *"What would I get if I added root of asphodel to an infusion of wormwood?"* | Movie 1 `00:52:09 – 00:53:09` | `evt_m1_potions_snape_questions_harry` (35.0) | `evt_m1_potions_snape_questions_harry` (35.0) | $+0.0$ | `SRT_CANDIDATE` | SRT verified; delta did not satisfy $10.0\text{ pt}$ margin | `FALLBACK_SRT` |
| **F** | *"Snape questions Harry at his desk."* | Movie 1 `00:54:15 – 00:55:15` | `srt_cue_hp_m1_sc_0234` (25.0) | `evt_m1_potions_harry_defends_self` (12.0) | $-13.0$ | `NO_VALID_VISUAL` | Neither candidate verified for questioning desk shot | `NO_VALID_VISUAL` |
| **G** | *"Neville draws the Sword of Gryffindor from the Sorting Hat."* | Movie 8 `00:37:21 – 00:38:21` | `srt_cue_hp_m8_sc_0158` (25.0) | `evt_m8_courtyard_neville_draws_sword` (80.0) | $+55.0$ | `MOVIE_EVENT` | SRT failed (dialogue only); MovieEvent verified | `VERIFIED` |
| **H** | *"Snape secretly suspected Harry was connected to Voldemort."* | Movie 1 `00:44:16 – 00:45:16` | `srt_cue_hp_m1_sc_0192` (25.0) | `evt_m1_potions_snape_walks_toward_harry` (25.0) | $+0.0$ | `NO_VALID_VISUAL` | Abstract internal claim; zero false positives | `NO_VALID_VISUAL` |

---

## 12. Performance & Runtime Cost
Measurements recorded on local runner:
- **Total Categories Evaluated:** 8
- **Total Candidates Searched:** 51
- **Total Candidates Verified:** 16
- **Average Retrieval Latency:** **$9.17\text{ ms}$**
- **Worst-Case Latency:** **$16.00\text{ ms}$**
- **Indexing Overhead:** In-memory SQLite FTS5 index lookup + pre-indexed event graph. **Zero redundant disk re-scans**.
- **GitHub Actions Scalability:** With latency $< 20\text{ ms}$ per beat, a full 10-beat Short evaluates in $< 200\text{ ms}$, fully compatible with cloud runners and the 4 Shorts/day schedule.

---

## 13. Known Limitations
1. **Event Index Density for Movies 4–7:** As documented in Section 10, Movies 4–7 lack structured observable events in `MovieEventIndex`. They rely on subtitle coarse localization and fall back safely to `NO_VALID_VISUAL` if physical verification cannot be established.
2. **Abstract Claim Boundary:** Narrative scripts with unfilmed lore or abstract internal thoughts require manual or upstream editorial rewriting into observable actions.
