"""
Database Models for SQLite relational schema.
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship
from typing import Optional
from config.constants import JobState, HistoricalCategory, LicenseType

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True)
    topic_id = Column(String(64), ForeignKey("topics.id"), nullable=True)
    state = Column(String(32), default=JobState.QUEUED.value, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    topic = relationship("Topic", back_populates="jobs")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    renders = relationship("RenderOutput", back_populates="job", cascade="all, delete-orphan")
    qa_reports = relationship("QAReport", back_populates="job", cascade="all, delete-orphan")


class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    stage = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="logs")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String(64), primary_key=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    category = Column(String(64), default=HistoricalCategory.AMERICAN_HISTORY.value, nullable=False)
    score = Column(Float, default=0.0)
    status = Column(String(32), default="DISCOVERED")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Phase 2 Event Intelligence Fields
    event_id = Column(String(64), nullable=True, index=True)
    verification_state = Column(String(64), default="SINGLE_CREDIBLE_SOURCE", nullable=True)
    independent_sources_count = Column(Integer, default=1, nullable=True)
    event_card_json = Column(Text, nullable=True)

    jobs = relationship("Job", back_populates="topic")
    sources = relationship("SourceRecord", back_populates="topic", cascade="all, delete-orphan")
    claims = relationship("ClaimRecord", back_populates="topic", cascade="all, delete-orphan")
    scripts = relationship("ScriptRecord", back_populates="topic", cascade="all, delete-orphan")
    articles = relationship("ArticleRecord", back_populates="topic")


class ArticleRecord(Base):
    __tablename__ = "articles"

    id = Column(String(64), primary_key=True)
    title = Column(String(512), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_type = Column(String(64), default="unknown", nullable=False)
    source_tier = Column(String(32), default="TIER_4_UNKNOWN", nullable=False)
    url = Column(Text, nullable=False)
    normalized_url = Column(String(512), nullable=False, unique=True, index=True)
    author = Column(String(255), nullable=True)
    language = Column(String(32), default=None, nullable=True)
    category = Column(String(64), default="Geopolitics", nullable=True)

    published_utc = Column(DateTime, nullable=True, index=True)
    discovered_utc = Column(DateTime, default=datetime.utcnow, nullable=False)
    freshness_tier = Column(String(32), default="TIER_4", nullable=False)
    freshness_score = Column(Float, default=0.0)
    source_confidence = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0)

    summary = Column(Text, nullable=True)
    raw_feed_text = Column(Text, nullable=True)
    article_text = Column(Text, nullable=True)

    extraction_status = Column(String(32), default="PENDING", nullable=False)
    retrieval_status = Column(String(32), default="SUCCESS", nullable=False)

    topic_id = Column(String(64), ForeignKey("topics.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="articles")

    @property
    def publisher(self) -> str:
        return self.source_name

    @property
    def description(self) -> Optional[str]:
        return self.summary


class SourceRecord(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(64), ForeignKey("topics.id"), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_url = Column(Text, nullable=True)
    source_type = Column(String(64), default="primary")
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="sources")


class ClaimRecord(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(64), ForeignKey("topics.id"), nullable=False)
    claim_text = Column(Text, nullable=False)
    verification_status = Column(String(32), default="VERIFIED")
    supporting_sources = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Phase 2 Provenance Fields
    source_article_id = Column(String(64), nullable=True)
    publisher = Column(String(255), nullable=True)
    source_url = Column(Text, nullable=True)
    evidence_excerpt = Column(Text, nullable=True)

    topic = relationship("Topic", back_populates="claims")


class ScriptRecord(Base):
    __tablename__ = "scripts"

    id = Column(String(64), primary_key=True)
    topic_id = Column(String(64), ForeignKey("topics.id"), nullable=False)
    hook = Column(Text, nullable=False)
    context = Column(Text, nullable=False)
    escalation = Column(Text, nullable=False)
    reveal = Column(Text, nullable=False)
    loop_twist = Column(Text, nullable=False)
    full_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    estimated_duration_sec = Column(Float, nullable=False)
    hook_archetype = Column(String(64), nullable=True)  # DATE_TIME_ANCHOR, CONTRADICTION_SHOCK, HYPOTHETICAL_CURIOSITY, IN_MEDIAS_RES, UNSOLVED_MYSTERY, OTHER
    duration_target = Column(String(64), nullable=True)  # ULTRA_TIGHT, SWEET_SPOT, NARRATIVE_RICH
    status = Column(String(32), default="APPROVED")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Phase 3 Journalistic Scripting Fields
    event_id = Column(String(64), nullable=True, index=True)
    script_document_json = Column(Text, nullable=True)
    provenance_complete = Column(Boolean, default=False)
    validation_status = Column(String(32), default="PENDING")

    topic = relationship("Topic", back_populates="scripts")


class AssetRecord(Base):
    __tablename__ = "assets"

    id = Column(String(64), primary_key=True)
    asset_type = Column(String(32), nullable=False)  # video, image, music, sfx, font
    source = Column(String(64), nullable=False)      # pexels, pollinations, yt_library, cc0, local
    source_url = Column(Text, nullable=True)
    license = Column(String(128), default=LicenseType.UNKNOWN.value, nullable=False)
    license_url = Column(Text, nullable=True)
    commercial_use = Column(Boolean, default=False, nullable=False)
    attribution_required = Column(Boolean, default=False)
    attribution_text = Column(Text, nullable=True)
    local_path = Column(Text, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_sec = Column(Float, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RenderOutput(Base):
    __tablename__ = "renders"

    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False)
    video_path = Column(Text, nullable=False)
    width = Column(Integer, default=1080)
    height = Column(Integer, default=1920)
    fps = Column(Float, default=30.0)
    duration_sec = Column(Float, nullable=False)
    video_codec = Column(String(32), default="h264")
    audio_codec = Column(String(32), default="aac")
    file_size_bytes = Column(Integer, nullable=False)
    bgm_mood = Column(String(128), nullable=True)
    motion_style = Column(String(64), nullable=True)  # DYNAMIC_ZOOM_PAN, KEN_BURNS_STANDARD, STATIC
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="renders")


class QAReport(Base):
    __tablename__ = "qa_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False)
    passed = Column(Boolean, default=False)
    resolution_ok = Column(Boolean, default=False)
    duration_ok = Column(Boolean, default=False)
    audio_ok = Column(Boolean, default=False)
    captions_ok = Column(Boolean, default=False)
    license_ok = Column(Boolean, default=False)
    policy_ok = Column(Boolean, default=False)
    failure_reasons = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="qa_reports")


class UploadRecord(Base):
    __tablename__ = "uploads"

    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), nullable=False, index=True)
    youtube_video_id = Column(String(64), nullable=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    tags = Column(Text, nullable=True)
    privacy_status = Column(String(32), default="private")
    scheduled_publish_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="SUCCESS")  # SCHEDULED, PUBLISHED, FAILED, TEST_VERIFIED
    reconciliation_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    snapshots = relationship("PerformanceSnapshot", back_populates="upload", cascade="all, delete-orphan")


class PerformanceSnapshot(Base):
    """Immutable time-series performance metrics for a published video."""
    __tablename__ = "performance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(String(64), ForeignKey("uploads.id"), nullable=False, index=True)
    youtube_video_id = Column(String(64), nullable=True, index=True)
    snapshot_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    hours_since_upload = Column(Float, default=0.0)

    # Core metrics
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    subscribers_gained = Column(Integer, default=0)
    subscribers_lost = Column(Integer, default=0)

    # Retention & watch depth
    average_view_duration_sec = Column(Float, default=0.0)
    average_view_percentage = Column(Float, default=0.0)
    estimated_minutes_watched = Column(Float, default=0.0)
    engagement_rate = Column(Float, default=0.0)

    # Traffic sources & extra metrics (JSON)
    traffic_sources_json = Column(Text, nullable=True)
    raw_analytics_json = Column(Text, nullable=True)
    validation_status = Column(String(32), default="VALID_REAL", nullable=True)  # VALID_REAL, UNVERIFIED, STALE, DUPLICATE, MOCK, TEST, ORPHANED, UNAVAILABLE

    upload = relationship("UploadRecord", back_populates="snapshots")


class VideoAnalysisRecord(Base):
    """Statistical classification and structured Fact vs Hypothesis breakdown."""
    __tablename__ = "video_analyses"

    id = Column(String(64), primary_key=True)
    upload_id = Column(String(64), nullable=False, index=True)
    youtube_video_id = Column(String(64), nullable=True)
    analyzed_at = Column(DateTime, default=datetime.utcnow)

    # Classification: OUTPERFORMER, AVERAGE, UNDERPERFORMER, INSUFFICIENT_DATA
    classification = Column(String(32), nullable=False, index=True)
    
    # Baselines compared against
    channel_median_views = Column(Float, default=0.0)
    channel_median_apv = Column(Float, default=0.0)
    category_median_apv = Column(Float, default=0.0)

    # Structured Reason Engine (Facts vs Hypotheses)
    facts_observed = Column(Text, nullable=False)        # JSON list
    hypotheses = Column(Text, nullable=False)            # JSON list
    evidence = Column(Text, nullable=False)              # JSON list
    uncertainties = Column(Text, nullable=False)         # JSON list
    recommended_test = Column(Text, nullable=True)

    # Multi-dimensional score
    performance_score = Column(Float, default=50.0)


class ContentPattern(Base):
    """Persistent learning database tracking what works across formats, hooks, topics."""
    __tablename__ = "content_patterns"

    id = Column(String(64), primary_key=True)
    pattern_type = Column(String(64), nullable=False, index=True)  # hook_archetype, category, duration_bracket, visual_style, cta_style, posting_window
    pattern_key = Column(String(128), nullable=False, index=True)  # e.g., 'Contradiction', '21-23s', 'Documented Disasters'
    description = Column(Text, nullable=True)

    # Evidence & sample tracking
    sample_size = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    underperform_count = Column(Integer, default=0)

    # Performance metrics
    avg_percentage_viewed = Column(Float, default=0.0)
    avg_engagement_rate = Column(Float, default=0.0)
    avg_subscriber_conversion = Column(Float, default=0.0)
    composite_effectiveness_score = Column(Float, default=50.0)

    # Confidence: LOW_CONFIDENCE (N=1), MEDIUM_CONFIDENCE (N=2-4), HIGH_CONFIDENCE (N>=5)
    confidence = Column(String(32), default="LOW_CONFIDENCE")
    status = Column(String(32), default="ACTIVE")  # ACTIVE, RETIRED, PROVEN, FAILED
    last_updated = Column(DateTime, default=datetime.utcnow)


class ExperimentRecord(Base):
    """Tracks controlled strategy assignments, experiments, and resulting learnings."""
    __tablename__ = "experiments"

    id = Column(String(64), primary_key=True)
    experiment_type = Column(String(64), nullable=True)  # STRATEGY_ASSIGNMENT, EXPERIMENT_A, etc.
    experiment_group_id = Column(String(64), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    hypothesis = Column(Text, nullable=True)
    
    # Controlled & test variables
    control_variable = Column(String(128), nullable=True)
    test_variable = Column(String(128), nullable=True)
    control_job_id = Column(String(64), nullable=True)
    test_job_id = Column(String(64), nullable=True)

    # Phase 4 Strategy Assignment Fields
    job_id = Column(String(64), nullable=True, index=True)
    topic_id = Column(String(64), nullable=True, index=True)
    hook_archetype = Column(String(64), nullable=True)
    duration_target = Column(String(64), nullable=True)
    bgm_mood = Column(String(128), nullable=True)
    motion_style = Column(String(64), nullable=True)
    category = Column(String(64), nullable=True)
    selection_mode = Column(String(32), default="EXPLOITATION")  # EXPLOITATION, EXPLORATION, MANUAL_OVERRIDE, DEFAULT
    strategy_reason = Column(Text, nullable=True)
    combination_type = Column(String(32), default="KNOWN")  # KNOWN, PARTIALLY_KNOWN, UNSEEN

    # Lifecycle State
    status = Column(String(32), default="PLANNED")  # PLANNED, SELECTED, PRODUCED, READY, UPLOADED, MEASURED, FAILED, CANCELLED
    failure_reason = Column(Text, nullable=True)
    
    # Upload & Metric Linking
    upload_id = Column(String(64), nullable=True, index=True)
    youtube_video_id = Column(String(64), nullable=True, index=True)
    outcome_snapshot_id = Column(Integer, nullable=True)
    outcome_summary = Column(Text, nullable=True)
    measured_delta_apv = Column(Float, nullable=True)
    confidence = Column(String(32), default="LOW_CONFIDENCE")
    created_at = Column(DateTime, default=datetime.utcnow)
    concluded_at = Column(DateTime, nullable=True)


class ProviderUsage(Base):
    __tablename__ = "provider_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(64), nullable=False, index=True)
    units_used = Column(Integer, default=1)
    model_name = Column(String(64), nullable=True)
    endpoint = Column(String(128), nullable=True)
    status_code = Column(Integer, nullable=True)
    rate_limit = Column(Integer, nullable=True)
    rate_remaining = Column(Integer, nullable=True)
    rate_reset = Column(Integer, nullable=True)
    is_observed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StrategyWeight(Base):
    """Stores persistent, deterministic strategy weights for content generation."""
    __tablename__ = "strategy_weights"

    id = Column(String(64), primary_key=True)
    feature_type = Column(String(64), nullable=False, index=True)  # hook_archetype, duration_target, bgm_mood, motion_style, category
    feature_value = Column(String(128), nullable=False, index=True)
    weight = Column(Float, default=1.0, nullable=False)  # Bounded [0.20, 2.00]
    sample_count = Column(Integer, default=0, nullable=False)
    performance_mean = Column(Float, default=50.0, nullable=False)
    baseline_performance = Column(Float, default=50.0, nullable=False)
    relative_lift = Column(Float, default=0.0, nullable=False)  # Percentage lift vs baseline (e.g. +15.2%)
    confidence_level = Column(String(32), default="INSUFFICIENT_EVIDENCE", nullable=False)  # INSUFFICIENT_EVIDENCE (<3), WEAK_EVIDENCE (3-4), USABLE_EVIDENCE (>=5)
    last_updated = Column(DateTime, default=datetime.utcnow)
    update_reason = Column(Text, nullable=True)


class SystemConfig(Base):
    """Stores persistent key-value configuration for pipeline operations (e.g. active voice)."""
    __tablename__ = "system_config"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningEvent(Base):
    """
    Immutable audit trail for closed-loop self-improvement decisions and strategy weight updates.
    Records exact mathematical deltas, evidence sample sizes, baseline comparisons,
    and tracks whether future generation has consumed the updated production profile.
    """
    __tablename__ = "learning_events"

    id = Column(String(64), primary_key=True)
    cycle_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Outcome: LEARNING_APPLIED, NO_CHANGE_INSUFFICIENT_EVIDENCE, NO_CHANGE_NO_SIGNIFICANT_SIGNAL, NO_CHANGE_MISSING_TELEMETRY
    outcome = Column(String(64), nullable=False, index=True)

    # Feature attribution
    feature_type = Column(String(64), nullable=True, index=True)  # hook_archetype, duration_target, category, etc.
    feature_value = Column(String(128), nullable=True)

    # Evidence & Maturation
    sample_size = Column(Integer, default=0, nullable=False)
    matured_count = Column(Integer, default=0, nullable=False)
    immature_count = Column(Integer, default=0, nullable=False)

    # Metrics & Signals
    signal_metric = Column(String(64), default="COMPOSITE_RETENTION_APV", nullable=False)
    baseline_metric = Column(Float, nullable=True)
    observed_metric = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)

    # Confidence & Bounded Weights
    confidence = Column(String(32), default="INSUFFICIENT_EVIDENCE", nullable=False)  # INSUFFICIENT_EVIDENCE, WEAK_EVIDENCE, USABLE_EVIDENCE
    old_weight = Column(Float, default=1.00, nullable=False)
    new_weight = Column(Float, default=1.00, nullable=False)

    # Explainability & Traceability
    reason = Column(Text, nullable=False)
    profile_version = Column(String(64), nullable=True)

    # Future generation consumption confirmation
    consumed_by_generation = Column(Boolean, default=False, nullable=False)
    consumed_by_job_id = Column(String(64), nullable=True, index=True)
    details_json = Column(Text, nullable=True)


class VisualEvidenceRecord(Base):
    """
    Phase 4: Auditable persistent record of beat-level visual evidence retrieval
    and coverage plan for a generated Short.
    """
    __tablename__ = "visual_evidence_records"

    id = Column(String(64), primary_key=True)
    event_id = Column(String(64), nullable=False, index=True)
    script_id = Column(String(64), nullable=False, index=True)
    overall_evidence_ratio = Column(Float, default=0.0, nullable=False)
    direct_evidence_count = Column(Integer, default=0, nullable=False)
    related_evidence_count = Column(Integer, default=0, nullable=False)
    contextual_count = Column(Integer, default=0, nullable=False)
    no_visual_count = Column(Integer, default=0, nullable=False)
    plan_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProductionAssetManifestRecord(Base):
    """
    Phase 5: Auditable persistent record of the production asset manifest
    connecting ScriptBeats, VisualEvidence, and Edit Decisions.
    """
    __tablename__ = "production_asset_manifest_records"

    id = Column(String(64), primary_key=True)
    manifest_id = Column(String(64), nullable=False, unique=True, index=True)
    event_id = Column(String(64), nullable=False, index=True)
    script_id = Column(String(64), nullable=False, index=True)
    total_duration_seconds = Column(Float, nullable=False)
    direct_evidence_ratio = Column(Float, default=0.0, nullable=False)
    no_visual_ratio = Column(Float, default=0.0, nullable=False)
    validation_status = Column(String(32), default="VALID", nullable=False)
    manifest_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RenderedVideoRecord(Base):
    """
    Phase 6: Auditable persistent record of headless rendered videos,
    audio-visual synchronizations, QA verification results, and cloud vault buffer status.
    """
    __tablename__ = "rendered_video_records"

    id = Column(String(64), primary_key=True)
    manifest_id = Column(String(64), nullable=False, index=True)
    event_id = Column(String(64), nullable=False, index=True)
    script_id = Column(String(64), nullable=False, index=True)
    video_path = Column(Text, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    width = Column(Integer, default=1080, nullable=False)
    height = Column(Integer, default=1920, nullable=False)
    fps = Column(Float, default=30.0, nullable=False)
    aspect_ratio = Column(String(32), default="9:16", nullable=False)
    qa_status = Column(String(32), default="PENDING", nullable=False)  # PASSED, FAILED, PENDING
    qa_report_json = Column(Text, nullable=True)
    cloud_storage_path = Column(Text, nullable=True)
    voice_id = Column(String(64), default="af_bella", nullable=False)
    has_bgm = Column(Boolean, default=True, nullable=False)
    has_sfx = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProductionAttemptRecord(Base):
    """
    Persistent attempt and retry ledger for all production operations.
    Enforces the zero-silent-retries invariant: every execution attempt, failure,
    retry count, and recovery status is explicitly recorded.
    A final success never erases prior failure attempts.
    """
    __tablename__ = "production_attempts"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), nullable=False, index=True)
    operation = Column(String(64), nullable=False, index=True)  # PRODUCE_BUFFER, MAINTAIN_BUFFER, SCHEDULE_READY, PRODUCE_BATCH, RECONCILE_PROCESSING
    stage = Column(String(64), nullable=False, index=True)      # DISCOVERY, SCRIPT, TTS, RENDER, QA, DRIVE_DEPOSIT, YOUTUBE_UPLOAD, SCHEDULING, RECONCILIATION
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="RUNNING", nullable=False, index=True)  # PENDING, RUNNING, SUCCESS, FAILED, RECOVERED
    error_type = Column(String(64), nullable=True, index=True)  # Canonical Failure Taxonomy Enum
    error_message = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    retry_number = Column(Integer, default=0, nullable=False)
    maximum_retries = Column(Integer, default=3, nullable=False)
    recovery_action = Column(Text, nullable=True)
    recovered = Column(Boolean, default=False, nullable=False)
    related_asset_id = Column(String(64), nullable=True)
    related_manifest_id = Column(String(64), nullable=True, index=True)
    related_drive_file_id = Column(String(64), nullable=True, index=True)
    related_youtube_video_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProductionIncidentRecord(Base):
    """
    Persistent audit trail for production incidents affecting autonomous operation.
    Enables autonomous debugging and answers 'What failed and why?' without chat history.
    """
    __tablename__ = "production_incidents"

    id = Column(String(64), primary_key=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    affected_workflow = Column(String(64), nullable=False)  # produce_buffer.yml, autopilot.yml, manual
    affected_run_id = Column(String(64), nullable=True, index=True)
    affected_assets_json = Column(Text, nullable=True)      # JSON list of affected asset filenames/IDs
    symptoms = Column(Text, nullable=False)
    exact_root_cause = Column(Text, nullable=False)
    failed_attempts_count = Column(Integer, default=0, nullable=False)
    recovery_status = Column(String(32), default="RESOLVED", nullable=False, index=True)  # OPEN, MITIGATED, RESOLVED
    permanent_fix_description = Column(Text, nullable=False)
    verification_evidence = Column(Text, nullable=True)
    regression_test = Column(String(128), nullable=True)
    git_commit_sha = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ==============================================================================
# HARRY POTTER NOVEL KNOWLEDGE BASE MODELS (Step 6)
# Authoritative text source of truth for the entire automated pipeline.
# ==============================================================================

class NovelBook(Base):
    """Authoritative record for each of the 7 Harry Potter novels."""
    __tablename__ = "novel_books"

    id = Column(String(64), primary_key=True)  # hp_book_1 .. hp_book_7
    book_number = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    us_title = Column(String(255), nullable=True)
    author = Column(String(128), default="J.K. Rowling", nullable=False)
    total_chapters = Column(Integer, default=0, nullable=False)
    total_pages = Column(Integer, default=0, nullable=False)
    total_chunks = Column(Integer, default=0, nullable=False)
    source_file = Column(String(255), nullable=False)
    source_drive_id = Column(String(128), nullable=True)
    file_checksum = Column(String(64), nullable=True)
    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chapters = relationship("NovelChapter", back_populates="book", cascade="all, delete-orphan", order_by="NovelChapter.chapter_number")
    chunks = relationship("NovelChunk", back_populates="book", cascade="all, delete-orphan", order_by="NovelChunk.global_chronology_index")


class NovelChapter(Base):
    """Chapter boundary and metadata within a Harry Potter novel."""
    __tablename__ = "novel_chapters"

    id = Column(String(64), primary_key=True)  # hp_b1_c01 ..
    book_id = Column(String(64), ForeignKey("novel_books.id"), nullable=False, index=True)
    book_number = Column(Integer, nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False, index=True)
    chapter_title = Column(String(255), nullable=False)
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)
    total_chunks = Column(Integer, default=0, nullable=False)
    word_count = Column(Integer, default=0, nullable=False)

    book = relationship("NovelBook", back_populates="chapters")
    chunks = relationship("NovelChunk", back_populates="chapter", cascade="all, delete-orphan", order_by="NovelChunk.chunk_index")


class NovelChunk(Base):
    """
    Searchable, contextual story passage preserving strict narrative chronology
    and exact source-to-page traceability across the 7 novels.
    """
    __tablename__ = "novel_chunks"

    id = Column(String(64), primary_key=True)  # hp_b1_c01_chk001 ..
    book_id = Column(String(64), ForeignKey("novel_books.id"), nullable=False, index=True)
    book_number = Column(Integer, nullable=False, index=True)
    book_title = Column(String(255), nullable=False)
    chapter_id = Column(String(64), ForeignKey("novel_chapters.id"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False, index=True)
    chapter_title = Column(String(255), nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Sequential within chapter
    global_chronology_index = Column(Integer, nullable=False, unique=True, index=True)  # 1 to N across all 7 books!
    text = Column(Text, nullable=False)
    word_count = Column(Integer, default=0, nullable=False)
    source_file = Column(String(255), nullable=False)
    source_location = Column(String(255), nullable=False)  # "Book 1 Chapter 1 Page 2-3"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    book = relationship("NovelBook", back_populates="chunks")
    chapter = relationship("NovelChapter", back_populates="chunks")


# ==============================================================================
# HARRY POTTER MOVIE & SRT ASSET MODELS (Step 6A)
# Deterministic pairing of movie video files and searchable SRT scene units.
# Enforces the audio-muting invariant on all movie clips.
# ==============================================================================

class MovieAssetRecord(Base):
    """Authoritative metadata and pairing record for Harry Potter movie footage."""
    __tablename__ = "movie_assets"

    id = Column(String(64), primary_key=True)  # hp_movie_1 .. hp_movie_3
    movie_number = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    video_filename = Column(String(255), nullable=False)
    video_drive_id = Column(String(128), nullable=False)
    video_file_size_bytes = Column(Integer, default=0, nullable=False)
    video_duration_seconds = Column(Float, default=0.0, nullable=False)
    width = Column(Integer, default=1920, nullable=False)
    height = Column(Integer, default=800, nullable=False)
    srt_filename = Column(String(255), nullable=False)
    srt_local_path = Column(String(512), nullable=False)
    total_raw_subtitles = Column(Integer, default=0, nullable=False)
    total_scene_chunks = Column(Integer, default=0, nullable=False)
    pairing_status = Column(String(32), default="VALID", nullable=False)
    audio_muted_invariant = Column(Boolean, default=True, nullable=False)  # Enforces -an on all clip extraction
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    subtitles = relationship("MovieSubtitleChunk", back_populates="movie", cascade="all, delete-orphan", order_by="MovieSubtitleChunk.seq_start")


class MovieSubtitleChunk(Base):
    """
    Searchable scene-sized subtitle unit preserving exact start/end timestamps
    for automated movie clip extraction and semantic visual retrieval.
    """
    __tablename__ = "movie_subtitle_chunks"

    id = Column(String(64), primary_key=True)  # hp_m1_scene_001 ..
    movie_id = Column(String(64), ForeignKey("movie_assets.id"), nullable=False, index=True)
    movie_number = Column(Integer, nullable=False, index=True)
    movie_title = Column(String(255), nullable=False)
    seq_start = Column(Integer, nullable=False)  # Starting raw SRT index
    seq_end = Column(Integer, nullable=False)    # Ending raw SRT index
    start_seconds = Column(Float, nullable=False, index=True)
    end_seconds = Column(Float, nullable=False, index=True)
    start_timecode = Column(String(32), nullable=False)  # "00:01:22,277"
    end_timecode = Column(String(32), nullable=False)    # "00:01:35,500"
    duration_seconds = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    source_srt = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    movie = relationship("MovieAssetRecord", back_populates="subtitles")


# ==============================================================================
# HARRY POTTER STEP 7: CONTENT PLANNING DATA MODELS
# Novel Story Candidates, Discovery Candidates, Chronology State.
# These are PLANNING records only — no final scripts, narration, or renders.
# ==============================================================================

class ChronologyState(Base):
    """
    Tracks the current chronological frontier across the 7 novels.
    Ensures the Novel Story Planner advances through the story without skipping
    or repeating segments. One row per state key ('novel_story_progress').
    """
    __tablename__ = "chronology_state"

    id = Column(String(64), primary_key=True)  # "novel_story_progress"
    last_planned_global_index = Column(Integer, default=0, nullable=False)
    last_planned_book_number = Column(Integer, default=0, nullable=False)
    last_planned_chapter_number = Column(Integer, default=0, nullable=False)
    total_candidates_generated = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NovStoryCandidate(Base):
    """
    Structured content plan for a Novel Story Short (~25-30 seconds).
    Grounded in canonical HP novel text. Does NOT contain final narration.
    Fully traceable: Book -> Chapter -> Chunk range -> Global Chronology Index.
    Visual policy: MOVIE FOOTAGE ONLY. No AI, stock, Pexels, or images.
    """
    __tablename__ = "nov_story_candidates"

    id = Column(String(64), primary_key=True)   # "ns_b1c01_gc001_003"
    content_type = Column(String(32), default="novel_story", nullable=False)

    # Novel Source Traceability
    book_number = Column(Integer, nullable=False, index=True)
    book_title = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False, index=True)
    chapter_title = Column(String(255), nullable=False)
    chunk_id_start = Column(String(64), nullable=False)
    chunk_id_end = Column(String(64), nullable=False)
    global_chronology_start = Column(Integer, nullable=False, index=True)
    global_chronology_end = Column(Integer, nullable=False, index=True)
    source_location = Column(String(255), nullable=False)
    source_text_preview = Column(Text, nullable=True)

    # Story Planning Fields (NOT final narration)
    story_event_summary = Column(Text, nullable=False)
    characters_json = Column(Text, nullable=True)
    locations_json = Column(Text, nullable=True)
    objects_events_json = Column(Text, nullable=True)
    beginning_context = Column(Text, nullable=True)
    central_development = Column(Text, nullable=True)
    payoff_conclusion = Column(Text, nullable=True)
    hook_concept = Column(Text, nullable=True)
    narration_complexity = Column(String(32), default="MODERATE", nullable=False)
    short_duration_feasibility = Column(String(32), default="FEASIBLE", nullable=False)

    # Visual Feasibility (Movie Footage ONLY)
    visual_beats_json = Column(Text, nullable=True)
    overall_visual_feasibility = Column(String(32), default="PENDING", nullable=False)

    # Candidate Status
    status = Column(String(32), default="ELIGIBLE", nullable=False, index=True)

    # Deduplication
    content_fingerprint = Column(String(64), unique=True, nullable=False, index=True)

    # Batch / Launch Assignment
    is_launch_candidate = Column(Boolean, default=False, nullable=False, index=True)
    batch_slot = Column(Integer, nullable=True)
    batch_date = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DiscoveryCandidate(Base):
    """
    Structured content plan for a Discovery Short (~25-30 seconds).
    Grounded in HP novel-vs-film differences. Does NOT contain final narration.
    Every fact is verifiable in the novel FTS index.
    Visual policy: MOVIE FOOTAGE ONLY. No AI, stock, Pexels, or images.
    """
    __tablename__ = "discovery_candidates"

    id = Column(String(64), primary_key=True)   # "disc_peeves_b1c08"
    content_type = Column(String(32), default="discovery", nullable=False)

    # Discovery Classification
    discovery_type = Column(String(64), nullable=False, index=True)
    # BOOK_ONLY_DETAIL / BOOK_VS_MOVIE_DIFFERENCE / CHARACTER_DEPTH /
    # LORE_DETAIL / MOTIVATION_REVEALED / NOVEL_ONLY_SCENE

    # Novel Source Traceability
    book_number = Column(Integer, nullable=False, index=True)
    book_title = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False, index=True)
    chapter_title = Column(String(255), nullable=False)
    chunk_id_primary = Column(String(64), nullable=False)
    chunk_ids_supporting = Column(Text, nullable=True)
    novel_fact_summary = Column(Text, nullable=False)
    novel_evidence_text = Column(Text, nullable=True)

    # Movie Comparison
    corresponding_movie_number = Column(Integer, nullable=True)
    corresponding_movie_title = Column(String(255), nullable=True)
    movie_chunk_id = Column(String(64), nullable=True)
    movie_shows = Column(Text, nullable=True)
    movie_omits_or_changes = Column(Text, nullable=True)

    # Planning Fields (NOT final narration)
    why_interesting = Column(Text, nullable=True)
    hook_concept = Column(Text, nullable=True)
    short_duration_feasibility = Column(String(32), default="FEASIBLE", nullable=False)

    # Visual Feasibility (Movie Footage ONLY)
    visual_beats_json = Column(Text, nullable=True)
    overall_visual_feasibility = Column(String(32), default="PENDING", nullable=False)

    # Candidate Status
    status = Column(String(32), default="ELIGIBLE", nullable=False, index=True)

    # Deduplication
    content_fingerprint = Column(String(64), unique=True, nullable=False, index=True)

    # Batch / Launch Assignment
    is_launch_candidate = Column(Boolean, default=False, nullable=False, index=True)
    batch_slot = Column(Integer, nullable=True)
    batch_date = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ==============================================================================
# HARRY POTTER STEP 8: SCRIPT GENERATION & VISUAL BEAT DATA MODELS
# ==============================================================================

class HarryPotterScript(Base):
    """
    Validated, fact-grounded production script and visual beat plan for a Harry Potter Short.
    Supports both Novel Story Shorts (Type A) and Discovery Shorts (Type B).
    Grounded in canonical novel text and movie evidence.
    Enforces strict MOVIE FOOTAGE ONLY visual policy and no-spoken-part-marker rule.
    """
    __tablename__ = "hp_scripts"

    id = Column(String(64), primary_key=True)  # e.g. "hps_ns_b1c01_gc0001_0003"
    candidate_id = Column(String(64), nullable=False, index=True)
    content_type = Column(String(32), nullable=False, index=True)  # "novel_story" or "discovery"

    # Novel Traceability
    book_number = Column(Integer, nullable=False, index=True)
    book_title = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False, index=True)
    chapter_title = Column(String(255), nullable=False)
    source_chunks_json = Column(Text, nullable=False)  # JSON list of chunk IDs
    source_reference = Column(String(255), nullable=False)  # e.g. "Book 1 Chapter 1 (p.2-13)"
    novel_evidence_excerpt = Column(Text, nullable=True)

    # Discovery / Movie Traceability
    discovery_type = Column(String(64), nullable=True)
    corresponding_movie_number = Column(Integer, nullable=True)
    movie_chunk_id = Column(String(64), nullable=True)
    movie_evidence_excerpt = Column(Text, nullable=True)

    # Production Metadata & Style
    part_marker = Column(String(32), nullable=True)  # e.g. "PART 01" (VISUAL ONLY, never spoken)
    voice_id = Column(String(64), default="af_bella", nullable=False)
    voice_pitch = Column(String(32), default="+0Hz", nullable=False)
    voice_rate = Column(String(32), default="+0%", nullable=False)
    narrator_style = Column(String(64), default="BELLA_CINEMATIC", nullable=False)

    # 3-Stage Narration (Hook -> Development -> Payoff)
    hook = Column(Text, nullable=False)
    development = Column(Text, nullable=False)
    payoff = Column(Text, nullable=False)
    full_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)
    estimated_duration_sec = Column(Float, nullable=False)

    # Visual Beat Plan (Step 9 input, MOVIE FOOTAGE ONLY)
    visual_beats_json = Column(Text, nullable=False)  # Structured list of visual beats
    total_beats = Column(Integer, default=0, nullable=False)

    # Script QA & AI Review
    qa_score = Column(Float, default=100.0, nullable=False)
    qa_status = Column(String(32), default="APPROVED", nullable=False, index=True)  # APPROVED, REJECTED, FLAGGED
    qa_feedback_json = Column(Text, nullable=True)
    model_name = Column(String(64), default="gemini-3.6-flash", nullable=False)

    # Lifecycle State
    status = Column(String(32), default="READY_FOR_STEP_9", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ==============================================================================
# HARRY POTTER STEP 9: MOVIE VISUAL RETRIEVAL & CLIP EXTRACTION DATA MODELS
# ==============================================================================

class HPMovieClip(Base):
    """
    Persisted metadata for an extracted movie visual clip.
    Strictly audio-muted (-an) with ffprobe verification (0 audio streams).
    Preserves full lineage: hp_script_id -> beat_id -> movie_number -> subtitle_chunk_id.
    """
    __tablename__ = "hp_movie_clips"

    id = Column(String(64), primary_key=True)  # e.g. "clip_hps_ns_b1c01_gc0001_0003_beat_1_shot_1"
    script_id = Column(String(64), ForeignKey("hp_scripts.id"), nullable=False, index=True)
    beat_id = Column(String(32), nullable=False, index=True)
    shot_id = Column(String(32), default="shot_1", nullable=False, index=True)  # shot_1, shot_2, shot_3
    shot_index = Column(Integer, default=1, nullable=False)

    # Movie Source Identity & Cloud Resolution
    movie_id = Column(String(64), nullable=False, index=True)
    movie_number = Column(Integer, nullable=False, index=True)
    movie_title = Column(String(255), nullable=False)
    source_asset_id = Column(String(64), nullable=True)
    source_drive_id = Column(String(128), nullable=True)  # Canonical Google Drive File ID
    source_mode = Column(String(32), default="CLOUD_RESOLVABLE", nullable=False)  # CLOUD_RESOLVABLE, CLOUD_MATERIALIZED, LOCAL_DEV_CACHE
    subtitle_chunk_id = Column(String(64), nullable=True)

    # Timecodes & Rapid-Fire Duration (Target 1.5s - 3.0s)
    source_start_seconds = Column(Float, nullable=False)
    source_end_seconds = Column(Float, nullable=False)
    clip_start_seconds = Column(Float, nullable=False)
    clip_end_seconds = Column(Float, nullable=False)
    duration_seconds = Column(Float, nullable=False)

    # Retrieval & Match Signals
    matched_text = Column(Text, nullable=True)
    retrieval_query = Column(Text, nullable=True)
    retrieval_score = Column(Float, default=0.0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    match_status = Column(String(32), default="ACCEPTED", nullable=False, index=True)  # ACCEPTED, REJECTED, FLAGGED
    rejection_reason = Column(Text, nullable=True)

    # Video Integrity & Audio Muting
    file_path = Column(String(512), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    audio_stream_count = Column(Integer, default=0, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    visual_source_policy = Column(String(64), default="MOVIE_FOOTAGE_ONLY", nullable=False)

    # State
    status = Column(String(32), default="READY_FOR_STEP_10", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ==============================================================================
# HARRY POTTER STEP 10: HEADLESS VIDEO RENDERING DATA MODELS
# ==============================================================================

class HPRender(Base):
    """
    Persisted record of a rendered vertical YouTube Short (1080x1920, 30 FPS).
    Integrates narration, BGM, synchronized captions, visual PART marker,
    and technical QA verification results.
    """
    __tablename__ = "hp_renders"

    id = Column(String(64), primary_key=True)  # e.g. "render_hps_ns_b1c01_gc0001_0003"
    script_id = Column(String(64), ForeignKey("hp_scripts.id"), nullable=False, index=True)
    content_type = Column(String(32), nullable=False, index=True)  # novel_story, discovery
    part_marker = Column(String(32), nullable=True)  # "PART 01" (purely visual)

    # Voice & Audio Specifications
    voice_id = Column(String(64), default="af_bella", nullable=False)
    voice_pitch = Column(String(32), default="+0Hz", nullable=False)
    voice_rate = Column(String(32), default="+0%", nullable=False)
    narration_duration_sec = Column(Float, nullable=False)
    narration_audio_path = Column(String(512), nullable=True)

    # Visual Assembly
    shot_count = Column(Integer, default=0, nullable=False)
    movie_numbers_used = Column(String(64), nullable=True)  # e.g. "1,8"
    visual_policy = Column(String(64), default="MOVIE_FOOTAGE_ONLY", nullable=False)

    # BGM & Loudness Master
    bgm_track = Column(String(128), nullable=True)
    bgm_volume_db = Column(Float, default=-20.0, nullable=False)
    master_lufs = Column(Float, nullable=True)  # Target -14.0 LUFS

    # Subtitles & Captions
    caption_style = Column(String(64), default="ASS_SAFE_ZONE_GOLD_ACTIVE", nullable=False)
    subtitles_path = Column(String(512), nullable=True)

    # Render Specifications
    video_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=True)
    width = Column(Integer, default=1080, nullable=False)
    height = Column(Integer, default=1920, nullable=False)
    fps = Column(Float, default=30.0, nullable=False)
    total_duration_sec = Column(Float, nullable=False)

    # Technical QA
    qa_status = Column(String(32), default="PENDING", nullable=False, index=True)  # PASSED, FAILED
    qa_report_json = Column(Text, nullable=True)
    audio_streams_count = Column(Integer, default=1, nullable=False)
    movie_audio_detected = Column(Boolean, default=False, nullable=False)  # Must be False

    # State & Review Gate
    status = Column(String(32), default="READY_FOR_REVIEW", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)



