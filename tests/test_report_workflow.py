from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from fieldtech_assistant import new_case


APP_PATH = Path(__file__).parents[1] / "app.py"


class ReportWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP_PATH)).run()
        self.click("Start / update case")

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()
        self.assertFalse(self.app.exception)

    def edit_report(self, text):
        self.app.text_area(key="report_editor").set_value(text).run()
        self.assertFalse(self.app.exception)

    def download(self):
        return self.app.get("download_button")[0]

    def button(self, label):
        return next(button for button in self.app.button if button.label == label)

    def record_observation(self, text):
        next(field for field in self.app.text_input if field.label == "Outcome / observation").set_value(text)
        self.click("Add to case")

    def test_unedited_report_refreshes_and_invalidates_review(self):
        self.click("Mark draft reviewed")
        self.assertTrue(self.app.session_state.report_reviewed)
        self.record_observation("Confirmed fault display F07.")
        self.assertIn("Confirmed fault display F07.", self.app.text_area(key="report_editor").value)
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertFalse(self.download().proto.disabled)
        self.assertEqual(self.download().proto.label, "Download draft report")

    def test_edited_report_blocks_review_and_download_until_reconciled(self):
        self.edit_report("Technician custom report")
        self.click("Mark draft reviewed")
        self.record_observation("New confirmed observation")
        self.assertEqual(self.app.text_area(key="report_editor").value, "Technician custom report")
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertTrue(self.button("Mark draft reviewed").disabled)
        self.assertTrue(self.download().proto.disabled)
        self.edit_report("Technician custom report\nNew confirmed observation")
        self.click("I reconciled my edits with the latest evidence")
        self.assertFalse(self.button("Mark draft reviewed").disabled)
        self.assertFalse(self.download().proto.disabled)
        self.click("Mark draft reviewed")
        self.assertEqual(self.download().proto.label, "Download reviewed report")
        self.edit_report("Another technician edit")
        self.assertFalse(self.app.session_state.report_reviewed)

    def test_replace_edits_uses_latest_check_evidence(self):
        self.click("Find documented checks")
        self.edit_report("Preserve until explicitly replaced")
        self.click("Mark draft reviewed")
        options = self.app.selectbox[0].options
        self.app.selectbox[0].select(options[1])
        next(field for field in self.app.text_input if field.label == "Outcome / observation").set_value(
            "Maintenance record verified."
        )
        self.click("Add to case")
        self.assertTrue(self.download().proto.disabled)
        self.click("Replace my edits with latest evidence")
        report = self.app.text_area(key="report_editor").value
        self.assertIn("Maintenance record verified.", report)
        self.assertIn(options[1], report)
        self.assertNotIn("Preserve until explicitly replaced", report)
        self.assertFalse(self.download().proto.disabled)
        self.assertFalse(self.app.session_state.report_reviewed)

    def test_guidance_changes_invalidate_review_and_preserve_edits(self):
        self.edit_report("Technician notes")
        self.click("Mark draft reviewed")
        self.click("Find documented checks")
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertTrue(self.download().proto.disabled)
        self.assertEqual(self.app.text_area(key="report_editor").value, "Technician notes")

    def test_unsupported_guidance_updates_follow_up_and_invalidates_review(self):
        self.click("Mark draft reviewed")
        next(field for field in self.app.text_input if field.label == "Ask about the fault").set_value(
            "What is tomorrow's weather forecast?"
        )
        self.click("Find documented checks")
        self.assertIn("won't guess", self.app.text_area(key="report_editor").value)
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertFalse(self.download().proto.disabled)

    def test_unchanged_evidence_preserves_review_on_rerun(self):
        self.click("Find documented checks")
        self.click("Mark draft reviewed")
        self.click("Find documented checks")
        self.assertTrue(self.app.session_state.report_reviewed)
        self.assertEqual(self.download().proto.label, "Download reviewed report")

    def test_ocr_confirmation_requires_reconciliation(self):
        self.edit_report("Technician notes")
        self.click("Mark draft reviewed")
        case = self.app.session_state.case
        case["image_clues"] = ["FAULT F07"]
        self.app.session_state.case = case
        # A tiny valid GIF allows the existing image UI to render without a live OCR call.
        self.app.session_state.image_bytes = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
            b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
            b"\x00\x02\x02D\x01\x00;"
        )
        self.app.run()
        self.assertTrue(self.app.session_state.report_reviewed)
        self.app.checkbox[0].check().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertTrue(self.download().proto.disabled)
        self.assertEqual(self.app.text_area(key="report_editor").value, "Technician notes")
        self.click("Replace my edits with latest evidence")
        self.assertIn("Technician-confirmed from equipment image: FAULT F07", self.app.text_area(key="report_editor").value)

    def test_case_replacement_resets_editor_even_if_id_is_reused(self):
        case_id = self.app.session_state.case["case_id"]
        self.edit_report("Previous case edits")
        self.click("Mark draft reviewed")
        replacement = new_case("HVAC-RTU-205", "Replacement case")
        replacement["case_id"] = case_id
        with patch("fieldtech_assistant.new_case", return_value=replacement):
            self.click("Start / update case")
        self.assertNotIn("Previous case edits", self.app.text_area(key="report_editor").value)
        self.assertIn("Replacement case", self.app.text_area(key="report_editor").value)
        self.assertFalse(self.app.session_state.report_reviewed)

    def test_empty_report_cannot_be_reviewed_or_downloaded(self):
        self.edit_report(" ")
        self.click("Mark draft reviewed")
        self.assertFalse(self.app.session_state.report_reviewed)
        self.assertTrue(self.download().proto.disabled)


if __name__ == "__main__":
    unittest.main()
