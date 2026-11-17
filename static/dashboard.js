const byId = id => document.getElementById(id);
const formatTime = value => new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short"
}).format(new Date(value)) + " IST";
const road = byId("road");
let currentPanel = "live";

function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
}

async function getJson(url) {
    const response = await fetch(url, {cache: "no-store"});
    if (!response.ok) throw new Error("Could not load data. Check the Flask terminal.");
    return response.json();
}

async function loadLive() {
    try {
        const roads = await getJson("/api/latest");
        byId("live-error").textContent = "";
        const withReadings = roads.filter(row => row.updated);
        const newest = withReadings.reduce((latest, row) =>
            !latest || new Date(row.updated) > new Date(latest.updated) ? row : latest, null);
        const latestTime = newest ? new Intl.DateTimeFormat("en-IN", {
            timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false
        }).format(new Date(newest.updated)) + " IST" : "Waiting for data";
        const stats = roads.map(row => [row.label, row.updated ? row.speed + " km/h" : "Waiting for data", row.status]);
        stats.push(["Latest update", latestTime, newest ? newest.status : ""]);
        byId("summary").replaceChildren(...stats.map(([label, value, status]) => {
            const card = element("article", "", "summary-card");
            card.append(element("h2", label), element("strong", value), element("span", status));
            return card;
        }));
        byId("cards").replaceChildren(...roads.map(row => {
            const card = element("article", "");
            card.append(element("span", row.status, "status"), element("h3", row.label));
            if (row.updated) {
                card.append(element("strong", row.speed + " km/h", "speed"));
                if (row.free !== null) {
                    card.append(element("p", row.free + " km/h free flow · " + row.below + "% below"));
                }
                card.append(element("p", "Updated " + formatTime(row.updated)));
            }
            return card;
        }));
    } catch (error) {
        byId("live-error").textContent = error.message;
    }
}

function loadCharts(charts, start, end, error) {
    if (!road.value) return;
    error.textContent = "";
    const params = new URLSearchParams({start, end});
    for (const [id, kind] of charts) {
        const image = byId(id);
        image.onerror = () => { error.textContent = "Could not load the charts."; };
        image.src = "/chart/" + kind + "/" + encodeURIComponent(road.value) + "?" + params;
    }
}

function loadOverview() {
    loadCharts([["overview-hourly", "hourly"]],
        road.dataset.start, road.dataset.end, byId("overview-error"));
}

const analysisRequests = {};

async function loadAnalysis(kind, targetId, start, end) {
    const target = byId(targetId);
    const requestId = (analysisRequests[kind] ?? 0) + 1;
    analysisRequests[kind] = requestId;
    const days = (Date.parse(end) - Date.parse(start)) / 86400000;
    if (!(days >= 0 && days < 30)) {
        target.textContent = "Choose a date range of 1 to 30 days.";
        return;
    }

    target.textContent = "Loading…";
    try {
        const params = new URLSearchParams({start, end});
        const response = await fetch("/traffic-analysis/" + kind + "?" + params);
        if (!response.ok) throw new Error("Could not load traffic analysis.");
        const html = await response.text();
        if (analysisRequests[kind] === requestId) target.innerHTML = html;
    } catch (error) {
        if (analysisRequests[kind] === requestId) target.textContent = error.message;
    }
}

function loadHistory() {
    const start = byId("start").value;
    const end = byId("end").value;
    const days = (Date.parse(end) - Date.parse(start)) / 86400000;
    const error = byId("history-error");
    if (!(days >= 0 && days < 30)) {
        error.textContent = "Choose a date range of 1 to 30 days.";
    } else {
        loadCharts([["trend", "trend"]], start, end, error);
    }
    loadAnalysis("heatmap", "heatmap", start, end);
}

function loadCongestion() {
    loadAnalysis("congestion", "congestion-chart", byId("start").value, byId("end").value);
}

const forecastRoad = byId("forecast-road");
const estimateHour = byId("estimate-hour");
const estimateDay = byId("estimate-day");
let forecastRequest = 0;
let hourlyProfile = null;

function updateHourlyEstimate() {
    const hour = estimateHour.value.padStart(2, "0") + ":00";
    const dayLabel = estimateDay.selectedOptions[0].textContent;
    byId("estimate-hour-label").textContent = hour;
    const entry = hourlyProfile?.[estimateDay.value]?.[Number(estimateHour.value)];
    byId("estimated-speed").textContent = entry ? entry.speed + " km/h" : "—";
    byId("estimate-note").textContent = entry
        ? dayLabel + " at " + hour + " IST · Average of " + entry.count + " readings from the last 14 days."
        : hourlyProfile ? "No readings for " + dayLabel.toLowerCase() + " at " + hour + " IST."
        : "The hourly estimate will appear after the road data loads.";
}

async function loadForecast() {
    const requestId = ++forecastRequest;
    const prediction = byId("prediction");
    const metricCards = byId("prediction-metrics");
    const metricNote = byId("forecast-metric-note");
    prediction.textContent = forecastRoad.value ? "Loading forecast…" : "No monitored roads are available.";
    byId("evaluation").hidden = true;
    metricCards.hidden = true;
    metricNote.textContent = "";
    hourlyProfile = null;
    updateHourlyEstimate();
    if (!forecastRoad.value) return;

    try {
        const result = await getJson("/api/forecast/" + encodeURIComponent(forecastRoad.value));
        if (requestId !== forecastRequest) return;
        hourlyProfile = result.hourly_profile;
        updateHourlyEstimate();
        if (result.message) {
            prediction.textContent = result.message;
            return;
        }

        const selectedModel = result.metrics.find(metric => metric.model === result.model);
        if (selectedModel) {
            byId("forecast-mae").textContent = Number(selectedModel.mae).toFixed(2) + " km/h";
            byId("forecast-rmse").textContent = Number(selectedModel.rmse).toFixed(2) + " km/h";
            metricNote.textContent = "15-minute forecast errors for " + result.model +
                " on " + result.test_count + " later readings held out for testing.";
            metricCards.hidden = false;
        }

        prediction.replaceChildren(
            element("h3", "15-minute speed forecast"),
            element("strong", result.speed + " km/h"),
            element("p", "Predicted for " + formatTime(result.target)),
            element("p", "Latest speed: " + result.latest_speed + " km/h at " + formatTime(result.issued)),
            element("p", "Method: " + result.model)
        );
        if (result.stale) {
            prediction.append(element("p", "Traffic updates are delayed. This forecast uses an older reading."));
        }
        byId("test-count").textContent =
            "All methods were tested on the same " + result.test_count + " past readings.";
        byId("metrics").replaceChildren(...result.metrics.map(metric => {
            const row = document.createElement("tr");
            row.append(element("td", metric.model), element("td", metric.mae), element("td", metric.rmse));
            return row;
        }));
        byId("evaluation").hidden = false;
    } catch (error) {
        if (requestId === forecastRequest) prediction.textContent = error.message;
    }
}

forecastRoad.addEventListener("change", loadForecast);
estimateHour.addEventListener("input", updateHourlyEstimate);
estimateDay.addEventListener("change", updateHourlyEstimate);

const tabs = document.querySelectorAll("[data-panel]");
for (const button of tabs) {
    button.addEventListener("click", () => {
        currentPanel = button.dataset.panel;
        for (const tab of tabs) {
            const selected = tab === button;
            tab.setAttribute("aria-pressed", selected);
            byId(tab.dataset.panel).hidden = !selected;
        }
        byId("road-filter").hidden = ["congestion", "forecast"].includes(currentPanel);
        byId("history-form").hidden = !["history", "congestion"].includes(currentPanel);
        if (currentPanel === "live") loadOverview();
        if (currentPanel === "history") loadHistory();
        if (currentPanel === "congestion") loadCongestion();
        if (currentPanel === "forecast") loadForecast();
    });
}
road.addEventListener("change", () => {
    if (currentPanel === "live") loadOverview();
    if (currentPanel === "history") loadHistory();
});
byId("history-form").addEventListener("submit", event => {
    event.preventDefault();
    if (currentPanel === "congestion") loadCongestion();
    else loadHistory();
});
loadLive();
loadOverview();
setInterval(loadLive, 60000);
setInterval(() => { if (currentPanel === "forecast") loadForecast(); }, 300000);
