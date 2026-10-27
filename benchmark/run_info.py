"""run_info.json: everything needed to understand and recreate a run.

Written into every run folder; --baseline publishes it with the results.
Server addresses are deliberately left out (they may be private); models are
identified by name and digest instead, which pins the exact weights.
"""

import hashlib
import os
import platform
import subprocess
import time
from importlib import metadata

import requests

import llm_judge
from app.core.config import OLLAMA_HOST
from app.services import llm
from app.services.form_filler import filler
from app.services.llm.ollama import OPTIONS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ["pypdf", "pdfplumber", "requests"]


def collect(provider, model, docs, argv):
    """Settings known before the run starts."""
    is_ollama = provider == "ollama"
    provider_settings = llm.get_registry().settings.providers[llm.LLMProvider(provider)]
    model_artifact = ollama_model_info(OLLAMA_HOST, model) if is_ollama else {
        "digest": None,
        "details": None,
        "note": "For a local llama.cpp run, record the GGUF SHA-256 and llama.cpp build in the report.",
    }
    return {
        "date": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "command": "python3 run.py " + " ".join(argv),
        "code": git_state(),
        "model_under_test": {
            "provider": provider,
            "model": model,
            **model_artifact,
            "options": OPTIONS if is_ollama else {
                "transport": "OpenAI-compatible API",
                "temperature": provider_settings.temperature,
                "structured_output": provider_settings.structured_output,
                "max_tokens": provider_settings.max_tokens,
                "settings": "record server flags in the benchmark report",
            },
            "timeout_seconds": provider_settings.timeout,
            "prompt_file": "prompt.txt",
            "prompt_sha256": sha256(filler.PROMPT),
        },
        "judge": {
            "model": llm_judge.JUDGE_MODEL,
            **ollama_model_info(llm_judge.JUDGE_HOST, llm_judge.JUDGE_MODEL),
            "options": llm_judge.JUDGE_OPTIONS,
            "timeout_seconds": llm_judge.JUDGE_TIMEOUT_SECONDS,
            "threshold": llm_judge.JUDGE_THRESHOLD,
        },
        "ollama_version": ollama_version(OLLAMA_HOST) if is_ollama else None,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: package_version(name) for name in PACKAGES},
        },
        "documents": docs,
    }


def add_results(info, scored, skipped, seconds):
    """Averages and skips, known after the run."""
    n = len(scored)
    info["results"] = {
        "documents_scored": n,
        "documents_skipped": {doc: reason for doc, reason in skipped},
        "average_accuracy": round(sum(r["accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None,
        "average_populated_accuracy": (
            round(sum(r["populated_accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None
        ),
        "average_raw_accuracy": round(sum(r["raw_accuracy"] for _, r, _ in scored) / n * 100, 2) if n else None,
        "total_seconds": round(seconds),
        "scored_documents_per_minute": round(n * 60 / seconds, 3) if seconds > 0 else None,
        "attempted_documents_per_minute": round((n + len(skipped)) * 60 / seconds, 3) if seconds > 0 else None,
    }
    return info


def git_state():
    def git(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
            ).stdout.rstrip()
        except (OSError, subprocess.CalledProcessError):
            return None

    changed = git("status", "--porcelain", "--", "app", "benchmark", "requirements.txt")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        # Results are only reproducible from the commit if this is empty
        "uncommitted_changes": [line[3:] for line in changed.splitlines()] if changed else [],
    }


def ollama_model_info(host, model):
    """Digest, size and quantization of the model on its Ollama server."""
    info = {"digest": None, "details": None}
    try:
        tags = requests.get(host + "/api/tags", timeout=10).json()
        for m in tags.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                info["digest"] = m.get("digest")
        show = requests.post(host + "/api/show", json={"model": model}, timeout=10).json()
        info["details"] = show.get("details")
    except (requests.RequestException, ValueError):
        pass
    return info


def ollama_version(host):
    try:
        return requests.get(host + "/api/version", timeout=10).json().get("version")
    except (requests.RequestException, ValueError):
        return None


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
