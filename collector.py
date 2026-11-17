import argparse
import os
import time
from datetime import timedelta

import psycopg

from forecast import forecast
from traffic import MODE, STEP, connect, now_slot, readings, road_catalog, tomtom_speed


def collect(key, probe=False):
    slot = now_slot()
    succeeded = 0
    with connect() as db:
        roads = road_catalog(db)
        if not roads:
            print("No roads are configured. Run schema.sql in Supabase.", flush=True)
            return False
        print(f"Supabase connected. Found {len(roads)} monitored roads.", flush=True)
        for road in roads:
            road_id = road["id"]
            if not probe and db.execute(
                "select 1 from traffic_readings where road_id = %s and collected_at = %s",
                (road_id, slot),
            ).fetchone():
                succeeded += 1
                print(f"{road['label']}: already stored for this five-minute slot.", flush=True)
                continue
            try:
                current, free = tomtom_speed(road["latitude"], road["longitude"], key)
            except ValueError as error:
                print(f"{road['label']}: {error}", flush=True)
                continue
            if not probe:
                db.execute("insert into traffic_readings values (%s, %s, %s, %s) on conflict do nothing",
                           (road_id, slot, current, free))
                result = forecast(readings(road_id, slot - timedelta(days=14), slot, db))
                if "speed" in result:
                    db.execute("""insert into traffic_forecasts values (%s, %s, %s, %s, %s)
                                  on conflict do nothing""",
                               (road_id, result["issued"], result["target"], result["model"], result["speed"]))
                db.commit()
            succeeded += 1
            action = "TomTom responded" if probe else "Reading stored"
            print(f"{road['label']}: {action} · {current} km/h", flush=True)
    print(f"{succeeded}/{len(roads)} roads ready.", flush=True)
    return succeeded == len(roads)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Store one collection round")
    mode.add_argument("--probe", action="store_true", help="Check TomTom responses without storing them")
    args = parser.parse_args()
    key = os.getenv("TOMTOM_API_KEY", "").strip()
    if MODE != "live":
        raise SystemExit("Set MODE=live in .env beside collector.py.")
    missing = [name for name in ("TOMTOM_API_KEY", "DATABASE_URL") if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Missing .env settings: " + ", ".join(missing))
    while True:
        slot = now_slot()
        try:
            complete = collect(key, probe=args.probe)
        except psycopg.Error as error:
            complete = False
            print(f"Supabase database error ({type(error).__name__}). Check the connection and schema.", flush=True)
            if args.once or args.probe:
                raise SystemExit(1) from None
        if args.once or args.probe:
            raise SystemExit(0 if complete else 1)
        time.sleep(max(0, (slot + STEP).timestamp() - time.time()))
