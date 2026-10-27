#!/usr/bin/env python3
"""Summarize profiler CSVs written by benchmark/profile_runtime.py.

Example:
  python3 benchmark/summarize_runtime.py benchmark/results/runtime-profile_*.csv

CPU percentages are fractions of one fully occupied core; values can exceed
100% on multi-core inference servers. RSS is summed across matching processes.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def summarize(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"{path}: no samples found (the command may have exited before the first sample)")
    cpu = [float(row["cpu_percent_one_core"]) for row in rows if row.get("cpu_percent_one_core") not in (None, "")]
    rss = [float(row["rss_mib"]) for row in rows if row.get("rss_mib") not in (None, "")]
    elapsed = [float(row["elapsed_seconds"]) for row in rows if row.get("elapsed_seconds") not in (None, "")]
    return {
        "file": str(path),
        "samples": len(rows),
        "duration_seconds": max(elapsed) if elapsed else None,
        "mean_cpu_percent_one_core": statistics.fmean(cpu) if cpu else None,
        "peak_cpu_percent_one_core": max(cpu) if cpu else None,
        "peak_rss_mib": max(rss) if rss else None,
        "max_matched_processes": max((int(row.get("matched_processes") or 0) for row in rows), default=0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", type=Path, help="runtime profile CSV files")
    args = parser.parse_args()
    failed = False
    for path in args.csv:
        try:
            result = summarize(path)
        except (OSError, ValueError, KeyError) as exc:
            print(f"ERROR {path}: {exc}")
            failed = True
            continue
        print(f"\n{result['file']}")
        print(f"  samples: {result['samples']}")
        print(f"  duration: {result['duration_seconds']} s")
        print(f"  mean CPU: {result['mean_cpu_percent_one_core']:.2f}% of one core" if result['mean_cpu_percent_one_core'] is not None else "  mean CPU: unavailable")
        print(f"  peak CPU: {result['peak_cpu_percent_one_core']:.2f}% of one core" if result['peak_cpu_percent_one_core'] is not None else "  peak CPU: unavailable")
        print(f"  peak summed RSS: {result['peak_rss_mib']:.2f} MiB" if result['peak_rss_mib'] is not None else "  peak summed RSS: unavailable")
        print(f"  max matched processes: {result['max_matched_processes']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
