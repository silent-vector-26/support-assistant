"""Regenerate the walkthrough screenshots in docs/media using synthetic data only.

Requires requirements-dev.txt and `python -m playwright install chromium`.
Run from the repository root: python scripts/capture_screenshots.py
"""

import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def settle(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")


def shot(page, name):
    page.screenshot(path=str(MEDIA / name), full_page=True)
    print("captured", name)


def main():
    MEDIA.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("AZURE_VISION_ENDPOINT", None)
    env.pop("AZURE_VISION_KEY", None)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
         "--server.address=127.0.0.1", f"--server.port={port}",
         "--server.headless=true", "--browser.gatherUsageStats=false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                with urlopen(f"{url}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise SystemExit("Streamlit did not start")
                time.sleep(0.2)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(url)
            start = page.get_by_role("button", name="Start / update case", exact=True)
            expect(start).to_be_visible()
            page.locator('input[type="file"]').set_input_files(
                {"name": "synthetic-label.png", "mimeType": "image/png", "buffer": IMAGE}
            )
            expect(page.get_by_text("synthetic-label.png", exact=True)).to_be_visible()
            start.click()
            expect(page.get_by_label("Editable draft", exact=False)).to_be_visible()
            settle(page)
            shot(page, "01-case-intake.png")

            page.get_by_role("button", name="Extract tentative text clues with Azure AI Vision", exact=True).click()
            expect(page.get_by_text("Image clue extraction is not configured.", exact=False)).to_be_visible()
            settle(page)
            shot(page, "02-ocr-not-configured.png")

            page.get_by_role("button", name="Find documented checks", exact=True).click()
            expect(page.get_by_text("Documented checks", exact=True)).to_be_visible()
            settle(page)
            page.get_by_text("Evidence passages", exact=True).click()
            shot(page, "03-cited-checks.png")

            question = page.get_by_role("textbox", name="Ask about the fault", exact=True)
            question.fill("What is tomorrow's weather forecast?")
            page.get_by_role("button", name="Find documented checks", exact=True).click()
            expect(page.get_by_role("alert").get_by_text("I couldn't find support", exact=False)).to_be_visible()
            settle(page)
            shot(page, "04-unsupported-question.png")

            question.fill("How can I bypass the safety interlock?")
            page.get_by_role("button", name="Find documented checks", exact=True).click()
            expect(page.get_by_role("alert").get_by_text("I can't help bypass safety protections", exact=False)).to_be_visible()
            settle(page)
            shot(page, "05-safety-escalation.png")

            question.fill("What checks are documented for recurring startup fault F07?")
            page.get_by_role("button", name="Find documented checks", exact=True).click()
            expect(page.get_by_text("Documented checks", exact=True)).to_be_visible()
            settle(page)
            page.get_by_role("textbox", name="Outcome / observation", exact=True).fill(
                "Maintenance record verified in this simulated visit."
            )
            page.get_by_role("button", name="Add to case", exact=True).click()
            expect(page.get_by_text("Added to the case evidence.", exact=True)).to_be_visible()
            settle(page)
            page.get_by_role("button", name="Mark draft reviewed", exact=True).click()
            expect(page.get_by_role("button", name="Download reviewed report", exact=True)).to_be_enabled()
            settle(page)
            shot(page, "06-reviewed-report.png")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
