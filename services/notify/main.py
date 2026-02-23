"""Notify service — sends daily ntfy notifications with cat sighting summaries."""

import asyncio
import os
from datetime import datetime, timedelta

import requests

CATALOG_URL = os.environ.get("CATALOG_URL", "http://catalog:8001")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NOTIFY_TIME = os.environ.get("NOTIFY_TIME", "08:00")
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "12"))


def seconds_until(target_time_str: str) -> float:
    """Calculate seconds from now until the next occurrence of target_time (HH:MM)."""
    now = datetime.now()
    hour, minute = map(int, target_time_str.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def get_sighting_count() -> int:
    """Query catalog API for sightings in the lookback window."""
    since = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)
    since_iso = since.isoformat() + "Z"
    # Fetch with a high limit; paginate if needed
    total = 0
    offset = 0
    while True:
        resp = requests.get(
            f"{CATALOG_URL}/sightings",
            params={"since": since_iso, "limit": 200, "offset": offset},
            timeout=10,
        )
        resp.raise_for_status()
        batch = resp.json()
        total += len(batch)
        if len(batch) < 200:
            break
        offset += 200
    return total


def send_notification(count: int):
    """Send a notification via ntfy."""
    if count == 0:
        body = f"No cat sightings in the last {LOOKBACK_HOURS} hours"
    elif count == 1:
        body = f"1 cat sighting in the last {LOOKBACK_HOURS} hours"
    else:
        body = f"{count} cat sightings in the last {LOOKBACK_HOURS} hours"

    resp = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        headers={"Title": "Cat Catalog"},
        data=body,
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Notification sent: {body}")


async def run():
    if not NTFY_TOPIC:
        print("ERROR: NTFY_TOPIC is not set. Exiting.")
        return

    print(f"Notify service started")
    print(f"  Topic:    {NTFY_TOPIC}")
    print(f"  Time:     {NOTIFY_TIME}")
    print(f"  Lookback: {LOOKBACK_HOURS}h")
    print(f"  Catalog:  {CATALOG_URL}")

    while True:
        wait = seconds_until(NOTIFY_TIME)
        next_run = datetime.now() + timedelta(seconds=wait)
        print(f"Next notification at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep(wait)

        try:
            count = get_sighting_count()
            send_notification(count)
        except Exception as e:
            print(f"Error sending notification: {e}")


if __name__ == "__main__":
    asyncio.run(run())
