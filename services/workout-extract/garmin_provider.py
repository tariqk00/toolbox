"""
Garmin Activity Provider.
Fetches activity metrics for a given date from Garmin Connect.
Designed to be called per gym session to enrich unified workout records.
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger("WorkoutExtract.Garmin")

TOOLBOX_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = TOOLBOX_ROOT / "config"
SECRETS_ENV_PATH = CONFIG_DIR / "secrets.env"
GARMIN_TOKEN_DIR = CONFIG_DIR / ".garminconnect"

# Activity types we consider "gym/strength" workouts — prefer these when matching
STRENGTH_TYPES = {
    "strength_training",
    "functional_strength_training",
    "weight_training",
    "weightlifting",
    "fitness_equipment",
    "indoor_climbing",
    "bouldering",
    "pilates",
    "yoga",
    "martial_arts",
    "boxing",
}


def load_credentials():
    if SECRETS_ENV_PATH.exists():
        load_dotenv(SECRETS_ENV_PATH)
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        logger.error("GARMIN_EMAIL and GARMIN_PASSWORD must be set in %s", SECRETS_ENV_PATH)
        return None, None
    return email, password


def authenticate():
    email, password = load_credentials()
    if not email:
        return None

    garmin = Garmin(email, password)
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    try:
        garmin.login(str(GARMIN_TOKEN_DIR))
        logger.info("Garmin: authenticated (resumed session)")
    except (FileNotFoundError, GarminConnectAuthenticationError):
        logger.info("Garmin: no saved session, performing fresh login...")
        try:
            garmin.login()
            garmin.garth.dump(str(GARMIN_TOKEN_DIR))
            logger.info("Garmin: fresh login successful")
        except GarminConnectAuthenticationError as e:
            logger.error("Garmin: authentication failed: %s", e)
            return None

    return garmin


def _format_hr_zones(activity):
    zones = {}
    for z in range(1, 6):
        val = activity.get(f"hrTimeInZone_{z}", 0)
        if val:
            zones[f"z{z}"] = int(val)
    return zones or None


def _build_metrics(activity):
    """Extract the metrics we care about from a Garmin activity dict."""
    return {
        "activity_id": str(activity.get("activityId", "")),
        "activity_name": activity.get("activityName", ""),
        "activity_type": activity.get("activityType", {}).get("typeKey", "unknown"),
        "start_time": activity.get("startTimeLocal", ""),
        "duration_seconds": int(activity.get("duration", 0) or 0),
        "calories": int(activity.get("calories", 0) or 0),
        "avg_hr": int(activity.get("averageHR", 0) or 0) or None,
        "max_hr": int(activity.get("maxHR", 0) or 0) or None,
        "hr_zones": _format_hr_zones(activity),
        "training_effect": {
            "aerobic": activity.get("aerobicTrainingEffect"),
            "anaerobic": activity.get("anaerobicTrainingEffect"),
        } if activity.get("aerobicTrainingEffect") else None,
        "body_battery_impact": activity.get("differenceBodyBattery"),
        "total_sets": activity.get("totalSets"),
        "total_reps": activity.get("totalReps"),
    }


def get_activity_for_date(garmin_client, date_str, gym_duration_minutes=None):
    """
    Fetch Garmin activity for a given date and return metrics dict.
    Prefers strength-type activities. Falls back to first activity of the day.
    Returns None if no activities found.

    Args:
        garmin_client: Authenticated Garmin instance
        date_str: Date in YYYY-MM-DD format
        gym_duration_minutes: Optional hint for best-match selection
    """
    if not garmin_client:
        return None

    try:
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=1)
        activities = garmin_client.get_activities_by_date(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.warning("Garmin: failed to fetch activities for %s: %s", date_str, e)
        return None

    if not activities:
        logger.info("Garmin: no activities found for %s", date_str)
        return None

    # Prefer strength-type activities
    strength_activities = [
        a for a in activities
        if a.get("activityType", {}).get("typeKey", "") in STRENGTH_TYPES
    ]

    candidates = strength_activities if strength_activities else activities

    # If we have a duration hint, pick the closest match
    if gym_duration_minutes and len(candidates) > 1:
        gym_secs = gym_duration_minutes * 60
        best = min(candidates, key=lambda a: abs((a.get("duration", 0) or 0) - gym_secs))
    else:
        best = candidates[0]

    activity_type = best.get("activityType", {}).get("typeKey", "unknown")
    logger.info("Garmin: matched activity '%s' (%s) for %s",
                best.get("activityName", ""), activity_type, date_str)

    return _build_metrics(best)
