#!/usr/bin/env python3
"""
One-time auth setup.
Uses real Chrome (not Playwright's bundled Chromium) to avoid Google's
automation detection during sign-in. Saves session to ./browser_profile/.

Run:  python3 setup_auth.py
Re-run if poll_usage.py reports auth expired.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).parent / "browser_profile"


def main():
    PROFILE_DIR.mkdir(exist_ok=True)
    print("Opening Chrome — log in to Claude, then come back here and press Enter.")
    print()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",           # real Chrome, not bundled Chromium
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.new_page()
        page.goto("https://claude.ai/login")

        input("[ Press Enter once you are fully logged in ] ")
        context.close()

    print(f"Session saved in {PROFILE_DIR}/")
    print("Run: python3 poll_usage.py")


if __name__ == "__main__":
    main()
