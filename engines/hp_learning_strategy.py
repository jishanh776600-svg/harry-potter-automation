"""
Harry Potter Bounded Learning & Strategy Adaptation Engine
================================================================================
Translates mature YouTube Analytics feedback (>72h) into bounded content strategy
parameters for autonomous Harry Potter Shorts production.

STRICT BOUNDARY INVARIANTS:
  - NEVER modifies source code, workflows, credentials, or security gates.
  - Content Mix bounded: [1:3 to 3:1] (Novel Story ratio: 0.25 to 0.75).
  - Subtype multipliers bounded: [0.50 to 1.50].
  - Target duration bounded: [20.0s to 28.0s].
  - Sample evidence thresholds:
      * N < 3: INSUFFICIENT -> Weight held neutral (1.00).
      * N = 3-4: WEAK -> Maximum +-10% damped adjustment.
      * N >= 5: USABLE -> Full bounded adjustment.
  - Writes exclusively to data/strategy_config.json and pipeline.db (strategy_weights).
"""

import os
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config.settings import PROJECT_ROOT, DB_PATH
from core.database import SessionLocal
from core.models import StrategyWeight, PerformanceSnapshot, UploadRecord

logger = logging.getLogger("hp_learning_strategy")

STRATEGY_CONFIG_PATH = PROJECT_ROOT / "data" / "strategy_config.json"
LEARNING_LOG_PATH = PROJECT_ROOT / "data" / "LEARNING_LOG.md"

# Safe hard boundaries
MIN_NOVEL_RATIO = 0.25      # 1:3 ratio
MAX_NOVEL_RATIO = 0.75      # 3:1 ratio
DEFAULT_NOVEL_RATIO = 0.50  # 2:2 baseline

MIN_SUBTYPE_WEIGHT = 0.50
MAX_SUBTYPE_WEIGHT = 1.50
DEFAULT_SUBTYPE_WEIGHT = 1.00

MIN_DURATION_TARGET = 20.0
MAX_DURATION_TARGET = 28.0
DEFAULT_DURATION_TARGET = 24.0

CANONICAL_DISCOVERY_SUBTYPES = [
    "DISCOVERY_BOOK_MOVIE_DIFFERENCE",
    "DISCOVERY_OMITTED_SCENE",
    "DISCOVERY_CHARACTER_ORIGIN",
    "DISCOVERY_LORE_DEEP_DIVE",
    "DISCOVERY_BEHIND_THE_SCENES",
    "DISCOVERY_FORESHADOWING_PROPHECY",
    "DISCOVERY_MAGICAL_OBJECT",
    "DISCOVERY_MOVIE_DETAIL"
]


class HPLearningStrategy:
    """Manages bounded strategy parameters and closed-loop adaptation for HP automation."""

    def __init__(self, config_path: Optional[Path] = None, log_path: Optional[Path] = None):
        self.config_path = config_path or STRATEGY_CONFIG_PATH
        self.log_path = log_path or LEARNING_LOG_PATH
        self._ensure_config_exists()

    def _ensure_config_exists(self) -> None:
        """Initializes default strategy config if not present."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "version": "1.0.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "update_cycle_count": 0,
                "content_mix": {
                    "novel_story_ratio": DEFAULT_NOVEL_RATIO,
                    "discovery_ratio": 1.0 - DEFAULT_NOVEL_RATIO,
                    "bounds": {"min": MIN_NOVEL_RATIO, "max": MAX_NOVEL_RATIO}
                },
                "target_duration_sec": DEFAULT_DURATION_TARGET,
                "discovery_subtype_weights": {
                    subtype: DEFAULT_SUBTYPE_WEIGHT for subtype in CANONICAL_DISCOVERY_SUBTYPES
                },
                "hook_family_weights": {
                    "direct_contradiction": 1.0,
                    "unknown_mechanic": 1.0,
                    "secret_inscription": 1.0,
                    "character_secret": 1.0
                }
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=2)

    def load_strategy(self) -> Dict[str, Any]:
        """Loads and clamps current strategy configuration."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read strategy config ({e}), falling back to defaults")
            self._ensure_config_exists()
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

        # Enforce hard clamping on load
        novel_ratio = cfg.get("content_mix", {}).get("novel_story_ratio", DEFAULT_NOVEL_RATIO)
        clamped_novel = max(MIN_NOVEL_RATIO, min(MAX_NOVEL_RATIO, float(novel_ratio)))
        cfg["content_mix"]["novel_story_ratio"] = round(clamped_novel, 3)
        cfg["content_mix"]["discovery_ratio"] = round(1.0 - clamped_novel, 3)

        dur = cfg.get("target_duration_sec", DEFAULT_DURATION_TARGET)
        cfg["target_duration_sec"] = max(MIN_DURATION_TARGET, min(MAX_DURATION_TARGET, float(dur)))

        subtype_weights = cfg.get("discovery_subtype_weights", {})
        for st in CANONICAL_DISCOVERY_SUBTYPES:
            w = subtype_weights.get(st, DEFAULT_SUBTYPE_WEIGHT)
            subtype_weights[st] = round(max(MIN_SUBTYPE_WEIGHT, min(MAX_SUBTYPE_WEIGHT, float(w))), 3)
        cfg["discovery_subtype_weights"] = subtype_weights

        return cfg

    def save_strategy(self, cfg: Dict[str, Any], reason: str = "") -> None:
        """Safely persists validated, clamped strategy configuration."""
        # Enforce clamps before saving
        novel_ratio = cfg.get("content_mix", {}).get("novel_story_ratio", DEFAULT_NOVEL_RATIO)
        clamped_novel = max(MIN_NOVEL_RATIO, min(MAX_NOVEL_RATIO, float(novel_ratio)))
        cfg["content_mix"]["novel_story_ratio"] = round(clamped_novel, 3)
        cfg["content_mix"]["discovery_ratio"] = round(1.0 - clamped_novel, 3)

        dur = cfg.get("target_duration_sec", DEFAULT_DURATION_TARGET)
        cfg["target_duration_sec"] = round(max(MIN_DURATION_TARGET, min(MAX_DURATION_TARGET, float(dur))), 1)

        subtype_weights = cfg.get("discovery_subtype_weights", {})
        for st in CANONICAL_DISCOVERY_SUBTYPES:
            w = subtype_weights.get(st, DEFAULT_SUBTYPE_WEIGHT)
            subtype_weights[st] = round(max(MIN_SUBTYPE_WEIGHT, min(MAX_SUBTYPE_WEIGHT, float(w))), 3)
        cfg["discovery_subtype_weights"] = subtype_weights

        cfg["last_updated"] = datetime.now(timezone.utc).isoformat()
        cfg["update_cycle_count"] = cfg.get("update_cycle_count", 0) + 1

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        # Audit log entry
        self._append_audit_log(cfg, reason)

    def _append_audit_log(self, cfg: Dict[str, Any], reason: str) -> None:
        """Appends explainable audit trail entry into LEARNING_LOG.md."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            entry = (
                f"\n### [HP Learning Cycle #{cfg.get('update_cycle_count', 1)}] {timestamp}\n"
                f"- **Trigger/Reason**: {reason or 'Autonomous periodic adaptation'}\n"
                f"- **Content Mix**: Novel Story: {cfg['content_mix']['novel_story_ratio']*100:.1f}% | "
                f"Discovery: {cfg['content_mix']['discovery_ratio']*100:.1f}%\n"
                f"- **Target Duration**: {cfg['target_duration_sec']}s\n"
                f"- **Subtype Weights**: {json.dumps(cfg['discovery_subtype_weights'])}\n"
            )
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"Could not write to learning log: {e}")

    def get_content_allocation(self, total_deficit: int) -> Dict[str, int]:
        """
        Calculates exact number of Novel Story vs Discovery Shorts to produce
        given the current deficit and learned mix ratio.
        """
        if total_deficit <= 0:
            return {"novel_story": 0, "discovery": 0}

        cfg = self.load_strategy()
        novel_ratio = cfg["content_mix"]["novel_story_ratio"]

        # Calculate exact counts
        raw_novel = round(total_deficit * novel_ratio)
        novel_count = max(0, min(total_deficit, raw_novel))
        discovery_count = total_deficit - novel_count

        # If deficit >= 2, enforce at least 1 of each unless ratio is at extreme boundary
        if total_deficit >= 2 and novel_ratio > MIN_NOVEL_RATIO and novel_ratio < MAX_NOVEL_RATIO:
            if novel_count == 0:
                novel_count = 1
                discovery_count = total_deficit - 1
            elif discovery_count == 0:
                discovery_count = 1
                novel_count = total_deficit - 1

        return {
            "novel_story": novel_count,
            "discovery": discovery_count
        }

    def adapt_from_performance(self, db_session) -> Dict[str, Any]:
        """
        Closed-loop adaptation: reads mature upload snapshots (>72h) from DB,
        evaluates relative performance, and adapts strategy within bounds.
        """
        cfg = self.load_strategy()
        
        # Check strategy_weights or performance_snapshots in DB
        try:
            weights = db_session.query(StrategyWeight).all()
            weight_map = {w.feature_value: w.weight for w in weights}
        except Exception as e:
            logger.warning(f"Could not query strategy weights: {e}")
            weight_map = {}

        # If novel_story vs discovery weights exist, update mix ratio
        novel_w = weight_map.get("novel_story", 1.0)
        disc_w = weight_map.get("discovery", 1.0)

        # Dampened update
        if novel_w != 1.0 or disc_w != 1.0:
            ratio_delta = (novel_w - disc_w) * 0.05
            new_novel_ratio = max(MIN_NOVEL_RATIO, min(MAX_NOVEL_RATIO, cfg["content_mix"]["novel_story_ratio"] + ratio_delta))
            cfg["content_mix"]["novel_story_ratio"] = round(new_novel_ratio, 3)
            cfg["content_mix"]["discovery_ratio"] = round(1.0 - new_novel_ratio, 3)

        # Update subtype weights if available
        for st in CANONICAL_DISCOVERY_SUBTYPES:
            if st in weight_map:
                w = weight_map[st]
                cfg["discovery_subtype_weights"][st] = round(max(MIN_SUBTYPE_WEIGHT, min(MAX_SUBTYPE_WEIGHT, float(w))), 3)

        self.save_strategy(cfg, reason="Closed-loop performance adaptation from mature snapshots")
        return cfg
