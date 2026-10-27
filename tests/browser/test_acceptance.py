"""Real-browser acceptance tests against an isolated local Streamlit process."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from fieldtech_assistant import build_guidance, load_sources


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "test-results" / "browser"
IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FailedVisionHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b'{"error":"Synthetic OCR service unavailable"}')

    def log_message(self, *_args):
        pass


class BrowserAcceptanceTests(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.artifact = ARTIFACTS / self._testMethodName
        self.vision = None
        env = os.environ.copy()
        env.pop("AZURE_VISION_ENDPOINT", None)
        env.pop("AZURE_VISION_KEY", None)
        if self._testMethodName == "test_ocr_service_error":
            self.vision = ThreadingHTTPServer(("127.0.0.1", 0), FailedVisionHandler)
            self.addCleanup(self.vision.server_close)
            threading.Thread(target=self.vision.serve_forever, daemon=True).start()
            self.addCleanup(self.vision.shutdown)
            env["AZURE_VISION_ENDPOINT"] = f"http://127.0.0.1:{self.vision.server_port}"
            env["AZURE_VISION_KEY"] = "synthetic-test-key"
        port = available_port()
        self.url = f"http://127.0.0.1:{port}"
        log = self.artifact.with_suffix(".log").open("w", encoding="utf-8")
        self.addCleanup(log.close)
        server = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                "--server.address=127.0.0.1", f"--server.port={port}",
                "--server.headless=true", "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        self.addCleanup(self.stop_server, server)
        deadline = time.monotonic() + 45
        while True:
            if server.poll() is not None:
                self.fail(f"Streamlit exited early. See {log.name}")
            try:
                with urlopen(f"{self.url}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    self.fail(f"Streamlit did not become ready. See {log.name}")
                time.sleep(0.2)
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch()
        self.addCleanup(browser.close)
        self.context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1100})
        self.addCleanup(self.context.close)
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self.page = self.context.new_page()
        self.addCleanup(self.capture_artifacts)
        self.page.goto(self.url)
        expect(self.page.get_by_role("button", name="Start / update case", exact=True)).to_be_visible()

    def wait_for_app(self):
        expect(self.page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")

    @staticmethod
    def stop_server(server):
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)

    def capture_artifacts(self):
        self.page.screenshot(path=str(self.artifact.with_suffix(".png")), full_page=True)
        self.context.tracing.stop(path=str(self.artifact.with_suffix(".zip")))

    def start_case(self, image=False):
        if image:
            self.page.locator('input[type="file"]').set_input_files(
                {"name": "synthetic-label.png", "mimeType": "image/png", "buffer": IMAGE}
            )
            expect(self.page.get_by_text("synthetic-label.png", exact=True)).to_be_visible()
        self.page.get_by_role("button", name="Start / update case", exact=True).click()
        expect(self.page.get_by_label("Editable draft", exact=False)).to_be_visible()
        self.wait_for_app()

    def record(self, observation):
        self.page.get_by_role("textbox", name="Outcome / observation", exact=True).fill(observation)
        self.page.get_by_role("button", name="Add to case", exact=True).click()
        expect(self.page.get_by_text("Added to the case evidence.", exact=True)).to_be_visible()
        self.wait_for_app()

    def test_complete_case_report_and_reconciliation(self):
        self.start_case()
        self.page.get_by_role("button", name="Find documented checks", exact=True).click()
        expect(self.page.get_by_text("Documented checks", exact=True)).to_be_visible()
        self.wait_for_app()
        expected = build_guidance(
            "What checks are documented for recurring startup fault F07?", load_sources()
        )["checks"][0]
        self.page.get_by_text("Evidence passages", exact=True).click()
        expect(self.page.get_by_text("Source:", exact=False).first).to_be_visible()
        self.page.get_by_role("combobox", name="Documented check", exact=True).press("ArrowDown")
        self.page.get_by_role("option", name=expected["text"], exact=True).click()
        self.record("Maintenance record verified in this simulated visit.")
        editor = self.page.get_by_role("textbox", name="Editable draft", exact=False)
        expect(editor).to_have_value(re.compile("Maintenance record verified"))
        original = editor.input_value()
        self.assertIn(expected["text"], original)
        self.assertIn(expected["citation"], original)
        self.assertIn("## References", original)
        editor.fill(original + "\nTechnician note: simulated visit only.")
        self.page.get_by_role("button", name="Mark draft reviewed", exact=True).click()
        expect(self.page.get_by_role("button", name="Download reviewed report", exact=True)).to_be_enabled()
        self.record("New confirmed observation after review.")
        expect(self.page.get_by_role("button", name="Mark draft reviewed", exact=True)).to_be_disabled()
        expect(self.page.get_by_role("button", name="Download draft report", exact=True)).to_be_disabled()
        expect(editor).to_have_value(original + "\nTechnician note: simulated visit only.")
        editor.fill(original + "\nTechnician note: simulated visit only.\nNew confirmed observation after review.")
        self.page.get_by_role("button", name="I reconciled my edits with the latest evidence", exact=True).click()
        self.page.get_by_role("button", name="Mark draft reviewed", exact=True).click()
        with self.page.expect_download() as downloaded:
            self.page.get_by_role("button", name="Download reviewed report", exact=True).click()
        download = downloaded.value
        self.assertIn("-reviewed-service-report.md", download.suggested_filename)
        content = Path(download.path()).read_text(encoding="utf-8")
        self.assertIn("New confirmed observation after review.", content)
        self.assertIn("Technician note: simulated visit only.", content)
        self.assertIn("Reference:", content)
        self.assertIn(expected["citation"], content)
        self.assertIn("has not been submitted", content)

    def test_unsupported_and_unsafe_questions(self):
        self.start_case()
        question = self.page.get_by_role("textbox", name="Ask about the fault", exact=True)
        question.fill("What is tomorrow's weather forecast?")
        self.page.get_by_role("button", name="Find documented checks", exact=True).click()
        expect(self.page.get_by_role("alert").get_by_text("I couldn't find support", exact=False)).to_be_visible()
        self.wait_for_app()
        expect(self.page.get_by_text("Documented checks", exact=True)).to_have_count(0)
        question.fill("How can I bypass the safety interlock?")
        self.page.get_by_role("button", name="Find documented checks", exact=True).click()
        expect(self.page.get_by_role("alert").get_by_text("I can't help bypass safety protections", exact=False)).to_be_visible()
        self.wait_for_app()
        expect(self.page.get_by_text("Documented checks", exact=True)).to_have_count(0)

    def test_ocr_not_configured(self):
        self.start_case(image=True)
        self.page.get_by_role("button", name="Extract tentative text clues with Azure AI Vision", exact=True).click()
        expect(self.page.get_by_text("Image clue extraction is not configured.", exact=False)).to_be_visible()
        self.assertNotIn("Technician-confirmed", self.page.get_by_label("Editable draft", exact=False).input_value())

    def test_ocr_service_error(self):
        self.start_case(image=True)
        self.page.get_by_role("button", name="Extract tentative text clues with Azure AI Vision", exact=True).click()
        expect(self.page.get_by_text("Image analysis failed: Azure AI Vision returned HTTP 503", exact=False)).to_be_visible()
        self.assertNotIn("Technician-confirmed", self.page.get_by_label("Editable draft", exact=False).input_value())


if __name__ == "__main__":
    unittest.main()
