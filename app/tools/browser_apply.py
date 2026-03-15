# app/tools/browser_apply.py
"""Model B — open a job's apply page in a VISIBLE, logged-in browser.

The user reviews and submits manually; this NEVER auto-submits. Meant to run as a
detached subprocess so the browser window outlives the Gradio request:

    python -m app.tools.browser_apply "<url>"

Uses a persistent Chromium profile (./.browser-profile) so your LinkedIn (and any
ATS) logins persist between runs — log in once in the opened window and you stay
logged in. Best-effort pre-fill of obvious name/email fields is applied if such a
form is present (most LinkedIn posting pages gate the form behind "Apply", so
there is usually nothing to pre-fill until you click through).
"""
import json
import sys
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[2] / ".browser-profile"


def _best_effort_prefill(page, profile: dict) -> None:
    """Fill common fields by visible label, if they happen to exist. Never fails."""
    mapping = {
        "name": profile.get("name"),
        "full name": profile.get("name"),
        "email": profile.get("email"),
        "phone": profile.get("phone"),
    }
    for label, value in mapping.items():
        if not value:
            continue
        try:
            loc = page.get_by_label(label, exact=False)
            if loc.count() > 0:
                loc.first.fill(value, timeout=2000)
        except Exception:
            continue


def open_apply_page(url: str, profile: dict | None = None) -> None:
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,               # VISIBLE — the whole point of Model B
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"navigation warning: {exc}", file=sys.stderr)

        if profile:
            _best_effort_prefill(page, profile)

        # Hand control to the human: keep the window open until they close it.
        try:
            while len(context.pages) > 0:
                context.pages[0].wait_for_timeout(1000)
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m app.tools.browser_apply "<url>" [profile_json]', file=sys.stderr)
        sys.exit(1)
    prof = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    open_apply_page(sys.argv[1], prof)
