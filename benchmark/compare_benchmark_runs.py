#!/usr/bin/env python3
"""Compare two FireForm benchmark summary.csv files on the same documents.

Example:
  python3 benchmark/compare_benchmark_runs.py results/ollama/summary.csv results/llama_cpp/summary.csv
  python3 benchmark/compare_benchmark_runs.py ollama.csv llama.csv --output comparison.csv

Time/throughput comparisons are only meaningful when the provider runs use the
same FireForm commit, prompts, document set, judge settings, hardware, and
comparable model weights/quantization. Token/s is not reported because the
current form-filler API returns text, not provider token-usage counters.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

NUMERIC = (
    "fill_wall_seconds", "document_wall_seconds", "total_accuracy_percent",
    "populated_accuracy_percent", "total_raw_accuracy_percent",
    "populated_raw_accuracy_percent", "missing_count", "unsupported_count",
)


def read_run(path: Path) -> tuple[dict[str, dict], dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"document", "provider", "model", "status", *NUMERIC}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        rows = {row["document"]: row for row in reader}
    if not rows:
        raise ValueError(f"{path}: no document rows")
    statuses = list(rows.values())
    scored = [row for row in statuses if row.get("status") == "ok"]
    times = [float(row["document_wall_seconds"]) for row in scored if row.get("document_wall_seconds")]
    fill_times = [float(row["fill_wall_seconds"]) for row in scored if row.get("fill_wall_seconds")]
    accuracy = [float(row["total_accuracy_percent"]) for row in scored if row.get("total_accuracy_percent")]
    summary = {
        "provider": statuses[0].get("provider", "unknown"),
        "model": statuses[0].get("model", "unknown"),
        "documents_requested": len(rows),
        "documents_scored": len(scored),
        "documents_skipped": len(rows) - len(scored),
        "mean_document_seconds": statistics.fmean(times) if times else None,
        "median_document_seconds": statistics.median(times) if times else None,
        "mean_fill_seconds": statistics.fmean(fill_times) if fill_times else None,
        "scored_docs_per_minute": (len(scored) * 60 / sum(times)) if times and sum(times) > 0 else None,
        "mean_judged_accuracy_percent": statistics.fmean(accuracy) if accuracy else None,
    }
    return rows, summary


def compare_runs(reference_path: Path, candidate_path: Path) -> tuple[dict, list[dict]]:
    reference_rows, reference = read_run(reference_path)
    candidate_rows, candidate = read_run(candidate_path)
    shared = sorted(reference_rows.keys() & candidate_rows.keys())
    only_reference = sorted(reference_rows.keys() - candidate_rows.keys())
    only_candidate = sorted(candidate_rows.keys() - reference_rows.keys())
    if not shared:
        raise ValueError("The runs have no documents in common")
    diffs = []
    for doc in shared:
        old, new = reference_rows[doc], candidate_rows[doc]
        old_ok, new_ok = old.get("status") == "ok", new.get("status") == "ok"
        row = {
            "document": doc,
            "reference_provider": old.get("provider"),
            "reference_model": old.get("model"),
            "reference_status": old.get("status"),
            "candidate_provider": new.get("provider"),
            "candidate_model": new.get("model"),
            "candidate_status": new.get("status"),
        }
        for field in NUMERIC:
            a = float(old[field]) if old_ok and old.get(field) not in (None, "") else None
            b = float(new[field]) if new_ok and new.get(field) not in (None, "") else None
            row[f"reference_{field}"] = a
            row[f"candidate_{field}"] = b
            row[f"delta_{field}"] = (b - a) if a is not None and b is not None else None
        diffs.append(row)
    comparison = {
        "reference": reference,
        "candidate": candidate,
        "common_documents": len(shared),
        "only_reference": only_reference,
        "only_candidate": only_candidate,
        "same_success_set": not only_reference and not only_candidate and all(
            (reference_rows[d].get("status") == "ok") == (candidate_rows[d].get("status") == "ok") for d in shared
        ),
    }
    return comparison, diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="baseline summary.csv, normally Ollama")
    parser.add_argument("candidate", type=Path, help="comparison summary.csv, normally llama.cpp")
    parser.add_argument("--output", type=Path, help="write per-document differences to this CSV")
    args = parser.parse_args()
    try:
        summary, diffs = compare_runs(args.reference, args.candidate)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    for label in ("reference", "candidate"):
        item = summary[label]
        print(f"\n{label.title()}: {item['provider']} / {item['model']}")
        print(f"  scored / requested / skipped: {item['documents_scored']} / {item['documents_requested']} / {item['documents_skipped']}")
        for key, title, unit in (
            ("median_document_seconds", "median document time", "s"),
            ("mean_document_seconds", "mean document time", "s"),
            ("scored_docs_per_minute", "scored throughput", "docs/min"),
            ("mean_judged_accuracy_percent", "mean judged accuracy", "%"),
        ):
            value = item[key]
            print(f"  {title}: {value:.2f} {unit}" if value is not None else f"  {title}: unavailable")
    print(f"\nCommon documents: {summary['common_documents']}; same successful-document set: {summary['same_success_set']}")
    if summary["only_reference"] or summary["only_candidate"]:
        print(f"WARNING: document lists differ. Only reference: {summary['only_reference']}; only candidate: {summary['only_candidate']}")
    if not summary["same_success_set"]:
        print("WARNING: at least one document succeeded in only one run; aggregate accuracy differences may be biased.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(diffs[0]) if diffs else ["document"]
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(diffs)
        print(f"Per-document differences: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
