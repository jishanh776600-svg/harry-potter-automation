"""
Script to execute Bella voice audition suite.
Generates all 48 audition samples across 16 delivery profiles and 3 intensity levels.
"""
import sys
import logging
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from engines.bella_audition_engine import BellaAuditionRunner

if __name__ == "__main__":
    runner = BellaAuditionRunner()
    result = runner.run_audition()
    print("\n" + "=" * 70)
    print("BELLA VOICE AUDITION GENERATION COMPLETE")
    print("=" * 70)
    print(f"Total Profiles: {result['total_profiles']}")
    print(f"Total Samples Generated: {result['total_samples']}")
    print(f"Audition Directory: {result['output_directory']}")
    print(f"Metadata JSON: {result['metadata_json']}")
    print(f"Audition Index README: {result['readme_index']}")
    print("=" * 70)
