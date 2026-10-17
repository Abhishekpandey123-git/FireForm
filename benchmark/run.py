
"""Benchmark app/services/form_filler against the ground truth.

    python3 run.py                          # every narrative in data/narratives
    python3 run.py -d ics_203_1 ics_206_1   # a subset
    python3 run.py -m qwen3.5:4b            # another Ollama model
    python3 run.py --baseline               # full run, then publish it to baselines/<model>/

Servers and models come from benchmark/.env (see .env.example and config.py).

Each run gets its own folder, results/<date>_<time>_<model>/.
"""

import argparse
import csv
import json
import logging
import os
import shutil
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import config  # noqa: E402,F401

from app.core.config import (  # noqa: E402
    LLM_PROVIDER,
    LLAMA_CPP_HOST,
    LLAMA_CPP_MODEL,
    LLAMA_CPP_TIMEOUT,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
)
from app.services.llm.factory import normalize_provider  # noqa: E402
from app.services.form_filler import filler  # noqa: E402
import compare  # noqa: E402
import report  # noqa: E402
import review_pdf  # noqa: E402
import run_info  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

DATA_DIR = os.path.join(HERE, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
NARRATIVE_DIR = os.path.join(DATA_DIR, "narratives")
GROUND_TRUTH_DIR = os.path.join(DATA_DIR, "ground_truth")
RESULTS_DIR = os.path.join(HERE, "results")
BASELINES_DIR = os.path.join(HERE, "baselines")
BASELINE_FILES = [
    "summary.csv",
    "wrong_fields.txt",
    "run_info.json",
    "prompt.txt",
]


def all_docs():
    names = [
        f[:-4]
        for f in os.listdir(NARRATIVE_DIR)
        if f.endswith(".txt")
    ]
    return sorted(
        names,
        key=lambda d: (
            d.rsplit("_", 1)[0],
            int(d.rsplit("_", 1)[1]),
        ),
    )


def run_doc(doc, run_dir, model):
    """Fill one document, save every step, score it."""
    form = doc.rsplit("_", 1)[0]
    pdf_path = os.path.join(PDF_DIR, form + ".pdf")
    narrative_path = os.path.join(NARRATIVE_DIR, doc + ".txt")
    ground_truth_path = os.path.join(GROUND_TRUTH_DIR, doc + ".json")
    doc_dir = os.path.join(run_dir, doc)
    os.makedirs(doc_dir, exist_ok=True)

    with open(narrative_path, encoding="utf-8") as f:
        narrative = f.read()

    logging.info("Starting document %s", doc)
    out = filler.fill(
        pdf_path,
        narrative,
        os.path.join(doc_dir, "filled.pdf"),
        model,
    )

    save_text(doc_dir, "prompt.txt", out["prompt"])
    save_json(doc_dir, "schema.json", out["schema"])
    save_text(doc_dir, "response.json", out["response_text"])
    save_json(doc_dir, "filled.json", out["values"])

    result = compare.run_compare(
        ground_truth_path=ground_truth_path,
        test_path=os.path.join(doc_dir, "filled.json"),
        narrative_path=narrative_path,
        tables=out["tables"],
        groups=out["groups"],
    )

    review_pdf.create_review_pdf(
        doc,
        os.path.join(doc_dir, "filled.pdf"),
        os.path.join(doc_dir, "review.pdf"),
        out["values"],
        result,
    )

    with open(ground_truth_path, encoding="utf-8") as f:
        ground_truth = json.load(f)

    entries = report.doc_entries(
        out["values"],
        ground_truth,
        out["tables"],
        out["groups"],
        result["judge"],
    )
    logging.info("Finished document %s", doc)
    return result, entries


def main():
    provider = normalize_provider(LLM_PROVIDER)

    if provider == "llama_cpp":
        default_model = LLAMA_CPP_MODEL
        provider_host = LLAMA_CPP_HOST
        provider_timeout = LLAMA_CPP_TIMEOUT
    else:
        default_model = OLLAMA_MODEL
        provider_host = OLLAMA_HOST
        provider_timeout = OLLAMA_TIMEOUT

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-m",
        "--model",
        default=default_model,
        help="Model name for the selected LLM provider",
    )
    parser.add_argument(
        "-d",
        "--docs",
        nargs="*",
        help="documents to run (default: all)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="publish this run to baselines/<model>/ (full runs only)",
    )
    args = parser.parse_args()

    if args.baseline and args.docs:
        parser.error("--baseline publishes the full benchmark; drop -d")

    docs = args.docs or all_docs()
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    run_name = (
        f"{stamp}_{safe_name(provider)}_{safe_name(args.model)}"
    )
    run_dir = os.path.join(RESULTS_DIR, run_name)
    os.makedirs(run_dir, exist_ok=True)

    sys.stdout = Tee(os.path.join(run_dir, "run.log"))
    sys.stderr = sys.stdout

    print(
        f"Provider: {provider} | Model: {args.model} @ {provider_host} "
        f"| Timeout: {provider_timeout}s | Documents: {len(docs)} "
        f"| Output: {run_dir}"
    )

    info = run_info.collect(args.model, docs, sys.argv[1:])
    save_text(run_dir, "prompt.txt", filler.PROMPT)

    scored = []
    skipped = []
    start = time.perf_counter()

    for doc in docs:
        print(f" --- {doc} --- ")
        doc_start = time.perf_counter()

        try:
            result, entries = run_doc(doc, run_dir, args.model)
        except requests.exceptions.Timeout:
            skipped.append((doc, "model call timed out"))
            print(f"SKIPPED {doc}: model call timed out")
            continue
        except requests.exceptions.RequestException as exc:
            skipped.append((doc, f"model call failed: {exc}"))
            print(f"SKIPPED {doc}: model call failed: {exc}")
            continue
        except json.JSONDecodeError:
            skipped.append((doc, "output cut off (runaway generation)"))
            print(f"SKIPPED {doc}: model output was not complete JSON")
            continue

        scored.append((doc, result, entries))
        print(f"{time.perf_counter() - doc_start:.1f}s")

    seconds = time.perf_counter() - start
    write_summary(
        os.path.join(run_dir, "summary.csv"),
        args.model,
        scored,
        skipped,
    )
    report.write(
        os.path.join(run_dir, "wrong_fields.txt"),
        args.model,
        scored,
        skipped,
    )
    save_json(
        run_dir,
        "run_info.json",
        run_info.add_results(info, scored, skipped, seconds),
    )
    print_averages(scored, skipped)
    print(f"Total time: {seconds:.0f}s   Results: {run_dir}")

    if args.baseline:
        publish_baseline(run_dir, args.model)


def publish_baseline(run_dir, model):
    """Publish this run to baselines/<model>/."""
    baseline_dir = os.path.join(BASELINES_DIR, safe_name(model))
    os.makedirs(baseline_dir, exist_ok=True)

    for name in BASELINE_FILES:
        shutil.copy(
            os.path.join(run_dir, name),
            os.path.join(baseline_dir, name),
        )

    print(f"Baseline published: {baseline_dir}")


def safe_name(model):
    return model.replace(":", "-").replace("/", "_")


def write_summary(path, model, scored, skipped):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "document",
            "model",
            "status",
            "total_accuracy_percent",
            "populated_accuracy_percent",
            "total_raw_accuracy_percent",
            "populated_raw_accuracy_percent",
            "missing_count",
            "unsupported_count",
        ])

        for doc, result, _ in scored:
            writer.writerow([
                doc,
                model,
                "ok",
                round(result["accuracy"] * 100, 2),
                round(result["populated_accuracy"] * 100, 2),
                round(result["raw_accuracy"] * 100, 2),
                round(result["populated_raw_accuracy"] * 100, 2),
                result["missing_count"],
                result["unsupported_count"],
            ])

        for doc, reason in skipped:
            writer.writerow([
                doc, model, f"skipped: {reason}", "", "", "", "", "", ""
            ])


def print_averages(scored, skipped):
    print("-----------------------")
    print("       RESULTS         ")
    print("-----------------------")

    if scored:
        count = len(scored)
        print(f"Documents scored: {count}")
        print(
            "Average accuracy:               "
            f"{sum(r['accuracy'] for _, r, _ in scored) / count:.2%}"
        )
        print(
            "Average accuracy (populated):   "
            f"{sum(r['populated_accuracy'] for _, r, _ in scored) / count:.2%}"
        )
        print(
            "Average raw accuracy:           "
            f"{sum(r['raw_accuracy'] for _, r, _ in scored) / count:.2%}"
        )
        lowest = sorted(scored, key=lambda item: item[1]["accuracy"])[:3]
        print(
            "Lowest: "
            + ", ".join(
                f"{doc} {result['accuracy']:.1%}"
                for doc, result, _ in lowest
            )
        )

    if skipped:
        print(
            f"Skipped {len(skipped)} (not in the averages): "
            + ", ".join(doc for doc, _ in skipped)
        )


def save_text(folder, name, content):
    with open(
        os.path.join(folder, name), "w", encoding="utf-8"
    ) as f:
        f.write(content)


def save_json(folder, name, data):
    with open(
        os.path.join(folder, name), "w", encoding="utf-8"
    ) as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class Tee:
    """Write output to both the terminal and run.log."""

    def __init__(self, path):
        self.terminal = sys.stdout
        self.log = open(path, "w", encoding="utf-8")

    def write(self, content):
        self.terminal.write(content)
        self.log.write(content)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


if __name__ == "__main__":
    main()
