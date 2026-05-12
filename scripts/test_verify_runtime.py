from __future__ import annotations

import contextlib
import io
import unittest

import verify_runtime


class VerifyRuntimeReviewRequiredTests(unittest.TestCase):
    def test_mock_pipeline_review_required_without_invoice_does_not_crash_for_ocr_space(self) -> None:
        original_post = verify_runtime.post

        def fake_post(context, path, payload):
            if path in {"/erp/sync-vendors", "/erp/sync-purchase-orders"}:
                return {"status": "success"}
            self.assertEqual(path, "/invoices/full-mock-pipeline")
            return {
                "workflow_status": "review_required",
                "invoice": None,
                "ocr_result": {
                    "fields": [{"field_name": "supplier_name", "value": "SuperStore"}],
                    "provider_metadata": {
                        "provider_name": "ocr_space",
                        "parsed_text_length": 479,
                    },
                    "raw_response": {
                        "provider_error_message": None,
                    },
                },
                "confidence_summary": {
                    "required_fields_missing": ["invoice_number", "invoice_date"],
                    "required_fields_low_confidence": [],
                },
                "review_status": "review_required",
            }

        verify_runtime.post = fake_post
        try:
            output = io.StringIO()
            context = verify_runtime.RuntimeContext(
                api_url="http://api.local",
                web_url="http://web.local",
                tenant_id="11111111-1111-1111-1111-111111111111",
            )
            with contextlib.redirect_stdout(output):
                result = verify_runtime.verify_mock_pipeline_flow(context, ocr_provider="ocr_space")
        finally:
            verify_runtime.post = original_post

        self.assertEqual(result["workflow_status"], "review_required")
        self.assertIn('"parsed_text_length": 479', output.getvalue())
        self.assertIn("invoice_number", output.getvalue())


if __name__ == "__main__":
    unittest.main()
