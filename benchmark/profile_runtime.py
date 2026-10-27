#!/usr/bin/env python3
"""Sample matching Linux inference-server processes while a command runs.

Example:
  python3 benchmark/profile_runtime.py --label llama-cpp \\
    --process-regex 'llama-server' -- python3 benchmark/run.py --provider custom -m MODEL

Run this on the same host as the inference server. CPU is reported as percent
of one core (so 100 means one fully utilized core); RSS is combined resident
memory across matching processes. This intentionally uses /proc only and has
no third-party dependencies.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "results"
# os.sysconf is available on Linux; the fallback keeps pure helper tests importable on Windows.
# Runtime profiling itself is Linux-only because process sampling reads /proc.
CLOCK_TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def parse_proc_stat(stat_text: str) -> tuple[int, int]:
    """Return (pid, user+system CPU ticks) from a /proc/<pid>/stat line."""
    close = stat_text.rfind(")")
    if close < 0:
        raise ValueError("Malformed /proc stat line: missing command delimiter")
    pid = int(stat_text[: stat_text.find(" ")])
    fields_after_comm = stat_text[close + 1 :].split()
    # fields_after_comm begins at field 3 (state); utime/stime are fields 14/15.
    if len(fields_after_comm) <= 12:
        raise ValueError("Malformed /proc stat line: missing CPU tick fields")
    return pid, int(fields_after_comm[11]) + int(fields_after_comm[12])


def cpu_percent(previous_ticks: int | None, current_ticks: int, elapsed: float) -> float:
    """CPU usage since the prior sample, in one-core percentage units."""
    if previous_ticks is None or elapsed <= 0:
        return 0.0
    return max(0.0, (current_ticks - previous_ticks) / CLOCK_TICKS / elapsed * 100.0)


def read_process(pid_dir: Path, pattern: re.Pattern[str]) -> dict | None:
    """Read a process if its comm name matches the requested regex."""
    try:
        pid = int(pid_dir.name)
        comm = (pid_dir / "comm").read_text(encoding="utf-8").strip()
        if not pattern.search(comm):
            return None
        stat_text = (pid_dir / "stat").read_text(encoding="utf-8")
        stat_pid, ticks = parse_proc_stat(stat_text)
        if stat_pid != pid:
            return None
        rss_kib = 0
        for line in (pid_dir / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                rss_kib = int(line.split()[1])
                break
        return {"pid": pid, "name": comm, "ticks": ticks, "rss_kib": rss_kib}
    except (OSError, ValueError, IndexError):
        # A process can exit between scanning /proc and reading its files.
        return None


def sample_processes(pattern: re.Pattern[str], excluded_pids: set[int]) -> list[dict]:
    matches = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError as exc:
        raise RuntimeError("This helper requires Linux /proc") from exc
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) in excluded_pids:
            continue
        process = read_process(entry, pattern)
        if process is not None:
            matches.append(process)
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="label used in the output filename")
    parser.add_argument("--process-regex", required=True, help="regex matched against Linux process comm names")
    parser.add_argument("--interval", type=float, default=1.0, help="sampling interval in seconds (default: 1)")
    parser.add_argument("--output", help="CSV path (default: benchmark/results/runtime-profile_<label>_<time>.csv)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run, prefixed by --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("provide a command after --")
    if args.interval <= 0:
        parser.error("--interval must be greater than zero")

    if not Path("/proc").is_dir():
        parser.error("runtime profiling requires Linux /proc; run this helper on the model-server host")

    pattern = re.compile(args.process_regex)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.label)
    output_path = Path(args.output) if args.output else DEFAULT_RESULTS / f"runtime-profile_{safe_label}_{stamp}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    child = subprocess.Popen(command)
    own_pids = {os.getpid(), child.pid}
    previous_ticks: dict[int, int] = {}
    last_sample = time.monotonic()
    print(f"Sampling process regex {args.process_regex!r} -> {output_path}", flush=True)
    try:
        with output_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=("timestamp_utc", "elapsed_seconds", "matched_processes", "cpu_percent_one_core", "rss_mib", "processes"),
            )
            writer.writeheader()
            started = time.monotonic()
            while child.poll() is None:
                now = time.monotonic()
                processes = sample_processes(pattern, own_pids)
                elapsed_sample = max(now - last_sample, 1e-9)
                total_ticks = sum(
                    max(0, proc["ticks"] - previous_ticks.get(proc["pid"], proc["ticks"]))
                    for proc in processes
                )
                total_rss_kib = sum(proc["rss_kib"] for proc in processes)
                writer.writerow({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "elapsed_seconds": round(now - started, 3),
                    "matched_processes": len(processes),
                    "cpu_percent_one_core": round(total_ticks / CLOCK_TICKS / elapsed_sample * 100.0, 2),
                    "rss_mib": round(total_rss_kib / 1024, 2),
                    "processes": ";".join(f"{p['name']}:{p['pid']}" for p in processes),
                })
                stream.flush()
                previous_ticks = {proc["pid"]: proc["ticks"] for proc in processes}
                last_sample = now
                time.sleep(args.interval)
    except KeyboardInterrupt:
        child.send_signal(signal.SIGINT)
        child.wait()
        raise
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait()
    print(f"Command exited with {child.returncode}; profile saved to {output_path}")
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
