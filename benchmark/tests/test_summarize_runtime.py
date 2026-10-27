"""Tests for runtime-profile CSV summarization."""
import csv
import tempfile
import unittest
from pathlib import Path

from summarize_runtime import summarize


class SummarizeRuntimeTests(unittest.TestCase):
    def test_summary_reports_peak_and_mean_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "elapsed_seconds", "cpu_percent_one_core", "rss_mib", "matched_processes"
                ])
                writer.writeheader()
                writer.writerows([
                    {"elapsed_seconds": "0.5", "cpu_percent_one_core": "20", "rss_mib": "100", "matched_processes": "1"},
                    {"elapsed_seconds": "1.5", "cpu_percent_one_core": "80", "rss_mib": "150", "matched_processes": "2"},
                ])
            result = summarize(path)
        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["duration_seconds"], 1.5)
        self.assertEqual(result["mean_cpu_percent_one_core"], 50)
        self.assertEqual(result["peak_cpu_percent_one_core"], 80)
        self.assertEqual(result["peak_rss_mib"], 150)
        self.assertEqual(result["max_matched_processes"], 2)

    def test_empty_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.csv"
            path.write_text("elapsed_seconds,cpu_percent_one_core,rss_mib,matched_processes\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no samples"):
                summarize(path)


if __name__ == "__main__":
    unittest.main()
