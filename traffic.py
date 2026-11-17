import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
MODE = os.getenv("MODE", "demo").strip().lower()
IST = timezone(timedelta(hours=5, minutes=30))
STEP = timedelta(minutes=5)
DEMO_ROADS = [
    {"id": "rohini-5", "label": "Rohini Sector 5", "latitude": 28.711948, "longitude": 77.107817},
    {"id": "madhuban-chowk", "label": "Madhuban Chowk (Outer Ring Road)", "latitude": 28.70560067, "longitude": 77.13226299},
    {"id": "rohini-7", "label": "Rohini Sector 7", "latitude": 28.709386, "longitude": 77.112108},
    {"id": "rithala", "label": "Rithala", "latitude": 28.7209, "longitude": 77.1073},
    {"id": "prashant-vihar", "label": "Prashant Vihar", "latitude": 28.71079, "longitude": 77.13414},
    {"id": "rohini-16", "label": "Rohini Sector 16", "latitude": 28.739163, "longitude": 77.127274},
]
TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/15/json"


def now_slot():
    now = datetime.now(timezone.utc)
    return now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)


def connect():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Add DATABASE_URL to .env for live mode.")
    return psycopg.connect(url, connect_timeout=8, row_factory=dict_row)


def road_catalog(db=None):
    if MODE == "demo":
        return DEMO_ROADS
    if db is None:
        with connect() as connection:
            return road_catalog(connection)
    return db.execute(
        "select id, label, latitude, longitude from road_segments where active order by label"
    ).fetchall()


def road_labels():
    return {road["id"]: road["label"] for road in road_catalog()}


def valid_speed(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 150


def tomtom_speed(latitude, longitude, key):
    try:
        response = requests.get(TOMTOM_URL, params={
            "key": key, "point": f"{latitude},{longitude}", "unit": "kmph"
        }, timeout=10)
    except requests.RequestException:
        raise ValueError("TomTom network request failed.") from None

    if not response.ok:
        raise ValueError(f"TomTom returned HTTP {response.status_code}.")
    try:
        segment = response.json()["flowSegmentData"]
        speed = segment["currentSpeed"]
        free = segment.get("freeFlowSpeed")
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("TomTom response is missing speed data.") from None
    if not valid_speed(speed):
        raise ValueError("TomTom returned an invalid current speed.")
    return speed, free if valid_speed(free) and free > 0 else None


def demo_readings(road, start, end):
    end = min(end, now_slot())
    index = [item["id"] for item in DEMO_ROADS].index(road)
    free = 56 + 5 * index
    rows = []
    while start <= end:
        local = start.astimezone(IST)
        hour = local.hour + local.minute / 60
        busy = 0.75 if local.weekday() >= 5 else 1
        rush = 22 * math.exp(-((hour - 9) / 2) ** 2)
        rush += 26 * math.exp(-((hour - 18) / 2.5) ** 2)
        rng = random.Random(int(start.timestamp()) + index)
        speed = round(free - 6 - busy * rush + rng.uniform(-3, 3), 1)
        rows.append({"collected_at": start, "current_speed": speed, "free_flow_speed": free})
        start += STEP
    return rows


def readings(road, start, end, db=None):
    if MODE == "demo":
        return demo_readings(road, max(start, now_slot() - timedelta(days=30)), end)
    query = """select collected_at, current_speed, free_flow_speed from traffic_readings
               where road_id = %s and collected_at >= %s and collected_at <= %s
               order by collected_at"""
    if db is not None:
        return db.execute(query, (road, start, end)).fetchall()
    with connect() as connection:
        return connection.execute(query, (road, start, end)).fetchall()


def latest_readings():
    if MODE == "demo":
        slot = now_slot()
        return {road: demo_readings(road, slot, slot)[0] for road in road_labels()}
    with connect() as db:
        rows = db.execute("""select distinct on (road_id) road_id, collected_at,
                             current_speed, free_flow_speed from traffic_readings
                             order by road_id, collected_at desc""").fetchall()
    return {row["road_id"]: row for row in rows}
