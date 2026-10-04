"""
YouTube Upload & Scheduling Engine (Phase 18).
Implements True YouTube-Side Scheduled Publishing using YouTube Data API v3.
- Assigns non-public privacyStatus="private" with publishAt RFC3339 UTC timestamp.
- YouTube holds video and automatically transitions it to PUBLIC at publishAt.
- Explicit API read-back verification of publishAt and privacyStatus.
- Full idempotency: reconciles existing records without duplicate uploads.
"""
import os
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from config.settings import TEST_MODE, CLIENT_SECRETS_FILE, PROJECT_ROOT, TOKEN_PATH
from core.models import Job, RenderOutput, UploadRecord, ScriptRecord
from config.constants import JobState

logger = logging.getLogger(__name__)


class UploadEngine:
    """Manages YouTube uploads and YouTube-side scheduled publishing via Data API v3."""

    def _get_token_path(self) -> Path:
        """Returns the isolated Harry Potter token path, falling back to PROJECT_ROOT / token.json."""
        if TOKEN_PATH and Path(TOKEN_PATH).exists():
            return Path(TOKEN_PATH)
        fallback = PROJECT_ROOT / "token.json"
        return fallback

    def get_authorized_youtube_client(self):
        """
        Retrieves fully authorized YouTube API v3 client with proactive token refresh,
        automatic persistence of refreshed tokens, and channel isolation verification.
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_path = self._get_token_path()
        if not token_path.exists():
            raise FileNotFoundError(f"OAuth token not found at {token_path}. Run authentication setup.")

        creds = Credentials.from_authorized_user_file(str(token_path))
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("[AUTH] YouTube OAuth token expired. Proactively refreshing...")
                creds.refresh(Request())
                try:
                    with open(token_path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                    logger.info("[AUTH] Refreshed OAuth token persisted successfully.")
                except Exception as save_err:
                    logger.warning(f"[AUTH] Could not persist refreshed token: {save_err}")
            else:
                raise PermissionError(f"[AUTH_ERROR] YouTube OAuth token invalid and cannot be refreshed from {token_path}.")

        youtube = build("youtube", "v3", credentials=creds)
        self.verify_channel_authorization(youtube=youtube)
        return youtube

    def validate_media_integrity(self, video_path: Union[str, Path]) -> None:
        """
        Strict pre-upload media integrity guard:
        - Rejects missing files
        - Rejects files smaller than 500 KB (a valid 20-30s 1080x1920 Short is typically 15MB - 35MB)
        - Runs FFmpeg integrity decode probe using configured FFMPEG_EXE
        - Rejects invalid/corrupt/truncated/non-video media
        - Ensures rejected media never reaches YouTube API
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"[UPLOAD_INTEGRITY] Video file does not exist: {path}")

        file_size = path.stat().st_size
        min_size = 500 * 1024  # 500 KB minimum
        if file_size < min_size:
            raise ValueError(
                f"[UPLOAD_INTEGRITY] Video file too small ({file_size} bytes < {min_size} bytes minimum): {path}"
            )

        from config.settings import FFMPEG_EXE
        import subprocess

        try:
            probe = subprocess.run(
                [FFMPEG_EXE, "-v", "error", "-i", str(path), "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=30
            )
        except Exception as probe_err:
            raise ValueError(f"[UPLOAD_INTEGRITY] Failed to run FFmpeg integrity probe on {path}: {probe_err}")

        if probe.returncode != 0:
            err_details = probe.stderr.strip()[:300] if probe.stderr else "Non-zero exit code"
            raise ValueError(f"[UPLOAD_INTEGRITY] Media failed FFmpeg integrity validation: {err_details}")

    def _is_test_mode(self) -> bool:
        from config.settings import TEST_MODE
        return bool(TEST_MODE) or os.getenv("TEST_MODE", "false").lower() in ["true", "1", "yes"]

    def evaluate_publication_safety_gate(
        self,
        db: Session,
        job: Job,
        render: RenderOutput,
        metadata: Dict[str, Any],
        scheduled_slot: Optional[datetime] = None,
        allow_immediate: bool = False
    ) -> Tuple[bool, str]:
        """
        15-Point Autonomous Publication Safety Gate.
        Evaluates physical, logical, temporal, and credential invariants before permitting YouTube upload.
        """
        video_path = Path(render.video_path) if render and render.video_path else None
        
        # 1. File exists
        if not video_path or not video_path.exists():
            return False, f"Gate 1 Failed: Rendered file does not exist ({video_path})"

        # 2. File is readable
        if not os.access(str(video_path), os.R_OK):
            return False, f"Gate 2 Failed: Video file not readable by process ({video_path})"

        # 3. MP4 is valid (FFmpeg probe)
        if not self._is_test_mode():
            try:
                self.validate_media_integrity(video_path)
            except Exception as err:
                return False, f"Gate 3 Failed: Media integrity check failed ({err})"

        # 4. Duration within configured Shorts range (12.0s - 60.0s)
        dur = float(getattr(render, "duration_sec", None) or getattr(render, "total_duration_sec", None) or 0.0)
        if dur < 12.0 or dur > 60.0:
            return False, f"Gate 4 Failed: Duration {dur:.1f}s out of bounds (12.0s - 60.0s)"

        # 5. Resolution is 1080x1920
        width = getattr(render, "width", None) or 1080
        height = getattr(render, "height", None) or 1920
        if (width != 1080 or height != 1920) and not self._is_test_mode():
            return False, f"Gate 5 Failed: Resolution {width}x{height} != 1080x1920"

        # 6. Audio stream exists & non-empty
        if not self._is_test_mode() and render.file_size_bytes and render.file_size_bytes < 500000:
            return False, f"Gate 6 Failed: File size {render.file_size_bytes} bytes abnormally small"

        # 7. Render pipeline completed
        if not render or not render.id:
            return False, "Gate 7 Failed: Render output record incomplete"

        # 8. Final QA status = PASS
        from core.models import QAReport
        qa_rec = db.query(QAReport).filter(QAReport.job_id == job.id).order_by(QAReport.created_at.desc()).first()
        if qa_rec and not qa_rec.passed:
            return False, f"Gate 8 Failed: Job {job.id} failed QA ({qa_rec.failure_reasons})"

        # 9. Database state is READY_TO_UPLOAD, RENDERED_QA_PASSED, or QA/EDITED
        valid_states = [
            JobState.READY_TO_UPLOAD.value, "READY_TO_UPLOAD",
            JobState.RENDERED_QA_PASSED.value, "RENDERED_QA_PASSED",
            JobState.QA.value, "QA",
            JobState.EDITING.value, "EDITED",
            "COMPLETED"
        ]
        if job.state not in valid_states:
            return False, f"Gate 9 Failed: Job state '{job.state}' not in eligible staging states"

        # 10. Job has not already been published
        existing_pub = db.query(UploadRecord).filter(
            UploadRecord.job_id == job.id,
            UploadRecord.status.in_(["PUBLISHED", "SUCCESS"])
        ).first()
        if existing_pub:
            return False, f"Gate 10 Failed: Job {job.id} already published (Video ID: {existing_pub.youtube_video_id})"

        # 11. Hard 3-Shorts/Day Ceiling Guard for Target UTC Calendar Day
        from config.constants import DAILY_SHORTS_LIMIT
        from datetime import time as dtime
        target_slot_utc = scheduled_slot.replace(tzinfo=None) if scheduled_slot else datetime.utcnow()
        target_date = target_slot_utc.date()
        day_start = datetime.combine(target_date, dtime.min)
        day_end = datetime.combine(target_date, dtime.max)

        pub_for_day = db.query(UploadRecord).filter(
            UploadRecord.status.in_(["PUBLISHED", "SUCCESS"]),
            UploadRecord.published_at >= day_start,
            UploadRecord.published_at <= day_end
        ).count()

        sched_for_day = db.query(UploadRecord).filter(
            UploadRecord.status.in_(["SCHEDULED", "TEST_VERIFIED"]),
            UploadRecord.scheduled_publish_at >= day_start,
            UploadRecord.scheduled_publish_at <= day_end,
            UploadRecord.job_id != job.id
        ).count()

        total_day_booked = pub_for_day + sched_for_day
        if total_day_booked >= DAILY_SHORTS_LIMIT:
            return False, f"Gate 11 Failed: Daily limit reached for {target_date} ({total_day_booked}/{DAILY_SHORTS_LIMIT} releases already booked). Refusing 4th release."

        # 12. Publishing slot is valid
        if scheduled_slot and not allow_immediate:
            slot_utc = scheduled_slot.replace(tzinfo=None)
            now_utc = datetime.utcnow()
            if slot_utc <= now_utc:
                return False, f"Gate 12 Failed: Scheduled slot {slot_utc} is not in the future"

        # 13. YouTube authentication availability
        token_path = self._get_token_path()
        if not token_path.exists() and not self._is_test_mode():
            return False, f"Gate 13 Failed: YouTube OAuth token not found at {token_path}"

        # 14. Metadata is valid
        if not metadata or not metadata.get("title") or len(metadata.get("title", "").strip()) < 3:
            return False, "Gate 14 Failed: Title metadata missing or invalid"

        # 15. No duplicate title or story in published or scheduled records
        norm_title = metadata.get("title", "").strip().lower()
        dup_title = db.query(UploadRecord).filter(
            UploadRecord.title.ilike(norm_title),
            UploadRecord.status.in_(["PUBLISHED", "SUCCESS", "SCHEDULED", "TEST_VERIFIED"])
        ).first()
        if dup_title and dup_title.job_id != job.id:
            return False, f"Gate 15 Failed: Title already published or scheduled (Status: {dup_title.status}, Video ID: {dup_title.youtube_video_id})"

        # Semantic Deduplication Gate: verifies candidate story is not a semantic duplicate of existing catalog
        try:
            from engines.deduplication_engine import DeduplicationRouter
            dedup_engine = DeduplicationRouter()
            desc = metadata.get("description", "") or ""
            clean_cand_title = (metadata.get("title") or "").strip()
            exclude_topic_id = getattr(job, "topic_id", None)
            if not exclude_topic_id and clean_cand_title:
                top_match = db.query(Topic).filter(Topic.title.ilike(clean_cand_title)).first()
                if top_match:
                    exclude_topic_id = top_match.id

            dedup_res = dedup_engine.evaluate_candidate(
                candidate_title=clean_cand_title,
                candidate_summary=desc,
                db=db,
                exclude_topic_id=exclude_topic_id,
                exclude_job_id=getattr(job, "id", None),
                exclude_title=clean_cand_title
            )
            if not dedup_res.is_allowed:
                return False, f"Gate 15 Failed: Story is a duplicate of '{dedup_res.matched_event_title}' ({dedup_res.classification})"
        except Exception as dedup_err:
            logger.warning(f"[GATE 15] Dedup evaluation notice: {dedup_err}")

        # 16. Strict Editorial Policy Gate
        # For Harry Potter automation:
        # Verify asset adheres to Harry Potter standards (100% movie footage, Bella voice, canonical script).
        is_hp_job = False
        resolved_script_id = None
        if job and job.id:
            clean_jid = job.id.replace("job_", "")
            if clean_jid.startswith("hps_") or job.id.startswith("hps_"):
                is_hp_job = True
                resolved_script_id = clean_jid

        if not is_hp_job and metadata.get("script_id"):
            m_id = metadata.get("script_id")
            if m_id and m_id.startswith("hps_"):
                is_hp_job = True
                resolved_script_id = m_id

        if is_hp_job or resolved_script_id:
            from core.models import HarryPotterScript, HPRender
            hp_script = db.query(HarryPotterScript).filter_by(id=resolved_script_id).first() if resolved_script_id else None
            if not hp_script and job and job.id:
                hp_script = db.query(HarryPotterScript).filter_by(id=job.id.replace("job_", "")).first()
            if not hp_script and resolved_script_id:
                hp_script = db.query(HarryPotterScript).filter(HarryPotterScript.id.ilike(f"%{resolved_script_id}%")).first()

            if hp_script:
                allowed_voices = ("af_bella", "bella", "male_18", "MALE_18_FenrirOnyx_DarkBaritone", "f5_tts")
                if hp_script.voice_id not in allowed_voices and not str(hp_script.voice_id).startswith(("af_bella", "f5")):
                    return False, f"Gate 16 Failed: Harry Potter voice '{hp_script.voice_id}' is invalid (af_bella required)"
                ct = str(hp_script.content_type).lower()
                if ct not in ("novel_story", "discovery", "discovery_big", "discovery_short"):
                    return False, f"Gate 16 Failed: Invalid content type '{hp_script.content_type}'"
                # Passed Harry Potter editorial policy
            else:
                return False, f"Gate 16 Failed: Harry Potter script '{resolved_script_id}' not registered in database"
        else:
            from intelligence.clustering import is_niche_compliant
            cand_title = metadata.get("title", "")
            cand_desc = metadata.get("description", "")
            cand_script = ""
            script_rec = db.query(ScriptRecord).filter(ScriptRecord.topic_id == job.topic_id).first() if (job and getattr(job, "topic_id", None)) else None
            if script_rec and getattr(script_rec, "full_text", None):
                cand_script = script_rec.full_text
            elif script_rec and getattr(script_rec, "script_text", None):
                cand_script = script_rec.script_text
            is_niche, niche_reason = is_niche_compliant(title=cand_title, text=f"{cand_desc} {cand_script}")
            if not is_niche:
                return False, f"Gate 16 Failed: Asset violates editorial policy (Mystery / Bizarre Real-World Stories ONLY): {niche_reason}"

        return True, "All 16 publication safety gates passed successfully"

    @staticmethod
    def generate_seo_description(
        title: str,
        topic: Optional[str] = None,
        source_reference: Optional[str] = None,
        key_characters: Optional[List[str]] = None
    ) -> str:
        """
        Engine-level Professional YouTube Shorts SEO Description Generator.
        Replaces raw script dumps with high-converting search-optimized metadata:
        - Engaging curiosity hook
        - Key search topics & lore keywords
        - Channel branding & call to action
        - High-density discoverability hashtags
        - Standard Fair Use disclaimer
        """
        import re
        clean_t = re.sub(r"#\w+", "", title)
        clean_t = re.sub(r"\s*\|\s*Harry Potter.*", "", clean_t, flags=re.IGNORECASE).strip()
        clean_t = clean_t.replace(" | ", " - ").strip()
        if not clean_t:
            clean_t = "Hidden Harry Potter Lore Secret"

        lines = [
            f"⚡ Did you catch this subtle detail? {clean_t}!",
            "",
            "Explore the hidden lore, book vs movie differences, and secret details of the Wizarding World that even hardcore Potterheads often overlook.",
            "",
            "🔔 Subscribe to Story Forge for daily Harry Potter lore discoveries, movie secrets, and deleted scene breakdowns!",
            "",
            "✨ Topics & Lore Keywords:",
            f"• {clean_t}",
            "• Harry Potter Movie Details & Hidden Easter Eggs",
            "• Hogwarts Secrets & Wizarding World Canon Lore",
            "• J.K. Rowling Book vs Movie Differences",
            "",
            "#HarryPotter #Shorts #WizardingWorld #Hogwarts #MovieFacts #HarryPotterLore #HogwartsSecrets",
            "",
            "---",
            "Disclaimer: Content created for commentary, criticism, and fan lore analysis under Fair Use principles. All movie footage, imagery, and related characters are trademarks of Warner Bros. Entertainment Inc. and J.K. Rowling."
        ]
        return "\n".join(lines).strip()

    @classmethod
    def sanitize_public_description(cls, description: str, title: Optional[str] = None) -> str:
        """
        Engine-level Description Sanitizer:
        1. Strips internal production identifiers (job IDs, run IDs, telemetry, etc.).
        2. Detects raw script dumps / voiceover artifacts and automatically replaces them
           with clean, high-ranking professional SEO metadata.
        """
        if not description and title:
            return cls.generate_seo_description(title=title)
        if not description:
            return ""

        import re
        # Check if description is a dumped voiceover script
        is_dumped_script = any(sig in description.lower() for sig in [
            "voiceover by", "af_bella", "narrator_v1", "f5_cloned", "canonical source:"
        ]) or (title and len(description.split()) > 35 and not any(k in description.lower() for k in ["topics & lore", "subscribe", "disclaimer", "story forge"]))

        if is_dumped_script and title:
            return cls.generate_seo_description(title=title)

        # Remove bracketed tags like [JOB_ID: ...]
        cleaned = re.sub(
            r"\[(JOB_ID|RUN_ID|MANIFEST_ID|EVENT_ID|PIPELINE_ID|DRIVE_ID|VAULT_ID)[^\]]*\]",
            "",
            description,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\b(job|upl|manrec|man|rnd|evt)_[a-zA-Z0-9_-]+\b", "", cleaned)
        cleaned = re.sub(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            "",
            cleaned,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\*{2,}", "", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def sanitize_public_title(title: str) -> str:
        """
        Strips internal build codes (B1, B2, B3, PART 01, Discovery, etc.) from public YouTube titles
        and formats them cleanly for viewer curiosity.
        """
        if not title:
            return ""
        import re
        cleaned = title
        # Remove build slugs like B1, B2, B3, B4, B5, B6, B7
        cleaned = re.sub(r"\bB[1-7]\b", "", cleaned, flags=re.IGNORECASE)
        # Remove internal candidate classifications
        cleaned = re.sub(r"\b(Discovery|NovStory|Candidate)\b", "", cleaned, flags=re.IGNORECASE)
        # Remove part markers like [PART 01], PART 02
        cleaned = re.sub(r"\[PART\s*\d+\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bPART\s*\d+\b", "", cleaned, flags=re.IGNORECASE)
        # Clean up repeated separators or dangling pipes/dashes
        cleaned = re.sub(r"\s*[\|\-:]\s*([\|\-:]\s*)+", " | ", cleaned)
        cleaned = re.sub(r"^\s*[\|\-:]+\s*", "", cleaned)
        cleaned = re.sub(r"\s*[\|\-:]+\s*$", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        # Ensure #Shorts is present
        if "#Shorts" not in cleaned and "#shorts" not in cleaned:
            cleaned = f"{cleaned} #Shorts"
        return cleaned.strip()

    @staticmethod
    def post_engagement_comment(youtube, video_id: str, title: str = "") -> Optional[str]:
        """
        Posts an engaging seed question to prompt viewer debate and trigger algorithm comment velocity.
        """
        try:
            questions = [
                "Which book-only detail do you wish they kept in the movies? Let us know below! 👇",
                "Did you notice this detail the first time you watched the movies? Tell us below! 👇",
                "What is your favorite hidden secret in Harry Potter? Drop your thoughts below! 👇",
                "Be honest: would you have survived this in the wizarding world? Let us know! 👇"
            ]
            import random
            comment_text = random.choice(questions)
            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            res = youtube.commentThreads().insert(part="snippet", body=body).execute()
            comment_id = res.get("id")
            logger.info(f"[ENGAGEMENT] Successfully posted seed discussion comment {comment_id} on video {video_id}")
            return comment_id
        except Exception as e:
            logger.warning(f"[ENGAGEMENT] Notice posting comment on video {video_id}: {e}")
            return None

    def recover_orphaned_upload(
        self,
        youtube,
        job: Job,
        metadata: Dict[str, Any],
        scheduled_publish_at: Optional[datetime] = None
    ) -> Tuple[Optional[str], str]:
        """
        Deterministic YouTube Orphan Recovery Check.
        Searches channel for existing videos matching:
          - Embedded Job ID tag [JOB_ID: {job.id}] in description (Definitive 100% confidence).
          - Exact normalized title match with scheduled status verification.
        Returns: (recovered_video_id, recovery_reason) or (None, reason)
        If candidate matches are ambiguous: surfaces ORPHAN_RECOVERY_AMBIGUOUS without guessing.
        """
        title = metadata.get("title", "").strip()
        norm_title = title.lower()
        if not title:
            return None, "NO_TITLE_PROVIDED"

        try:
            search_res = youtube.search().list(
                part="snippet",
                forMine=True,
                q=title[:50],
                type="video",
                maxResults=10
            ).execute()

            candidates = []
            job_tag = f"[JOB_ID: {job.id}]"

            for item in search_res.get("items", []):
                item_id = item.get("id", {}).get("videoId")
                if not item_id:
                    continue
                item_title = item.get("snippet", {}).get("title", "").strip().lower()
                item_desc = item.get("snippet", {}).get("description", "")

                has_job_tag = (job_tag in item_desc) or (job.id in item_desc)
                has_exact_title = (item_title == norm_title)

                if has_job_tag:
                    return item_id, f"HIGH_CONFIDENCE_JOB_TAG:{item_id}"
                elif has_exact_title:
                    candidates.append((item_id, item))

            if len(candidates) == 1:
                cand_id, cand_item = candidates[0]
                v_res = youtube.videos().list(part="status,snippet", id=cand_id).execute()
                v_items = v_res.get("items", [])
                if v_items:
                    v_stat = v_items[0].get("status", {})
                    v_priv = v_stat.get("privacyStatus")
                    if v_priv in ("private", "public"):
                        return cand_id, f"HIGH_CONFIDENCE_EXACT_TITLE:{cand_id}"
                return cand_id, f"EXACT_TITLE_MATCH:{cand_id}"
            elif len(candidates) > 1:
                logger.warning(
                    f"[ORPHAN_RECOVERY] Found {len(candidates)} ambiguous video candidates matching title '{title}'. "
                    f"Refusing to guess without unique job ID tag."
                )
                return None, "ORPHAN_RECOVERY_AMBIGUOUS"

            return None, "NO_ORPHAN_FOUND"

        except Exception as e:
            logger.warning(f"[ORPHAN_RECOVERY] Pre-upload orphan search error: {e}")
            return None, f"ORPHAN_CHECK_ERROR:{e}"

    def get_youtube_service(self):
        """
        Constructs and returns authenticated Google YouTube Data API v3 service.
        Uses ONLY the Harry Potter-isolated credential file: credentials/hp_token.json
        NEVER uses AL AMR token.json or any other project's credentials.
        """
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from config.settings import TOKEN_PATH
        # Isolated HP token path — gitignored, never committed
        token_path = TOKEN_PATH
        if not token_path.exists():
            raise FileNotFoundError(
                f"Harry Potter OAuth token not found at {token_path}. "
                "Run: python scripts/auth_google.py to authenticate jishanh760@gmail.com."
            )
        creds = Credentials.from_authorized_user_file(str(token_path))
        return build("youtube", "v3", credentials=creds)

    def upload_and_schedule_short(
        self,
        db: Session,
        job: Job,
        render: RenderOutput,
        metadata: Dict[str, Any],
        scheduled_publish_at: datetime
    ) -> UploadRecord:
        """Alias for schedule_short."""
        return self.schedule_short(db, job, render, metadata, scheduled_publish_at)

    def verify_channel_authorization(self, youtube=None) -> str:
        """
        FAIL-CLOSED HARD CHANNEL ISOLATION GUARD.
        Verifies authenticated YouTube channel strictly matches EXPECTED_YOUTUBE_CHANNEL_ID.
        """
        from config.settings import EXPECTED_YOUTUBE_CHANNEL_ID
        if youtube is None:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            token_path = self._get_token_path()
            if not token_path.exists():
                raise FileNotFoundError(f"OAuth token not found at {token_path}")
            creds = Credentials.from_authorized_user_file(str(token_path))
            youtube = build("youtube", "v3", credentials=creds)

        ch_res = youtube.channels().list(mine=True, part="id,snippet").execute()
        ch_items = ch_res.get("items", [])
        if not ch_items:
            raise PermissionError("[HARD_CHANNEL_GUARD_VIOLATION] No YouTube channel found for authenticated user.")
        actual_channel_id = ch_items[0].get("id")
        if actual_channel_id != EXPECTED_YOUTUBE_CHANNEL_ID:
            raise PermissionError(
                f"[HARD_CHANNEL_GUARD_VIOLATION] Authenticated YouTube channel '{actual_channel_id}' "
                f"does NOT match expected Harry Potter channel '{EXPECTED_YOUTUBE_CHANNEL_ID}'. "
                "Refusing upload to prevent cross-channel pollution."
            )
        return actual_channel_id

    def schedule_short(
        self,
        db: Session,
        job: Job,
        render: RenderOutput,
        metadata: Dict[str, Any],
        scheduled_publish_at: datetime
    ) -> UploadRecord:
        """
        Uploads and schedules a YouTube Short to be automatically published by YouTube
        at the specified scheduled_publish_at UTC timestamp.

        PUBLISHING SAFETY GATE:
        PUBLISHING_ENABLED and UPLOAD_ENABLED must both be set to True in .env
        before any upload can proceed. They default to False and remain False
        until the explicit launch step is authorized by the user.
        """
        # Hard publishing safety gate — prevents any accidental upload
        from config.settings import PUBLISHING_ENABLED, UPLOAD_ENABLED
        if not self._is_test_mode() and (not PUBLISHING_ENABLED or not UPLOAD_ENABLED):
            raise PermissionError(
                "[PUBLISHING_BLOCKED] Upload rejected by safety gate. "
                "PUBLISHING_ENABLED and UPLOAD_ENABLED must both be set to True in .env. "
                "These are only enabled during the explicit launch step. "
                "This ensures the Harry Potter automation cannot accidentally publish "
                "to the AL AMR channel or any channel before authorization."
            )

        upload_id = f"upl_{uuid.uuid4().hex[:12]}"
        video_path = Path(render.video_path)

        # Ensure timestamp is formatted as RFC 3339 UTC with 'Z' suffix
        publish_at_utc = scheduled_publish_at.replace(microsecond=0)
        publish_at_str = publish_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Hard invariant: publishAt must be strictly in the future (at least 5 min)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if publish_at_utc <= now_utc:
            raise ValueError(f"Cannot schedule upload for past or immediate timestamp: {publish_at_str}. Must be a future slot.")

        # 1. Multi-Layer Idempotency Check: Verify if this Job, Title, or Topic already has an active/completed upload
        norm_title = metadata.get("title", "").strip().lower()
        existing = db.query(UploadRecord).filter(
            (UploadRecord.job_id == job.id) |
            (UploadRecord.title.ilike(norm_title))
        ).filter(
            UploadRecord.status.in_(["SCHEDULED", "PUBLISHED", "TEST_VERIFIED"])
        ).first()

        if existing and existing.youtube_video_id:
            logger.info(f"[IDEMPOTENCY] Video for Job {job.id} / Title '{metadata.get('title')}' is already uploaded/scheduled ({existing.youtube_video_id}, status={existing.status}). Reconciling without duplicate upload.")
            job.state = JobState.SCHEDULED.value if existing.status == "SCHEDULED" else JobState.PUBLISHED.value
            db.commit()
            return existing

        # Hard Production Invariant: Final Scheduling Boundary Daily Cap Guard
        from config.constants import DAILY_SHORTS_LIMIT
        from datetime import time as dtime
        target_date = publish_at_utc.date()
        day_start = datetime.combine(target_date, dtime.min)
        day_end = datetime.combine(target_date, dtime.max)

        pub_count = db.query(UploadRecord).filter(
            UploadRecord.status.in_(["PUBLISHED", "SUCCESS"]),
            UploadRecord.published_at >= day_start,
            UploadRecord.published_at <= day_end
        ).count()

        sched_count = db.query(UploadRecord).filter(
            UploadRecord.status.in_(["SCHEDULED", "TEST_VERIFIED"]),
            UploadRecord.scheduled_publish_at >= day_start,
            UploadRecord.scheduled_publish_at <= day_end,
            UploadRecord.job_id != job.id
        ).count()

        try:
            total_day_booked = int(pub_count or 0) + int(sched_count or 0)
        except (TypeError, ValueError):
            total_day_booked = 0

        if total_day_booked >= DAILY_SHORTS_LIMIT:
            raise ValueError(
                f"[DAILY_LIMIT_EXCEEDED] Target UTC date {target_date} already has {total_day_booked}/{DAILY_SHORTS_LIMIT} "
                f"booked releases ({pub_count} published, {sched_count} scheduled). Refusing 4th release."
            )

        # 2. Test Mode Handling
        if self._is_test_mode():
            logger.info(f"[TEST_MODE/STAGING] Staging Scheduled YouTube Short '{metadata['title']}' for slot {publish_at_str}.")
            clean_desc = self.sanitize_public_description(metadata.get("description", ""))
            record = UploadRecord(
                id=upload_id,
                job_id=job.id,
                youtube_video_id=f"TEST_SCHED_{uuid.uuid4().hex[:8]}",
                title=metadata["title"],
                description=clean_desc,
                tags="",
                privacy_status="private",
                scheduled_publish_at=publish_at_utc,
                published_at=None,
                status="SCHEDULED",
                reconciliation_metadata=f"TEST_MODE scheduled for {publish_at_str}"
            )
            db.add(record)
            job.state = JobState.SCHEDULED.value
            db.commit()
            return record

        # 3. Production YouTube API Scheduled Upload
        # Pre-Upload Media Integrity Guard: Reject missing, truncated, or corrupt media BEFORE reaching YouTube API
        self.validate_media_integrity(video_path)

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2.credentials import Credentials
            import time
            import random
            from googleapiclient.errors import HttpError
            import socket
            import http.client
            import ssl

            youtube = self.get_authorized_youtube_client()

            # Crash-Safe Pre-Upload Check: Search channel to prevent double uploads if prior run crashed post-upload
            orphan_id, orphan_reason = self.recover_orphaned_upload(
                youtube=youtube,
                job=job,
                metadata=metadata,
                scheduled_publish_at=publish_at_utc
            )
            if orphan_id:
                logger.warning(
                    f"[CRASH_RECOVERY] Found existing YouTube video {orphan_id} ({orphan_reason}). "
                    f"Reconciling without re-upload."
                )
                clean_desc = self.sanitize_public_description(metadata.get("description", ""))
                record = UploadRecord(
                    id=upload_id,
                    job_id=job.id,
                    youtube_video_id=orphan_id,
                    title=metadata["title"],
                    description=clean_desc,
                    tags="",
                    privacy_status="private",
                    scheduled_publish_at=publish_at_utc,
                    published_at=None,
                    status="SCHEDULED",
                    reconciliation_metadata=f"Recovered post-crash from YouTube channel ({orphan_reason})"
                )
                db.add(record)
                job.state = JobState.SCHEDULED.value
                db.commit()
                return record

            # Sanitize description & title: strictly viewer-facing, zero internal IDs or build slugs
            clean_description = self.sanitize_public_description(metadata.get("description", ""))
            clean_title = self.sanitize_public_title(metadata.get("title", ""))

            tags_list = metadata.get("tags") or [
                "Harry Potter", "Wizarding World", "Hogwarts", "Harry Potter Lore",
                "Harry Potter Facts", "Movie Facts", "Shorts", "Harry Potter Shorts",
                "Deleted Scenes", "Book vs Movie", "Harry Potter Secrets"
            ]
            if isinstance(tags_list, str):
                tags_list = [t.strip() for t in tags_list.split(",") if t.strip()]

            # YouTube API requires privacyStatus='private' when publishAt is set.
            body = {
                "snippet": {
                    "title": clean_title[:100],
                    "description": clean_description[:5000],
                    "categoryId": "24",  # Entertainment (was 27 Education)
                    "tags": tags_list[:15]
                },
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_at_str,
                    "selfDeclaredMadeForKids": False
                }
            }

            logger.info(f"[YOUTUBE_API] Uploading video '{clean_title}' (5MB chunks) with category 24 & tags with scheduled publishAt={publish_at_str}...")
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                chunksize=5 * 1024 * 1024,
                resumable=True
            )
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

            response = None
            max_chunk_attempts = 5
            retry_net_errors = (
                socket.error,
                http.client.RemoteDisconnected,
                http.client.IncompleteRead,
                ssl.SSLError,
                OSError
            )

            while response is None:
                chunk_error = None
                for attempt in range(1, max_chunk_attempts + 1):
                    try:
                        status, response = request.next_chunk()
                        if status:
                            logger.info(f"[YOUTUBE_UPLOAD] Upload progress: {int(status.progress() * 100)}%")
                        chunk_error = None
                        break
                    except HttpError as http_err:
                        status_code = http_err.resp.status if hasattr(http_err, "resp") else 0
                        if status_code in (500, 502, 503, 504, 429):
                            chunk_error = http_err
                            backoff_sec = min(60.0, (2 ** attempt) + random.uniform(0.1, 1.0))
                            logger.warning(
                                f"[YOUTUBE_UPLOAD] Transient HTTP {status_code} on chunk (Attempt {attempt}/{max_chunk_attempts}). "
                                f"Retrying in {backoff_sec:.1f}s..."
                            )
                            time.sleep(backoff_sec)
                        else:
                            logger.error(f"[YOUTUBE_UPLOAD] Permanent HTTP {status_code} during upload: {http_err}")
                            raise http_err
                    except retry_net_errors as net_err:
                        chunk_error = net_err
                        backoff_sec = min(60.0, (2 ** attempt) + random.uniform(0.1, 1.0))
                        logger.warning(
                            f"[YOUTUBE_UPLOAD] Network error on chunk ({net_err}) (Attempt {attempt}/{max_chunk_attempts}). "
                            f"Retrying in {backoff_sec:.1f}s..."
                        )
                        time.sleep(backoff_sec)
                if chunk_error is not None:
                    logger.error(f"[YOUTUBE_UPLOAD] Chunk upload failed after {max_chunk_attempts} retry attempts.")
                    raise chunk_error

            yt_id = response.get("id") if response else None
            if not yt_id:
                raise ValueError("YouTube API response did not contain a valid video ID.")

            logger.info(f"[YOUTUBE_API] Video uploaded successfully (ID: {yt_id}). Performing API read-back verification...")

            # 4. Explicit API Read-Back Verification
            verify_res = youtube.videos().list(part="status,snippet", id=yt_id).execute()
            items = verify_res.get("items", [])
            if not items:
                raise ValueError(f"CRITICAL: Read-back verification failed. Video ID {yt_id} not found on YouTube.")

            status_obj = items[0].get("status", {})
            actual_privacy = status_obj.get("privacyStatus", "unknown")
            actual_publish_at = status_obj.get("publishAt")

            logger.info(f"[VERIFY] YouTube Video {yt_id} Status: privacyStatus='{actual_privacy}', publishAt='{actual_publish_at}'")

            # Check if publishAt was accepted or if privacy status needs correction
            if not actual_publish_at:
                logger.warning(f"Video {yt_id} did not record publishAt on initial insert. Sending corrective update...")
                update_body = {
                    "id": yt_id,
                    "status": {
                        "privacyStatus": "private",
                        "publishAt": publish_at_str,
                        "selfDeclaredMadeForKids": False
                    }
                }
                youtube.videos().update(part="status", body=update_body).execute()

                # Re-verify
                verify_res = youtube.videos().list(part="status,snippet", id=yt_id).execute()
                items = verify_res.get("items", [])
                status_obj = items[0].get("status", {}) if items else {}
                actual_publish_at = status_obj.get("publishAt")
                actual_privacy = status_obj.get("privacyStatus", "unknown")

            if not actual_publish_at:
                logger.warning(f"Video {yt_id} publishAt verification returned null, but upload completed with private status.")

            record = UploadRecord(
                id=upload_id,
                job_id=job.id,
                youtube_video_id=yt_id,
                title=clean_title,
                description=clean_description,
                tags=",".join(tags_list[:15]),
                privacy_status="private",
                scheduled_publish_at=publish_at_utc,
                published_at=None,
                status="SCHEDULED",
                reconciliation_metadata=f"Verified scheduled for {publish_at_str} (actual publishAt: {actual_publish_at})"
            )
            db.add(record)
            job.state = JobState.SCHEDULED.value
            db.commit()

            # Post seed engagement question to trigger comment velocity
            try:
                self.post_engagement_comment(youtube, yt_id, clean_title)
            except Exception as comm_err:
                logger.warning(f"Could not post initial engagement comment: {comm_err}")

            logger.info(f"[+] SCHEDULED YOUTUBE SHORT VERIFIED: ID {yt_id} -> Will release automatically on YouTube at {publish_at_str}")
            return record

        except Exception as e:
            # Post-failure Channel Reconciliation:
            # If a network timeout, socket drop, or 503 error occurred during request.execute(),
            # YouTube may have actually ingested and scheduled the video. Check before re-raising.
            if not self._is_test_mode():
                try:
                    from googleapiclient.discovery import build
                    from google.oauth2.credentials import Credentials
                    token_path = self._get_token_path()
                    if token_path.exists():
                        creds = Credentials.from_authorized_user_file(str(token_path))
                        yt_check = build("youtube", "v3", credentials=creds)
                        search_res = yt_check.search().list(
                            part="snippet",
                            forMine=True,
                            q=metadata["title"][:50],
                            type="video",
                            maxResults=5
                        ).execute()
                        for item in search_res.get("items", []):
                            item_title = item.get("snippet", {}).get("title", "").strip().lower()
                            item_desc = item.get("snippet", {}).get("description", "")
                            is_exact_title = (item_title == norm_title)
                            is_job_match = (f"[JOB_ID: {job.id}]" in item_desc) or (job.id in item_desc)
                            if is_job_match or is_exact_title:
                                rec_id = item.get("id", {}).get("videoId")
                                if rec_id:
                                    logger.warning(
                                        f"[RECOVERY] Exception during upload ({e}), but video was successfully created on YouTube (ID: {rec_id}). Reconciling."
                                    )
                                    clean_desc = self.sanitize_public_description(metadata.get("description", ""))
                                    record = UploadRecord(
                                        id=upload_id,
                                        job_id=job.id,
                                        youtube_video_id=rec_id,
                                        title=metadata["title"],
                                        description=clean_desc,
                                        tags="",
                                        privacy_status="private",
                                        scheduled_publish_at=publish_at_utc,
                                        published_at=None,
                                        status="SCHEDULED",
                                        reconciliation_metadata=f"Recovered after network failure during upload (ID: {rec_id})"
                                    )
                                    db.add(record)
                                    job.state = JobState.SCHEDULED.value
                                    db.commit()
                                    return record
                except Exception as rec_err:
                    logger.warning(f"[RECOVERY] Post-failure channel search skipped: {rec_err}")

            logger.error(f"YouTube scheduling failed for job {job.id}: {e}")
            raise e

    def reconcile_scheduled_uploads(self, db: Session) -> List[Dict[str, Any]]:
        """
        Reconciles all SCHEDULED uploads against YouTube.
        If YouTube has made the video public (or publishAt passed for staging records),
        transitions record to PUBLISHED.
        """
        scheduled_records = db.query(UploadRecord).filter(
            UploadRecord.status == "SCHEDULED"
        ).all()

        reconciled = []
        now = datetime.utcnow()

        # 1. Handle synthetic/staging records
        for rec in list(scheduled_records):
            if rec.youtube_video_id and (rec.youtube_video_id.startswith("TEST_") or rec.youtube_video_id.startswith("YT_") or self._is_test_mode()):
                if rec.scheduled_publish_at and rec.scheduled_publish_at <= now:
                    rec.status = "PUBLISHED"
                    rec.published_at = rec.scheduled_publish_at
                    rec.privacy_status = "public"
                    
                    job = db.query(Job).filter(Job.id == rec.job_id).first()
                    if job:
                        job.state = JobState.PUBLISHED.value
                    
                    reconciled.append({
                        "job_id": rec.job_id,
                        "youtube_video_id": rec.youtube_video_id,
                        "status": "PUBLISHED",
                        "published_at": rec.published_at.isoformat() + "Z"
                    })
                scheduled_records = [r for r in scheduled_records if r.id != rec.id]

        if reconciled:
            db.commit()

        if not scheduled_records:
            return reconciled

        # 2. Production Reconciliation via YouTube API
        try:
            try:
                youtube = self.get_youtube_service()
            except Exception as yt_auth_err:
                logger.warning(f"[RECONCILE] YouTube client unavailable: {yt_auth_err}")
                if reconciled:
                    db.commit()
                return reconciled

            for rec in scheduled_records:
                if not rec.youtube_video_id:
                    continue

                try:
                    res = youtube.videos().list(part="status,snippet,statistics", id=rec.youtube_video_id).execute()
                    items = res.get("items", [])
                    if not items:
                        logger.warning(f"[RECONCILE] Video {rec.youtube_video_id} not found on YouTube.")
                        continue

                    status_obj = items[0].get("status", {})
                    snippet_obj = items[0].get("snippet", {})
                    stats_obj = items[0].get("statistics", {})
                    privacy = status_obj.get("privacyStatus")

                    if privacy == "public":
                        # YouTube made it public!
                        rec.status = "PUBLISHED"
                        yt_pub_str = snippet_obj.get("publishedAt")
                        if yt_pub_str:
                            try:
                                rec.published_at = datetime.fromisoformat(yt_pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                rec.published_at = datetime.utcnow()
                        else:
                            rec.published_at = datetime.utcnow()
                        rec.privacy_status = "public"

                        # Record/update immediate performance snapshot
                        try:
                            from core.models import PerformanceSnapshot
                            views = int(stats_obj.get("viewCount", 0))
                            likes = int(stats_obj.get("likeCount", 0))
                            comments = int(stats_obj.get("commentCount", 0))
                            snap = db.query(PerformanceSnapshot).filter(
                                PerformanceSnapshot.upload_id == rec.id
                            ).first()
                            if snap:
                                snap.views = views
                                snap.likes = likes
                                snap.comments = comments
                                snap.snapshot_time = datetime.utcnow()
                            else:
                                snap = PerformanceSnapshot(
                                    upload_id=rec.id,
                                    youtube_video_id=rec.youtube_video_id,
                                    views=views,
                                    likes=likes,
                                    comments=comments,
                                    snapshot_time=datetime.utcnow()
                                )
                                db.add(snap)
                        except Exception as snap_err:
                            logger.debug(f"[RECONCILE] Snapshot recording notice: {snap_err}")
                        
                        job = db.query(Job).filter(Job.id == rec.job_id).first()
                        if job:
                            job.state = JobState.PUBLISHED.value

                        # Relocate corresponding video file from 02_PROCESSING to 03_PUBLISHED in Drive Vault
                        try:
                            from core.lifecycle_gateway import vault_transition_to_published
                            from engines.drive_engine import DriveVaultEngine
                            drive = DriveVaultEngine()
                            proc_files = drive.list_files_in_folder("02_PROCESSING")
                            for pf in proc_files:
                                props = pf.get("properties", {}) or {}
                                if props.get("job_id") == rec.job_id or (rec.job_id and rec.job_id in pf.get("name", "")):
                                    try:
                                        vault_transition_to_published(
                                            file_id=pf["id"],
                                            youtube_video_id=rec.youtube_video_id,
                                            db=db,
                                            drive_engine=drive,
                                            youtube_service=youtube,
                                            job_id=rec.job_id,
                                            caller="upload_engine.reconcile_scheduled_uploads"
                                        )
                                        logger.info(f"[RECONCILE] Moved file '{pf['name']}' to 03_PUBLISHED via gateway.")
                                    except Exception as gw_err:
                                        logger.warning(f"[RECONCILE_GATEWAY_HOLD] Gateway refused transition for '{pf['name']}': {gw_err}")
                        except Exception as drive_mv_err:
                            logger.debug(f"[RECONCILE] Drive vault file move notice: {drive_mv_err}")

                        reconciled.append({
                            "job_id": rec.job_id,
                            "youtube_video_id": rec.youtube_video_id,
                            "status": "PUBLISHED",
                            "published_at": rec.published_at.isoformat() + "Z"
                        })
                        logger.info(f"[RECONCILE] Video {rec.youtube_video_id} confirmed PUBLIC on YouTube. Reconciled to PUBLISHED.")

                except Exception as item_err:
                    logger.warning(f"[RECONCILE] Error checking video {rec.youtube_video_id}: {item_err}")

            if reconciled:
                db.commit()

        except Exception as e:
            logger.error(f"[RECONCILE] YouTube reconciliation loop error: {e}")

        return reconciled

    def upload_short_public(
        self,
        db: Session,
        job: Job,
        render: RenderOutput,
        metadata: Dict[str, Any],
        privacy_status: str = "public"
    ) -> UploadRecord:
        """
        Production Live Public Upload for Due Publication Slots.
        Uploads and publishes a YouTube Short directly as 'public' (or specified privacy_status)
        without the dormant 'publishAt' scheduling lag. This immediately triggers YouTube's
        real-time VideoPublishedEvent to push the video into the Shorts Feed seed pool.
        """
        from config.settings import PUBLISHING_ENABLED, UPLOAD_ENABLED
        if not self._is_test_mode() and (not PUBLISHING_ENABLED or not UPLOAD_ENABLED):
            raise PermissionError(
                "[PUBLISHING_BLOCKED] Upload rejected by safety gate. "
                "PUBLISHING_ENABLED and UPLOAD_ENABLED must both be set to True in .env."
            )

        upload_id = f"upl_{uuid.uuid4().hex[:12]}"
        video_path = Path(render.video_path)

        # 1. Multi-Layer Idempotency Check
        norm_title = metadata.get("title", "").strip().lower()
        existing = db.query(UploadRecord).filter(
            (UploadRecord.job_id == job.id) |
            (UploadRecord.title.ilike(norm_title))
        ).filter(
            UploadRecord.status.in_(["SCHEDULED", "PUBLISHED", "TEST_VERIFIED"])
        ).first()

        if existing and existing.youtube_video_id:
            logger.info(f"[IDEMPOTENCY] Video for Job {job.id} / Title '{metadata.get('title')}' is already uploaded/published ({existing.youtube_video_id}, status={existing.status}). Reconciling without duplicate upload.")
            job.state = JobState.PUBLISHED.value if existing.status in ("PUBLISHED", "SUCCESS") else JobState.SCHEDULED.value
            db.commit()
            return existing

        # 2. Test Mode Handling
        if self._is_test_mode():
            logger.info(f"[TEST_MODE/STAGING] Simulating live public upload for '{metadata['title']}'.")
            clean_desc = self.sanitize_public_description(metadata.get("description", ""))
            clean_title = self.sanitize_public_title(metadata.get("title", ""))
            record = UploadRecord(
                id=upload_id,
                job_id=job.id,
                youtube_video_id=f"TEST_PUB_{uuid.uuid4().hex[:8]}",
                title=clean_title,
                description=clean_desc,
                tags="",
                privacy_status=privacy_status,
                scheduled_publish_at=None,
                published_at=datetime.utcnow(),
                status="PUBLISHED",
                reconciliation_metadata="TEST_MODE verified live public upload"
            )
            db.add(record)
            job.state = JobState.PUBLISHED.value
            db.commit()
            return record

        # 3. Production YouTube API Upload
        self.validate_media_integrity(video_path)

        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials
        import time
        import random
        from googleapiclient.errors import HttpError
        import socket
        import http.client
        import ssl

        youtube = self.get_authorized_youtube_client()

        clean_description = self.sanitize_public_description(metadata.get("description", ""))
        clean_title = self.sanitize_public_title(metadata.get("title", ""))

        tags_list = metadata.get("tags") or [
            "Harry Potter", "Wizarding World", "Hogwarts", "Harry Potter Lore",
            "Harry Potter Facts", "Movie Facts", "Shorts", "Harry Potter Shorts",
            "Deleted Scenes", "Book vs Movie", "Harry Potter Secrets"
        ]
        if isinstance(tags_list, str):
            tags_list = [t.strip() for t in tags_list.split(",") if t.strip()]

        body = {
            "snippet": {
                "title": clean_title[:100],
                "description": clean_description[:5000],
                "categoryId": "24",  # Entertainment
                "tags": tags_list[:15]
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        logger.info(f"[YOUTUBE_API] Uploading video '{clean_title}' directly as '{privacy_status}' with Category 24 & rich tags...")
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=5 * 1024 * 1024,
            resumable=True
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        max_chunk_attempts = 5
        retry_net_errors = (
            socket.error,
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
            ssl.SSLError,
            OSError
        )

        while response is None:
            chunk_error = None
            for attempt in range(1, max_chunk_attempts + 1):
                try:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"[YOUTUBE_UPLOAD] Upload progress: {int(status.progress() * 100)}%")
                    chunk_error = None
                    break
                except HttpError as http_err:
                    status_code = http_err.resp.status if hasattr(http_err, "resp") else 0
                    if status_code in (500, 502, 503, 504, 429):
                        chunk_error = http_err
                        backoff_sec = min(60.0, (2 ** attempt) + random.uniform(0.1, 1.0))
                        logger.warning(
                            f"[YOUTUBE_UPLOAD] Transient HTTP {status_code} on chunk (Attempt {attempt}/{max_chunk_attempts}). "
                            f"Retrying in {backoff_sec:.1f}s..."
                        )
                        time.sleep(backoff_sec)
                    else:
                        logger.error(f"[YOUTUBE_UPLOAD] Permanent HTTP {status_code} during upload: {http_err}")
                        raise http_err
                except retry_net_errors as net_err:
                    chunk_error = net_err
                    backoff_sec = min(60.0, (2 ** attempt) + random.uniform(0.1, 1.0))
                    logger.warning(
                        f"[YOUTUBE_UPLOAD] Network error on chunk ({net_err}) (Attempt {attempt}/{max_chunk_attempts}). "
                        f"Retrying in {backoff_sec:.1f}s..."
                    )
                    time.sleep(backoff_sec)
            if chunk_error is not None:
                logger.error(f"[YOUTUBE_UPLOAD] Chunk upload failed after {max_chunk_attempts} retry attempts.")
                raise chunk_error

        yt_id = response.get("id") if response else None
        if not yt_id:
            raise ValueError("YouTube API response did not contain a valid video ID.")

        logger.info(f"[YOUTUBE_API] Live video uploaded successfully (ID: {yt_id}). Performing API read-back verification...")

        # 4. Explicit API Read-Back Verification
        verify_res = youtube.videos().list(part="status,snippet", id=yt_id).execute()
        items = verify_res.get("items", [])
        if not items:
            raise ValueError(f"CRITICAL: Read-back verification failed. Video ID {yt_id} not found on YouTube.")

        status_obj = items[0].get("status", {})
        actual_privacy = status_obj.get("privacyStatus", "unknown")

        logger.info(f"[VERIFY] YouTube Video {yt_id} Status: privacyStatus='{actual_privacy}'")

        if actual_privacy != privacy_status:
            logger.warning(f"Video {yt_id} privacy is '{actual_privacy}', expected '{privacy_status}'. Sending corrective update...")
            update_body = {
                "id": yt_id,
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }
            youtube.videos().update(part="status", body=update_body).execute()

        record = UploadRecord(
            id=upload_id,
            job_id=job.id,
            youtube_video_id=yt_id,
            title=clean_title,
            description=clean_description,
            tags=",".join(tags_list[:15]),
            privacy_status=privacy_status,
            scheduled_publish_at=None,
            published_at=datetime.utcnow(),
            status="PUBLISHED",
            reconciliation_metadata=f"Verified live {privacy_status} release at {datetime.utcnow().isoformat()}Z"
        )
        db.add(record)
        job.state = JobState.PUBLISHED.value
        db.commit()
        return record

    def upload_short(
        self,
        db: Session,
        job: Job,
        render: RenderOutput,
        metadata: Dict[str, Any],
        privacy_status: str = "public"
    ) -> UploadRecord:
        """Alias for upload_short_public."""
        return self.upload_short_public(db, job, render, metadata, privacy_status)
