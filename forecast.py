import math
from datetime import timedelta

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from traffic import IST, STEP

HORIZON = timedelta(minutes=15)


def features(speeds, slot):
    previous = [speeds.get(slot - STEP * offset) for offset in range(3)]
    if None in previous:
        return None
    target = (slot + HORIZON).astimezone(IST)
    angle = 2 * math.pi * (target.hour * 60 + target.minute) / 1440
    return previous + [math.sin(angle), math.cos(angle), int(target.weekday() >= 5)]


def forecast(rows):
    speeds = {row["collected_at"]: row["current_speed"] for row in rows}
    examples = []
    for slot in sorted(speeds):
        inputs = features(speeds, slot)
        target = speeds.get(slot + HORIZON)
        if inputs is not None and target is not None:
            examples.append((slot, inputs, target))

    if len(examples) < 120:
        return {"message": f"Waiting for history. {len(examples)} of 120 usable training examples available."}
    first = len(examples) * 6 // 10
    second = len(examples) * 8 // 10
    # Targets from one period must occur before the next period's first prediction.
    train = [row for row in examples[:first] if row[0] + HORIZON < examples[first][0]]
    validation = [row for row in examples[first:second] if row[0] + HORIZON < examples[second][0]]
    test = examples[second:]

    def fit(model, period):
        model.fit([row[1] for row in period], [row[2] for row in period])

    def predict(model, period):
        inputs = [row[1] for row in period]
        values = model.predict(inputs) if model is not None else [row[0] for row in inputs]
        return [max(0, float(value)) for value in values]

    models = {"Latest speed baseline": None, "Linear Regression": LinearRegression(),
              "Random Forest": RandomForestRegressor(n_estimators=25, max_depth=7, random_state=12)}
    validation_error = {}
    metrics = []
    for name, model in models.items():
        if model is not None:
            fit(model, train)
        validation_error[name] = mean_absolute_error(
            [row[2] for row in validation], predict(model, validation))
        actual = [row[2] for row in test]
        predicted = predict(model, test)
        metrics.append({"model": name, "mae": round(mean_absolute_error(actual, predicted), 2),
                        "rmse": round(math.sqrt(mean_squared_error(actual, predicted)), 2)})

    chosen = min(models, key=validation_error.get)
    model = models[chosen]
    if model is not None:
        fit(model, examples)
    issued = max(speeds)
    latest = features(speeds, issued)
    if latest is None:
        chosen, model, latest = "Latest speed baseline", None, [speeds[issued]]
    return {"model": chosen, "speed": round(predict(model, [(issued, latest, None)])[0], 1),
            "latest_speed": speeds[issued], "issued": issued, "target": issued + HORIZON, "metrics": metrics, "test_count": len(test)}
