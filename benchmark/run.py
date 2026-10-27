"""Benchmark app/services/form_filler against the ground truth.

    python3 run.py                          # every narrative in data/narratives
    python3 run.py -d ics_203_1 ics_206_1   # a subset
    python3 run.py --provider custom -m <model-id>  # an OpenAI-compatible server
    python3 run.py --baseline               # full run, then publish it to baselines/<model>/

Provider settings and models come from benchmark/.env (see .env.example and config.py).
Use --provider to choose a provider without changing the global default.

Each run gets its own folder, results/<date>_<time>_<model>/:

    summary.csv         one row per document (skipped documents included)
    wrong_fields.txt    expected vs got for every wrong field, before and after the judge
    run.log             everything printed during the run
    run_info.json       model, options, prompt hash, judge, code version: how to recreate it
    prompt.txt          the prompt file the run used
    <doc>/              prompt.txt, schema.json, response.json, filled.json,
                        filled.pdf, review.pdf

A document whose model call times out or fails, or whose output is cut off
mid-JSON, is skipped and listed; it is left out of the averages.
"""

import argparse
import csv
import json
import os
import shutil
import sys
import time

import requests

# so `app` imports from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: F401  imported for its side effect: loads benchmark/.env before `app`

from app.core.config import LLM_PROVIDER
from app.services import llm
from app.services.form_filler import filler
from app.services.llm.errors import LLMError
import compare
import report
import review_pdf
import run_info

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
NARRATIVE_DIR = os.path.join(DATA_DIR, "narratives")
GROUND_TRUTH_DIR = os.path.join(DATA_DIR, "ground_truth")
RESULTS_DIR = os.path.join(HERE, "results")
BASELINES_DIR = os.path.join(HERE, "baselines")
# What a baseline publishes: small, text, diffable
BASELINE_FILES = ["summary.csv", "wrong_fields.txt", "run_info.json", "prompt.txt"]


def all_docs():
    names = [f[:-4] for f in os.listdir(NARRATIVE_DIR) if f.endswith(".txt")]
    # ics_201_2 before ics_201_10
    return sorted(names, key=lambda d: (d.rsplit("_", 1)[0], int(d.rsplit("_", 1)[1])))


def run_doc(doc, run_dir, model, provider, timings):
    """Fill one document, save every step, score it. Returns (result, entries)."""
    form = doc.rsplit("_", 1)[0]
    pdf_path = os.path.join(PDF_DIR, form + ".pdf")
    narrative_path = os.path.join(NARRATIVE_DIR, doc + ".txt")
    ground_truth_path = os.path.join(GROUND_TRUTH_DIR, doc + ".json")
    doc_dir = os.path.join(run_dir, doc)
    os.makedirs(doc_dir, exist_ok=True)

    with open(narrative_path, "r", encoding="utf-8") as f:
        narrative = f.read()

    # 1. Fill
    fill_start = time.perf_counter()
    try:
        out = filler.fill(
            pdf_path, narrative, os.path.join(doc_dir, "filled.pdf"), model, provider=provider
        )
    finally:
        # Includes schema construction, provider inference, and PDF writing.
        timings.setdefault(doc, {})["fill_wall_seconds"] = round(time.perf_counter() - fill_start, 3)
    save_text(doc_dir, "prompt.txt", out["prompt"])
    save_json(doc_dir, "schema.json", out["schema"])
    save_text(doc_dir, "response.json", out["response_text"])
    save_json(doc_dir, "filled.json", out["values"])

    # 2. Score (prints raw and judged accuracy)
    result = compare.run_compare(
        ground_truth_path=ground_truth_path,
        test_path=os.path.join(doc_dir, "filled.json"),
        narrative_path=narrative_path,
        tables=out["tables"],
        groups=out["groups"],
    )

    # 3. Review PDF and wrong-field list
    review_pdf.create_review_pdf(
        doc,
        os.path.join(doc_dir, "filled.pdf"),
        os.path.join(doc_dir, "review.pdf"),
        out["values"],
        result,
    )
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    entries = report.doc_entries(out["values"], ground_truth, out["tables"], out["groups"], result["judge"])
    return result, entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--provider",
        choices=("ollama", "openai", "gemini", "anthropic", "custom", "llama_cpp"),
        default=LLM_PROVIDER,
        help="LLM provider (default: configured LLM_PROVIDER)",
    )
    parser.add_argument(
        "-m", "--model", default=None,
        help="provider model ID (default: the provider's configured default model)",
    )
    parser.add_argument("-d", "--docs", nargs="*", help="documents to run (default: all)")
    parser.add_argument("--baseline", action="store_true",
                        help="publish this run to baselines/<model>/ (full runs only)")
    args = parser.parse_args()
    if args.baseline and args.docs:
        parser.error("--baseline publishes the full benchmark; drop -d")
    docs = args.docs or all_docs()

    # Resolve the exact provider/model pair once, so metadata and outputs describe
    # the target actually used and a misconfigured provider fails before the run.
    try:
        choice = llm.get_registry().resolve(args.provider, args.model)
    except LLMError as exc:
        parser.error(exc.message)
    provider, model = choice.provider.value, choice.model

    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    run_dir = os.path.join(RESULTS_DIR, f"{stamp}_{provider}_{safe_name(model)}")
    os.makedirs(run_dir, exist_ok=True)
    sys.stdout = Tee(os.path.join(run_dir, "run.log"))
    # Do not print provider URLs; they may contain internal hostnames.
    print(f"Provider: {provider}   Model: {model}   Documents: {len(docs)}   Output: {run_dir}")

    info = run_info.collect(provider, model, docs, sys.argv[1:])
    save_text(run_dir, "prompt.txt", filler.PROMPT)

    scored = []    # (doc, result, entries)
    skipped = []   # (doc, reason)
    timings = {}   # elapsed wall seconds for every document, including failures
    start = time.perf_counter()
    for doc in docs:
        print(f" --- {doc} --- ")
        doc_start = time.perf_counter()
        try:
            result, entries = run_doc(doc, run_dir, model, provider, timings)
        except requests.exceptions.Timeout:
            skipped.append((doc, "model call timed out"))
            print(f"SKIPPED {doc}: model call timed out")
            continue
        except requests.exceptions.RequestException as e:
            # e.g. an Ollama 500 or a dropped connection
            skipped.append((doc, f"model call failed: {e}"))
            print(f"SKIPPED {doc}: model call failed: {e}")
            continue
        except LLMError as e:
            # Provider adapters normalize provider failures into LLMError.
            skipped.append((doc, f"model call failed: {e.message}"))
            print(f"SKIPPED {doc}: model call failed: {e.message}")
            continue
        except json.JSONDecodeError:
            # num_predict cut off a runaway generation mid-JSON
            skipped.append((doc, "output cut off (runaway generation)"))
            print(f"SKIPPED {doc}: model output was not complete JSON")
            continue
        finally:
            timings.setdefault(doc, {})["document_wall_seconds"] = round(time.perf_counter() - doc_start, 3)
        scored.append((doc, result, entries))
        print(f'{timings[doc]["document_wall_seconds"]:.3f}s')

    seconds = time.perf_counter() - start
    write_summary(os.path.join(run_dir, "summary.csv"), provider, model, scored, skipped, timings)
    report.write(os.path.join(run_dir, "wrong_fields.txt"), f"{provider}/{model}", scored, skipped)
    save_json(run_dir, "run_info.json", run_info.add_results(info, scored, skipped, seconds))
    print_averages(scored, skipped)
    print(f"Total time: {seconds:.0f}s   Results: {run_dir}")

    if args.baseline:
        publish_baseline(run_dir, provider, model)


def publish_baseline(run_dir, provider, model):
    """Publish compact results without overwriting another provider's baseline."""
    key = safe_name(model) if provider == "ollama" else f"{provider}--{safe_name(model)}"
    baseline_dir = os.path.join(BASELINES_DIR, key)
    os.makedirs(baseline_dir, exist_ok=True)
    for name in BASELINE_FILES:
        shutil.copy(os.path.join(run_dir, name), os.path.join(baseline_dir, name))
    print(f"Baseline published: {baseline_dir}")


def safe_name(model):
    return model.replace(":", "-").replace("/", "_")


def write_summary(path, provider, model, scored, skipped, timings):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "document", "provider", "model", "status", "fill_wall_seconds", "document_wall_seconds",
            "total_accuracy_percent", "populated_accuracy_percent",
            "total_raw_accuracy_percent", "populated_raw_accuracy_percent",
            "missing_count", "unsupported_count",
        ])
        for doc, r, _ in scored:
            writer.writerow([
                doc, provider, model, "ok",
                timings.get(doc, {}).get("fill_wall_seconds"),
                timings.get(doc, {}).get("document_wall_seconds"),
                round(r["accuracy"] * 100, 2), round(r["populated_accuracy"] * 100, 2),
                round(r["raw_accuracy"] * 100, 2), round(r["populated_raw_accuracy"] * 100, 2),
                r["missing_count"], r["unsupported_count"],
            ])
        for doc, reason in skipped:
            writer.writerow([
                doc, provider, model, f"skipped: {reason}",
                timings.get(doc, {}).get("fill_wall_seconds"),
                timings.get(doc, {}).get("document_wall_seconds"),
                "", "", "", "", "", ""
            ])


def print_averages(scored, skipped):
    print("-----------------------")
    print("       RESULTS         ")
    print("-----------------------")
    if scored:
        n = len(scored)
        print(f"Documents scored: {n}")
        print(f"Average accuracy:               {sum(r['accuracy'] for _, r, _ in scored) / n:.2%}")
        print(f"Average accuracy (populated):   {sum(r['populated_accuracy'] for _, r, _ in scored) / n:.2%}")
        print(f"Average raw accuracy:           {sum(r['raw_accuracy'] for _, r, _ in scored) / n:.2%}")
        lowest = sorted(scored, key=lambda s: s[1]["accuracy"])[:3]
        print("Lowest: " + ", ".join(f"{doc} {r['accuracy']:.1%}" for doc, r, _ in lowest))
    if skipped:
        print(f"Skipped {len(skipped)} (not in the averages): " + ", ".join(doc for doc, _ in skipped))


def save_text(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def save_json(folder, name, data):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class Tee:
    """Print to the terminal and to run.log."""

    def __init__(self, path):
        self.terminal = sys.stdout
        self.log = open(path, "w", encoding="utf-8")

    def write(self, text):
        self.terminal.write(text)
        self.log.write(text)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


if __name__ == "__main__":
    main()
