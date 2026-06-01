# Claude Clock

A dashboard that shows when Claude is in peak/off-peak usage hours and tracks your personal usage quota over time.

## What it does

- **Clock tab** — displays local and UTC time, highlights peak hours (Mon–Fri 13:00–19:00 UTC) when quota drains faster, and counts down to the next window change.
- **Usage tab** — shows your 5-hour window and 7-day quota utilisation with trend projection and a history chart.
- **Stats tab** — shows Headroom proxy performance over time: token reduction rate, cache hit rate, tokens saved, and proxy overhead. Powered by [Headroom](https://headroom-docs.vercel.app/docs), a context optimisation layer that wraps Claude to reduce token usage.

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium
```

### 2. Authenticate

Run the setup script once to log in and save a browser session:

```bash
venv/bin/python setup_auth.py
```

Follow the prompts to log in to claude.ai. Your session is saved locally in `browser_profile/`.

### 3. Configure

Copy `.env.example` to `.env` and fill in your organisation ID:

```bash
cp .env.example .env
# edit .env and set CLAUDE_ORG_ID=your-org-id
```

Your org ID appears in the URL when you visit `claude.ai/settings/usage`.

### 4. Run the poller once to verify

```bash
venv/bin/python poll_usage.py
```

You should see output like:
```
[2026-05-31 19:18 UTC]  5h: 35.0%  |  7d: 4.0%
```

### 5. Schedule with cron

Add the poller to your crontab to collect readings automatically. Run `crontab -e` and add:

```
* * * * * cd /path/to/claudeclock && venv/bin/python poll_usage.py >> poll.log 2>&1
```

Replace `/path/to/claudeclock` with the absolute path to this directory. The `cd` is required so relative paths inside the script resolve correctly. Using `venv/bin/python` directly (rather than activating the venv) is more reliable in cron's minimal shell environment.

Every reading is appended to `usage_history.jsonl` and the last 35 days are summarised into `usage_data.json` and `usage_data.js`.

### 6. Open the dashboard

Open `index.html` directly in your browser (`file://`) or serve it locally:

```bash
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.

## Headroom Stats setup

The Stats tab reads data collected by `headroom-perf/collect.py`, which runs `headroom perf` and parses its output into structured JSON.

### 1. Run the collector once

```bash
cd headroom-perf && python3 collect.py
```

### 2. Schedule with cron

```
* * * * * cd /home/chrisl/codetest/claudeclock/headroom-perf && python3 collect.py >> collect.log 2>&1
```

Each run appends a snapshot to `headroom-perf/perf_history.jsonl` and rebuilds `headroom-perf/perf_data.json` for the dashboard.

## Files

| File | Purpose |
|---|---|
| `index.html` | Dashboard UI (Clock, Usage, Stats tabs) |
| `poll_usage.py` | Fetches usage data from claude.ai and writes history |
| `setup_auth.py` | One-time browser login to save a session |
| `usage_history.jsonl` | Raw usage readings (one JSON object per line) |
| `usage_data.json` | Processed usage data read by the dashboard |
| `usage_data.js` | Same data as a JS assignment (enables `file://` mode) |
| `headroom-perf/collect.py` | Runs `headroom perf`, parses output, appends to JSONL |
| `headroom-perf/perf_history.jsonl` | Raw Headroom perf snapshots (includes `raw` field) |
| `headroom-perf/perf_data.json` | Processed perf data read by the Stats tab |

## Credits

- Peak/off-peak window logic is based on [isitclaudetime.com](https://isitclaudetime.com/en).
- Stats tab powered by [Headroom](https://headroom-docs.vercel.app/docs) — a context optimisation proxy for Claude.

## Notes

- If the poller starts returning 401 errors, your session has expired — re-run `setup_auth.py`.
- The `browser_profile/` directory contains your saved session. Do not commit it.
- The `.env` file contains your org ID. Do not commit it.
