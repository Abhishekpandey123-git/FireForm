
"""run_info.json: metadata needed to understand and recreate a benchmark run.

Written into every run folder; --baseline publishes it with the results.
Private server addresses are deliberately omitted.

Configured options are recorded separately from provider request options.
Server-side settings are recorded only when explicitly supplied through
environment variables; they are not inferred from shared OPTIONS.
"""

import hashlib
import os
import platform
import subprocess
import time
from importlib import metadata
from pathlib import Path

import requests

import llm_judge
from app.core.config import (
    LLM_PROVIDER,
    LLAMA_CPP_HOST,
    LLAMA_CPP_MODEL,
    LLAMA_CPP_TIMEOUT,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
)
from app.services.form_filler import filler
from app.services.llm.factory import normalize_provider
from app.services.llm.options import OPTIONS

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["pypdf", "pdfplumber", "requests"]


def collect(model, docs, argv):
    """Collect settings known before the benchmark run starts."""
    provider = normalize_provider(LLM_PROVIDER)

    if provider == "llama_cpp":
        host = LLAMA_CPP_HOST
        timeout = LLAMA_CPP_TIMEOUT
        configured_model = LLAMA_CPP_MODEL

        model_info = {
            "digest": None,
            "details": None,
            "model_source": "llama.cpp server; model digest unavailable",
            "model_file_sha256": model_file_sha256(),
        }

        server_version = llama_cpp_version(host)
        server_settings = {
            "context_size": env_int("LLAMA_CPP_CONTEXT"),
            "threads": env_int("LLAMA_CPP_THREADS"),
        }
        request_options = llama_cpp_request_options()

    else:
        host = OLLAMA_HOST
        timeout = OLLAMA_TIMEOUT
        configured_model = OLLAMA_MODEL
        model_info = ollama_model_info(host, model)
        model_info["model_source"] = "Ollama model registry"
        model_info["model_file_sha256"] = None

        server_version = ollama_version(host)
        server_settings = None
        request_options = ollama_request_options()

    return {
        "date": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "command": "python3 run.py " + " ".join(argv),
        "code": git_state(),
        "provider": provider,
        "model_under_test": {
            "provider": provider,
            "model": model,
            "configured_model": configured_model,
            **model_info,

            # Shared configuration as loaded by this process.
            # These are not necessarily all sent to every provider.
            "configured_options": dict(OPTIONS),

            # The generation settings this adapter is expected to send.
            "request_options": request_options,

            # Backwards-compatible field; explicitly documents that these
            # are shared configured options, not necessarily effective ones.
            "options": dict(OPTIONS),

            "server_settings": server_settings,
            "timeout_seconds": timeout,
            # Do not write the actual private server address into metadata.
            "host_configured": bool(host),
            "prompt_file": "prompt.txt",
            "prompt_sha256": sha256(filler.PROMPT),
        },
        "judge": {
            "provider": "ollama",
            "model": llm_judge.JUDGE_MODEL,
            **ollama_model_info(
                llm_judge.JUDGE_HOST,
                llm_judge.JUDGE_MODEL,
            ),
            "options": dict(llm_judge.JUDGE_OPTIONS),
            "timeout_seconds": llm_judge.JUDGE_TIMEOUT_SECONDS,
            "threshold": llm_judge.JUDGE_THRESHOLD,
        },
        "inference_server_version": server_version,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{
                name: package_version(name)
                for name in PACKAGES
            },
        },
        "documents": docs,
    }


def llama_cpp_request_options():
    """Describe the options sent by app/services/llm/llama_cpp.py.

    Keep this aligned with the adapter payload. num_ctx and repeat_last_n
    are intentionally excluded because the current adapter does not send
    them in its HTTP request.
    """
    return {
        "temperature": OPTIONS["temperature"],
        "seed": OPTIONS["seed"],
        "max_tokens": OPTIONS["num_predict"],
        "repeat_penalty": OPTIONS["repeat_penalty"],
        "stream": False,
        "json_schema": True,
    }


def ollama_request_options():
    """Describe generation options sent by the Ollama adapter."""
    return {
        "options": dict(OPTIONS),
        "stream": False,
        "format": "json",
    }


def model_file_sha256():
    """Hash a local GGUF file when LLAMA_CPP_MODEL_PATH is configured.

    Example:
        LLAMA_CPP_MODEL_PATH=/workspaces/models/model.gguf

    Returns None when no readable model file is configured.
    """
    raw_path = os.getenv("LLAMA_CPP_MODEL_PATH", "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_file():
        return None

    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None

    return digest.hexdigest()


def env_int(name):
    """Return an explicitly configured integer environment variable."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def add_results(info, scored, skipped, seconds):
    """Add aggregate results after the benchmark finishes."""
    count = len(scored)

    info["results"] = {
        "documents_scored": count,
        "documents_skipped": {
            doc: reason for doc, reason in skipped
        },
        "average_accuracy": (
            round(
                sum(result["accuracy"] for _, result, _ in scored)
                / count
                * 100,
                2,
            )
            if count
            else None
        ),
        "average_populated_accuracy": (
            round(
                sum(
                    result["populated_accuracy"]
                    for _, result, _ in scored
                )
                / count
                * 100,
                2,
            )
            if count
            else None
        ),
        "average_raw_accuracy": (
            round(
                sum(result["raw_accuracy"] for _, result, _ in scored)
                / count
                * 100,
                2,
            )
            if count
            else None
        ),
        "total_seconds": round(seconds),
    }

    return info


def git_state():
    """Capture commit, branch, and relevant uncommitted changes."""

    def git(*args):
        try:
            return subprocess.run(
                ["git", *args],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.rstrip()
        except (OSError, subprocess.CalledProcessError):
            return None

    changed = git(
        "status",
        "--porcelain",
        "--",
        "app",
        "benchmark",
        "requirements.txt",
    )

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "uncommitted_changes": (
            [line[3:] for line in changed.splitlines()]
            if changed
            else []
        ),
    }


def ollama_model_info(host, model):
    """Return model digest and details from Ollama when available."""
    info = {
        "digest": None,
        "details": None,
    }

    try:
        tags_response = requests.get(
            f"{host}/api/tags",
            timeout=10,
        )
        tags_response.raise_for_status()
        tags = tags_response.json()

        for item in tags.get("models", []):
            if item.get("name") == model or item.get("model") == model:
                info["digest"] = item.get("digest")
                break

        show_response = requests.post(
            f"{host}/api/show",
            json={"model": model},
            timeout=10,
        )
        show_response.raise_for_status()
        info["details"] = show_response.json().get("details")

    except (requests.RequestException, ValueError):
        pass

    return info


def ollama_version(host):
    """Return the Ollama version, or None if unavailable."""
    try:
        response = requests.get(
            f"{host}/api/version",
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("version")
    except (requests.RequestException, ValueError):
        return None


def llama_cpp_version(host):
    """Return llama.cpp server version metadata when exposed."""
    try:
        response = requests.get(
            f"{host}/health",
            timeout=5,
        )
        response.raise_for_status()
        body = response.json()

        if isinstance(body, dict):
            return body.get("version") or body.get("build")

    except (requests.RequestException, ValueError):
        pass

    # Many llama.cpp builds return only {"status": "ok"}.
    return None


def package_version(name):
    """Return an installed package version, if available."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def sha256(text):
    """Return the SHA-256 digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
