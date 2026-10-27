import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import profile_runtime


class ProcStatTests(unittest.TestCase):
    def test_parse_proc_stat_handles_spaces_in_command_name(self):
        # Fields 3..13, followed by utime=123 and stime=45.
        fields_after_comm = ["S"] + ["0"] * 10 + ["123", "45", "0"]
        pid, ticks = profile_runtime.parse_proc_stat(
            "321 (llama server worker) " + " ".join(fields_after_comm)
        )
        self.assertEqual(pid, 321)
        self.assertEqual(ticks, 168)

    def test_cpu_percent(self):
        self.assertEqual(profile_runtime.cpu_percent(None, 100, 1.0), 0.0)
        expected = 50.0 / profile_runtime.CLOCK_TICKS * 100.0
        self.assertAlmostEqual(profile_runtime.cpu_percent(100, 150, 1.0), expected)
        self.assertEqual(profile_runtime.cpu_percent(100, 120, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
