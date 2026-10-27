# Form-filling benchmark

Runs `app/services/form_filler` on the ICS narratives and scores the filled
fields against hand-written ground truth, with an LLM judge for answers that
are right but worded differently. The same runner can select any configured
FireForm LLM provider, including an OpenAI-compatible `custom` endpoint such
as a local llama.cpp server.

## Setup

```bash
pip install -r requirements.txt
cp benchmark/.env.example benchmark/.env   # set the model and judge settings
```

`benchmark/.env` is gitignored, so a private server address stays local.
Settings (see `config.py` and `.env.example`):

| Variable | Default | Used for |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | model under test (read by `app.core.config`) |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | model under test |
| `OLLAMA_TIMEOUT` | `300` | seconds per fill request |
| `LLM_PROVIDER` | `ollama` | default provider, when `--provider` is omitted |
| `LLM_MODEL` | provider default | default model when configured for the default provider |
| `CUSTOM_BASE_URL` | — | OpenAI-compatible server URL, e.g. `http://localhost:8080/v1` |
| `CUSTOM_API_KEY` | — | key expected by the custom server; use its documented local value |
| `CUSTOM_MODELS` | — | comma-separated model IDs allowed for the custom provider |
| `LLAMA_CPP_BASE_URL` | `http://localhost:8080/v1` | llama-server OpenAI-compatible endpoint |
| `LLAMA_CPP_API_KEY` | empty | optional key if configured by the server |
| `LLAMA_CPP_MODELS` | — | comma-separated llama.cpp model IDs allowed |
| `LLM_TIMEOUT` | `OLLAMA_TIMEOUT` | request timeout used by provider adapters |
| `JUDGE_HOST` | `OLLAMA_HOST` | LLM judge |
| `JUDGE_MODEL` | `qwen3.5:4b` | LLM judge |
| `JUDGE_TIMEOUT_SECONDS` | `300` | seconds per judge request |

Shell environment variables override `.env`. The judge still uses the existing
Ollama-native endpoint; keep `JUDGE_HOST` pointed at the same separate Ollama judge
server for both runs so scoring is consistent and judge load does not skew target-server
CPU/RAM measurements. The Ollama model must
be pulled on its server. For llama.cpp, start its OpenAI-compatible server first
and set `CUSTOM_BASE_URL`, `CUSTOM_MODELS`, and (if required) `CUSTOM_API_KEY`.

## Running

```bash
cd benchmark
python3 run.py                                      # configured provider/model, all narratives
python3 run.py -d ics_203_1 ics_206_1              # same subset for each provider
python3 run.py --provider ollama -m qwen2.5:1.5b   # Ollama run
python3 run.py --provider llama_cpp -m your-model-id  # explicit llama.cpp provider
python3 run.py --provider llama_cpp -m your-model-id -d ics_203_1 ics_206_1
python3 run.py --baseline --provider ollama        # full run, then publish baseline
```

Use exactly the same `-d` document list for each provider. For a fair runtime
comparison, pin the same model weights and quantization where possible, use the
same FireForm commit and prompt, keep the judge model/configuration fixed, and
run multiple repetitions. llama.cpp's `/v1/models` name must match the `-m`
argument and be allowed by `LLAMA_CPP_MODELS`. Do not compare results from runs
that skipped different documents without reporting those skips.

### CPU and memory profiling (Linux, on the model server)

`run.py` records both fill-phase wall time (schema construction, inference and PDF
writing) and total document-processing wall time in `summary.csv`. CPU/RAM belong to the
inference server process, not the Python benchmark process, so sample the server
on the machine where it runs. The helper writes a time-series CSV to the
gitignored `benchmark/results/` directory:

```bash
python3 benchmark/profile_runtime.py --label ollama \
  --process-regex 'ollama' -- \
  python3 benchmark/run.py --provider ollama -m qwen2.5:1.5b -d ics_203_1 ics_206_1

python3 benchmark/profile_runtime.py --label llama-cpp \
  --process-regex 'llama-server' -- \
  python3 benchmark/run.py --provider llama_cpp -m your-model-id -d ics_203_1 ics_206_1
```

Run the profiler on the same host as the server. It samples matching Linux
processes' combined RSS and CPU usage (100% means one fully used CPU core).
If the server is remote, collect its CPU/RAM on that machine separately. Record
the hardware, OS, server command/build, GGUF SHA-256, context size, quantization,
warm/cold state, and profile CSV location in the report. GPU VRAM is not exposed
by `/proc`; collect it separately with the platform's GPU monitoring tools.

Summarize profiler samples and compare provider summaries with these helpers:

```bash
python3 benchmark/summarize_runtime.py benchmark/results/runtime-profile_*.csv
python3 benchmark/compare_benchmark_runs.py path/to/ollama/summary.csv path/to/llama_cpp/summary.csv --output benchmark/results/comparison.csv
```

`run_info.json` also records scored and attempted documents per minute. The comparison
helper reports skipped documents and differing success sets.

A document whose model call fails or times out, or whose output is cut off
mid-JSON (runaway generation hitting `num_predict`), is skipped and listed;
it is left out of the averages.

## Output

Each run gets its own folder, `results/<date>_<time>_<model>/` (gitignored):

| File | Contents |
|---|---|
| `summary.csv` | one row per document: provider/model, elapsed wall time, judged, populated and raw accuracy, status |
| `wrong_fields.txt` | every wrong field, expected vs got, with the score before and after the judge |
| `run.log` | everything printed during the run |
| `run_info.json` | how to recreate the run (see below) |
| `prompt.txt` | the prompt file the run used |
| `<doc>/prompt.txt` | exact prompt sent to the model |
| `<doc>/schema.json` | JSON schema sent as Ollama's `format` |
| `<doc>/response.json` | raw model output |
| `<doc>/filled.json` | flat `{widget name: value}` written to the PDF |
| `<doc>/filled.pdf` | the filled form |
| `<doc>/review.pdf` | the filled form with wrong (red), partial (yellow) and missing (orange) fields marked |

## run_info.json

Every run records what produced it:

- **code**: git commit, branch, and any uncommitted changes under `app/`,
  `benchmark/` or `requirements.txt` (a run is only reproducible from its
  commit when that list is empty)
- **model_under_test**: provider/model, Ollama digest and quantization when
  available, generation settings, timeout, and the prompt's SHA-256
  (the prompt itself is saved next to it as `prompt.txt`)
- **judge**: the same for the judge model, plus its threshold
- **ollama_version**, Python and package versions, platform
- **documents** run, and the **results**: averages, skipped documents, time

Server addresses are left out on purpose; the digest identifies the model.
To recreate a run: check out the commit, `ollama pull` the models and check
their digests match, and run the same command.

## Baselines

Most runs stay local in `results/`. When a change is worth recording (a new
prompt, template change or model), run the full benchmark with `--baseline`:

```bash
python3 run.py --baseline
```

It overwrites `baselines/<model>/` for Ollama runs and `baselines/<provider>--<model>/`
for other providers with that run's `summary.csv`, `wrong_fields.txt`, `run_info.json`
and `prompt.txt`. Use `benchmark/LLAMA_CPP_COMPARISON_REPORT_TEMPLATE.md` to record
repeated results, model equivalence, hardware, and the adoption recommendation. The diff then shows the effect
on every document, and the folder's git history is the record of how
accuracy changed over time. The large per-document files (PDFs, raw
responses) are not published; attach a zipped run folder to the PR if
someone needs them.

`--baseline` refuses `-d`, so a baseline always covers every document.

Ollama is not fully deterministic even at temperature 0 with a fixed seed:
the same prompt can give different answers between runs, and single
documents (especially ICS 203) can move 10-30 points. Compare averages, and
treat one document's change as meaningful only if it repeats.

## Scoring

- Tables are compared row by row, matching each expected row to its
  best-matching output row, so rows in a different order are not wrong.
- Short values (6 words or fewer) must match exactly after lowercasing and
  punctuation removal; longer text is scored by word overlap.
- Filled-in fields scoring below 0.99 go to the LLM judge with the narrative,
  which accepts (1.0) or rejects (0.0) them. Blank answers are not judged.
  "Accuracy" is after the judge; "raw accuracy" is before it.
- "Populated" accuracy leaves out fields that are blank in the ground truth.

## Files

| File | Role |
|---|---|
| `run.py` | runner: fill, save, score, report, publish baselines |
| `config.py` | settings and `.env` loading |
| `run_info.py` | writes `run_info.json` |
| `compare.py` | shapes output and ground truth, computes the scores |
| `accuracy.py` | field and row similarity |
| `llm_judge.py` | LLM judge for failing fields |
| `report.py` | writes `wrong_fields.txt` |
| `review_pdf.py` | writes `review.pdf` |
| `data/pdfs/` | the 11 blank ICS forms |
| `data/narratives/` | 56 incident narratives, `<form>_<n>.txt` |
| `data/ground_truth/` | expected field values per narrative, keyed by widget name |
| `data/ICS_DATASET_GENERATOR_PROMPT.md` | prompt used to generate the narratives and ground truth |
| `baselines/<model>/` | published baseline results (committed) |
| `results/` | every run (gitignored) |
