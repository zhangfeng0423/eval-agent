"""
test_storage.py — Unit tests for AtomicJsonStorage, schema validation, and report generation.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import RunResult, CaseEvalSummary, QualityResult
from storage import AtomicJsonStorage, ReportGenerator


class TestStorage(unittest.TestCase):

    def test_atomic_json_storage_success(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            run_res = RunResult(
                status="success",
                exit_code=0,
                log_summary="Build succeeded",
                elapsed_seconds=12.5
            )
            AtomicJsonStorage.save(path, run_res)
            
            loaded = AtomicJsonStorage.load(path, RunResult)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status, "success")
            self.assertEqual(loaded.exit_code, 0)
            self.assertEqual(loaded.elapsed_seconds, 12.5)
            self.assertTrue(AtomicJsonStorage.is_completed(path, RunResult))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_atomic_json_storage_invalid_schema(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("corrupted json {")
            path = f.name

        try:
            self.assertIsNone(AtomicJsonStorage.load(path, RunResult))
            self.assertFalse(AtomicJsonStorage.is_completed(path, RunResult))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_report_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "output.md")
            html_path = os.path.join(tmpdir, "output_viz.html")

            summary1 = CaseEvalSummary(
                case_id="case_01",
                task_type="generation",
                total_elapsed_seconds=45.2,
                run_result=RunResult(status="success"),
                quality_result=QualityResult(
                    status="success",
                    overall_score=92.0,
                    strengths=["High modularity"],
                    weaknesses=["Missing docstrings"]
                ),
                overall_verdict="PASS"
            )

            ReportGenerator.generate_markdown_summary([summary1], md_path)
            ReportGenerator.generate_html_dashboard([summary1], html_path)

            self.assertTrue(os.path.exists(md_path))
            self.assertTrue(os.path.exists(html_path))

            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
                self.assertIn("case_01", md_content)
                self.assertIn("PASS", md_content)
                self.assertIn("High modularity", md_content)


if __name__ == "__main__":
    unittest.main()
