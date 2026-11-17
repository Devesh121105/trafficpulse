import hmac
import math
import os
from datetime import date, datetime, time, timedelta
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import pandas as pd
import psycopg
from flask import Flask, abort, jsonify, render_template, request, send_file
from matplotlib.figure import Figure

from collector import collect
from forecast import forecast
from traffic import IST, MODE, latest_readings, now_slot, readings, road_catalog, road_labels

app = Flask(__name__)


def local_time(value):
    return value.astimezone(IST).isoformat()


@app.errorhandler(psycopg.Error)
@app.errorhandler(RuntimeError)
def backend_error(error):
    app.logger.error("Backend error: %s", type(error).__name__)
    return jsonify(error="Database unavailable. Check DATABASE_URL and run schema.sql."), 503


@app.get("/")
def dashboard():
    today = now_slot().astimezone(IST).date()
    return render_template("index.html", roads=road_catalog(), demo=MODE == "demo",
                           today=today, start=today - timedelta(days=6))


@app.post("/api/collect")
def collect_scheduled():
    secret = os.getenv("CRON_SECRET", "").strip()
    authorization = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(
        authorization.encode(), f"Bearer {secret}".encode()
    ):
        return jsonify(error="Unauthorized"), 401

    key = os.getenv("TOMTOM_API_KEY", "").strip()
    if MODE != "live" or not key or not os.getenv("DATABASE_URL", "").strip():
        return jsonify(error="Live collection is not configured."), 503

    if not collect(key):
        return jsonify(error="One or more roads could not be collected. Check the function logs."), 503
    return jsonify(ok=True)


@app.get("/api/latest")
def latest():
    rows = latest_readings()
    result = []
    for road, label in road_labels().items():
        row = rows.get(road)
        if row is None:
            result.append({"id": road, "label": label, "status": "Waiting for data"})
            continue
        current, free = row["current_speed"], row["free_flow_speed"]
        result.append({
            "id": road, "label": label, "speed": current, "free": free,
            "below": round(max(0, (free - current) / free * 100)) if free else None,
            "updated": local_time(row["collected_at"]),
            "status": "Stale" if now_slot() - row["collected_at"] >= timedelta(minutes=10)
            else "Sample" if MODE == "demo" else "Current"
        })
    return jsonify(result)


@app.get("/api/forecast/<road>")
def road_forecast(road):
    if road not in road_labels():
        abort(404)
    end = now_slot()
    rows = readings(road, end - timedelta(days=14), end)
    result = forecast(rows)
    buckets = {"weekday": [[] for _ in range(24)], "weekend": [[] for _ in range(24)]}
    for row in rows:
        observed = row["collected_at"].astimezone(IST)
        day_type = "weekend" if observed.weekday() >= 5 else "weekday"
        buckets[day_type][observed.hour].append(row["current_speed"])
    result["hourly_profile"] = {
        day_type: [
            {"speed": round(sum(values) / len(values), 1), "count": len(values)} if values else None
            for values in hours
        ]
        for day_type, hours in buckets.items()
    }
    if "speed" in result:
        result["stale"] = end - result["issued"] >= timedelta(minutes=10)
        result["issued"] = local_time(result["issued"])
        result["target"] = local_time(result["target"])
    return jsonify(result)


def chart_dates():
    try:
        start = date.fromisoformat(request.args.get("start", ""))
        end = date.fromisoformat(request.args.get("end", ""))
    except ValueError:
        abort(400, "Choose valid dates.")
    if not 0 <= (end - start).days < 30:
        abort(400, "Choose a date range of 1 to 30 days.")
    return datetime.combine(start, time.min, IST), datetime.combine(end, time(23, 55), IST)


@app.get("/traffic-analysis/<kind>")
def traffic_analysis(kind):
    if kind not in ("heatmap", "congestion"):
        abort(404)
    first, last = chart_dates()
    labels = road_labels()
    observations = {road: readings(road, first, last) for road in labels}

    if kind == "congestion":
        counts = {"Low": 0, "Medium": 0, "High": 0}
        skipped = 0
        for rows in observations.values():
            for row in rows:
                speed, free = row["current_speed"], row["free_flow_speed"]
                if not free or free <= 0:
                    skipped += 1
                elif speed <= free * 0.6:
                    counts["High"] += 1
                elif speed <= free * 0.8:
                    counts["Medium"] += 1
                else:
                    counts["Low"] += 1
        total = sum(counts.values())
        rates = {label: count * 100 / total if total else 0 for label, count in counts.items()}
        return render_template("traffic-analysis.html", kind=kind, counts=counts,
                               rates=rates, total=total, skipped=skipped)

    grid = []
    for road, label in labels.items():
        buckets = [[] for _ in range(24)]
        for row in observations[road]:
            hour = row["collected_at"].astimezone(IST).hour
            buckets[hour].append(row["current_speed"])
        grid.append((label, [sum(values) / len(values) if values else None for values in buckets]))

    highest = max((speed for _, speeds in grid for speed in speeds if speed is not None), default=0)
    maximum = max(60, math.ceil(highest / 10) * 10)
    return render_template("traffic-analysis.html", kind=kind, grid=grid, maximum=maximum)


@app.get("/chart/<kind>/<road>")
def chart(kind, road):
    if road not in road_labels() or kind not in ("trend", "hourly"):
        abort(404)
    first, last = chart_dates()
    rows = readings(road, first, last)
    figure = Figure(figsize=(8, 3.5), layout="constrained", facecolor="#0b172d")
    axes = figure.subplots()
    axes.set_facecolor("#0b172d")
    axes.tick_params(colors="#b9cce5", labelsize=9)
    for spine in axes.spines.values():
        spine.set_color("#29415c")
    if not rows:
        axes.text(0.5, 0.5, "No observations in this date range", ha="center", va="center", color="#b9cce5")
        axes.set_axis_off()
    else:
        frame = pd.DataFrame(rows).set_index("collected_at")
        frame.index = pd.to_datetime(frame.index, utc=True).tz_convert(IST)
        speeds = frame["current_speed"].reindex(pd.date_range(first, last, freq="5min"))
        if kind == "trend":
            axes.plot(speeds.index, speeds, color="#54cfff", linewidth=1.3, marker=".", markersize=1.7)
            axes.set_ylabel("Speed (km/h)", color="#b9cce5")
            locator = mdates.AutoDateLocator(tz=IST)
            axes.xaxis.set_major_locator(locator)
            axes.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=IST))
            axes.xaxis.get_offset_text().set_color("#b9cce5")
            axes.grid(color="#223b58", alpha=0.7)
        else:
            hourly = speeds.groupby(speeds.index.hour).mean().reindex(range(24)).dropna()
            axes.bar(hourly.index, hourly.values, color="#78c8fc", width=0.76)
            axes.set_xticks(range(0, 24, 2))
            axes.set_xlim(-0.7, 23.7)
            axes.set_ylabel("Average speed (km/h)", color="#b9cce5")
            axes.set_axisbelow(True)
            axes.grid(axis="y", color="#223b58", alpha=0.7)
        axes.set_xlabel("Time (IST)", color="#b9cce5")
    output = BytesIO()
    figure.savefig(output, format="png", dpi=120)
    output.seek(0)
    return send_file(output, mimetype="image/png", max_age=0)


if __name__ == "__main__":
    app.run()
