import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fieldtech_assistant import (
    VisionNotConfigured,
    analyze_image,
    build_guidance,
    build_service_report,
    load_sources,
    lookup_mock_asset,
)


class FieldTechnicianAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_sources()

    def test_supported_fault_returns_checks_with_citations(self):
        result = build_guidance(
            "What checks are documented for recurring startup fault F07?",
            self.sources,
        )

        self.assertEqual(result["status"], "supported")
        self.assertTrue(result["checks"])
        self.assertTrue(result["evidence"])
        self.assertTrue(all(check["citation"] for check in result["checks"]))
        self.assertTrue(all(ref["source_id"] for ref in result["evidence"]))

    def test_unsupported_question_does_not_guess(self):
        result = build_guidance("What is tomorrow's weather forecast?", self.sources)

        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["evidence"], [])
        self.assertIn("won't guess", result["message"])

    def test_request_to_bypass_safety_control_escalates(self):
        result = build_guidance("How can I bypass the safety interlock?", self.sources)

        self.assertEqual(result["status"], "escalate")
        self.assertEqual(result["checks"], [])
        self.assertIn("can't help", result["message"])

    def test_service_report_preserves_sources_and_draft_status(self):
        report = build_service_report(
            {
                "case_id": "CASE-DEMO",
                "asset_id": "HVAC-RTU-104",
                "symptom": "Recurring startup fault F07",
                "created_at": "2026-10-26T12:00:00+00:00",
                "observations": ["Technician confirmed displayed code F07."],
                "checks": [
                    {
                        "check": "Review approved maintenance record.",
                        "outcome": "Filter service recorded last month.",
                        "citation": "Demo Manual, section 4 [DEMO-1]",
                    }
                ],
                "references": ["Demo Manual, section 4 [DEMO-1]"],
                "follow_up": "Supervisor review if fault repeats.",
            }
        )

        self.assertIn("Draft service report", report)
        self.assertIn("Technician confirmed displayed code F07.", report)
        self.assertIn("[DEMO-1]", report)
        self.assertIn("has not been submitted", report)

    def test_mock_asset_lookup_only_returns_known_demo_asset(self):
        self.assertIsNotNone(lookup_mock_asset("hvac-rtu-104"))
        self.assertIsNone(lookup_mock_asset("REAL-CUSTOMER-ASSET"))

    def test_vision_requires_configuration(self):
        with self.assertRaises(VisionNotConfigured):
            analyze_image(b"fake image", "", "")

    def test_vision_parses_ocr_as_text_clues(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "readResult": {
                            "blocks": [
                                {"lines": [{"text": "MODEL ABC-123"}, {"text": "FAULT F07"}]}
                            ]
                        }
                    }
                ).encode()

        with patch("fieldtech_assistant.urlopen", return_value=FakeResponse()):
            clues = analyze_image(b"image bytes", "https://vision.example.test", "demo-key")

        self.assertEqual(clues, ["MODEL ABC-123", "FAULT F07"])

    def test_corpus_file_is_checked_into_project(self):
        self.assertTrue(Path(__file__).parents[1].joinpath("data", "manuals.json").is_file())


if __name__ == "__main__":
    unittest.main()
