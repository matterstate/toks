# Performance

## Workloads and reproduction

The current consumer is Qwen3.5-4B decision scoring and text preprocessing in
`typed-decisions`. Benchmarks load tokenizer files only and use no GPU or model
weights. A decision workload encodes each rendered prompt and validates its
answer-letter extensions. Text workloads measure encoding and Python list
construction for FineWeb-Edu and Pleias SYNTH, excluding NumPy conversion.

Prepare the local corpus with the consumer's locked environment:

```sh
mkdir -p build/readout
DEV=CPU ../typed-decisions-baseline/.env/bin/typed-decisions-run python tools/bench/readout-corpus.py \
  --project ../typed-decisions-baseline \
  --model ../typed-decisions-baseline/model-cache/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --cases "$HOME/data/decisions/synth_verified_reasoning_v1/train_00.jsonl" \
  --fineweb "$HOME/data/text/fineweb_edu.jsonl" \
  --pleias "$HOME/data/text/pleias_synth.jsonl" \
  --out build/readout/corpus.json
```

The required local datasets are not part of this repository. The recorded
corpus has 256 decision prompts and 1,024 documents from each text source:
6,821,217 bytes, SHA-256
`66f20155468079c24fe68640ec911e594911f7684329a1364ae7e199de60a082`.
A direct HF tokenizers 0.23.2 comparison matched all 2,304 inputs and 1,438,578
tokens.

Run the same helper against isolated installed baseline and candidate wheels:

```sh
nix-shell -p util-linux --run 'taskset -c 8-15 build/python-env/bin/python tools/bench/readout-bench.py --corpus build/readout/corpus.json --out build/readout/run.json --repetitions 3'
```

Each sample starts with a fresh tokenizer. Loading and answer preparation are
outside timing; lazy caches and worker creation are inside. Every output digest
includes each document's length and complete token sequence. Alternate whole
baseline/candidate processes in ABBA/BAAB blocks and keep every cell. See
[validation](validation.md) for comparison and review rules.

For native callers, `tools/bench/corpora.py` materializes the public corpus
manifest in [benchmarks/corpora.json](../benchmarks/corpora.json).
On 2026-10-20, Gutenberg's live copy of book 2701 differed from the recorded hash;
reproduction requires the matching archived bytes. The helper rejects changed
sources rather than silently replacing the benchmark corpus or its pins.
Compile `tools/bench/e2e.c` against each revision's static library, then compare
with `tools/bench/compare.py --baseline <binary> --candidate <binary>`.
`tools/bench/report.py <results.json>` summarizes complete paired blocks.

## Measured results

Measurements below are from Atlas, AMD EPYC 9124, Linux x86-64, CPython 3.13,
CPU affinity 8–15, Rust 1.98.1 and GCC 16.2.0 for assembly. Both sides used the
`python` profile and portable CPU target. The current Nix shell uses Clang;
these GCC measurements do not establish Clang build performance.

The batch change compared `e16b816` with `e865559` in five paired blocks with
three samples per process. Mean block medians and paired geometric-mean ratios:

| Workload | Method | Baseline ms | Candidate ms | Speedup |
| --- | --- | ---: | ---: | ---: |
| 256 decision prompts | encode | 1.36 | 1.43 | 0.95× |
| 256 decision prompts | buffer | 1.08 | 1.08 | 0.99× |
| 256 decision prompts | answer-letter validation | 3.11 | 3.08 | 1.01× |
| 1,024 FineWeb-Edu documents | single calls | 35.41 | 35.36 | 1.00× |
| 1,024 FineWeb-Edu documents | batches of 32 | 35.57 | 35.33 | 1.01× |
| 1,024 FineWeb-Edu documents | one batch | 33.70 | 21.80 | 1.55× |
| 1,024 Pleias documents | single calls | 18.07 | 18.07 | 1.00× |
| 1,024 Pleias documents | batches of 32 | 18.01 | 17.68 | 1.02× |
| 1,024 Pleias documents | one batch | 17.12 | 13.10 | 1.31× |

[Complete batch receipt](../benchmarks/results/readout-parallel-epyc9124.json).
A three-block decision-only follow-up with 15 samples per process measured
1.01× for encoding and answer validation and 1.00× for buffers; it did not
establish a readout speedup. [Complete decision receipt](../benchmarks/results/readout-decisions-epyc9124.json).

The integer-list change compared `e865559` with the optimized adapter in four
paired blocks with seven samples per cell. It measured answer validation at
3.102 → 2.970 ms, 1.044× (all blocks 1.022–1.072×). Plain decision encoding varied
around parity; the buffer path measured 0.994×. Large text batches improved
about 1%, beyond the earlier worker-pool gain.
[Complete integer-list receipt](../benchmarks/results/readout-int-list-epyc9124.json).

All before/after token digests matched. These results describe tokenizer wall
time on one host and corpus. They do not establish GPU training or end-to-end
inference improvements, or guarantee performance on other hosts.

## Consumer preprocessing

A CPU profile of the integrated consumer found that Python integer-list
conversion costs about 21 ms per frozen FineWeb batch. The consumer now uses
`encode_into` with a reusable NumPy buffer and an owned copy per retained
document. Both sides use the same installed fork binary; this change is in
[typed-decisions `34da9d5`](https://github.com/matterstate/typed-decisions/blob/34da9d5/reports/tokenizer_integration_profile.md).

Original JSONL prefixes, 1,024 documents each, with reading, JSON decoding,
tokenization, array construction and held-out/training packing included:

| Workload | Baseline ms | Candidate ms | Speedup |
| --- | ---: | ---: | ---: |
| FineWeb-Edu JSONL | 63.841 | 48.792 | 1.308× |
| Pleias SYNTH JSONL | 28.323 | 22.625 | 1.252× |
| 256 decision questions | 20.471 | 20.382 | 1.004× |

Two whole-process ABBA/BAAB blocks, three fresh-tokenizer samples per process,
CPU affinity 8–15. Inputs are warm in the OS page cache; loading, output hashing
and persistence are outside timing. Previous outputs are released and GC
collected before each measurement; automatic GC inside workloads stays enabled.
The four-block frozen-corpus comparison measured 1.371× FineWeb and 1.256×
Pleias. Every output digest matches. Decision preparation is unchanged and no
readout speedup is established; chat-template rendering dominates that path.

The [complete receipt](../benchmarks/results/consumer-tokenization-epyc9124.json)
retains all final samples, source hashes, prefix hashes and separate warm
CPU/memory diagnostics. The consumer CPU suite passed 138 tests with 19 GPU
skips, including three new buffer/split regressions. These measurements do not
establish model inference or GPU training throughput.

## Batched consumer buffers (2026-10-20)

`encode_batch_into(texts, out)` combines the existing worker pool with a flat
caller-owned integer buffer and document offsets. The consumer's text planner
now uses it in place of serial `encode_into` calls. The tokenizer creates no
Python integer per token; small or oversized batches retain the serial
fallback. See the [Python API](../python/README.md) for capacity checks.

The production Nix build at `ba97f0b` was measured against itself with consumer
baseline `34da9d5` and candidate `aaf5f87`. Four ABBA/BAAB blocks, three fresh
tokenizers per process and CPU affinity 8–15 give these original-source JSONL
preprocessing times (1,024 documents each):

| Source | Serial buffer | Batched buffer | Speedup |
| --- | ---: | ---: | ---: |
| FineWeb, 1,090,466 tokens | 48.810 ms | 33.664 ms | **1.450×** |
| Pleias, 336,377 tokens | 22.572 ms | 18.402 ms | **1.227×** |

Times are means of block medians; speedups are geometric means of paired
ratios. Every block improves: FineWeb 1.423–1.462×, Pleias 1.212–1.236×.
The two-block frozen-corpus check confirms 1.362× and 1.233× respectively.
Complete token and packed-array hashes match in every sample. Rendering and
decision preparation show no established improvement.

The consumer reserves one integer slot per character and retries once at the
exact required size on overflow. Warm traced Python/NumPy allocation peaks
increase from 22.99 to 36.79 MB for FineWeb and 7.16 to 11.29 MB for Pleias.
These include unused NumPy capacity and exclude native Rust allocations;
they do not measure resident memory. This change trades transient allocation
capacity for throughput. Model inference and GPU training were not measured.

The [complete receipt](../benchmarks/results/consumer-batch-buffer-epyc9124.json)
contains all 24 paired processes and 288 timed observations, input/output
hashes, the Nix binary fingerprint and separate warm profiles. The production
build passed 377 Python tests with 43 skips; standalone and independently
rebuilt source-distribution wheels each passed 44 focused tests. The consumer
passed 138 CPU tests with 19 GPU skips. The
[consumer report](https://github.com/matterstate/typed-decisions/blob/aaf5f879cdfe6554d5a75b679ed0f02e1eecadf3/reports/tokenizer_batch_buffer.md)
describes the integration and measurement scope.
