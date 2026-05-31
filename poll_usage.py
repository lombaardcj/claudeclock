#!/usr/bin/env python3
"""
Claude usage poller — run setup_auth.py once first.

Suggested cron (every 15 min):
  */15 * * * * cd /home/chrisl/codetest/claudeclock && python3 poll_usage.py >> poll.log 2>&1
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
ENV_FILE = BASE / ".env"
PROFILE_DIR = BASE / "browser_profile"
HIST_FILE = BASE / "usage_history.jsonl"
DATA_FILE = BASE / "usage_data.json"
KEEP_DAYS = 35


def load_env():
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fetch_usage(org_id: str) -> dict:
    if not PROFILE_DIR.exists():
        raise FileNotFoundError(f"{PROFILE_DIR} not found — run setup_auth.py first")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

        resp = context.request.get(
            f"https://claude.ai/api/organizations/{org_id}/usage",
            headers={
                "Accept": "application/json",
                "Referer": "https://claude.ai/settings/usage",
            },
        )

        if resp.status == 401:
            context.close()
            raise PermissionError("Session expired — run setup_auth.py again")

        if not resp.ok:
            context.close()
            raise RuntimeError(f"HTTP {resp.status} from usage API")

        data = resp.json()
        # cookies are auto-persisted to PROFILE_DIR by launch_persistent_context
        context.close()

    return data


def rebuild_data_file():
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    readings = []
    if HIST_FILE.exists():
        with open(HIST_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    ts = datetime.fromisoformat(r["ts"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        readings.append(r)
                except (ValueError, KeyError, json.JSONDecodeError):
                    pass
    payload = {"readings": readings, "last_updated": datetime.now(timezone.utc).isoformat()}
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f)
    # JS version so index.html works from file:// without a local server
    with open(BASE / "usage_data.js", "w") as f:
        f.write(f"window.USAGE_DATA={json.dumps(payload)};")


def main():
    load_env()
    org_id = os.environ.get("CLAUDE_ORG_ID", "").strip()
    if not org_id:
        print("ERROR: Set CLAUDE_ORG_ID in .env", file=sys.stderr)
        sys.exit(1)

    try:
        data = fetch_usage(org_id)
    except (FileNotFoundError, PermissionError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}

    reading = {
        "ts": now.isoformat(),
        "five_hour": five.get("utilization"),
        "seven_day": seven.get("utilization"),
        "five_hour_resets_at": five.get("resets_at"),
        "seven_day_resets_at": seven.get("resets_at"),
    }

    with open(HIST_FILE, "a") as f:
        f.write(json.dumps(reading) + "\n")

    rebuild_data_file()

    print(
        f"[{now.strftime('%Y-%m-%d %H:%M UTC')}]"
        f"  5h: {reading['five_hour']}%"
        f"  |  7d: {reading['seven_day']}%"
    )


if __name__ == "__main__":
    main()
