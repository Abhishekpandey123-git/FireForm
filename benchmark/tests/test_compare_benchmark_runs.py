"""Tests for paired FireForm benchmark summary comparison."""
import csv
import tempfile
import unittest
from pathlib import Path

from compare_benchmark_runs import compare_runs, read_run

FIELDS = [
    "document", "provider", "model", "status", "fill_wall_seconds", "document_wall_seconds",
    "total_accuracy_percent", "populated_accuracy_percent", "total_raw_accuracy_percent",
    "populated_raw_accuracy_percent", "missing_count", "unsupported_count",
]


def write_summary(path: Path, provider: str, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"provider": provider, "model": "same-model", **row})


class CompareBenchmarkRunsTests(unittest.TestCase):
    def test_paired_comparison_reports_latency_accuracy_and_same_success_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reference = root / "ollama.csv"
            candidate = root / "llama.csv"
            common = [
                {"document": "ics_203_1", "status": "ok", "fill_wall_seconds": "10", "document_wall_seconds": "12",
                 "total_accuracy_percent": "80", "populated_accuracy_percent": "85", "total_raw_accuracy_percent": "75",
                 "populated_raw_accuracy_percent": "82", "missing_count": "2", "unsupported_count": "1"},
                {"document": "ics_206_1", "status": "ok", "fill_wall_seconds": "8", "document_wall_seconds": "10",
                 "total_accuracy_percent": "90", "populated_accuracy_percent": "92", "total_raw_accuracy_percent": "88",
                 "populated_raw_accuracy_percent": "91", "missing_count": "1", "unsupported_count": "0"},
            ]
            write_summary(reference, "ollama", common)
            candidate_rows = [dict(row, fill_wall_seconds=str(float(row["fill_wall_seconds"]) * 0.8),
                                   document_wall_seconds=str(float(row["document_wall_seconds"]) * 0.8)) for row in common]
            candidate_rows[0]["total_accuracy_percent"] = "79"
            write_summary(candidate, "llama_cpp", candidate_rows)
            comparison, diffs = compare_runs(reference, candidate)
        self.assertEqual(comparison["common_documents"], 2)
        self.assertTrue(comparison["same_success_set"])
        self.assertEqual(comparison["reference"]["provider"], "ollama")
        self.assertEqual(comparison["candidate"]["provider"], "llama_cpp")
        self.assertEqual(len(diffs), 2)
        self.assertAlmostEqual(diffs[0]["delta_document_wall_seconds"], -2.4)
        self.assertEqual(diffs[0]["delta_total_accuracy_percent"], -1)

    def test_mismatched_skipped_document_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reference = root / "ollama.csv"
            candidate = root / "llama.csv"
            base = {"document": "ics_203_1", "status": "ok", "fill_wall_seconds": "10", "document_wall_seconds": "12",
                    "total_accuracy_percent": "80", "populated_accuracy_percent": "85", "total_raw_accuracy_percent": "75",
                    "populated_raw_accuracy_percent": "82", "missing_count": "2", "unsupported_count": "1"}
            skipped = dict(base, status="skipped: timeout", fill_wall_seconds="", document_wall_seconds="",
                           total_accuracy_percent="", populated_accuracy_percent="", total_raw_accuracy_percent="",
                           populated_raw_accuracy_percent="", missing_count="", unsupported_count="")
            write_summary(reference, "ollama", [base])
            write_summary(candidate, "llama_cpp", [skipped])
            comparison, diffs = compare_runs(reference, candidate)
        self.assertFalse(comparison["same_success_set"])
        self.assertIsNone(diffs[0]["candidate_document_wall_seconds"])

    def test_run_without_rows_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.csv"
            path.write_text(",".join(FIELDS) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no document rows"):
                read_run(path)


if __name__ == "__main__":
    unittest.main()
