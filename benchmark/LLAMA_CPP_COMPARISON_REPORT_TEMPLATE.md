# FireForm Issue #702 — Ollama vs. llama.cpp comparison

> Fill this report only after the benchmark has completed. Keep raw run folders, `summary.csv`, `run_info.json`, and runtime profile CSVs as evidence. Do not infer missing measurements.

## 1. Reproducibility record

| Item | Value |
|---|---|
| Date/time and timezone | TODO |
| FireForm commit SHA | TODO |
| OS and kernel | TODO |
| CPU model / cores | TODO |
| RAM | TODO |
| GPU / VRAM (if used) | TODO |
| Python / dependency versions | From `run_info.json` |
| ICS documents included | TODO |
| Number of repetitions per provider | At least 3 |
| Judge model and host | TODO; keep identical across runs |
| Prompt SHA-256 | From `run_info.json` |

## 2. Model equivalence and runtime configuration

| Item | Ollama | llama.cpp |
|---|---|---|
| Model family and exact weights | TODO | TODO |
| Artifact SHA-256 / digest | TODO | GGUF SHA-256: TODO |
| Quantization | TODO | TODO |
| Context window | TODO | TODO |
| Server version/build SHA | TODO | TODO |
| Exact server launch command | TODO | TODO |
| API/provider config (omit secrets) | TODO | `llama_cpp` / OpenAI-compatible (or `custom` if running before the explicit provider lands) |
| Warm-up procedure | TODO | TODO |

Confirm that the model weights are equivalent. If exact equivalence is not possible, state this as a limitation and do not attribute all observed differences to the runtime alone.

## 3. Per-run results

Include one row per repetition and provider. Use the same documents and scoring configuration in all runs.

| Provider | Run | Documents scored | Skipped | Total wall time (s) | Median doc latency (s) | Judged accuracy (%) | Populated accuracy (%) | Raw accuracy (%) | Missing fields | Unsupported fields |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ollama | 1 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| Ollama | 2 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| Ollama | 3 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| llama.cpp | 1 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| llama.cpp | 2 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| llama.cpp | 3 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

## 4. Resource usage

Use the `profile_runtime.py` CSV captured on the model-server host. Record GPU measurements separately if available.

| Metric | Ollama | llama.cpp | Measurement method |
|---|---:|---:|---|
| Mean CPU usage (% of one core) | TODO | TODO | profile CSV |
| Peak CPU usage (% of one core) | TODO | TODO | profile CSV |
| Peak resident RAM (MiB) | TODO | TODO | profile CSV |
| Peak GPU VRAM (MiB) | TODO / N/A | TODO / N/A | TODO |

## 5. Validity checks and limitations

- Same FireForm commit and prompt: TODO
- Same document set and narrative order: TODO
- Same judge model/settings: TODO
- Same weights/quantization: TODO
- Any skipped documents or failed judge calls: TODO
- Cold-start versus warm-run behavior: TODO
- Remote server or unmeasured GPU resource limits: TODO
- Other confounding factors: TODO

Runs with different skipped-document sets must not be compared as if they cover the same workload. Report failed or unavailable judge results instead of treating them as correct.

## 6. Summary and recommendation

**Latency:** TODO (report fill-phase median and variation across repeated runs, plus end-to-end document time; do not rely only on the fastest run).

**Accuracy:** TODO (state any regression or uncertainty).

**Resource use:** TODO.

**Integration / maintenance costs:** TODO.

**Recommendation:** Adopt llama.cpp / keep Ollama / gather more evidence. Explain the trade-off and the exact scope of the recommendation. Do not recommend a runtime solely from a single run or from latency if accuracy regresses.

## 7. Artifacts

- Ollama run folders: TODO
- llama.cpp run folders: TODO
- Runtime profile CSVs: TODO
- `run_info.json` files: TODO
- Commands used: TODO
