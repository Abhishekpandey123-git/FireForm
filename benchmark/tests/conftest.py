"""Make benchmark helper modules importable when pytest runs from repository root."""
from pathlib import Path
import sys

BENCHMARK_ROOT = str(Path(__file__).resolve().parents[1])
if BENCHMARK_ROOT not in sys.path:
    sys.path.insert(0, BENCHMARK_ROOT)
