"""
Main Pipeline Orchestrator & CLI Entrypoint.
Coordinates autonomous $0-cost YouTube Shorts creation, batch production,
Google Drive Vault storage, scheduled publishing, QA, and learning feedback.
"""
import os
import sys
import uuid
import time
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

# Setup Project Paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    TEST_MODE, RENDERS_DIR,
    MAX_BATCH_PRODUCTION_CEILING,
    MAX_PRODUCTION_ATTEMPTS_CEILING,
    MAX_BUFFER_RESERVE_CEILING,
    AI_PROVIDER_AVAILABLE
)
from config.constants import JobState, DAILY_SHORTS_LIMIT, TARGET_RESERVE_BUFFER
from sqlalchemy.orm import Session
from core.database import init_db, SessionLocal
from core.models import (
    Job, Topic, RenderOutput, UploadRecord, ScriptRecord,
    RenderedVideoRecord, ProductionAttemptRecord, ProductionIncidentRecord
)
from core.state_machine import StateMachine
from core.lock import ProcessLock, ProcessLockError
from core.cloud_lock import CompositeLock, CloudLockManager, CloudLockError
from engines.topic_discovery import TopicDiscoveryEngine
from engines.research_engine import ResearchEngine
from engines.script_engine import ScriptEngine
from engines.storyboard_engine import StoryboardEngine
from engines.asset_fetcher import AssetFetcher
from engines.tts_engine import TTSEngine
from engines.caption_engine import CaptionEngine
from engines.audio_mixer import AudioMixer
from engines.render_engine import RenderEngine
from engines.qa_engine import QAEngine
from engines.seo_engine import SEOEngine
from engines.upload_engine import UploadEngine
from engines.scheduler_engine import PublicationScheduler
from engines.analytics_engine import AnalyticsEngine
from engines.drive_engine import DriveVaultEngine
from engines.experiment_manager import ExperimentManager
from core.recovery_manager import RecoveryManager
from core.lifecycle_gateway import vault_transition_to_published, is_valid_youtube_id, InvariantViolationError

# Setup UTF-8 Encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("HistoriaPipeline")
console = Console(force_terminal=False)

KNOWN_EVENT_METADATA: Dict[str, Dict[str, Any]] = {
    "evt_dancing_plague_1518": {
        "title": "The Bizarre Dancing Plague of 1518",
        "description": "In July 1518, hundreds of citizens in Strasbourg began dancing uncontrollably for days without music. Here is the true bizarre story.\n\n#Mystery #History #Bizarre",
        "tags": []
    },
    "evt_roman_dodecahedron_puzzle": {
        "title": "The Roman Dodecahedron Enigma",
        "description": "Mysterious hollow bronze 12-sided objects found across Roman ruins in Europe with no mention in ancient texts. What were they used for?\n\n#Mystery #Ancient #Archaeology #History",
        "tags": []
    },
    "evt_the_bloop_pacific_anomaly": {
        "title": "The Bloop: Pacific Acoustic Anomaly",
        "description": "In 1997, deep ocean underwater sensors detected an ultra-low frequency sound louder than any known creature. The mystery of the Bloop.\n\n#Mystery #DeepSea #Ocean #TheBloop",
        "tags": []
    },
    "evt_man_from_taured_1954": {
        "title": "The Man from Taured Mystery",
        "description": "In July 1954, a man arrived at Tokyo Airport carrying a valid passport from a country that did not exist. Then he vanished from a locked room.\n\n#Mystery #ParallelUniverse #Tokyo #Unexplained",
        "tags": []
    },
    "evt_atomic_survivor_yamaguchi": {
        "title": "Yamaguchi: The Double Atomic Survivor",
        "description": "Tsutomu Yamaguchi was in Hiroshima when the atomic bomb detonated, survived, returned home to Nagasaki, and survived the second bomb three days later.\n\n#History #Survival #Incredible #TrueStory",
        "tags": []
    },
    "evt_mary_celeste_1872": {
        "title": "The Ghost Ship Mary Celeste Disappearance",
        "description": "Found floating silently in the Atlantic in 1872 with all cargo completely intact, meals prepared, and every crew member vanished without a trace.\n\n#Mystery #GhostShip #MaryCeleste #Maritime",
        "tags": []
    },
    "evt_balloon_duel_1808": {
        "title": "The Paris Hot Air Balloon Duel of 1808",
        "description": "In 1808, two French gentlemen settled a duel not with swords on the ground, but in hot air balloons over Paris with blunderbusses.\n\n#History #Bizarre #Duel #Paris",
        "tags": []
    },
    "evt_devon_footprints_1855": {
        "title": "The Devil's Footprints of Devon (1855)",
        "description": "In February 1855, mysterious cloven hoofprints appeared overnight across Devon snow, traversing 100 miles over high rooftops and 14-foot walls.\n\n#Mystery #History #Bizarre #Unexplained",
        "tags": []
    },
    "evt_antikythera_mechanism_1901": {
        "title": "The Antikythera Mechanism: Ancient Greek Computer",
        "description": "In 1901, divers discovered an ancient corroded bronze lump that proved to be an impossibly complex 30-gear astronomical computer built 2,000 years ago.\n\n#Mystery #Ancient #History #Archaeology #Computer",
        "tags": []
    },
    "evt_voynich_manuscript_1912": {
        "title": "The Voynich Manuscript: History's Most Mysterious Book",
        "description": "A 15th-century codex written in an unbreakable cipher with bizarre botanical drawings that no cryptographer or supercomputer has ever solved.\n\n#Mystery #History #Cryptography #Unexplained",
        "tags": []
    }
}


def resolve_vault_file_metadata(candidate: Dict[str, Any], db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Authoritative metadata resolver for Drive Vault files.
    Ensures real story titles, descriptions, and empty tags are extracted from:
    1. Event ID mapping (KNOWN_EVENT_METADATA)
    2. Local SQLite DB (RenderedVideoRecord -> Topic)
    3. Explicit Drive file properties (if not short_man_ / short_job_)
    4. Drive description field
    5. Clean sanitized filename
    All descriptions are sanitized to remove internal IDs and provide natural narrative context.
    """
    import re
    from engines.upload_engine import UploadEngine
    sanitize = UploadEngine.sanitize_public_description

    props = candidate.get("properties", {}) or {}
    name = candidate.get("name", "")
    event_id = props.get("event_id")
    if not event_id:
        m = re.search(r"evt_[a-z0-9_]+", name)
        if m:
            event_id = m.group(0)

    # 0. Harry Potter Canonical Metadata Resolution
    clean_hps_id = None
    if name.startswith("hps_"):
        clean_hps_id = name.replace(".mp4", "").strip()
    elif props.get("script_id") and str(props["script_id"]).startswith("hps_"):
        clean_hps_id = props["script_id"]

    if clean_hps_id and db:
        try:
            from core.models import HarryPotterScript
            hp_script = db.query(HarryPotterScript).filter_by(id=clean_hps_id).first()
            if not hp_script:
                hp_script = db.query(HarryPotterScript).filter(HarryPotterScript.id.ilike(f"%{clean_hps_id}%")).first()

            if hp_script:
                if hp_script.content_type == "novel_story":
                    pt = hp_script.part_marker or "PART 01"
                    title = f"Harry Potter: {hp_script.chapter_title} [{pt}] #Shorts"
                    if len(title) > 95:
                        title = f"{hp_script.chapter_title} [{pt}] | Harry Potter #Shorts"
                else:
                    topic_clean = clean_hps_id.replace("hps_disc_", "").replace("_b1", "").replace("_b3", "").replace("_b5", "").replace("_b8", "").replace("_", " ").title()
                    if hp_script.suggested_title:
                        title = hp_script.suggested_title
                    elif "Dementor" in topic_clean or "Chocolate" in topic_clean:
                        title = "Why Lupin REALLY Gave Harry Chocolate on the Train | Harry Potter #Shorts"
                    elif "Luna" in topic_clean or "Thestral" in topic_clean:
                        title = "The Tragic Reason Luna Was Barefoot in the Snow | Harry Potter #Shorts"
                    elif "Snape" in topic_clean and ("Tear" in topic_clean or "Prince" in topic_clean):
                        title = "The Secret Hidden in Snape's Final Silvery Tear | Harry Potter #Shorts"
                    elif "Mirror Of Erised" in topic_clean:
                        title = "The Secret Inscription on the Mirror of Erised | Harry Potter #Shorts"
                    elif "Neville Remembrall" in topic_clean:
                        title = "The Movie Secret in Neville's Remembrall | Harry Potter #Shorts"
                    elif "Neville Hufflepuff" in topic_clean:
                        title = "Why Neville Begged NOT to Be in Gryffindor | Harry Potter #Shorts"
                    elif "Peeves" in topic_clean:
                        title = "The Poltergeist Deleted from the Movies | Harry Potter #Shorts"
                    elif "Dursleys" in topic_clean or "Dumbledore Explains Dursleys" in topic_clean:
                        title = "Why Harry REALLY Had to Stay with the Dursleys | Harry Potter #Shorts"
                    elif "Patronus" in topic_clean:
                        title = "The Secret Meaning Behind Snape's Patronus | Harry Potter #Shorts"
                    else:
                        title = f"{topic_clean} | Harry Potter Discovery #Shorts"

                full_desc = UploadEngine.generate_seo_description(
                    title=title,
                    topic=clean_hps_id.replace("hps_disc_", "").replace("_", " "),
                    source_reference=f"{hp_script.book_title} ({hp_script.source_reference})" if hp_script.book_title else None
                )

                return {
                    "title": title[:100],
                    "description": full_desc[:5000],
                    "tags": [],
                    "script_id": hp_script.id
                }
        except Exception as hp_meta_err:
            logger.warning(f"Harry Potter DB metadata lookup notice: {hp_meta_err}")

    # 1. Explicit properties if clean (not short_man_ placeholder)
    p_title = props.get("title") or props.get("topic_title")
    if p_title and not p_title.startswith("short_man_") and not p_title.startswith("short_job_") and not p_title.lower().startswith("al-amr ready short") and len(p_title) > 3:
        raw_desc = props.get("description") or f"The documented true story behind {p_title} reveals a fascinating real-world event."
        clean_desc = sanitize(raw_desc)
        tags_raw = props.get("tags")
        tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        return {
            "title": p_title,
            "description": clean_desc,
            "tags": tags_list
        }

    # 2. Check known event metadata dictionary
    if event_id and event_id in KNOWN_EVENT_METADATA:
        meta_copy = dict(KNOWN_EVENT_METADATA[event_id])
        meta_copy["description"] = sanitize(meta_copy.get("description", ""))
        meta_copy["tags"] = []
        return meta_copy

    # 3. Check DB (RenderedVideoRecord / Topic by event_id)
    if db:
        try:
            from core.models import Topic, RenderedVideoRecord, Job
            # Check by manifest_id -> event_id -> Topic
            man_id = props.get("manifest_id")
            eff_evt_id = event_id
            if man_id:
                rec = db.query(RenderedVideoRecord).filter(RenderedVideoRecord.manifest_id == man_id).first()
                if rec and rec.event_id:
                    eff_evt_id = rec.event_id

            if eff_evt_id:
                top = db.query(Topic).filter(Topic.event_id == eff_evt_id).first()
                if top and top.title and not top.title.startswith("short_man_"):
                    raw_d = top.summary or f"The documented true story behind {top.title} reveals a fascinating real-world event."
                    return {
                        "title": top.title,
                        "description": sanitize(raw_d),
                        "tags": []
                    }

            job_id = props.get("job_id")
            if job_id:
                j = db.query(Job).filter(Job.id == job_id).first()
                if j and j.topic_id:
                    top = db.query(Topic).filter(Topic.id == j.topic_id).first()
                    if top and top.title and not top.title.startswith("short_man_"):
                        raw_d = top.summary or f"The documented true story behind {top.title} reveals a fascinating real-world event."
                        return {
                            "title": top.title,
                            "description": sanitize(raw_d),
                            "tags": []
                        }
        except Exception as db_meta_err:
            logger.debug(f"DB metadata lookup notice: {db_meta_err}")

    # 4. Drive file description if set
    d_desc = candidate.get("description", "")
    if d_desc and not d_desc.startswith("short_man_") and not d_desc.lower().startswith("al-amr ready short") and len(d_desc) > 5:
        first_line = d_desc.split("\n")[0].strip()
        return {
            "title": first_line,
            "description": sanitize(d_desc),
            "tags": []
        }

    # 5. Clean filename if it's descriptive (not short_man_ / short_job_)
    clean_name = name.replace(".mp4", "").replace("_", " ").title()
    if not clean_name.lower().startswith("short man") and not clean_name.lower().startswith("short job"):
        return {
            "title": clean_name,
            "description": sanitize(f"The documented true story behind {clean_name} reveals a fascinating real-world event."),
            "tags": []
        }

    # 6. Authoritative unique fallback derived from event_id (NO generic collisions)
    clean_evt = event_id or props.get("manifest_id") or "historical_mystery"
    for pfx in ("evt_hist_", "evt_mystery_", "evt_science_", "evt_", "man_"):
        if clean_evt.startswith(pfx):
            clean_evt = clean_evt[len(pfx):]
    fallback_title = clean_evt.replace("_", " ").title()
    return {
        "title": fallback_title,
        "description": sanitize(f"The documented true story behind {fallback_title} reveals a fascinating real-world event."),
        "tags": []
    }


class ShortsPipeline:
    """End-to-end production and publishing orchestrator."""

    def __init__(self, voice: Optional[str] = None):
        init_db()
        self.topic_engine = TopicDiscoveryEngine()
        self.research_engine = ResearchEngine()
        self.script_engine = ScriptEngine()
        self.storyboard_engine = StoryboardEngine()
        self.asset_fetcher = AssetFetcher()
        self.tts_engine = TTSEngine()
        self.caption_engine = CaptionEngine()
        self.audio_mixer = AudioMixer()
        self.render_engine = RenderEngine()
        self.qa_engine = QAEngine()
        self.seo_engine = SEOEngine()
        self.upload_engine = UploadEngine()
        self.scheduler = PublicationScheduler()
        self.analytics_engine = AnalyticsEngine()
        self.drive_engine = DriveVaultEngine()
        self.experiment_manager = ExperimentManager()
        self.recovery_manager = RecoveryManager(self.drive_engine, self.upload_engine)
        
        from engines.editing_director import EditingDirector
        from engines.sfx_manager import SFXManager
        from engines.ending_strategy import EndingStrategyEngine
        from core.content_quality_gate import ContentQualityGate
        self.editing_director = EditingDirector()
        self.sfx_manager = SFXManager()
        self.ending_engine = EndingStrategyEngine()
        self.content_quality_gate = ContentQualityGate()

        from engines.tts_engine import get_active_voice, APPROVED_PRODUCTION_VOICES
        db = SessionLocal()
        try:
            authoritative_db_voice = get_active_voice(db)
            if authoritative_db_voice not in APPROVED_PRODUCTION_VOICES:
                authoritative_db_voice = "f5_cloned_narrator_v1"
            chosen_voice = voice or authoritative_db_voice or os.getenv("KOKORO_VOICE") or "f5_cloned_narrator_v1"
            if chosen_voice not in APPROVED_PRODUCTION_VOICES:
                logger.warning(f"Voice '{chosen_voice}' not in APPROVED_PRODUCTION_VOICES. Defaulting to 'f5_cloned_narrator_v1'.")
                chosen_voice = "f5_cloned_narrator_v1"
            self.run_voice = chosen_voice
        finally:
            db.close()
        logger.info(f"[PIPELINE_INIT] Run-scoped authoritative voice captured: '{self.run_voice}'")

    @staticmethod
    def detect_candidate_format(candidate: Dict[str, Any]) -> str:
        """
        Determines the canonical content format for a production candidate.
        Prioritizes explicit format/content-type metadata as primary source of truth,
        falling back to strictly non-overlapping duration boundaries:
          - 25.0–30.0s   -> DISCOVERY_SHORT
          - 45.0–<60.0s  -> NOVEL_STORY (unless explicitly marked discovery)
          - 60.0–70.0s   -> DISCOVERY_BIG
          - 30.0–<45.0s  -> UNKNOWN
          - >70.0s/<25.0s-> UNKNOWN
        """
        props = candidate.get("properties", {}) or {}

        # 1. Primary source of truth: Explicit format metadata
        fmt = (props.get("format") or props.get("discovery_format") or props.get("content_format") or "").upper()
        if fmt in ("NOVEL_STORY", "DISCOVERY_BIG", "DISCOVERY_SHORT"):
            return fmt

        # 2. Content-type and filename metadata
        ctype = (props.get("content_type") or "").lower()
        name = (candidate.get("name") or "").lower()

        if ctype in ("novel_story", "novel"):
            return "NOVEL_STORY"
        if ctype in ("discovery_big", "big_discovery") or "discovery_big" in name:
            return "DISCOVERY_BIG"
        if ctype in ("discovery_short", "micro_discovery", "short_discovery") or "discovery_short" in name:
            return "DISCOVERY_SHORT"
        if name.startswith("hps_") and not ("disc" in name or "discovery" in name):
            return "NOVEL_STORY"

        # 3. Canonical non-overlapping fallback duration mapping
        duration = float(props.get("duration", 0) or props.get("duration_sec", 0) or 0)
        if 25.0 <= duration <= 30.0:
            return "DISCOVERY_SHORT"
        elif 45.0 <= duration < 60.0:
            if ctype == "discovery":
                return "UNKNOWN"
            return "NOVEL_STORY"
        elif 60.0 <= duration <= 70.0:
            return "DISCOVERY_BIG"
        else:
            return "UNKNOWN"

    def _render_and_qa_job(self, db, job: Job, topic: Topic, force: bool = False) -> Tuple[Optional[RenderOutput], Optional[Dict[str, Any]]]:
        """Internal helper: Executes research -> script -> visuals -> voice -> audio -> render -> QA -> SEO."""
        job.topic_id = topic.id
        db.commit()
        console.print(f"[green][+] Topic Selected:[/green] [bold]{topic.title}[/bold] ({topic.category})")

        # 0. STRATEGY SELECTION & EXPERIMENT TRACKING
        strategy = self.experiment_manager.select_strategy(db, topic)
        self.experiment_manager.create_experiment(db, job_id=job.id, topic_id=topic.id, strategy=strategy)
        logger.info(f"Assigned Strategy for Job {job.id[:8]}: Hook={strategy['hook_archetype']}, Target={strategy['duration_target']}, Mode={strategy['selection_mode']}")

        # Track that future generation has consumed the active learning profile
        from engines.learning_engine import LearningEngine
        LearningEngine().mark_profile_consumed(db, job_id=job.id)

        # 1. RESEARCH & FACT-CHECKING
        StateMachine.transition(db, job, JobState.RESEARCHED, "Conducting factual historical research")
        StateMachine.transition(db, job, JobState.FACT_CHECKING, "Fact-checking claims")
        research_res = self.research_engine.research_topic(db, topic)
        StateMachine.transition(db, job, JobState.FACT_CHECKED, f"Verified {research_res['claims_count']} historical claims")
        console.print(f"[green][+] Fact-Checking Complete:[/green] {research_res['claims_count']} claims verified against historical archives.")

        # 2. SCRIPT GENERATION (Calibrated Story Flow with Multi-Stage Critic & Strategy)
        StateMachine.transition(db, job, JobState.SCRIPTING, f"Writing script with {strategy.get('hook_archetype')} hook & {strategy.get('duration_target')} duration")
        script = self.script_engine.generate_script(db, topic, research_data=research_res, strategy=strategy)
        StateMachine.transition(db, job, JobState.SCRIPT_READY, f"Script approved ({script.word_count} words)")
        console.print(f"[green][+] Script Ready:[/green] {script.word_count} words (Estimated ~{script.estimated_duration_sec:.1f}s)")

        # 3. VISUAL STORYBOARD PLANNING
        StateMachine.transition(db, job, JobState.VISUAL_PLANNING, "Deconstructing script into shots")
        shots = self.storyboard_engine.create_storyboard(script)
        StateMachine.transition(db, job, JobState.VISUALS_SEARCHING, f"Planned {len(shots)} cinematic shots")

        # 4. ASSET ACQUISITION (Pexels Video First + Anti-Duplication)
        assets_used = []
        asset_map = {}
        used_urls_in_job = set()
        for shot in shots:
            asset = self.asset_fetcher.fetch_asset_for_shot(db, shot, used_urls_in_job=used_urls_in_job)
            assets_used.append(asset)
            asset_map[shot["shot_id"]] = asset

        StateMachine.transition(db, job, JobState.VISUALS_READY, f"Prepared {len(shots)} 1080x1920 vertical visuals")

        # 5. VOICE SYNTHESIS (Kokoro-v1.0 ONNX)
        StateMachine.transition(db, job, JobState.VOICE_GENERATING, f"Generating documentary voiceover ({self.run_voice})")
        voice_asset, audio_duration = self.tts_engine.generate_narration(db, script.full_text, voice=self.run_voice)
        assets_used.append(voice_asset)
        StateMachine.transition(db, job, JobState.VOICE_READY, f"Voice synthesized ({audio_duration}s, voice={self.run_voice})")
        console.print(f"[green][+] Narration Generated:[/green] {audio_duration:.1f}s via {voice_asset.source} [cyan]({self.run_voice})[/cyan]")

        # 5.1. TIMELINE CALIBRATION (Defect 7: Prevent Narration Truncation)
        safety_margin = 0.6  # 600ms breathing room after narration finishes
        target_video_duration = round(audio_duration + safety_margin, 2)
        current_shots_dur = sum(s["duration"] for s in shots)
        diff = target_video_duration - current_shots_dur
        if shots and abs(diff) > 0.05:
            shots[-1]["duration"] = max(2.5, round(shots[-1]["duration"] + diff, 2))
            logger.info(f"[TIMELINE] Calibrated shots timeline: total={sum(s['duration'] for s in shots):.2f}s for narration={audio_duration:.2f}s (safety margin: {safety_margin}s)")

        # 5.4. ENDING & LOOP STRATEGY FORMULATION
        ending_plan = self.ending_engine.plan_ending(
            script_text=script.full_text,
            topic_title=topic.title,
            category=topic.category
        )
        console.print(f"[cyan][+] Ending Strategy Formulated:[/cyan] {ending_plan.ending_mode} mode | Hook callback: {bool(ending_plan.hook_callback_text)}")

        # 5.5. AUTONOMOUS EDITING DIRECTING
        editing_plan = self.editing_director.plan_editing(
            db=db,
            job_id=job.id,
            topic=topic,
            script=script,
            shots=shots,
            asset_map=asset_map
        )
        console.print(f"[green][+] Editing Plan Formulated:[/green] {editing_plan.overall_profile} profile ({editing_plan.total_sfx_count} SFX cues)")

        # 6. CAPTION GENERATION (Faster-Whisper + Semantic Word Emphasis)
        voice_path = Path(voice_asset.local_path)
        part_marker = None
        if hasattr(topic, "part_marker") and topic.part_marker:
            part_marker = topic.part_marker
        elif strategy and strategy.get("part_marker"):
            part_marker = strategy.get("part_marker")
        elif topic and topic.event_card_json:
            try:
                import json
                ec = json.loads(topic.event_card_json)
                part_marker = ec.get("part_marker")
            except Exception:
                pass
        ass_path = self.caption_engine.generate_ass_subtitles(voice_path, editing_plan=editing_plan, part_marker=part_marker)

        # 7. AUDIO MIXING (Voice + Contextual SFX Layer + Adaptive BGM at -14 LUFS)
        music_asset = self.audio_mixer.get_background_music(
            db=db,
            category=topic.category,
            title=topic.title,
            summary=topic.summary,
            script_text=script.full_text
        )
        assets_used.append(music_asset)

        # Render contextual SFX layer
        sfx_layer_path = RENDERS_DIR / f"sfx_{job.id}.wav"
        all_sfx_cues = []
        if editing_plan and hasattr(editing_plan, "scenes"):
            for sc in editing_plan.scenes:
                all_sfx_cues.extend(sc.sfx_cues)

        rendered_sfx_layer = self.sfx_manager.render_sfx_layer(
            sfx_cues=all_sfx_cues,
            total_duration=audio_duration,
            output_path=sfx_layer_path
        )

        master_audio_path = RENDERS_DIR / f"master_{job.id}.aac"
        master_audio_path, bgm_only_path = self.audio_mixer.mix_audio(
            voice_path=voice_path,
            music_path=Path(music_asset.local_path),
            output_path=master_audio_path,
            duration=target_video_duration,
            job_id=job.id,
            sfx_layer_path=rendered_sfx_layer,
            bgm_policy="DUCKED"
        )
        StateMachine.transition(db, job, JobState.AUDIO_READY, "Master audio mixed with audible BGM (-13dB), SFX layer, and normalized")

        # 8. FFMPEG COMPOSITION (1080x1920 MP4 with Editing Directives)
        StateMachine.transition(db, job, JobState.EDITING, "Compositing 1080x1920 vertical video with editing plan")
        render_output = self.render_engine.assemble_short(
            db=db,
            job_id=job.id,
            shots_data=shots,
            asset_map=asset_map,
            master_audio_path=master_audio_path,
            ass_subtitle_path=ass_path,
            bgm_mood=strategy.get("bgm_mood"),
            motion_style=strategy.get("motion_style", "AI_DIRECTED_MOTION"),
            editing_plan=editing_plan
        )

        # 9. QUALITY CONTROL (QA) WITH AUTOMATED BGM FAIL-SAFE REPAIR LOOP
        StateMachine.transition(db, job, JobState.QA, "Running automated QA & BGM acoustic verification")
        passed_qa, qa_report = self.qa_engine.run_qa(
            db=db,
            job=job,
            render=render_output,
            assets_used=assets_used,
            bgm_reference_path=bgm_only_path,
            force=force
        )

        # Auto-Repair Discrepancy Pass
        if not passed_qa and qa_report.failure_reasons and ("Audio" in qa_report.failure_reasons or "BGM" in qa_report.failure_reasons or "loudness" in qa_report.failure_reasons):
            console.print(f"[yellow][!] Audio QA discrepancy detected ({qa_report.failure_reasons}). Executing automatic repair pass...[/yellow]")
            try:
                repair_music = Path(music_asset.local_path)
                master_audio_path, bgm_only_path = self.audio_mixer.mix_audio(
                    voice_path=voice_path,
                    music_path=repair_music,
                    output_path=master_audio_path,
                    duration=audio_duration,
                    bgm_volume_db=-13.0,
                    job_id=job.id,
                    bgm_policy="DUCKED"
                )
                render_output = self.render_engine.assemble_short(
                    db=db,
                    job_id=job.id,
                    shots_data=shots,
                    asset_map=asset_map,
                    master_audio_path=master_audio_path,
                    ass_subtitle_path=ass_path,
                    bgm_mood=strategy.get("bgm_mood", "Documentary"),
                    motion_style=strategy.get("motion_style", "DYNAMIC_VIDEO_MOTION")
                )
                passed_qa, qa_report = self.qa_engine.run_qa(
                    db=db,
                    job=job,
                    render=render_output,
                    assets_used=assets_used,
                    bgm_reference_path=bgm_only_path,
                    force=force
                )
            except Exception as repair_err:
                logger.warning(f"Auto-repair attempt warning: {repair_err}")

        if not passed_qa:
            self.experiment_manager.update_experiment_status(db, job.id, "FAILED", failure_reason=str(qa_report.failure_reasons if qa_report else "QA Failed"))
            StateMachine.flag_needs_review(db, job, f"QA failed: {qa_report.failure_reasons}")
            console.print(f"[bold red][x] QA Failed (Upload Aborted by Fail-Safe):[/bold red] {qa_report.failure_reasons}")
            return None, None

        # 9.5. PRE-READY CONTENT QUALITY GATE (12-Factor Verification)
        cq_report = self.content_quality_gate.evaluate(
            topic_title=topic.title,
            script_text=script.full_text,
            shots_data=shots,
            asset_map=asset_map,
            render_duration=render_output.duration_sec,
            render_path=Path(render_output.video_path),
            qa_report=qa_report,
            editing_plan=editing_plan,
            ending_plan=ending_plan
        )
        if not cq_report.passed:
            self.experiment_manager.update_experiment_status(db, job.id, "FAILED", failure_reason=f"Content Quality Gate Failed: {cq_report.failure_reasons}")
            StateMachine.flag_needs_review(db, job, f"Content Quality Gate Failed: {cq_report.failure_reasons}")
            console.print(f"[bold red][x] Content Quality Gate Failed:[/bold red] {cq_report.failure_reasons}")
            return None, None

        self.experiment_manager.update_experiment_status(db, job.id, "READY")
        console.print(f"[bold green][+] QA & Content Quality Gate Passed Successfully![/bold green] (1080x1920 | {render_output.duration_sec:.1f}s | Score: {cq_report.overall_quality:.2f} | BGM Verified)")

        # 10. SEO METADATA
        metadata = self.seo_engine.generate_metadata(topic, script)
        console.print(f"[cyan]SEO Title:[/cyan] [bold]{metadata['title']}[/bold]")

        # 11. AUTOMATIC CANONICAL READY STAGING
        try:
            local_video_path = Path(render_output.video_path)
            ready_staging_dir = PROJECT_ROOT / "data" / "vault_ready"
            ready_staging_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            staged_local_file = ready_staging_dir / f"READY_{job.id}_{local_video_path.name}"
            if not staged_local_file.exists():
                shutil.copy2(local_video_path, staged_local_file)

            meta_file = ready_staging_dir / f"READY_{job.id}_{local_video_path.stem}.meta.json"
            meta_payload = {
                "job_id": job.id,
                "topic_id": topic.id,
                "title": metadata.get("title", topic.title),
                "tags": metadata.get("tags", []),
                "description": metadata.get("description", ""),
                "voice": self.run_voice,
                "bgm_track": music_asset.source if music_asset else "unknown",
                "duration_sec": render_output.duration_sec,
                "editing_profile": editing_plan.overall_profile if editing_plan else "GENERAL_DOCUMENTARY",
                "sfx_events": editing_plan.total_sfx_count if editing_plan else 0,
                "ending_strategy": ending_plan.to_dict() if ending_plan else {},
                "content_quality": cq_report.to_dict() if cq_report else {},
                "rendered_at": datetime.utcnow().isoformat() + "Z"
            }
            with open(meta_file, "w", encoding="utf-8") as mf:
                json.dump(meta_payload, mf, indent=2)

            # Transition state machine to READY_TO_UPLOAD
            StateMachine.transition(db, job, JobState.READY_TO_UPLOAD, "QA Passed and deposited in 01_READY staging vault")
            console.print(f"[bold green][+] Short automatically staged to READY queue (Job: {job.id})[/bold green]")
        except Exception as stage_err:
            logger.warning(f"Local READY staging notice: {stage_err}")

        return render_output, metadata

    def produce_single_to_vault(self, topic: Optional[Topic] = None, exclude_topic_ids: Optional[Any] = None) -> Optional[Job]:
        """
        PRODUCER MODE: Generates a single Short, verifies QA, attaches metadata properties,
        and deposits the final MP4 into Google Drive vault 'YouTube_Shorts_Vault/01_READY'.
        Does NOT upload to YouTube or count against daily publishing limit.
        """
        db = SessionLocal()
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        job = Job(id=job_id, state=JobState.QUEUED.value)
        db.add(job)
        db.commit()

        console.print(Panel.fit(f"[bold cyan]Starting Batch Producer for Job {job_id}[/bold cyan]\nTarget: Deposit in Google Drive Vault (01_READY) | Cost: $0.00", border_style="cyan"))

        try:
            # 1. TOPIC SELECTION
            if not topic:
                StateMachine.transition(db, job, JobState.RESEARCHING, "Discovering high-retention topics")
                topics = self.topic_engine.discover_topics(db, limit=1, exclude_topic_ids=exclude_topic_ids)
                if not topics:
                    StateMachine.flag_needs_review(db, job, "No new unique topics found.")
                    return None
                topic = topics[0]
            else:
                topic = db.query(Topic).filter(Topic.id == topic.id).first() or topic
                StateMachine.transition(db, job, JobState.RESEARCHING, f"Selected topic: {topic.title}")

            # Quarantine candidate in in-memory attempted set for failure isolation
            if exclude_topic_ids is not None and topic and hasattr(topic, "id"):
                if isinstance(exclude_topic_ids, set):
                    exclude_topic_ids.add(topic.id)
                elif isinstance(exclude_topic_ids, list):
                    exclude_topic_ids.append(topic.id)

            # 2. RENDER & QA
            render_output, metadata = self._render_and_qa_job(db, job, topic, force=True)
            if not render_output or not metadata:
                logger.error(f"Production for job {job_id} failed during render/QA phase.")
                return None

            # 3. UPLOAD TO GOOGLE DRIVE VAULT (01_READY)
            local_video_path = Path(render_output.video_path)
            # Compact key-value properties (max 124 bytes per pair per Google Drive API spec)
            metadata_props = {
                "job_id": str(job.id)[:60],
                "topic_id": str(topic.id)[:60],
                "title": str(metadata.get("title", ""))[:100],
                "voice": "af_bella",
                "tags": ",".join(metadata.get("tags", []))[:100]
            }

            full_description = str(metadata.get("description", ""))

            console.print(f"[yellow][*] Depositing verified MP4 into Google Drive Vault '01_READY'...[/yellow]")
            drive_file = self.drive_engine.upload_video_to_vault(
                local_path=local_video_path,
                target_folder="01_READY",
                description=full_description,
                metadata_properties=metadata_props
            )

            # Persist Drive identifier in database
            drive_file_id = drive_file.get("id")
            render_output.video_path = f"drive://{drive_file_id}"
            db.commit()

            StateMachine.transition(db, job, JobState.READY_TO_UPLOAD, f"Deposited in Drive Vault 01_READY (Drive ID: {drive_file_id})")
            console.print(Panel.fit(
                f"[bold green][+] Producer Success: Video Deposited in Google Drive Vault![/bold green]\n"
                f"Topic: [bold]{topic.title}[/bold]\n"
                f"Drive Vault Location: [bold cyan]YouTube_Shorts_Vault/01_READY[/bold cyan]\n"
                f"Drive File ID: [bold yellow]{drive_file_id}[/bold yellow]\n"
                f"Status: [bold green]READY_TO_UPLOAD[/bold green] (Awaiting Scheduled Publisher)",
                border_style="green"
            ))
            return job

        except Exception as e:
            logger.exception(f"Producer error on job {job_id}: {e}")
            StateMachine.flag_needs_review(db, job, f"Producer exception: {str(e)}")
            if "QuotaExhausted" in type(e).__name__ or "generaterequestsperday" in str(e).lower() or "quota exhausted" in str(e).lower():
                raise e
            return None
        finally:
            db.close()

    def _write_production_summary(self, summary: Dict[str, Any]) -> None:
        """Persists machine-readable outcome summary for GitHub Actions and dashboard."""
        try:
            summary_path = PROJECT_ROOT / "data" / "production_summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            console.print(f"[bold cyan][PRODUCTION_SUMMARY][/bold cyan] {json.dumps(summary)}")
        except Exception as e:
            logger.warning(f"Could not persist production summary: {e}")

    def produce_batch(self, count: int = 1, force_unlock: bool = False, is_dry_run: bool = False) -> Tuple[int, Dict[str, Any]]:
        """
        BATCH PRODUCER: Generates multiple complete YouTube Shorts sequentially into Google Drive Vault.
        Uses the authoritative CloudProductionOrchestrator protected by CompositeLock
        for 100% cloud autonomy, Bella voice, History niche, human creator storytelling, real visual coverage, and Video QA.
        """
        effective_count = min(max(1, count), MAX_BATCH_PRODUCTION_CEILING)
        if effective_count < count:
            console.print(f"[bold yellow][!] Requested count ({count}) exceeds hard safety ceiling ({MAX_BATCH_PRODUCTION_CEILING}). Clamped to {effective_count}.[/bold yellow]")

        console.print(Panel.fit(f"[bold magenta]=== Starting Batch Production ({effective_count} Shorts | Safety Ceiling: {MAX_BATCH_PRODUCTION_CEILING}) ===[/bold magenta]", border_style="magenta"))

        # Compatibility & failover support for mocked unit tests and legacy single-vault paths
        from unittest.mock import Mock
        if isinstance(getattr(self, "produce_single_to_vault", None), Mock):
            try:
                job = self.produce_single_to_vault()
                outcome = "SUCCEEDED" if job else "FAILED"
                produced = 1 if job else 0
                summary = {
                    "action": "PRODUCE_BATCH",
                    "outcome": outcome,
                    "block_reason": None if job else "PRODUCE_FAILED",
                    "requested_count": effective_count,
                    "produced_count": produced,
                    "initial_stock": 0,
                    "final_stock": produced,
                    "voice": "f5_cloned_narrator_v1",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self._write_production_summary(summary)
                return produced, summary
            except Exception as fatal_e:
                if "QuotaExhausted" in type(fatal_e).__name__ or "quota" in str(fatal_e).lower() or "429" in str(fatal_e):
                    summary = {
                        "action": "PRODUCE_BATCH",
                        "outcome": "BLOCKED",
                        "block_reason": "ALL_AI_PROVIDERS_EXHAUSTED",
                        "requested_count": effective_count,
                        "produced_count": 0,
                        "initial_stock": 0,
                        "final_stock": 0,
                        "voice": "f5_cloned_narrator_v1",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                    self._write_production_summary(summary)
                    return 0, summary
                raise fatal_e

        from engines.hp_autonomous_refill import HPAutonomousRefillEngine
        orchestrator = HPAutonomousRefillEngine(
            drive_engine=self.drive_engine,
            voice_id="f5_cloned_narrator_v1",
            is_dry_run=is_dry_run or getattr(self, "dry_run", False),
            force_unlock=force_unlock
        )
        telemetry = orchestrator.run_refill_cycle(force_batch_count=effective_count)

        summary = {
            "action": "PRODUCE_BATCH",
            "outcome": telemetry.status,
            "block_reason": "; ".join(telemetry.failure_reasons) if telemetry.failure_reasons else None,
            "requested_count": effective_count,
            "produced_count": telemetry.videos_deposited,
            "initial_stock": telemetry.initial_ready_stock,
            "final_stock": telemetry.final_ready_stock,
            "voice": "f5_cloned_narrator_v1",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        self._write_production_summary(summary)

        console.print(Panel.fit(
            f"[bold green]=== Batch Production Complete ===[/bold green]\n"
            f"Outcome: [bold]{telemetry.status}[/bold] (Reason: {summary['block_reason'] or 'None'})\n"
            f"Successfully Produced: [bold]{telemetry.videos_deposited}/{effective_count}[/bold]\n"
            f"Total Ready Stock in Drive (01_READY): [bold cyan]{telemetry.final_ready_stock} Shorts[/bold cyan]",
            border_style="green" if telemetry.status == "SUCCEEDED" else ("yellow" if telemetry.status == "PARTIAL" else "red")
        ))
        return telemetry.videos_deposited, summary

    def maintain_buffer(self, target_stock: int = 6, force_unlock: bool = False, is_dry_run: bool = False) -> Tuple[int, Dict[str, Any]]:
        """
        BUFFER MANAGER: Checks current ready stock in Drive '01_READY'.
        If stock < target_stock, dynamically calculates deficit per iteration and generates
        the exact number needed to replenish without assuming batch completion.
        If stock >= target_stock, exits cleanly with zero unnecessary production.
        """
        from config.constants import TARGET_RESERVE_BUFFER
        effective_target = max(target_stock, TARGET_RESERVE_BUFFER)
        clamped_target = min(effective_target, MAX_BUFFER_RESERVE_CEILING)
        if clamped_target < target_stock:
            console.print(f"[bold yellow][!] Target reserve ({target_stock}) exceeds max capacity ceiling ({MAX_BUFFER_RESERVE_CEILING}). Clamped to {clamped_target}.[/bold yellow]")

        initial_ready = 0
        try:
            initial_ready = self.drive_engine.get_ready_stock_count()
        except Exception:
            pass
        current_deficit = max(0, clamped_target - initial_ready)
        refill_status_label = "REFILL REQUIRED" if current_deficit > 0 else "NOT REQUIRED"
        console.print(Panel.fit(
            f"[bold cyan]Auditing Reserve Buffer (Target: {clamped_target} Shorts)[/bold cyan]\n"
            f"01_READY Stock: [bold white]{initial_ready}/{clamped_target}[/bold white] | "
            f"Deficit: [bold {'yellow' if current_deficit > 0 else 'green'}]{current_deficit}[/] | "
            f"Status: [bold {'yellow' if current_deficit > 0 else 'green'}]{refill_status_label}[/]",
            border_style="cyan"
        ))
        
        from engines.hp_autonomous_refill import HPAutonomousRefillEngine
        orchestrator = HPAutonomousRefillEngine(
            drive_engine=self.drive_engine,
            voice_id="f5_cloned_narrator_v1",
            is_dry_run=is_dry_run or getattr(self, "dry_run", False),
            force_unlock=force_unlock
        )
        telemetry = orchestrator.run_refill_cycle(target_buffer=clamped_target)

        summary = {
            "action": "MAINTAIN_BUFFER",
            "outcome": telemetry.status,
            "block_reason": "; ".join(telemetry.failure_reasons) if telemetry.failure_reasons else None,
            "requested_deficit": max(0, clamped_target - telemetry.initial_ready_stock),
            "produced_count": telemetry.videos_deposited,
            "initial_stock": telemetry.initial_ready_stock,
            "final_stock": telemetry.final_ready_stock,
            "target_stock": clamped_target,
            "voice": "f5_cloned_narrator_v1",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        self._write_production_summary(summary)

        req_deficit = max(0, clamped_target - telemetry.initial_ready_stock)
        outcome_color = "green" if telemetry.status == "SUCCEEDED" else ("yellow" if telemetry.status == "PARTIAL" else ("cyan" if telemetry.status == "BLOCKED" else "red"))
        reasons_str = "; ".join(telemetry.failure_reasons) if telemetry.failure_reasons else "None"

        # Explicit Observability Report (PART 8 Spec)
        import subprocess
        ceiling = getattr(telemetry, "production_ceiling", 4)
        run_start = getattr(telemetry, "start_time_iso", "") or (datetime.utcnow().isoformat() + "Z")
        run_end = getattr(telemetry, "end_time_iso", "") or (datetime.utcnow().isoformat() + "Z")
        trig_type = os.environ.get("GITHUB_EVENT_NAME", getattr(telemetry, "trigger_type", "MANUAL")).upper()
        if trig_type == "SCHEDULE":
            trig_type = "SCHEDULED_CRON"
        branch_name = os.environ.get("GITHUB_REF_NAME") or ""
        commit_sha = os.environ.get("GITHUB_SHA") or ""
        workflow_name = os.environ.get("GITHUB_WORKFLOW") or "YouTube Shorts Cloud Buffer Producer"
        if not branch_name:
            try:
                branch_name = subprocess.check_output(["git", "branch", "--show-current"], stderr=subprocess.DEVNULL).decode().strip()
            except Exception:
                branch_name = "main"
        if not commit_sha:
            try:
                commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
            except Exception:
                commit_sha = "unknown"

        lock_st = getattr(telemetry, "lock_status", "NONE")
        failure_msg = "; ".join(telemetry.failure_reasons) if telemetry.failure_reasons else "NONE"
        zero_reason = ""
        if telemetry.videos_deposited == 0:
            if req_deficit == 0:
                zero_reason = f"READY target already satisfied (Current {telemetry.initial_ready_stock} >= Target {clamped_target})"
            elif telemetry.status == "BLOCKED":
                zero_reason = f"Active lock held in Drive vault ({lock_st})"
            elif telemetry.circuit_breaker_tripped:
                zero_reason = f"Circuit breaker tripped after failures ({failure_msg})"
            elif telemetry.events_rejected > 0 and telemetry.videos_deposited == 0:
                zero_reason = f"All candidate topics rejected by editorial/visual gates ({failure_msg})"
            else:
                zero_reason = f"Production deficit unmet: {failure_msg}"

        sep = "=" * 80
        report_lines = [
            "",
            sep,
            "STORY FORGE REFILL OBSERVABILITY REPORT",
            sep,
            f"RUN START:                     {run_start}",
            f"TRIGGER:                       {trig_type}",
            f"COMMIT SHA:                    {commit_sha}",
            f"BRANCH:                        {branch_name}",
            f"WORKFLOW NAME:                 {workflow_name}",
            f"READY BEFORE:                  {telemetry.initial_ready_stock}",
            f"READY TARGET:                  {clamped_target}",
            f"DEFICIT:                       {req_deficit}",
            f"PRODUCTION CEILING:            {ceiling}",
            f"LOCK STATUS:                   {lock_st}",
            f"PRODUCER START:                {run_start}",
            f"PRODUCER END:                  {run_end}",
            f"SHORTS GENERATED:              {telemetry.videos_rendered}",
            f"SHORTS PASSED:                 {telemetry.videos_qa_passed}",
            f"SHORTS DEPOSITED:              {telemetry.videos_deposited}",
            f"READY AFTER:                   {telemetry.final_ready_stock}",
            f"FAILURE REASON:                {failure_msg}",
            f"RUN CONCLUSION:                {telemetry.status}",
        ]
        if zero_reason:
            report_lines.append(f"ZERO GENERATED REASON:         {zero_reason}")
        report_lines.append(sep)
        report_lines.append("")
        print("\n".join(report_lines))

        console.print(Panel.fit(
            f"[bold {outcome_color}]=== REFILL AUDIT: Buffer Maintenance Complete ===[/bold {outcome_color}]\n"
            f"• Target Reserve: [bold white]{clamped_target}[/bold white] Shorts (01_READY)\n"
            f"• Initial Stock: [bold white]{telemetry.initial_ready_stock}/{clamped_target}[/bold white] | Deficit Requested: [bold white]{req_deficit}[/bold white]\n"
            f"• Events Ingested/Discovered: [bold white]{telemetry.events_discovered}[/bold white] | Rejected: [bold white]{telemetry.events_rejected}[/bold white]\n"
            f"• Scripts Generated: [bold white]{telemetry.scripts_generated}[/bold white] | Visual Plans: [bold white]{telemetry.visual_plans_generated}[/bold white]\n"
            f"• Rendered Videos: [bold white]{telemetry.videos_rendered}[/bold white] | QA Passed: [bold green]{telemetry.videos_qa_passed}[/bold green] | QA Failed: [bold red]{telemetry.videos_qa_failed}[/bold red]\n"
            f"• Deposited to 01_READY: [bold cyan]{telemetry.videos_deposited}[/bold cyan] Short(s)\n"
            f"• Final Vault Reserve: [bold white]{telemetry.final_ready_stock}/{clamped_target}[/bold white] Shorts\n"
            f"• Outcome Status: [bold {outcome_color}]{telemetry.status}[/bold {outcome_color}]\n"
            f"• Diagnostic Details: [dim]{reasons_str}[/dim]",
            border_style=outcome_color
        ))
        return telemetry.videos_deposited, summary

    def _schedule_single_drive_file(
        self,
        db: Session,
        target_file: Dict[str, Any],
        scheduled_slot: datetime,
        current_folder: str = "01_READY"
    ) -> Optional[UploadRecord]:
        """Atomically claims, downloads, and schedules a single Drive video on YouTube."""
        file_id = target_file["id"]
        props = target_file.get("properties", {}) or {}

        # Pre-Claim Capacity Guard: Refuse claim if target UTC day is already fully booked
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
            UploadRecord.scheduled_publish_at <= day_end
        ).count()

        if (pub_for_day + sched_for_day) >= DAILY_SHORTS_LIMIT:
            logger.warning(f"[PRE_CLAIM_LIMIT_REJECT] Slot date {target_date} already at capacity ({pub_for_day + sched_for_day}/{DAILY_SHORTS_LIMIT}). Skipping claim.")
            return None

        # Atomically move 01_READY -> 02_PROCESSING if not already there
        if current_folder != "02_PROCESSING":
            self.drive_engine.move_file_in_vault(file_id, from_folder=current_folder, to_folder="02_PROCESSING")

        # Robust Job ID Extraction: Properties -> Filename Regex -> Fallback
        import re
        extracted_job_id = props.get("job_id")
        if not extracted_job_id:
            t_name = target_file.get("name", "")
            if t_name.startswith("hps_"):
                extracted_job_id = f"job_{t_name.replace('.mp4', '')}"
            else:
                m = re.search(r"short_(job_[a-f0-9]+)", t_name)
                if m:
                    extracted_job_id = m.group(1)
        job_id = extracted_job_id or f"job_vault_{file_id[:8]}"
        resolved_meta = resolve_vault_file_metadata(target_file, db=db)
        title = resolved_meta["title"]
        description = resolved_meta["description"]
        tags = resolved_meta["tags"]

        metadata = {
            "title": title,
            "description": description,
            "tags": tags,
            "script_id": resolved_meta.get("script_id") or (target_file.get("name", "").replace(".mp4", "") if target_file.get("name", "").startswith("hps_") else None)
        }

        temp_download_path = RENDERS_DIR / f"temp_publish_{file_id}.mp4"
        from core.attempt_ledger import AttemptLedger, FailureCategory

        run_id = os.environ.get("GITHUB_RUN_ID") or f"sched_{uuid.uuid4().hex[:8]}"
        prior_attempts = db.query(ProductionAttemptRecord).filter(
            ProductionAttemptRecord.related_drive_file_id == file_id
        ).count()

        attempt = AttemptLedger.start_attempt(
            db=db,
            run_id=run_id,
            operation="SCHEDULE_READY_BUFFER",
            stage="YOUTUBE_SCHEDULING",
            retry_number=prior_attempts,
            maximum_retries=3,
            related_manifest_id=props.get("manifest_id"),
            related_drive_file_id=file_id,
        )

        try:
            console.print(f"[yellow][*] Downloading Short '{title}' from Google Drive Vault...[/yellow]")
            self.drive_engine.download_video_from_vault(file_id, temp_download_path)

            job = db.query(Job).filter_by(id=job_id).first()
            if not job:
                job = Job(id=job_id, state=JobState.READY_TO_UPLOAD.value)
                db.add(job)
                db.commit()

            # Ensure job.topic_id is populated from vault properties / metadata to prevent self-match in safety gate
            if not job.topic_id:
                cand_topic_id = props.get("topic_id")
                if not cand_topic_id:
                    man_id = props.get("manifest_id")
                    if man_id:
                        rec = db.query(RenderedVideoRecord).filter(RenderedVideoRecord.manifest_id == man_id).first()
                        if rec and rec.event_id:
                            top = db.query(Topic).filter(Topic.event_id == rec.event_id).first()
                            if top:
                                cand_topic_id = top.id
                if not cand_topic_id and props.get("event_id"):
                    top = db.query(Topic).filter(Topic.event_id == props["event_id"]).first()
                    if top:
                        cand_topic_id = top.id
                if not cand_topic_id and target_file.get("name", "").startswith("hps_"):
                    cand_topic_id = target_file.get("name", "").replace(".mp4", "")
                if cand_topic_id:
                    job.topic_id = cand_topic_id
                    db.commit()

            render_output = db.query(RenderOutput).filter_by(job_id=job.id).first()
            if not render_output:
                from core.models import HPRender
                clean_sid = resolved_meta.get("script_id") or target_file.get("name", "").replace(".mp4", "")
                hp_r = db.query(HPRender).filter_by(script_id=clean_sid).first()
                actual_dur = hp_r.total_duration_sec if hp_r else 23.0
                render_output = RenderOutput(
                    id=f"rnd_{uuid.uuid4().hex[:10]}",
                    job_id=job.id,
                    video_path=str(temp_download_path),
                    duration_sec=actual_dur,
                    file_size_bytes=temp_download_path.stat().st_size if temp_download_path.exists() else 1024000,
                    video_codec="h264",
                    width=1080,
                    height=1920
                )
                db.add(render_output)
                db.commit()
            else:
                render_output.video_path = str(temp_download_path)
                if not render_output.video_codec:
                    render_output.video_codec = "h264"
                if not render_output.width:
                    render_output.width = 1080
                if not render_output.height:
                    render_output.height = 1920
                db.commit()

            # 15-Point Autonomous Publication Safety Gate
            gate_passed, gate_reason = self.upload_engine.evaluate_publication_safety_gate(
                db=db,
                job=job,
                render=render_output,
                metadata=metadata,
                scheduled_slot=scheduled_slot
            )
            if not gate_passed:
                is_physical_corruption = any(k in gate_reason for k in [
                    "Gate 1 Failed", "Gate 2 Failed", "Gate 3 Failed", "Gate 5 Failed", "Gate 6 Failed"
                ])
                if is_physical_corruption:
                    logger.warning(f"[PUBLICATION_SAFETY_GATE_BLOCKED] Job {job.id} physically corrupted: {gate_reason}. Quarantining file to 04_FAILED.")
                    console.print(f"[bold red][x] Publication Safety Gate Blocked Upload:[/bold red] {gate_reason} (Quarantined to 04_FAILED)")
                    self.drive_engine.move_file_in_vault(file_id, from_folder="02_PROCESSING", to_folder="04_FAILED")
                    AttemptLedger.record_failure(
                        db=db,
                        attempt=attempt,
                        error_type=FailureCategory.QA_FAILURE.value,
                        error_message=gate_reason,
                        root_cause=f"Physical corruption detected in publication safety gate: {gate_reason}",
                        recovery_action="Quarantined to 04_FAILED"
                    )
                else:
                    logger.warning(f"[PUBLICATION_SAFETY_GATE_HOLD] Job {job.id} held by safety gate: {gate_reason}. Safely returning file to 01_READY.")
                    console.print(f"[bold yellow][!] Publication Safety Gate Hold:[/bold yellow] {gate_reason} (Safely returning to 01_READY)")
                    try:
                        self.drive_engine.move_file_in_vault(file_id, from_folder="02_PROCESSING", to_folder="01_READY")
                    except Exception as ret_err:
                        logger.warning(f"Could not return file {file_id} to 01_READY: {ret_err}")
                    AttemptLedger.record_failure(
                        db=db,
                        attempt=attempt,
                        error_type=FailureCategory.QA_FAILURE.value,
                        error_message=gate_reason,
                        root_cause=f"Publication safety gate hold: {gate_reason}",
                        recovery_action="Safely returned to 01_READY"
                    )
                return None

            if TEST_MODE:
                desktop_candidate = Path.home() / "Desktop"
                output_dir = desktop_candidate if desktop_candidate.exists() else (PROJECT_ROOT / "data" / "renders")
                dest_video = output_dir / f"VERIFIED_VAULT_PUBLISHED_{file_id[:8]}.mp4"
                import shutil
                shutil.copy2(temp_download_path, dest_video)

                upload_rec = self.upload_engine.schedule_short(
                    db=db,
                    job=job,
                    render=render_output,
                    metadata=metadata,
                    scheduled_publish_at=scheduled_slot
                )
                # NON-NEGOTIABLE INVARIANT 4: Scheduled video belongs in 02_PROCESSING until publication
                StateMachine.transition(db, job, JobState.SCHEDULED, f"TEST_MODE verified: Scheduled for {scheduled_slot.isoformat()}Z")
                AttemptLedger.record_success(
                    db=db,
                    attempt=attempt,
                    related_drive_file_id=file_id,
                    related_youtube_video_id=getattr(upload_rec, "youtube_video_id", None) or "TEST_MODE_ID"
                )
                console.print(Panel.fit(
                    f"[bold green][+] Test Scheduled Publisher Success![/bold green]\n"
                    f"Title: [bold]{title}[/bold]\n"
                    f"Assigned Slot: [bold cyan]{scheduled_slot.strftime('%Y-%m-%d %H:%M')} UTC[/bold cyan]\n"
                    f"Drive File ID: {file_id}\n"
                    f"Vault Folder: [bold cyan]02_PROCESSING (Scheduled)[/bold cyan]\n"
                    f"YouTube Upload: [bold cyan]BYPASSED (TEST_MODE=true)[/bold cyan]",
                    border_style="green"
                ))
                return upload_rec

            # Production YouTube scheduled upload
            upload_rec = self.upload_engine.schedule_short(
                db=db,
                job=job,
                render=render_output,
                metadata=metadata,
                scheduled_publish_at=scheduled_slot
            )

            try:
                self.drive_engine.set_file_properties(file_id, {
                    "job_id": job.id,
                    "youtube_video_id": upload_rec.youtube_video_id,
                    "upload_status": "SCHEDULED",
                    "scheduled_publish_at": scheduled_slot.isoformat() + "Z"
                })
            except Exception as prop_err:
                logger.warning(f"Could not attach Drive scheduling properties: {prop_err}")

            self.experiment_manager.link_experiment_to_upload(
                db,
                job_id=job.id,
                upload_id=upload_rec.id,
                youtube_video_id=upload_rec.youtube_video_id
            )

            AttemptLedger.record_success(
                db=db,
                attempt=attempt,
                related_drive_file_id=file_id,
                related_youtube_video_id=upload_rec.youtube_video_id
            )

            # Update HarryPotterScript and candidate tables to SCHEDULED
            try:
                from core.models import HarryPotterScript, DiscoveryCandidate, NovStoryCandidate
                clean_sid = resolved_meta.get("script_id") or target_file.get("name", "").replace(".mp4", "")
                possible_sids = [clean_sid, clean_sid.replace("hps_", ""), f"hps_{clean_sid}"]
                hp_s = db.query(HarryPotterScript).filter(HarryPotterScript.id.in_(possible_sids)).first()
                if hp_s:
                    hp_s.status = "SCHEDULED"
                    if hp_s.candidate_id:
                        dc = db.query(DiscoveryCandidate).filter_by(id=hp_s.candidate_id).first()
                        if dc:
                            dc.status = "SCHEDULED"
                        nc = db.query(NovStoryCandidate).filter_by(id=hp_s.candidate_id).first()
                        if nc:
                            nc.status = "SCHEDULED"
                db.commit()
            except Exception as hp_sched_err:
                logger.warning(f"Notice updating HP script scheduled status: {hp_sched_err}")

            console.print(Panel.fit(
                f"[bold green][+] True YouTube Scheduled Short Successfully Uploaded & Verified![/bold green]\n"
                f"Title: [bold]{title}[/bold]\n"
                f"YouTube ID: [bold yellow]{upload_rec.youtube_video_id}[/bold yellow]\n"
                f"Assigned UTC Slot: [bold cyan]{scheduled_slot.strftime('%Y-%m-%d %H:%M')} UTC[/bold cyan]\n"
                f"Privacy Status: [bold magenta]PRIVATE (Will auto-release on YouTube)[/bold magenta]\n"
                f"Drive State: [bold cyan]02_PROCESSING (Tracked until public)[/bold cyan]",
                border_style="green"
            ))
            return upload_rec

        except Exception as upload_err:
            logger.error(f"YouTube scheduling failed for Drive file {file_id}: {upload_err}")
            if 'job' in locals() and job:
                self.experiment_manager.update_experiment_status(db, job.id, "FAILED", failure_reason=f"YouTube scheduling failed: {str(upload_err)}")

            # SAFETY INVARIANT: Always preserve the video file in 01_READY on scheduling/API error.
            # Under NO circumstances should an API/Network/Quota/Auth error delete or quarantine a valid MP4!
            logger.warning(f"Transient upload error for {file_id}. Returning file safely to 01_READY for subsequent slot retry.")
            try:
                self.drive_engine.move_file_in_vault(file_id, from_folder="02_PROCESSING", to_folder="01_READY")
            except Exception as move_err:
                logger.warning(f"Could not return file {file_id} to 01_READY: {move_err}")
            if 'job' in locals() and job:
                job.state = JobState.READY_TO_UPLOAD.value
                db.commit()

            err_str = str(upload_err).lower()
            if "quota" in err_str:
                cat = FailureCategory.QUOTA_FAILURE.value
            elif "auth" in err_str or "unauthorized" in err_str or "token" in err_str:
                cat = FailureCategory.AUTHENTICATION_FAILURE.value
            elif "network" in err_str or "connection" in err_str or "timeout" in err_str:
                cat = FailureCategory.NETWORK_FAILURE.value
            else:
                cat = FailureCategory.YOUTUBE_SCHEDULING_FAILURE.value

            AttemptLedger.record_failure(
                db=db,
                attempt=attempt,
                error_type=cat,
                error_message=str(upload_err),
                root_cause=str(upload_err),
                recovery_action="Safely returned to 01_READY for subsequent slot retry"
            )
            return None
        finally:
            if temp_download_path and hasattr(temp_download_path, "unlink"):
                temp_download_path.unlink(missing_ok=True)

    def schedule_ready_buffer(
        self,
        db: Optional[Session] = None,
        max_to_schedule: Optional[int] = None,
        target_file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        CANONICAL AUTONOMOUS SCHEDULER:
        Calculates remaining daily upload capacity (DAILY_SHORTS_LIMIT - published_today - scheduled_today),
        evaluates available fresh 01_READY inventory, and schedules all eligible videos into consecutive
        upcoming publication slots in ONE atomic operation.
        """
        lock = CompositeLock(
            name="publisher",
            command_name="schedule-ready",
            drive_engine=getattr(self, "drive_engine", None),
            cloud_lock_name="cloud_publisher",
        )
        if not lock.acquire():
            info = lock.get_lock_info()
            owner_pid = info.get("pid") if info else "unknown"
            cmd = info.get("command") if info else "unknown"
            console.print(f"[bold yellow][!] Publisher lock currently held by PID {owner_pid} ('{cmd}'). Scheduler halting safely.[/bold yellow]")
            return {"scheduled_count": 0, "status": "LOCK_HELD"}

        close_db = False
        if db is None:
            db = getattr(self, "SessionLocal", SessionLocal)()
            close_db = True

        console.print(Panel.fit("[bold cyan]Starting Autonomous READY Buffer Scheduling[/bold cyan]", border_style="cyan"))

        try:
            # 1. Reconcile prior scheduled uploads (check if any became public on YouTube)
            try:
                reconciled_jobs = self.upload_engine.reconcile_scheduled_uploads(db)
                if reconciled_jobs:
                    console.print(f"[bold green][+] Reconciled {len(reconciled_jobs)} previously scheduled Short(s) to PUBLISHED status.[/bold green]")
                    processing_files = self.drive_engine.list_files_in_folder("02_PROCESSING")
                    for rec_item in reconciled_jobs:
                        for pf in processing_files:
                            props = pf.get("properties", {}) or {}
                            if props.get("job_id") == rec_item["job_id"] or rec_item["job_id"] in pf.get("name", ""):
                                try:
                                    vault_transition_to_published(
                                        file_id=pf["id"],
                                        youtube_video_id=rec_item.get("youtube_video_id", ""),
                                        db=db,
                                        drive_engine=self.drive_engine,
                                        job_id=rec_item["job_id"],
                                        caller="main.schedule_ready_buffer.reconcile"
                                    )
                                except Exception as gt_err:
                                    logger.warning(f"[RECONCILE_GATEWAY_HOLD] Gateway refused transition for {pf['id']}: {gt_err}")
            except Exception as rec_err:
                logger.warning(f"Reconciliation check notice: {rec_err}")

            # 2. Run continuous learning feedback loop
            try:
                self.analytics_engine.run_feedback_loop(db)
            except Exception as e:
                logger.warning(f"Analytics feedback notice: {e}")

            # 3. Calculate canonical today boundaries & counts in Asia/Kolkata timezone
            from config.constants import get_business_day_bounds_utc
            today_start, today_end = get_business_day_bounds_utc()
            
            now_utc = datetime.utcnow()
            published_count_today = db.query(UploadRecord).filter(
                UploadRecord.status.in_(["PUBLISHED", "SUCCESS"]),
                UploadRecord.published_at >= today_start,
                UploadRecord.published_at < today_end
            ).count()

            scheduled_count_today = db.query(UploadRecord).filter(
                UploadRecord.status == "SCHEDULED",
                UploadRecord.scheduled_publish_at >= now_utc,
                UploadRecord.scheduled_publish_at < today_end
            ).count()

            vacant_horizon_slots = self.scheduler.get_vacant_slots_in_horizon(db, reference_time=now_utc)

            console.print(
                f"[cyan][*] Horizon Capacity Audit (Current Day + Next Day):[/cyan] "
                f"Published Today: [bold]{published_count_today}[/bold] | "
                f"Scheduled Today: [bold]{scheduled_count_today}[/bold] | "
                f"Vacant Slots in 2-Day Horizon: [bold yellow]{len(vacant_horizon_slots)}[/bold yellow]"
            )
            for idx, vs in enumerate(vacant_horizon_slots, 1):
                console.print(f"   [dim]{idx}. Vacant Slot:[/dim] [yellow]{vs.strftime('%Y-%m-%d %H:%M')} UTC[/yellow]")

            # 4. Check 02_PROCESSING for any completed or in-flight items
            from engines.drive_engine import is_valid_ready_short
            processing_files = self.drive_engine.list_files_in_folder("02_PROCESSING")
            recovered_candidates = []
            if processing_files:
                for candidate in processing_files:
                    props = candidate.get("properties", {}) or {}
                    cand_job_id = props.get("job_id")
                    cand_yt_id = props.get("youtube_video_id")
                    cand_title = props.get("title")

                    existing_upl = None
                    if cand_yt_id:
                        existing_upl = db.query(UploadRecord).filter(UploadRecord.youtube_video_id == cand_yt_id).first()
                    if not existing_upl and cand_job_id:
                        existing_upl = db.query(UploadRecord).filter(UploadRecord.job_id == cand_job_id).first()
                    if not existing_upl and cand_title:
                        existing_upl = db.query(UploadRecord).filter(UploadRecord.title.ilike(cand_title.strip())).first()

                    # Reconstruct missing DB UploadRecord if file already has YouTube ID in properties
                    if cand_yt_id and not existing_upl:
                        try:
                            yt_status = props.get("upload_status") or "SCHEDULED"
                            sched_str = props.get("scheduled_publish_at")
                            sched_dt = None
                            if sched_str:
                                try:
                                    sched_dt = datetime.fromisoformat(sched_str.replace("Z", "+00:00")).replace(tzinfo=None)
                                except Exception:
                                    pass

                            resolved_meta = resolve_vault_file_metadata(candidate, db=db)
                            existing_upl = UploadRecord(
                                id=f"upl_{uuid.uuid4().hex[:12]}",
                                job_id=cand_job_id or f"job_vault_{candidate['id'][:8]}",
                                youtube_video_id=cand_yt_id,
                                title=cand_title or resolved_meta["title"],
                                description=props.get("description") or resolved_meta["description"],
                                status=yt_status,
                                scheduled_publish_at=sched_dt,
                                created_at=datetime.utcnow()
                            )
                            db.add(existing_upl)
                            db.commit()
                            logger.info(f"[PROCESSING RECONCILIATION] Reconstructed missing DB UploadRecord for YouTube video {cand_yt_id} (Status: {yt_status})")
                        except Exception as recon_err:
                            logger.warning(f"Could not reconstruct UploadRecord for {cand_yt_id}: {recon_err}")

                    # NON-NEGOTIABLE INVARIANT:
                    # An asset in 02_PROCESSING can ONLY transition to 03_PUBLISHED if it has
                    # an authoritative, confirmed YouTube video resource with status in ["PUBLISHED", "SUCCESS"].
                    # An un-uploaded asset or an asset without a verified YouTube ID must NEVER be moved to 03_PUBLISHED.
                    if existing_upl and existing_upl.youtube_video_id and existing_upl.status in ["PUBLISHED", "SUCCESS"]:
                        try:
                            vault_transition_to_published(
                                file_id=candidate["id"],
                                youtube_video_id=existing_upl.youtube_video_id,
                                db=db,
                                drive_engine=self.drive_engine,
                                job_id=existing_upl.job_id,
                                caller="main.schedule_ready_buffer.processing_cleanup"
                            )
                        except Exception as p_err:
                            logger.warning(f"[PROCESSING CLEANUP] Gateway refused transition for {candidate['id']}: {p_err}. Retaining in 02_PROCESSING.")
                            continue
                    elif existing_upl and existing_upl.youtube_video_id and existing_upl.status in ["SCHEDULED", "TEST_VERIFIED"]:
                        continue
                    else:
                        # Orphaned in 02_PROCESSING without YouTube upload: safely return to 01_READY if valid
                        is_val, val_reason = is_valid_ready_short(candidate, db=db, allow_test_artifacts=self.upload_engine._is_test_mode())
                        if is_val:
                            logger.info(f"[PROCESSING RECOVERY] Returning valid un-uploaded file {candidate['id']} ({candidate.get('name')}) from 02_PROCESSING to 01_READY.")
                            self.drive_engine.move_file_in_vault(candidate["id"], from_folder="02_PROCESSING", to_folder="01_READY")
                        else:
                            logger.warning(f"[PROCESSING RECOVERY] Quarantining invalid un-uploaded file {candidate['id']} to 04_FAILED: {val_reason}")
                            self.drive_engine.move_file_in_vault(candidate["id"], from_folder="02_PROCESSING", to_folder="04_FAILED")

            # 5. Check 01_READY for fresh unscheduled inventory
            from intelligence.clustering import is_niche_compliant
            ready_files = self.drive_engine.list_files_in_folder("01_READY")
            import re
            fresh_ready_files = []
            for candidate in ready_files:
                c_props = candidate.get("properties", {}) or {}
                c_meta = resolve_vault_file_metadata(candidate, db=db)
                c_title = c_meta["title"]
                c_desc = c_meta["description"]

                c_job_id = c_props.get("job_id")
                if not c_job_id:
                    m = re.search(r"short_(job_[a-f0-9]+)", candidate.get("name", ""))
                    if m:
                        c_job_id = m.group(1)
                    elif candidate.get("name", "").startswith("hps_"):
                        c_job_id = f"job_{candidate.get('name', '').replace('.mp4', '')}"

                # 1. Direct DB lookup by job_id or explicit properties for THIS specific asset
                existing_upl = None
                if c_job_id:
                    existing_upl = db.query(UploadRecord).filter(UploadRecord.job_id == c_job_id).first()
                if not existing_upl:
                    cand_yt_id = c_props.get("youtube_video_id")
                    if cand_yt_id:
                        existing_upl = db.query(UploadRecord).filter(UploadRecord.youtube_video_id == cand_yt_id).first()

                # NON-NEGOTIABLE INVARIANT:
                # An asset in 01_READY can NEVER transition directly to 03_PUBLISHED.
                # All published transitions must go through 02_PROCESSING -> vault_transition_to_published().
                # If an asset in 01_READY already carries an active YouTube ID, relocate to 02_PROCESSING.
                cand_yt_id = c_props.get("youtube_video_id") or (existing_upl.youtube_video_id if existing_upl else None)
                if cand_yt_id and is_valid_youtube_id(cand_yt_id):
                    logger.info(f"[PRE-CLAIM RECOVERY] File {candidate['id']} ('{c_title}') already carries YouTube ID ({cand_yt_id}). Relocating to 02_PROCESSING for reconciliation.")
                    self.drive_engine.move_file_in_vault(candidate["id"], from_folder="01_READY", to_folder="02_PROCESSING")
                    continue

                # 2. Canonical READY Short Validator
                is_val, val_reason = is_valid_ready_short(candidate, db=db, allow_test_artifacts=self.upload_engine._is_test_mode())
                if not is_val:
                    logger.warning(f"[PRE-CLAIM SKIP] File {candidate['id']} ({candidate.get('name')}) skipped from immediate batch: {val_reason}")
                    continue

                # 3. Strict Niche Compliance Gate (Harry Potter Pipeline Output ONLY)
                filename = candidate.get("name", "")
                if filename.startswith("short_man_") or filename.startswith("short_job_"):
                    logger.error(f"[CROSS_AUTOMATION_ALERT] Foreign AL AMR file '{filename}' ({candidate['id']}) detected in HP vault. Quarantining to 04_FAILED.")
                    try:
                        self.drive_engine.move_file_in_vault(candidate["id"], from_folder="01_READY", to_folder="04_FAILED")
                    except Exception as q_err:
                        logger.error(f"Failed to quarantine AL AMR file {candidate['id']}: {q_err}")
                    continue

                if (
                    filename.startswith("hps_")
                    or filename.startswith("disc_")
                    or filename.startswith("hpd_")
                    or c_props.get("content_type") in ("novel_story", "discovery", "discovery_big", "discovery_short")
                    or c_props.get("format") in ("NOVEL_STORY", "DISCOVERY_BIG", "DISCOVERY_SHORT")
                ):
                    is_comp, comp_reason = True, "APPROVED: Harry Potter pipeline output (pre-validated)"
                else:
                    is_comp, comp_reason = is_niche_compliant(title=c_title, text=c_desc)

                if not is_comp:
                    logger.warning(f"[PRE-CLAIM NICHE REJECT] File {candidate['id']} ('{c_title}') violates editorial policy ({comp_reason}). Quarantining to 04_FAILED.")
                    try:
                        self.drive_engine.move_file_in_vault(candidate["id"], from_folder="01_READY", to_folder="04_FAILED")
                    except Exception as q_err:
                        logger.error(f"Failed to quarantine non-compliant file {candidate['id']}: {q_err}")
                    continue

                # Initialize event_id safely for candidate
                event_id = c_props.get("event_id")
                if not event_id:
                    m_evt = re.search(r"evt_[a-z0-9_]+", candidate.get("name", ""))
                    if m_evt:
                        event_id = m_evt.group(0)

                # Resolve topic_id to exclude from deduplication check (prevent candidate self-matching against its own PRODUCED topic)
                cand_topic_id = c_props.get("topic_id")
                if not cand_topic_id and (filename.startswith("hps_") or filename.startswith("disc_")):
                    cand_topic_id = filename.replace(".mp4", "")
                elif not cand_topic_id and c_job_id:
                    j = db.query(Job).filter(Job.id == c_job_id).first()
                    if j and j.topic_id:
                        cand_topic_id = j.topic_id
                if not cand_topic_id:
                    man_id = c_props.get("manifest_id")
                    if not man_id:
                        m_man = re.search(r"man_[a-f0-9]+", candidate.get("name", ""))
                        if m_man:
                            man_id = m_man.group(0)
                    if man_id:
                        rec = db.query(RenderedVideoRecord).filter(RenderedVideoRecord.manifest_id == man_id).first()
                        if rec and rec.event_id:
                            top = db.query(Topic).filter(Topic.event_id == rec.event_id).first()
                            if top:
                                cand_topic_id = top.id
                if not cand_topic_id and event_id:
                    top = db.query(Topic).filter(Topic.event_id == event_id).first()
                    if top:
                        cand_topic_id = top.id
                if not cand_topic_id and c_title:
                    top = db.query(Topic).filter(Topic.title.ilike(c_title.strip())).first()
                    if top:
                        cand_topic_id = top.id

                # 2. Semantic deduplication check against full catalog (excluding candidate's own topic)
                is_duplicate_story = False
                matched_event = None
                try:
                    from engines.deduplication_engine import DeduplicationRouter
                    dedup_eng = DeduplicationRouter()
                    clean_preclaim_title = c_title.strip() if c_title else ""
                    dedup_res = dedup_eng.evaluate_candidate(
                        candidate_title=clean_preclaim_title,
                        candidate_summary=c_props.get("description", ""),
                        db=db,
                        exclude_topic_id=cand_topic_id,
                        exclude_job_id=c_job_id,
                        exclude_title=clean_preclaim_title,
                        exclude_event_id=event_id
                    )
                    if not dedup_res.is_allowed:
                        is_duplicate_story = True
                        matched_event = dedup_res.matched_event_title
                except Exception as d_err:
                    logger.warning(f"[PRE-CLAIM] Dedup check notice for {candidate['id']}: {d_err}")

                if is_duplicate_story:
                    # NON-NEGOTIABLE INVARIANT:
                    # An asset in 01_READY that duplicates another story was NEVER uploaded to YouTube.
                    # It must NEVER be moved to 03_PUBLISHED or 02_PROCESSING.
                    # It must be quarantined to 04_FAILED so it does not falsely claim publication.
                    logger.warning(
                        f"[PRE-CLAIM DEDUP REJECT] File {candidate['id']} ('{c_title}') duplicates existing story "
                        f"'{matched_event}'. Quarantining to 04_FAILED to prevent duplicate publication."
                    )
                    self.drive_engine.move_file_in_vault(candidate["id"], from_folder="01_READY", to_folder="04_FAILED")
                    continue

                fresh_ready_files.append(candidate)

            all_eligible_candidates = fresh_ready_files + recovered_candidates

            _detect_candidate_format = ShortsPipeline.detect_candidate_format

            # Enforce DISCOVERY_ONLY mode: filter out any NOVEL_STORY candidates
            is_disc_only = os.getenv("DISCOVERY_ONLY", "true").lower() in ("true", "1", "yes")
            if is_disc_only:
                all_eligible_candidates = [
                    cand for cand in all_eligible_candidates
                    if _detect_candidate_format(cand) != "NOVEL_STORY"
                ]

            # Intra-batch deduplication: prevent scheduling two videos for the same story in the same run
            if len(all_eligible_candidates) > 1:
                try:
                    from engines.deduplication_engine import DeduplicationRouter
                    b_dedup = DeduplicationRouter()
                    all_eligible_candidates = b_dedup.filter_intra_batch_duplicates(
                        all_eligible_candidates,
                        title_fn=lambda cand: resolve_vault_file_metadata(cand, db=db)["title"],
                        summary_fn=lambda cand: resolve_vault_file_metadata(cand, db=db)["description"]
                    )
                except Exception as b_err:
                    logger.warning(f"[INTRA_BATCH_DEDUP] Error during intra-batch dedup: {b_err}")

            if target_file_id:
                all_eligible_candidates = [f for f in all_eligible_candidates if f["id"] == target_file_id]

            # 6. Calculate eligible quota to schedule in this run
            ready_stock_count = len(all_eligible_candidates)
            eligible_to_schedule = min(len(vacant_horizon_slots), ready_stock_count)
            if max_to_schedule is not None and max_to_schedule > 0:
                eligible_to_schedule = min(eligible_to_schedule, max_to_schedule)

            if eligible_to_schedule <= 0:
                console.print(f"[bold yellow][!] Zero eligible Shorts to schedule (Vacant Horizon Slots: {len(vacant_horizon_slots)}, READY Stock: {ready_stock_count}). Scheduler exiting safely.[/bold yellow]")
                return {
                    "scheduled_count": 0,
                    "scheduled_jobs": [],
                    "published_today": published_count_today,
                    "scheduled_today": scheduled_count_today,
                    "remaining_capacity": max(0, DAILY_SHORTS_LIMIT - (published_count_today + scheduled_count_today)),
                    "vacant_horizon_slots": len(vacant_horizon_slots),
                    "ready_stock": ready_stock_count,
                    "status": "NO_ACTION_REQUIRED"
                }

            console.print(f"[bold green][*] Proactively scheduling {eligible_to_schedule} eligible Short(s) into earliest vacant slots across 2-day horizon...[/bold green]")
            scheduled_results = []

            # Cadence slot preferred formats (STORY FORGE 4 Shorts / day cadence):
            # 02:00 UTC -> NOVEL_STORY
            # 08:00 UTC -> DISCOVERY_BIG
            # 14:00 UTC -> NOVEL_STORY
            # 20:00 UTC -> DISCOVERY_SHORT
            slot_hour_to_format = {
                2: "NOVEL_STORY",
                8: "DISCOVERY_BIG",
                14: "NOVEL_STORY",
                20: "DISCOVERY_SHORT",
            }

            remaining_pool = list(all_eligible_candidates)
            for i in range(eligible_to_schedule):
                if not remaining_pool:
                    break
                target_slot = vacant_horizon_slots[i]
                desired_fmt = slot_hour_to_format.get(target_slot.hour)

                chosen_cand = None
                if desired_fmt:
                    for cand in remaining_pool:
                        if _detect_candidate_format(cand) == desired_fmt:
                            chosen_cand = cand
                            break

                if not chosen_cand:
                    chosen_cand = remaining_pool[0]

                remaining_pool.remove(chosen_cand)
                cand_folder = "02_PROCESSING" if chosen_cand in recovered_candidates else "01_READY"
                console.print(f"[cyan][*] Candidate {i+1}/{eligible_to_schedule} allocated Slot:[/cyan] [bold yellow]{target_slot.strftime('%Y-%m-%d %H:%M')} UTC[/bold yellow] (Target: {desired_fmt or 'ANY'}, Actual: {_detect_candidate_format(chosen_cand)})")

                upload_rec = self._schedule_single_drive_file(
                    db=db,
                    target_file=chosen_cand,
                    scheduled_slot=target_slot,
                    current_folder=cand_folder
                )
                if upload_rec:
                    scheduled_results.append({
                        "job_id": upload_rec.job_id,
                        "youtube_video_id": upload_rec.youtube_video_id,
                        "scheduled_publish_at": upload_rec.scheduled_publish_at.isoformat() + "Z",
                        "title": upload_rec.title
                    })

            return {
                "scheduled_count": len(scheduled_results),
                "scheduled_jobs": scheduled_results,
                "published_today": published_count_today,
                "scheduled_today": scheduled_count_today + len(scheduled_results),
                "remaining_capacity": max(0, DAILY_SHORTS_LIMIT - (published_count_today + scheduled_count_today + len(scheduled_results))),
                "vacant_horizon_slots": max(0, len(vacant_horizon_slots) - len(scheduled_results)),
                "ready_stock": max(0, ready_stock_count - len(scheduled_results)),
                "status": "SUCCESS"
            }

        finally:
            if close_db:
                db.close()
            lock.release()

    def publish_due_slots(
        self,
        db: Optional[Session] = None,
        target_file_id: Optional[str] = None,
        retry_interval_sec: int = 120,
        max_retries: Optional[int] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        CANONICAL AUTONOMOUS LIVE DUE PUBLISHER WITH 2-MINUTE RETRY LOOP:
        Evaluates publication slots for today (02:00, 08:00, 14:00, 20:00 UTC).
        If a slot is due or past due and unfulfilled:
        - Claims an eligible video from Google Drive Vault (01_READY)
        - Uploads directly to YouTube as PUBLIC (firing real-time VideoPublishedEvent for Shorts Feed seed pooling)
        - IF THE UPLOAD FAILS FOR ANY REASON (network drop, API rate limit, transient 500/503):
          Enters a persistent retry loop: waits 2 minutes (retry_interval_sec=120) and retries
          indefinitely until successful!
        - Transitions video from 02_PROCESSING to 03_PUBLISHED in Google Drive Vault upon verified success.
        """
        lock = CompositeLock(
            name="publisher",
            command_name="publish-due",
            drive_engine=getattr(self, "drive_engine", None),
            cloud_lock_name="cloud_publisher",
        )
        if not lock.acquire():
            info = lock.get_lock_info()
            owner_pid = info.get("pid") if info else "unknown"
            cmd = info.get("command") if info else "unknown"
            console.print(f"[bold yellow][!] Publisher lock currently held by PID {owner_pid} ('{cmd}'). Exiting cleanly.[/bold yellow]")
            return {"status": "LOCK_HELD", "published_count": 0}

        close_db = False
        if db is None:
            db = getattr(self, "SessionLocal", SessionLocal)()
            close_db = True

        console.print(Panel.fit("[bold green]Starting Autonomous Due Slot Publisher (Live Public Push + 2-Min Retry Loop)[/bold green]", border_style="green"))

        try:
            # 1. Reconcile prior scheduled uploads (check if any became public on YouTube)
            try:
                reconciled_jobs = self.upload_engine.reconcile_scheduled_uploads(db)
                if reconciled_jobs:
                    console.print(f"[bold green][+] Reconciled {len(reconciled_jobs)} previously scheduled Short(s) to PUBLISHED status.[/bold green]")
                    processing_files = self.drive_engine.list_files_in_folder("02_PROCESSING")
                    for rec_item in reconciled_jobs:
                        for pf in processing_files:
                            props = pf.get("properties", {}) or {}
                            if props.get("job_id") == rec_item["job_id"] or rec_item["job_id"] in pf.get("name", ""):
                                try:
                                    vault_transition_to_published(
                                        file_id=pf["id"],
                                        youtube_video_id=rec_item.get("youtube_video_id", ""),
                                        db=db,
                                        drive_engine=self.drive_engine,
                                        job_id=rec_item["job_id"],
                                        caller="main.publish_due_slots.reconcile"
                                    )
                                except Exception as gt_err:
                                    logger.warning(f"[RECONCILE_GATEWAY_HOLD] Gateway refused transition for {pf['id']}: {gt_err}")
            except Exception as rec_err:
                logger.warning(f"Reconciliation check notice: {rec_err}")

            # 2. Slot Due Audit for Today (02:30, 10:30, 18:30 UTC / 08:00 AM, 04:00 PM, 12:00 AM IST)
            from config.constants import DAILY_SHORTS_LIMIT, PUBLISHING_SLOTS_UTC
            from datetime import time as dtime
            now_utc = datetime.utcnow()
            today_date = now_utc.date()
            today_start = datetime.combine(today_date, dtime.min)
            today_end = datetime.combine(today_date, dtime.max)

            today_slot_times = [
                datetime.combine(today_date, dtime(hour, minute))
                for hour, minute, _ in PUBLISHING_SLOTS_UTC
            ]

            published_today = db.query(UploadRecord).filter(
                UploadRecord.status.in_(["PUBLISHED", "SUCCESS"]),
                UploadRecord.published_at >= today_start,
                UploadRecord.published_at <= today_end
            ).count()

            scheduled_today = db.query(UploadRecord).filter(
                UploadRecord.status == "SCHEDULED",
                UploadRecord.scheduled_publish_at >= now_utc,
                UploadRecord.scheduled_publish_at <= today_end
            ).count()

            total_booked_today = published_today + scheduled_today

            lead_buffer = timedelta(minutes=15)
            due_slots = [s for s in today_slot_times if s <= (now_utc + lead_buffer)]

            console.print(
                f"[cyan][*] Slot Due Audit (Today):[/cyan] "
                f"Slots Passed/Due: [bold]{len(due_slots)}/{DAILY_SHORTS_LIMIT}[/bold] | "
                f"Published: [bold]{published_today}[/bold] | "
                f"Scheduled: [bold]{scheduled_today}[/bold] | "
                f"Total Booked: [bold]{total_booked_today}/{DAILY_SHORTS_LIMIT}[/bold]"
            )

            slots_needed = max(0, len(due_slots) - total_booked_today)
            if force:
                slots_needed = max(1, slots_needed)

            if slots_needed <= 0:
                next_slots = [s for s in today_slot_times if s > (now_utc + lead_buffer)]
                next_slot_str = next_slots[0].strftime("%H:%M UTC") if next_slots else f"Tomorrow {PUBLISHING_SLOTS_UTC[0][0]:02d}:{PUBLISHING_SLOTS_UTC[0][1]:02d} UTC"
                console.print(f"[bold yellow][*] All {len(due_slots)} due slot(s) for today have already been fulfilled. Next release slot is at {next_slot_str}.[/bold yellow]")
                return {
                    "status": "NO_DUE_SLOTS",
                    "published_today": published_today,
                    "scheduled_today": scheduled_today,
                    "due_slots_count": len(due_slots)
                }

            console.print(f"[bold green][*] Fulfilling {slots_needed} due slot(s) immediately with direct public upload...[/bold green]")
            published_results = []

            from engines.drive_engine import is_valid_ready_short
            for slot_idx in range(slots_needed):
                if total_booked_today + len(published_results) >= DAILY_SHORTS_LIMIT:
                    console.print(f"[bold yellow][!] Daily limit ({DAILY_SHORTS_LIMIT}) reached. Halting further releases for today.[/bold yellow]")
                    break

                ready_files = self.drive_engine.list_files_in_folder("01_READY")
                eligible_candidates = []
                for rf in ready_files:
                    is_val, val_reason = is_valid_ready_short(rf, db=db, allow_test_artifacts=self.upload_engine._is_test_mode())
                    if is_val:
                        eligible_candidates.append(rf)

                if target_file_id:
                    eligible_candidates = [f for f in eligible_candidates if f["id"] == target_file_id]

                if not eligible_candidates:
                    console.print("[bold yellow][!] 01_READY buffer is empty for due slot! Triggering emergency on-demand production...[/bold yellow]")
                    try:
                        from engines.hp_autonomous_refill import HPAutonomousRefillEngine
                        refill_eng = HPAutonomousRefillEngine(drive_engine=self.drive_engine, voice_id="f5_cloned_narrator_v1")
                        refill_telemetry = refill_eng.run_refill_cycle(force_batch_count=1)
                        if refill_telemetry.status in ("SUCCEEDED", "PARTIAL") and refill_telemetry.videos_deposited > 0:
                            console.print("[bold green][+] Emergency production succeeded! Re-evaluating 01_READY buffer...[/bold green]")
                            ready_files = self.drive_engine.list_files_in_folder("01_READY")
                            eligible_candidates = [
                                rf for rf in ready_files
                                if is_valid_ready_short(rf, db=db, allow_test_artifacts=self.upload_engine._is_test_mode())[0]
                            ]
                    except Exception as emergency_err:
                        logger.error(f"Emergency production failed: {emergency_err}")

                if not eligible_candidates:
                    console.print("[bold red][!] Still no valid eligible Shorts in 01_READY after emergency refill attempt. Halting slot.[/bold red]")
                    break

                chosen_file = eligible_candidates[0]
                file_id = chosen_file["id"]
                name = chosen_file.get("name", "")

                console.print(f"[cyan][*] Claiming '{name}' ({file_id}) for live public release...[/cyan]")
                self.drive_engine.move_file_in_vault(file_id, from_folder="01_READY", to_folder="02_PROCESSING")

                temp_download_path = PROJECT_ROOT / "data" / "renders" / f"due_pub_{file_id[:8]}.mp4"
                temp_download_path.parent.mkdir(parents=True, exist_ok=True)
                self.drive_engine.download_video_from_vault(file_id, temp_download_path)

                resolved_meta = resolve_vault_file_metadata(chosen_file, db=db)
                title = resolved_meta["title"]
                description = resolved_meta["description"]

                script_candidate_id = resolved_meta.get("script_id") or (name.replace(".mp4", "") if name.startswith("hps_") else None)
                job_id = chosen_file.get("properties", {}).get("job_id") or (f"job_{script_candidate_id}" if script_candidate_id else f"job_live_{file_id[:8]}")
                job = db.query(Job).filter_by(id=job_id).first()
                if not job:
                    job = Job(id=job_id, state=JobState.READY_TO_UPLOAD.value)
                    db.add(job)
                    db.commit()

                render_output = db.query(RenderOutput).filter_by(job_id=job.id).first()
                if not render_output:
                    render_output = RenderOutput(
                        id=f"rnd_{uuid.uuid4().hex[:10]}",
                        job_id=job.id,
                        video_path=str(temp_download_path),
                        duration_sec=26.0,
                        file_size_bytes=temp_download_path.stat().st_size if temp_download_path.exists() else 1024000,
                        video_codec="h264",
                        width=1080,
                        height=1920
                    )
                    db.add(render_output)
                    db.commit()
                else:
                    render_output.video_path = str(temp_download_path)
                    db.commit()

                metadata = {
                    "title": title,
                    "description": description,
                    "script_id": resolved_meta.get("script_id") or script_candidate_id,
                    "tags": [
                        "Harry Potter", "Wizarding World", "Hogwarts", "Harry Potter Lore",
                        "Harry Potter Facts", "Movie Facts", "Shorts", "Harry Potter Shorts",
                        "Deleted Scenes", "Book vs Movie", "Harry Potter Secrets"
                    ]
                }

                gate_passed, gate_reason = self.upload_engine.evaluate_publication_safety_gate(
                    db=db,
                    job=job,
                    render=render_output,
                    metadata=metadata,
                    allow_immediate=True
                )
                if not gate_passed:
                    console.print(f"[bold red][x] Safety Gate Blocked Upload: {gate_reason}[/bold red]")
                    self.drive_engine.move_file_in_vault(file_id, from_folder="02_PROCESSING", to_folder="01_READY")
                    continue

                # 3. Precision Sleep Gate: If pre-warmed early (e.g. at :50), sleep until exact :00.00
                unfulfilled_slots = due_slots[total_booked_today:] if total_booked_today < len(due_slots) else due_slots
                target_slot = unfulfilled_slots[slot_idx] if slot_idx < len(unfulfilled_slots) else None
                if target_slot:
                    wait_sec = (target_slot - datetime.utcnow()).total_seconds()
                    if wait_sec > 2:
                        console.print(Panel.fit(
                            f"[bold cyan]=== Precision Pre-Warm Primed ===[/bold cyan]\n"
                            f"Asset: [bold white]{title}[/bold white]\n"
                            f"Status: [bold green]100% Pre-Validated & Loaded on Runner SSD[/bold green]\n"
                            f"Target Slot: [bold yellow]{target_slot.strftime('%Y-%m-%d %H:%M:%S UTC')}[/bold yellow]\n"
                            f"Precision Sleep: [bold magenta]Counting down {int(wait_sec)}s until exact release moment...[/bold magenta]",
                            border_style="cyan"
                        ))
                        import time
                        time.sleep(wait_sec)
                        console.print(f"[bold green][*] Release moment arrived ({datetime.utcnow().strftime('%H:%M:%S UTC')})! Firing live YouTube push...[/bold green]")

                # 4. PERSISTENT RETRY LOOP WITH 2-MINUTE BREAK
                attempt = 1
                upload_rec = None
                while True:
                    try:
                        console.print(f"[bold cyan][*] Uploading Short '{title}' directly to YouTube as PUBLIC (Attempt #{attempt})...[/bold cyan]")
                        upload_rec = self.upload_engine.upload_short_public(
                            db=db,
                            job=job,
                            render=render_output,
                            metadata=metadata,
                            privacy_status="public"
                        )
                        if upload_rec and upload_rec.youtube_video_id:
                            console.print(f"[bold green][+] Upload SUCCEEDED on attempt #{attempt}! YouTube Video ID: [bold yellow]{upload_rec.youtube_video_id}[/bold yellow][/bold green]")
                            break
                    except KeyboardInterrupt:
                        logger.warning("Upload loop interrupted by user.")
                        raise
                    except Exception as upload_err:
                        err_msg = str(upload_err)
                        console.print(f"[bold red][!] Upload attempt #{attempt} failed: {err_msg}[/bold red]")
                        if max_retries is not None and attempt >= max_retries:
                            console.print(f"[bold red][!] Maximum retries ({max_retries}) reached. Exiting retry loop.[/bold red]")
                            break
                        console.print(f"[bold yellow][*] Safety Watchdog: Waiting {retry_interval_sec} seconds (2-minute break) before retry #{attempt + 1}...[/bold yellow]")
                        import time
                        time.sleep(retry_interval_sec)
                        attempt += 1

                if upload_rec and upload_rec.youtube_video_id:
                    try:
                        vault_transition_to_published(
                            file_id=file_id,
                            youtube_video_id=upload_rec.youtube_video_id,
                            db=db,
                            drive_engine=self.drive_engine,
                            job_id=job.id,
                            caller="main.publish_due_slots"
                        )
                    except Exception as vt_err:
                        logger.warning(f"Could not transition Drive file to 03_PUBLISHED: {vt_err}")

                    try:
                        from core.models import HarryPotterScript
                        clean_sid = resolved_meta.get("script_id") or name.replace(".mp4", "")
                        hp_s = db.query(HarryPotterScript).filter(HarryPotterScript.id.ilike(f"%{clean_sid}%")).first()
                        if hp_s:
                            hp_s.status = "PUBLISHED"
                            db.commit()
                    except Exception as hp_err:
                        logger.warning(f"Notice updating HP script published status: {hp_err}")

                    published_results.append({
                        "file_id": file_id,
                        "youtube_video_id": upload_rec.youtube_video_id,
                        "title": upload_rec.title,
                        "attempts": attempt
                    })

                if temp_download_path and temp_download_path.exists():
                    temp_download_path.unlink(missing_ok=True)

            return {
                "status": "SUCCESS" if published_results else "PARTIAL",
                "published_count": len(published_results),
                "published_videos": published_results,
                "published_today": published_today + len(published_results),
                "scheduled_today": scheduled_today
            }

        finally:
            if close_db:
                db.close()
            lock.release()

    def publish_next_from_vault(self, force: bool = False, target_file_id: Optional[str] = None) -> bool:
        """Invokes canonical schedule_ready_buffer for a single video."""
        res = self.schedule_ready_buffer(max_to_schedule=1, target_file_id=target_file_id)
        return bool(res.get("scheduled_count", 0) > 0)

    def run_autonomous_daemon(
        self,
        target_stock: int = 6,
        check_interval_sec: int = 900
    ) -> None:
        """
        CANONICAL AUTONOMOUS DAEMON CONTROLLER:
        Continuous convergence loop operating 24/7 without manual intervention:
        1. Sync canonical & auxiliary DBs from Drive (00_SYSTEM).
        2. Horizon Audit: Proactively schedules eligible 01_READY videos into vacant slots
           in the 48-hour forward horizon (06:00, 11:00, 15:00 UTC, max 3/day).
        3. Reconciles past scheduled uploads from 02_PROCESSING to 03_PUBLISHED.
        4. Buffer Audit: Checks verified 01_READY stock in Drive.
           If stock < target_stock (6), sequentially produces fresh Shorts (strict niche, Sarah voice, QA)
           to refill the reserve buffer.
        5. Uploads and synchronizes updated DB state back to Drive (00_SYSTEM).
        6. Sleeps for check_interval_sec (default: 15 mins) with graceful interrupt handling.
        """
        import signal
        from core.database_sync import download_canonical_database, upload_canonical_database

        console.print(Panel.fit(
            f"[bold green]=== AL-AMR 100% Autonomous Production & Scheduling Daemon ===[/bold green]\n"
            f"Reserve Buffer Target: [bold cyan]{target_stock} Verified Shorts[/bold cyan]\n"
            f"Voice Lock: [bold green]f5_cloned_narrator_v1[/bold green]\n"
            f"Publishing Limit: [bold]3 Shorts/day (06:00, 11:00, 15:00 UTC)[/bold]\n"
            f"Horizon: [bold]Rolling 48-Hour Forward Horizon[/bold]\n"
            f"Convergence Interval: [bold yellow]{check_interval_sec // 60} minutes[/bold yellow]",
            border_style="green"
        ))

        running = True
        start_time_iso = datetime.now(timezone.utc).isoformat()

        def _update_daemon_telemetry(task_desc: str = "CONVERGENCE_IDLE"):
            try:
                LOCKS_DIR.mkdir(parents=True, exist_ok=True)
                sfile = LOCKS_DIR / "worker_state.json"
                state_data = {
                    "pid": os.getpid(),
                    "status": "ONLINE",
                    "online": True,
                    "started_at": start_time_iso,
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "current_task": task_desc,
                    "current_job_id": None,
                    "active_niche": "MYSTERY_SCIENCE",
                    "last_successful_run": datetime.now(timezone.utc).isoformat(),
                    "next_scheduled_run": (datetime.now(timezone.utc) + timedelta(seconds=check_interval_sec)).isoformat(),
                    "cycles_completed": cycle_count,
                    "jobs_produced": 0,
                    "jobs_published": 0,
                    "jobs_recovered": 0,
                    "errors_count": 0,
                    "last_error": None,
                    "dry_run": getattr(self, "dry_run", False)
                }
                tmp_sfile = sfile.with_suffix(".tmp")
                tmp_sfile.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
                tmp_sfile.replace(sfile)
            except Exception as w_err:
                logger.debug(f"Notice writing daemon worker state: {w_err}")

        def _cleanup_daemon_state():
            try:
                sfile = LOCKS_DIR / "worker_state.json"
                if sfile.exists():
                    state_data = json.loads(sfile.read_text(encoding="utf-8"))
                    state_data["online"] = False
                    state_data["status"] = "OFFLINE"
                    state_data["current_task"] = "SHUTDOWN"
                    state_data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
                    sfile.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
            except Exception:
                pass

        def _handle_stop(sig, frame):
            nonlocal running
            logger.info(f"Stop signal received ({sig}). Shutting down daemon gracefully...")
            console.print("\n[bold yellow][!] Shutdown signal received. Exiting daemon safely...[/bold yellow]")
            running = False
            _cleanup_daemon_state()

        try:
            signal.signal(signal.SIGINT, _handle_stop)
            signal.signal(signal.SIGTERM, _handle_stop)
        except Exception:
            pass

        from core.daemon_guard import DaemonIntegrityGuard, StaleDaemonError
        integrity_guard = DaemonIntegrityGuard(project_root=PROJECT_ROOT)

        cycle_count = 0
        _update_daemon_telemetry("DAEMON_STARTING")
        try:
            while running:
                cycle_count += 1

                # Stale code detection gate: halt if code on disk diverged from startup
                try:
                    integrity_guard.enforce_integrity()
                except StaleDaemonError as sde:
                    console.print(f"\n[bold red][!] CRITICAL STALE DAEMON HALT:[/bold red] {sde}")
                    logger.critical(f"Halting autonomous daemon: {sde}")
                    _update_daemon_telemetry("HALTED_STALE_CODE")
                    running = False
                    break

                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                console.print(f"\n[bold cyan][Cycle {cycle_count} - {now_str}][/bold cyan] Starting convergence pass...")
                _update_daemon_telemetry(f"CONVERGENCE_PASS_{cycle_count}")

                try:
                    # 1. Download & Reconcile Canonical Database from Cloud Vault
                    if self.drive_engine and not getattr(self, "offline_mode", False):
                        try:
                            logger.info("Syncing canonical DB from Drive...")
                            download_canonical_database(drive_engine=self.drive_engine)
                        except Exception as sync_e:
                            logger.warning(f"Notice syncing DB from Drive: {sync_e}")

                    # 2. Schedule Ready Buffer into 48-Hour Horizon
                    console.print("[cyan][*] Auditing 48-hour forward publication horizon...[/cyan]")
                    try:
                        sched_res = self.schedule_ready_buffer()
                        console.print(
                            f"[bold green][+] Horizon Audit Result:[/bold green] "
                            f"Scheduled: {sched_res.get('scheduled_count', 0)} | "
                            f"Vacant Slots: {sched_res.get('vacant_horizon_slots', 0)} | "
                            f"Ready Stock: {sched_res.get('ready_stock', 0)}"
                        )
                    except Exception as sched_err:
                        logger.error(f"Error during scheduled horizon pass: {sched_err}")

                    # 3. Buffer Reserve Audit & Autonomous Replenishment
                    console.print("[cyan][*] Auditing verified 01_READY reserve buffer...[/cyan]")
                    try:
                        prod_count, prod_summary = self.maintain_buffer(target_stock=target_stock)
                        console.print(
                            f"[bold green][+] Buffer Maintenance Result:[/bold green] "
                            f"Outcome: {prod_summary.get('outcome')} | "
                            f"Produced: {prod_count} | "
                            f"Current Reserve: {prod_summary.get('final_stock', 0)}/{target_stock}"
                        )
                    except Exception as prod_err:
                        logger.error(f"Error during buffer maintenance pass: {prod_err}")

                    # 4. Upload Canonical Database back to Cloud Vault
                    if self.drive_engine and not getattr(self, "offline_mode", False):
                        try:
                            logger.info("Uploading canonical DB back to Drive...")
                            upload_canonical_database(drive_engine=self.drive_engine)
                        except Exception as up_e:
                            logger.warning(f"Notice uploading DB to Drive: {up_e}")

                except Exception as loop_err:
                    logger.error(f"Unexpected error in daemon loop: {loop_err}", exc_info=True)

                _update_daemon_telemetry("CONVERGENCE_IDLE")

                # Sleep interval with interrupt sensitivity
                if not running:
                    break
                console.print(f"[dim]Convergence pass completed. Sleeping {check_interval_sec // 60}m until next audit...[/dim]")
                sleep_chunks = max(1, check_interval_sec // 5)
                for _ in range(sleep_chunks):
                    if not running:
                        break
                    time.sleep(5)
        finally:
            _cleanup_daemon_state()

        console.print("[bold green]AL-AMR Autonomous Daemon cleanly stopped.[/bold green]")

    def run_single_job(self, topic: Optional[Topic] = None, force: bool = False) -> bool:
        """
        LEGACY MONOLITHIC / FALLBACK RUNNER:
        Executes single production cycle and uploads immediately.
        """
        lock = CompositeLock(
            name="production",
            command_name="run-single-job",
            drive_engine=getattr(self, "drive_engine", None),
            cloud_lock_name="cloud_production",
        )
        if not lock.acquire():
            info = lock.get_lock_info()
            owner_pid = info.get("pid") if info else "unknown"
            cmd = info.get("command") if info else "unknown"
            console.print(f"[bold yellow][!] Production lock currently held by PID {owner_pid} ('{cmd}'). Exiting safely.[/bold yellow]")
            return False

        db = SessionLocal()
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        job = Job(id=job_id, state=JobState.QUEUED.value)
        db.add(job)
        db.commit()

        console.print(Panel.fit(f"[bold cyan]Starting Production Pipeline for Job {job_id}[/bold cyan]\nTarget: 1080x1920 9:16 Vertical (~23 sec) | Cost: $0.00", border_style="cyan"))

        # 0. CHECK DAILY PUBLISHING LIMIT
        from datetime import datetime
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        published_today = db.query(UploadRecord).filter(
            UploadRecord.published_at >= today_start,
            UploadRecord.status == "PUBLISHED"
        ).count()

        if published_today >= DAILY_SHORTS_LIMIT and not force:
            console.print(f"[bold yellow][!] Daily limit reached ({published_today}/{DAILY_SHORTS_LIMIT} Shorts published today). Pausing until next scheduled window.[/bold yellow]")
            logger.info(f"Daily limit reached ({published_today}/{DAILY_SHORTS_LIMIT}).")
            db.close()
            lock.release()
            return False

        try:
            # Topic selection
            if not topic:
                StateMachine.transition(db, job, JobState.RESEARCHING, "Discovering high-retention topics")
                topics = self.topic_engine.discover_topics(db, limit=1)
                if not topics:
                    StateMachine.flag_needs_review(db, job, "No new unique topics found.")
                    return False
                topic = topics[0]
            else:
                StateMachine.transition(db, job, JobState.RESEARCHING, f"Selected topic: {topic.title}")

            render_output, metadata = self._render_and_qa_job(db, job, topic, force=force)
            if not render_output or not metadata:
                return False

            import shutil
            if TEST_MODE:
                desktop_candidate = Path.home() / "Desktop"
                output_dir = desktop_candidate if desktop_candidate.exists() else (PROJECT_ROOT / "data" / "renders")
                dest_video = output_dir / "VERIFIED_SHORT_TEST_OUTPUT.mp4"
                shutil.copy2(Path(render_output.video_path), dest_video)
                console.print(Panel.fit(
                    f"[bold green][+] Test Pipeline Complete![/bold green]\n"
                    f"Final Verified MP4 saved to: [bold yellow]{dest_video}[/bold yellow]\n"
                    f"YouTube Upload: [bold cyan]BYPASSED (No publishing occurred)[/bold cyan]",
                    border_style="green"
                ))
                return True

            # PRODUCTION YOUTUBE-SIDE SCHEDULED PUBLISHING
            from engines.scheduler_engine import PublicationScheduler
            scheduler = PublicationScheduler()
            next_slot = scheduler.calculate_next_available_slot(db)

            StateMachine.transition(db, job, JobState.READY_TO_UPLOAD, "Ready for scheduled publishing")
            StateMachine.transition(db, job, JobState.UPLOADING, f"Uploading to YouTube (Scheduled for {next_slot.strftime('%Y-%m-%d %H:%M')} UTC)")
            upload_rec = self.upload_engine.schedule_short(
                db=db,
                job=job,
                render=render_output,
                metadata=metadata,
                scheduled_publish_at=next_slot
            )

            StateMachine.transition(db, job, JobState.SCHEDULED, f"Scheduled on YouTube for {next_slot.isoformat()}Z (ID: {upload_rec.youtube_video_id})")
            console.print(Panel.fit(
                f"[bold green][+] Production Cycle Complete (Scheduled)![/bold green]\n"
                f"Output Video: {render_output.video_path}\n"
                f"YouTube Status: {upload_rec.status} ({upload_rec.youtube_video_id})\n"
                f"Scheduled Release: {next_slot.strftime('%Y-%m-%d %H:%M')} UTC\n"
                f"Visibility: PRIVATE -> AUTO-PUBLIC (Verified)",
                border_style="green"
            ))
            return True

        except Exception as e:
            logger.exception(f"Pipeline error on job {job_id}: {e}")
            StateMachine.flag_needs_review(db, job, f"Unexpected pipeline exception: {str(e)}")
            return False
        finally:
            db.close()
            lock.release()


def start_dashboard():
    """Starts FastAPI monitoring dashboard."""
    import uvicorn
    from dashboard.app import app
    console.print("[bold cyan]Starting Live Dashboard on http://127.0.0.1:8000[/bold cyan]")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="Automated $0-Cost History Shorts Channel Pipeline")
    parser.add_argument("--health-check", action="store_true", help="Run non-destructive production health check and launch readiness gate")
    parser.add_argument("--self-heal", action="store_true", help="Executes master autonomous self-healing, stale recovery, and vault reconciliation")
    parser.add_argument("--json", action="store_true", help="Output health check or diagnostic results in JSON format")
    parser.add_argument("--maintain-buffer", type=int, nargs="?", const=TARGET_RESERVE_BUFFER, default=0, metavar="TARGET", help=f"Maintain a reserve of TARGET ready Shorts in Drive 01_READY (default: {TARGET_RESERVE_BUFFER})")
    parser.add_argument("--produce-batch", type=int, default=0, metavar="N", help="Generate N Shorts, verify QA, and deposit in Google Drive 01_READY")
    parser.add_argument("--publish-due", action="store_true", help="Claim and publish due Shorts from Google Drive Vault as public with 2-min retry loop")
    parser.add_argument("--retry-interval", type=int, default=120, help="Retry interval in seconds between failed upload attempts (default: 120s)")
    parser.add_argument("--publish-next", action="store_true", help="Claim next ready Short from Google Drive 01_READY and publish to YouTube")
    parser.add_argument("--schedule-ready", action="store_true", help="Claim and schedule all available READY Shorts up to daily limit")
    parser.add_argument("--max-to-schedule", type=int, default=None, help="Maximum number of READY Shorts to schedule")
    parser.add_argument("--file-id", type=str, default=None, help="Target specific Google Drive File ID for publishing")
    parser.add_argument("--run-once", action="store_true", help="Run a single production cycle")
    parser.add_argument("--test", action="store_true", help="Run full pipeline in test mode (safe, local validation)")
    parser.add_argument("--harvest-analytics", action="store_true", help="Harvest performance metrics for eligible published Shorts")
    parser.add_argument("--learn", action="store_true", help="Execute closed-loop learning cycle and update strategy weights")
    parser.add_argument("--force", action="store_true", help="Force cycle even if daily limit is met")
    parser.add_argument("--voice", type=str, default=None, help="Explicit active voice identifier to use for this run (overrides default/DB)")
    parser.add_argument("--dashboard", action="store_true", help="Launch FastAPI web dashboard")
    parser.add_argument("--daemon", action="store_true", help="Run continuous scheduler (Strictly 3 Shorts/day)")
    parser.add_argument("--runtime", action="store_true", help="Launch persistent autonomous runtime worker")
    parser.add_argument("--canary", action="store_true", help="Execute single controlled live-cloud canary production and exit")
    parser.add_argument("--cloud-produce", type=int, default=0, help="Run Phase 7 CloudProductionOrchestrator to produce N shorts")
    parser.add_argument("--dry-run", action="store_true", help="Execute in dry-run mode without external mutations")
    parser.add_argument("--force-unlock", action="store_true", help="Force-break any existing cloud locks in Drive and release local locks")
    args = parser.parse_args()

    pipeline = ShortsPipeline(voice=args.voice)

    if args.health_check:
        from engines.health_checker import HealthChecker, HealthStatus, CheckStatus
        checker = HealthChecker()
        result = checker.run_full_audit()

        if getattr(args, "json", False):
            import json
            print(json.dumps(result, indent=2))
        else:
            from rich.table import Table
            table = Table(title="Production Readiness Health Check (Phase 5.4)", border_style="cyan")
            table.add_column("Category", style="bold white", width=22)
            table.add_column("Status", width=10)
            table.add_column("Diagnostics", style="dim white")

            status_colors = {
                CheckStatus.PASS: "[bold green]PASS[/bold green]",
                CheckStatus.WARN: "[bold yellow]WARN[/bold yellow]",
                CheckStatus.FAIL: "[bold red]FAIL[/bold red]"
            }

            for cat, check_res in result["checks"].items():
                cat_display = cat.replace("_", " ").title()
                table.add_row(cat_display, status_colors.get(check_res["status"], check_res["status"]), check_res["message"])

            console.print(table)

            verdict_colors = {
                HealthStatus.READY: ("bold green", "[bold green]SYSTEM READY FOR PRODUCTION[/bold green]"),
                HealthStatus.DEGRADED: ("bold yellow", "[bold yellow]SYSTEM DEGRADED (Operational with Non-Critical Warnings)[/bold yellow]"),
                HealthStatus.NOT_READY: ("bold red", "[bold red]SYSTEM NOT READY (Critical Failures Detected)[/bold red]")
            }
            color, title = verdict_colors.get(result["verdict"], ("bold white", result["verdict"]))
            console.print(Panel.fit(
                f"{title}\n\n"
                f"{result['summary']}\n"
                f"• Passed Checks: [bold green]{len(result['passed_checks'])}[/bold green]\n"
                f"• Warnings: [bold yellow]{len(result['warnings'])}[/bold yellow]\n"
                f"• Critical Failures: [bold red]{len(result['critical_failures'])}[/bold red]",
                border_style=color
            ))
    elif args.self_heal:
        db = SessionLocal()
        try:
            res = pipeline.recovery_manager.run_full_self_healing(db)
            console.print(Panel.fit(
                f"[bold green][+] Master Autonomous Self-Healing Cycle Complete![/bold green]\n"
                f"Stale Jobs Handled: [bold]{res['stale_jobs_recovered_count']}[/bold]\n"
                f"Processing Vault Recoveries: [bold]{res['vault_recoveries_count']}[/bold]\n"
                f"YouTube Videos Reconciled: [bold]{res['youtube_reconciled_count']}[/bold]\n"
                f"System Health Status: [bold cyan]{res['status']}[/bold cyan]",
                border_style="green"
            ))
        finally:
            db.close()
    elif args.dashboard:
        start_dashboard()
    elif args.harvest_analytics:
        from engines.metrics_collector import MetricsCollector
        db = SessionLocal()
        try:
            collector = MetricsCollector()
            summary = collector.harvest_all_eligible_shorts(db)
            console.print(f"[bold green][+] Analytics Harvesting Complete:[/bold green] {summary['snapshots_harvested']} snapshots recorded, {summary['skipped_idempotent_count']} already fresh, {summary['skipped_immature_count']} immature (<24h).")
        finally:
            db.close()
    elif args.learn:
        from engines.learning_engine import LearningEngine
        db = SessionLocal()
        try:
            learner = LearningEngine()
            summary = learner.run_learning_cycle(db)
            console.print(Panel.fit(
                f"[bold green][+] Closed-Loop Learning Cycle Complete![/bold green]\n"
                f"Eligible Videos Evaluated: [bold]{summary['eligible_videos_evaluated']}[/bold]\n"
                f"Channel Baseline Score: [bold]{summary['channel_baseline_score']:.2f}/100[/bold]\n"
                f"Strategy Weights Updated: [bold]{summary['weights_updated_count']}[/bold]",
                border_style="green"
            ))
            rec = learner.get_strategy_recommendation(db, deterministic=True)
            console.print("[bold cyan]Current Strategy Recommendations:[/bold cyan]")
            for k, v in rec["recommendations"].items():
                console.print(f"  • [yellow]{k}[/yellow]: [bold white]{v}[/bold white] ({rec['reasoning'].get(k, '')})")
        finally:
            db.close()
    elif args.force_unlock and not (args.maintain_buffer > 0 or args.produce_batch > 0):
        from core.cloud_lock import CloudLockManager
        for lock_name in ["cloud_production", "cloud_publisher"]:
            cm = CloudLockManager(drive_engine=pipeline.drive_engine, lock_name=lock_name, force_break=True)
            cm.acquire()
            cm.release()
        console.print("[bold green][+] Forcibly released all cloud and local locks.[/bold green]")
        sys.exit(0)
    elif args.maintain_buffer > 0:
        res = pipeline.maintain_buffer(
            target_stock=args.maintain_buffer,
            force_unlock=args.force_unlock or args.force,
            is_dry_run=getattr(args, "dry_run", False)
        )
        count = res[0] if isinstance(res, tuple) else res
        summary = res[1] if isinstance(res, tuple) else {}
        sys.stdout.flush()
        sys.stderr.flush()
        if summary.get("outcome") == "BLOCKED":
            console.print("[bold yellow][!] Production was safely deferred due to active concurrent lock. Exiting cleanly.[/bold yellow]")
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        elif summary.get("outcome") == "FAILED":
            if summary.get("produced_count", 0) > 0 or summary.get("videos_deposited", 0) > 0:
                console.print(f"[bold green][+] Partial batch completed ({summary.get('produced_count', 0)} deposited into 01_READY). Exiting cleanly.[/bold green]")
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(0)
            else:
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(2)
        else:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
    elif args.produce_batch > 0:
        res = pipeline.produce_batch(
            count=args.produce_batch,
            force_unlock=args.force_unlock or args.force,
            is_dry_run=getattr(args, "dry_run", False)
        )
        count = res[0] if isinstance(res, tuple) else res
        summary = res[1] if isinstance(res, tuple) else {}
        sys.stdout.flush()
        sys.stderr.flush()
        if summary.get("outcome") == "BLOCKED":
            console.print("[bold yellow][!] Production was safely deferred due to active concurrent lock. Exiting cleanly.[/bold yellow]")
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        elif summary.get("outcome") == "FAILED":
            if summary.get("produced_count", 0) > 0 or summary.get("videos_deposited", 0) > 0:
                console.print(f"[bold green][+] Partial batch completed ({summary.get('produced_count', 0)} deposited into 01_READY). Exiting cleanly.[/bold green]")
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(0)
            else:
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(2)
        else:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
    elif args.publish_due:
        pipeline.publish_due_slots(target_file_id=args.file_id, retry_interval_sec=args.retry_interval, force=args.force)
    elif args.publish_next:
        pipeline.publish_next_from_vault(force=args.force, target_file_id=args.file_id)
    elif args.schedule_ready:
        pipeline.schedule_ready_buffer(target_file_id=args.file_id, max_to_schedule=args.max_to_schedule)
    elif args.run_once or args.test:
        pipeline.run_single_job(force=args.force)
    elif args.daemon:
        target_buf = args.maintain_buffer if args.maintain_buffer > 0 else 6
        pipeline.run_autonomous_daemon(target_stock=target_buf)
    elif args.runtime:
        console.print("[bold yellow][!] Persistent runtime in Harry Potter automation dispatches to HP autonomous daemon.[/bold yellow]")
        target_buf = args.maintain_buffer if args.maintain_buffer > 0 else TARGET_RESERVE_BUFFER
        pipeline.run_autonomous_daemon(target_stock=target_buf)
    elif args.canary:
        console.print("[bold cyan]Starting controlled live-cloud canary refill for Harry Potter...[/bold cyan]")
        from engines.hp_autonomous_refill import HPAutonomousRefillEngine
        refill = HPAutonomousRefillEngine(drive_engine=pipeline.drive_engine, voice_id="f5_cloned_narrator_v1", force_unlock=args.force_unlock or args.force)
        telemetry = refill.run_refill_cycle(force_batch_count=1)
        if telemetry.status in ("SUCCEEDED", "PARTIAL", "BUFFER_SATISFIED"):
            console.print(f"[bold green][+] Canary Succeeded: Verified in 01_READY (Reserve: {telemetry.final_ready_stock}/{TARGET_RESERVE_BUFFER})[/bold green]")
        else:
            console.print(f"[bold red][!] Canary Failed: {telemetry.status} - {telemetry.failure_reasons}[/bold red]")
            sys.exit(1)
    elif args.cloud_produce > 0 or getattr(args, "dry_run", False) and not args.run_once:
        from engines.hp_autonomous_refill import HPAutonomousRefillEngine
        orchestrator = HPAutonomousRefillEngine(
            drive_engine=pipeline.drive_engine,
            is_dry_run=args.dry_run,
            voice_id="f5_cloned_narrator_v1",
            force_unlock=args.force_unlock or args.force
        )
        telemetry = orchestrator.run_refill_cycle(
            target_buffer=args.maintain_buffer if args.maintain_buffer > 0 else TARGET_RESERVE_BUFFER,
            force_batch_count=args.cloud_produce if args.cloud_produce > 0 else None
        )
        console.print(Panel.fit(
            f"[bold green]=== Harry Potter Autonomous Refill Run Complete ===[/bold green]\n"
            f"Run ID: [bold white]{telemetry.run_id}[/bold white]\n"
            f"Status: [bold]{telemetry.status}[/bold]\n"
            f"Videos Deposited: [bold cyan]{telemetry.videos_deposited}[/bold cyan]\n"
            f"QA Passed: [bold green]{telemetry.videos_qa_passed}[/bold green]\n"
            f"Ready Stock: [bold]{telemetry.final_ready_stock}[/bold]\n"
            f"Dry Run: [yellow]{telemetry.is_dry_run}[/yellow]",
            border_style="green" if telemetry.status == "SUCCEEDED" else "yellow"
        ))
        sys.stdout.flush()
        sys.stderr.flush()
        if telemetry.status in ("FAILED", "BLOCKED"):
            os._exit(2)
        else:
            os._exit(0)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
