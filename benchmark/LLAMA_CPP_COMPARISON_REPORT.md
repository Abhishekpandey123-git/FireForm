# FireForm #702 — Ollama vs llama.cpp Benchmark Report

**Project:** FireForm  
**Benchmark objective:** Evaluate llama.cpp as an alternative inference backend to Ollama for structured FEMA Incident Command System (ICS) PDF form filling.  
**Platform:** Windows 11  
**Model:** Qwen2.5-1.5B-Instruct, Q4_K_M  
**Benchmark period:** November 1–2, 2026

---

## 1. Objective

Evaluate whether llama.cpp can improve FireForm's inference performance compared with Ollama while maintaining structured data extraction accuracy.

The evaluation focuses on:

- End-to-end document processing time.
- Raw benchmark accuracy.
- Accuracy on populated fields.
- Missing and unsupported values.
- Reproducibility of the benchmark configuration.

## 2. Hardware and software environment

### Hardware

| Component | Specification |
|---|---|
| CPU | AMD Ryzen 5 5600H |
| CPU cores | 6 cores / 12 logical processors |
| RAM | 16 GB |
| GPU | NVIDIA RTX 2050 |
| GPU VRAM | 4 GB |
| Operating system | Windows 11 |

### Software

| Component | Version / Configuration |
|---|---|
| Python | 3.12.10 |
| Ollama | 0.40.13 |
| llama.cpp | 0.7.0-dev |
| llama.cpp build | 11695 |
| llama.cpp commit | 9a16f1dbe |
| Compiler | Clang 20.1.8 |
| Model quantization | Q4_K_M |

### Model artifact verification

Both inference providers used the exact same GGUF model artifact.

The SHA-256 hash of the local llama.cpp model file was compared with the SHA-256 blob identifier referenced by Ollama's generated Modelfile.

**Verified SHA-256:**

`6A1A2EB6D15622BF3C96857206351BA97E1AF16C30D7A74EE38970E434E9407E`

| Verification | Result |
|---|---|
| llama.cpp GGUF file hash | `6a1a2eb6...e434e9407e` |
| Ollama underlying model blob | `sha256-6a1a2eb6...e434e9407e` |
| Hash comparison | Exact match |

This confirms that both providers used identical model weights, eliminating different model artifacts as a source of variation.

## 3. Benchmark methodology

Both providers were evaluated using FireForm's benchmark runner:

`benchmark/run.py`

The benchmark documents included:

- `ics_203_1`
- `ics_206_1`

For the aligned ICS203 comparison, the following generation settings were used:

| Parameter | Ollama | llama.cpp |
|---|---:|---:|
| Context size | 16,384 | 16,384 |
| Maximum output tokens | 8,192 | 8,192 |
| Temperature | 0 | 0 |
| Seed | 42 | 42 |
| Structured output | JSON schema | Structured output enabled |

Additional llama.cpp server settings:

- Host: `127.0.0.1`
- Port: `8081`
- GPU layers: `99`
- Parallel slots: `1`

The ICS203 prompt hash recorded by both runs was:

`5db932cd809037ef88bc480296e64a11d353ab2c4089a00145c02c91948442ec`

The identical model weights and aligned generation settings improve comparability. However, the providers may still differ in decoding implementation and inference behavior.

## 4. ICS203 results

### Raw benchmark comparison

| Metric | Ollama | llama.cpp |
|---|---:|---:|
| Raw accuracy | 25.00% | 22.69% |
| Populated-only accuracy | 32.73% | 29.70% |
| Missing values | 2 | 2 |
| Unsupported values | 42 | 24 |
| Document processing time | 58.43 sec | 25.80 sec |

### Observations

- llama.cpp completed the document approximately 55.8% faster.
- Ollama achieved 2.31 percentage points higher raw accuracy.
- llama.cpp generated 18 fewer unsupported values.
- Both providers had two missing values.

Neither provider achieved satisfactory accuracy on this document.

## 5. ICS206 results

Three runs were conducted for each provider.

### Average results

| Metric | Ollama | llama.cpp |
|---|---:|---:|
| Mean raw accuracy | 86.09% | 83.50% |
| Mean populated-only accuracy | 87.50% | 84.72% |
| Mean document processing time | 21.46 sec | 15.69 sec |
| LLM-judged accuracy | 95.67% | 95.67% |

### Run consistency

**Ollama:**

- Raw accuracy remained 86.09% across all three runs.
- Document processing times ranged from 20.93 to 21.74 seconds.

**llama.cpp:**

- Raw accuracy ranged from 78.95% to 85.77%.
- Document processing times ranged from 15.34 to 16.36 seconds.

### Observations

- llama.cpp was approximately 26.9% faster based on mean document processing time.
- Ollama achieved 2.59 percentage points higher mean raw accuracy.
- llama.cpp showed variation in raw accuracy across runs.

## 6. Performance comparison

| Document | Provider | Mean/observed time |
|---|---|---:|
| ICS203 | Ollama | 58.43 sec |
| ICS203 | llama.cpp | 25.80 sec |
| ICS206 | Ollama | 21.46 sec |
| ICS206 | llama.cpp | 15.69 sec |

The results show a consistent latency advantage for llama.cpp on both tested documents.

## 7. Limitations and reproducibility considerations

1. **Limited document coverage:** Only two ICS document examples were evaluated. These results should not be generalized to the entire FireForm workload.

2. **Inference implementation differences:** Although the underlying model weights were verified identical, Ollama and llama.cpp may differ in structured decoding, sampling implementation, and inference execution.

3. **LLM judge reliability:** The judge used a small model from the same model family. Its scores should be treated cautiously because it accepted some incorrect field values in earlier evaluations.

4. **Judge availability:** The final November 2 llama.cpp ICS203 run could not connect to the Ollama judge endpoint. Its reported judged accuracy therefore fell back to raw accuracy.

5. **Server metadata:** Context size, seed, GPU layers, and parallel slots were verified from the llama.cpp startup command, but were not automatically captured in `run_info.json`.

6. **Hardware specificity:** Performance measurements reflect one Windows 11 machine with an RTX 2050 and 16 GB RAM.

7. **Run variation:** ICS206 results show variation in llama.cpp raw accuracy, so additional repetitions and document coverage would strengthen the conclusions.

## 8. Conclusion

Based on the tested ICS203 and ICS206 documents, llama.cpp demonstrated a consistent performance advantage over Ollama.

- ICS203 processing was approximately 55.8% faster.
- ICS206 processing was approximately 26.9% faster.
- Ollama achieved slightly higher raw accuracy on both documents.
- llama.cpp produced fewer unsupported values on ICS203.
- Both providers used identical model weights, verified through SHA-256.

The evidence supports llama.cpp as a promising performance-oriented inference backend for FireForm.

However, the current results are not sufficient to establish a universal replacement for Ollama. Further testing across additional ICS forms, repeated runs, and independently verified evaluation is recommended.

**Recommendation:** Continue evaluating llama.cpp through FireForm's existing configurable LLM provider architecture. Preserve Ollama as a comparison baseline until broader accuracy and reliability testing is completed.

---

## 9. Reproducibility artifacts

The benchmark outputs are available in the local repository:

- ICS203 Ollama: `benchmark/results/2026-11-01_115300_ollama_fireform-qwen2.5-1.5b-16k-latest`
- ICS203 llama.cpp: `benchmark/results/2026-11-02_162259_llama_cpp_E-`
- ICS206: Refer to the three-run Ollama and llama.cpp result directories from November 1.

Relevant artifacts include `run_info.json`, `summary.csv`, `run.log`, and document-level outputs.

**Benchmark status:** Initial comparative evaluation completed. Further validation recommended before production adoption or making a definitive provider recommendation.
