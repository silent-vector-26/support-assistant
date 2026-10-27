import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from explanations import (
    ExplanationError,
    ExplanationNotConfigured,
    ModelConfig,
    build_messages,
    call_model,
    config_from_env,
    explain,
    validate_output,
)
from fieldtech_assistant import build_guidance, load_sources

ROOT = Path(__file__).parents[1]
QUESTION = "What checks are documented for recurring startup fault F07?"
GOOD = json.dumps({
    "explanation": "Fault F07 means the airflow-proving input was not confirmed during startup. "
                   "Review recent filter or airflow maintenance.",
    "citations": ["DEMO-RTU-MANUAL-4.2"],
})
ENV = {
    "AI_EXPLANATIONS_ENABLED": "true",
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "AZURE_OPENAI_KEY": "k",
    "AZURE_OPENAI_DEPLOYMENT": "d",
}


def guidance(query=QUESTION):
    return build_guidance(query, load_sources())


class ConfigTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with self.assertRaisesRegex(ExplanationNotConfigured, "disabled"):
            config_from_env({})

    def test_enabled_requires_all_settings(self):
        with self.assertRaisesRegex(ExplanationNotConfigured, "AZURE_OPENAI_KEY"):
            config_from_env({**ENV, "AZURE_OPENAI_KEY": ""})

    def test_requires_https(self):
        with self.assertRaises(ExplanationNotConfigured):
            config_from_env({**ENV, "AZURE_OPENAI_ENDPOINT": "http://example.com"})

    def test_valid_configuration(self):
        self.assertEqual(config_from_env(ENV).deployment, "d")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = guidance()["evidence"]

    def test_accepts_grounded_cited_output(self):
        result = validate_output(GOOD, self.evidence)
        self.assertEqual(result.citations, ("DEMO-RTU-MANUAL-4.2",))

    def test_rejects_bad_outputs(self):
        bad = [
            "not json",
            json.dumps({"explanation": "x", "citations": "DEMO-RTU-MANUAL-4.2"}),
            json.dumps({"explanation": "Airflow startup fault.", "citations": ["DEMO-NOPE"]}),
            json.dumps({"explanation": "Airflow startup fault.", "citations": []}),
            json.dumps({"explanation": "Jumper the control board terminals and replace the capacitor.",
                        "citations": ["DEMO-RTU-MANUAL-4.2"]}),
            json.dumps({"explanation": "x" * 1300, "citations": ["DEMO-RTU-MANUAL-4.2"]}),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:40]), self.assertRaises(ExplanationError):
                validate_output(raw, self.evidence)

    def test_prompt_contains_only_retrieved_evidence(self):
        messages = build_messages(QUESTION, self.evidence)
        self.assertNotIn("DEMO-NOPE", messages[1]["content"])
        for item in self.evidence:
            self.assertIn(item["source_id"], messages[1]["content"])

    def test_evidence_contains_documented_checks(self):
        source = next(s for s in load_sources() if s.source_id == "DEMO-RTU-MANUAL-4.2")
        passage = next(item for item in self.evidence if item["source_id"] == source.source_id)
        for check in source.checks:
            self.assertIn(check, passage["excerpt"])
        self.assertIn("return-air grille", build_messages(QUESTION, self.evidence)[1]["content"])

    def test_unsupported_and_unsafe_never_reach_the_model(self):
        calls = []
        for query in ("What is tomorrow's weather forecast?", "How can I bypass the safety interlock?"):
            with self.assertRaises(ExplanationError):
                explain(query, guidance(query), ModelConfig("https://x", "k", "d"),
                        lambda *_: calls.append(1) or GOOD)
        self.assertEqual(calls, [])


class ProviderTests(unittest.TestCase):
    def serve(self, status, body):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler):
                handler.rfile.read(int(handler.headers.get("Content-Length", 0)))
                handler.send_response(status)
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(*_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return ModelConfig(f"http://127.0.0.1:{server.server_port}", "k", "d", timeout=2)

    def test_success_returns_content(self):
        body = json.dumps({"choices": [{"message": {"content": GOOD}}]}).encode()
        self.assertEqual(call_model(self.serve(200, body), []), GOOD)

    def test_http_error_is_reported(self):
        with self.assertRaisesRegex(ExplanationError, "HTTP 503"):
            call_model(self.serve(503, b"{}"), [])

    def test_unreadable_response_is_reported(self):
        with self.assertRaisesRegex(ExplanationError, "unreadable"):
            call_model(self.serve(200, b"{}"), [])

    def test_unreachable_service_is_reported(self):
        with self.assertRaisesRegex(ExplanationError, "reached"):
            call_model(ModelConfig("http://127.0.0.1:1", "k", "d", timeout=2), [])


class EvaluationTests(unittest.TestCase):
    def test_live_failures_fail_the_evaluation(self):
        from evaluation.run_evaluation import run_live

        cases = [
            {"id": "supported", "question": QUESTION, "expect": "accepted"},
            {"id": "unsafe", "question": "How can I bypass the safety interlock?", "expect": "not_called"},
        ]
        config = ModelConfig("https://offline.invalid", "offline", "offline")
        calls = []

        def failed_model(*_):
            calls.append(1)
            raise ExplanationError("The model request timed out.")

        with patch("builtins.print"):
            self.assertEqual(run_live(cases, load_sources(), config, failed_model), ["supported"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(run_live(cases, load_sources(), config, lambda *_: GOOD), [])

    def test_reference_evaluation_passes(self):
        result = subprocess.run([sys.executable, str(ROOT / "evaluation" / "run_evaluation.py")],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)


class UiTests(unittest.TestCase):
    def run_app(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        next(b for b in app.button if b.label == "Start / update case").click().run()
        next(b for b in app.button if b.label == "Find documented checks").click().run()
        return app

    def labels(self, app):
        return [b.label for b in app.button]

    def test_base_workflow_without_credentials(self):
        with patch.dict(os.environ, {"AI_EXPLANATIONS_ENABLED": ""}):
            app = self.run_app()
        self.assertFalse(app.exception)
        self.assertNotIn("Explain these checks with AI (optional)", self.labels(app))
        self.assertTrue(any("disabled" in c.value for c in app.caption))
        self.assertTrue(app.markdown)

    def explain_click(self, app):
        next(b for b in app.button if b.label == "Explain these checks with AI (optional)").click().run()

    def test_valid_explanation_is_labeled_and_cited(self):
        with patch.dict(os.environ, ENV), patch("explanations.call_model", return_value=GOOD):
            app = self.run_app()
            self.explain_click(app)
        text = " ".join(i.value for i in app.info)
        self.assertIn("AI-generated explanation", text)
        self.assertIn("DEMO-RTU-MANUAL-4.2", text)

    def test_failure_is_visible_and_checks_remain(self):
        with patch.dict(os.environ, ENV), patch(
                "explanations.call_model", side_effect=ExplanationError("The model request timed out.")):
            app = self.run_app()
            self.explain_click(app)
        self.assertTrue(any("AI explanation unavailable" in w.value for w in app.warning))
        self.assertFalse(app.info)
        self.assertTrue(any("Documented checks" in m.value for m in app.markdown))

    def test_rejected_output_is_not_shown(self):
        bad = json.dumps({"explanation": "Anything.", "citations": ["DEMO-FAKE"]})
        with patch.dict(os.environ, ENV), patch("explanations.call_model", return_value=bad):
            app = self.run_app()
            self.explain_click(app)
        self.assertFalse(app.info)
        self.assertTrue(any("rejected" in w.value for w in app.warning))

    def test_unsupported_question_has_no_explain_button(self):
        with patch.dict(os.environ, ENV):
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            next(b for b in app.button if b.label == "Start / update case").click().run()
            next(f for f in app.text_input if f.label == "Ask about the fault")            .set_value("weather forecast?")
            next(b for b in app.button if b.label == "Find documented checks").click().run()
        self.assertNotIn("Explain these checks with AI (optional)", self.labels(app))


if __name__ == "__main__":
    unittest.main()
