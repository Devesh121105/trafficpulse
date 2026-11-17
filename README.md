# TrafficPulse

A Flask dashboard for six traffic monitoring points in and around Rohini, Delhi. The app has a separate Python collector, Supabase PostgreSQL storage, Matplotlib charts, and a scikit-learn speed forecast.

## Start in VS Code

1. Extract the ZIP and open the inner **TrafficPulse** folder in VS Code.
2. Open **Terminal → New Terminal**. With Python 3.11 or 3.12 installed, run these commands in Windows PowerShell.

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py
   ```

   On macOS or Linux, use `python3 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

3. Open <http://127.0.0.1:5000>. The dashboard starts in **Demo mode** with 30 days of simulated traffic.

## Connect TomTom and Supabase

1. Create a [TomTom developer API key](https://developer.tomtom.com/) and a [Supabase project](https://supabase.com/dashboard).
2. Open **SQL Editor** in Supabase, paste the contents of `schema.sql`, and run it against your existing or new database. It activates Madhuban Chowk (Outer Ring Road) and deactivates the four legacy IDs for Pitampura, ITO, AIIMS, and Dhaula Kuan while preserving their stored readings. Run it before starting the updated app and collector.
3. In Supabase, use **Connect → Session pooler** and copy its connection URI. Substitute your database password. Percent-encode reserved characters in the password and add `?sslmode=require` if the URI has no existing query string. See the [Supabase connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).
4. Copy `.env.example` to `.env` and enter your own values. Keep `.env` private.

   ```dotenv
   MODE=live
   TOMTOM_API_KEY=your_tomtom_key
   DATABASE_URL=your_supabase_postgres_uri
   ```

5. In a second VS Code terminal, check that the six configured points return traffic.

   ```powershell
   .\.venv\Scripts\python.exe collector.py --probe
   ```

   The coordinates in `schema.sql` are starting points. The [TomTom Flow Segment Data endpoint](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data) returns the closest road segment. Verify the matched segment and direction for each point during live setup.

6. Once your TomTom terms allow storing the readings and using them for training, run the collector. Six points at five-minute intervals make up to 1,728 TomTom requests per day with one continuously running collector. Check your plan's request allowance.

   ```powershell
   .\.venv\Scripts\python.exe collector.py
   ```

   Keep this terminal open to collect automatically. Use `--once` for one stored round. Both one-shot commands report how many roads succeeded and return a failure status if any road fails. Restart `app.py` after editing `.env`. A live dashboard with no saved observations displays a waiting message.

## Where to make changes

| File | What it does |
| --- | --- |
| `app.py` | Starts Flask and serves the dashboard, chart images, and JSON |
| `traffic.py` | Reads TomTom speeds, loads database observations, and generates demo data |
| `collector.py` | Collects readings and saves one observation per road per five-minute slot |
| `forecast.py` | Predicts 15 minutes ahead and scores all three models |
| `schema.sql` | Creates the database tables and seeds six monitoring points and deactivates the legacy points |
| `templates/index.html`, `static/` | Dashboard layout, styles, and interactions |

The forecast uses the latest three five-minute readings, local time of day, and a weekend indicator. It matches each example to an actual reading exactly 15 minutes later and requires at least 120 usable examples. It uses a chronological 60/20/20 split, with a gap at each split boundary to prevent look-ahead. Validation MAE selects a model. The dashboard reports MAE and RMSE for all candidates over the same test timestamps. A selected regression model is refit on all eligible past examples for the displayed forecast.

History filters accept a maximum of 30 days per view. The charts use IST. Blank portions of the speed line and dark grey cells in the heatmap indicate missing observations. Traffic Analysis compares average road speeds by hour. Congestion Check groups observations by how far speed was below the free-flow reference.

The Prediction tab shows a 15-minute forecast with test metrics for the selected model. The hour and day-type controls show a separate historical average for that road over the last 14 days.
