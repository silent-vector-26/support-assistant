import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deployment_settings import build_parameters, main  # noqa: E402


class DeploymentSettingsTests(unittest.TestCase):
    def test_defaults_disable_paid_features(self):
        self.assertEqual(build_parameters({})["parameters"], {
            "aiExplanationsEnabled": {"value": False},
            "budgetAmount": {"value": 0},
        })

    def test_enabled_model_requires_all_credentials(self):
        settings = {
            "AI_EXPLANATIONS_ENABLED": "true",
            "AZURE_OPENAI_ENDPOINT": "https://demo.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "explanations",
            "AZURE_OPENAI_KEY": "test-key",
        }
        parameters = build_parameters(settings)["parameters"]
        self.assertTrue(parameters["aiExplanationsEnabled"]["value"])
        self.assertEqual(parameters["openAiKey"]["value"], "test-key")
        for key in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_KEY"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_parameters({k: v for k, v in settings.items() if k != key})
        for endpoint in ("http://example.com", "https://user:pass@example.com", "https://example.com/api"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                build_parameters({**settings, "AZURE_OPENAI_ENDPOINT": endpoint})

    def test_disabled_model_does_not_export_credentials(self):
        self.assertNotIn("openAiKey", build_parameters({"AZURE_OPENAI_KEY": "test-key"})["parameters"])
        with self.assertRaises(ValueError):
            build_parameters({"AI_EXPLANATIONS_ENABLED": "yes"})

    def test_budget_requires_valid_amount_start_and_recipient(self):
        settings = {
            "BUDGET_AMOUNT": "50",
            "BUDGET_START_DATE": "2026-10-01",
            "BUDGET_CONTACT_EMAILS": '["operator@example.com"]',
        }
        parameters = build_parameters(settings)["parameters"]
        self.assertEqual(parameters["budgetAmount"]["value"], 50)
        self.assertEqual(parameters["budgetContactEmails"]["value"], ["operator@example.com"])
        for key, values in {
            "BUDGET_AMOUNT": ["-1", "fifty", "50.0"],
            "BUDGET_START_DATE": ["", "2026-10-02", "2026-13-01"],
            "BUDGET_CONTACT_EMAILS": ["", "[]", "{}", '"operator@example.com"', '["invalid"]', "[3]"],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    build_parameters({**settings, key: value})

    def test_file_writer_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(main([str(path)]), 0)
                self.assertEqual(json.loads(path.read_text()), build_parameters({}))
                with self.assertRaises(FileExistsError):
                    main([str(path)])
            invalid = Path(directory) / "invalid.json"
            with patch.dict("os.environ", {"BUDGET_AMOUNT": "-1"}, clear=True):
                with patch("sys.stderr"):
                    self.assertEqual(main([str(invalid)]), 1)
            self.assertFalse(invalid.exists())


if __name__ == "__main__":
    unittest.main()
