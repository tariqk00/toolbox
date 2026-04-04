"""
Workout Extract Service — Entry Point.
Orchestrates gym screenshot extraction + Garmin enrichment into unified workout records.
Runs daily via systemd timer.

Usage:
  python main.py                  # dry-run (default)
  python main.py --execute        # extract + save
  python main.py --execute --force  # reprocess already-extracted screenshots
  python main.py --gym-only       # skip Garmin
  python main.py --garmin-only    # only sync Garmin .fit files (no screenshot extraction)
"""
import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# Ensure toolbox root is on path
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent.parent
PARENT_DIR = TOOLBOX_ROOT.parent
SERVICE_DIR = Path(__file__).resolve().parent
for p in [str(TOOLBOX_ROOT), str(PARENT_DIR), str(SERVICE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.google_api import GoogleAuth
import gym_extract
import garmin_provider
import merger

CONFIG_DIR = TOOLBOX_ROOT / "config"
SECRETS_ENV_PATH = CONFIG_DIR / "secrets.env"
LOG_DIR = TOOLBOX_ROOT / "logs"
LOG_FILE = LOG_DIR / "workout-extract.log"

LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("WorkoutExtract")

fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
logging.getLogger("WorkoutExtract").addHandler(fh)


def load_gemini_key():
    if SECRETS_ENV_PATH.exists():
        load_dotenv(SECRETS_ENV_PATH)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        logger.error("GEMINI_API_KEY not set in %s", SECRETS_ENV_PATH)
        sys.exit(1)
    return key


def get_drive_service():
    auth = GoogleAuth(base_dir=str(TOOLBOX_ROOT))
    creds = auth.get_credentials(
        token_filename="token_full_drive.json",
        credentials_filename="config/credentials.json",
    )
    return auth.get_service("drive", "v3", creds)


def run(args):
    start = time.time()
    dry_run = not args.execute

    if dry_run:
        logger.info("=== Workout Extract — DRY RUN ===")
    else:
        logger.info("=== Workout Extract — EXECUTE ===")

    drive_service = get_drive_service()

    # --- Garmin sync (.fit files) ---
    garmin_client = None
    if not args.gym_only:
        garmin_client = garmin_provider.authenticate()
        if not garmin_client:
            logger.warning("Garmin auth failed — workout records will have no biometric data")

    # --- Gym screenshot extraction ---
    sessions = []
    if not args.garmin_only:
        api_key = load_gemini_key()
        sessions = gym_extract.extract_all(
            drive_service, api_key,
            dry_run=dry_run,
            force=args.force,
        )
        logger.info("Extracted %d gym sessions", len(sessions))

    # --- Merge and save unified records ---
    saved = 0
    for session in sessions:
        date = session.get("date_completed") or ""
        gym_duration = None
        metrics = session.get("metrics") or {}
        if metrics.get("duration_minutes"):
            gym_duration = metrics["duration_minutes"]

        garmin_data = None
        if garmin_client and date:
            garmin_data = garmin_provider.get_activity_for_date(
                garmin_client, date[:10], gym_duration_minutes=gym_duration
            )

        record = merger.create_unified_record(session, garmin=garmin_data)

        file_id = merger.save_unified_record(drive_service, record, dry_run=dry_run)
        if file_id:
            saved += 1

    elapsed = int(time.time() - start)
    logger.info("=== Done in %ds. Sessions extracted: %d, Records saved: %d ===",
                elapsed, len(sessions), saved)


def parse_args():
    parser = argparse.ArgumentParser(description="Workout Extract Service")
    parser.add_argument("--execute", action="store_true",
                        help="Execute extraction and save (default is dry-run)")
    parser.add_argument("--force", action="store_true",
                        help="Reprocess already-extracted screenshots")
    parser.add_argument("--gym-only", action="store_true",
                        help="Skip Garmin enrichment")
    parser.add_argument("--garmin-only", action="store_true",
                        help="Skip gym screenshot extraction")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    run(args)
