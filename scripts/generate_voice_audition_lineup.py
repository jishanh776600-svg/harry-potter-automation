"""
STORY FORGE — Generate Voice Audition Lineup (60 Voices: 30 Male + 30 Female)
================================================================================
Generates a single combined, normalized audition audio file containing all 60
voice candidates with clear spoken labels ("Voice Male 01.", etc.) and produces
the authoritative audition manifest JSON.
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.voice_audition.voice_discovery import VoiceDiscoveryService
from engines.voice_audition.audition_synthesizer import AuditionSynthesizer, DEFAULT_AUDITION_SCRIPT
from engines.editorial.voice_selection_gate import VoiceSelectionGate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GenerateAuditionLineup")


def main():
    logger.info("==================================================")
    logger.info("STORY FORGE — 60-VOICE AUDITION LINEUP GENERATOR")
    logger.info("==================================================")

    # 1. Discover 30 Male + 30 Female candidates
    service = VoiceDiscoveryService(include_kokoro=True, include_edge=True)
    lineup, m_count, f_count = service.build_lineup(target_males=30, target_females=30)
    logger.info(f"Discovered {len(lineup)} total candidates ({m_count} Males, {f_count} Females)")

    if len(lineup) < 60:
        logger.warning(f"Note: Found {len(lineup)} candidates (fewer than 60 requested). Reporting exact count.")

    # 2. Setup output directories
    repo_output_dir = Path(__file__).parent.parent / "data" / "auditions"
    repo_output_dir.mkdir(parents=True, exist_ok=True)

    artifacts_dir = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 3. Synthesize combined audio and manifest
    synthesizer = AuditionSynthesizer(script=DEFAULT_AUDITION_SCRIPT, inter_candidate_silence=0.8)
    audio_path, manifest_path, manifest = synthesizer.generate_audition_session(
        lineup=lineup,
        output_dir=repo_output_dir,
        session_id="voice_audition_lineup_60"
    )

    logger.info(f"Audition audio successfully generated at: {audio_path}")
    logger.info(f"Audition manifest written to: {manifest_path}")
    logger.info(f"Total session duration: {manifest.total_duration_seconds:.2f} seconds ({manifest.total_duration_seconds / 60.0:.2f} minutes)")

    # 4. Copy to artifacts directory for immediate user auditioning
    art_audio = artifacts_dir / audio_path.name
    art_manifest = artifacts_dir / manifest_path.name
    try:
        shutil.copy2(audio_path, art_audio)
        shutil.copy2(manifest_path, art_manifest)
        logger.info(f"Copied audition media to artifact dir: {art_audio}")
    except Exception as e:
        logger.warning(f"Could not copy to artifacts dir: {e}")

    # 5. Verify production gate remains fail-closed
    assert VoiceSelectionGate.is_approved() is False, "CRITICAL ERROR: VoiceSelectionGate was erroneously approved!"
    logger.info("VoiceSelectionGate verified: CLOSED (VOICE SELECTION REQUIRED).")


if __name__ == "__main__":
    main()
