# Performance

## Scanner compaction exploration

Niles Salter's [AVX-512 tokenizer talk](https://youtu.be/E6dWIwPLx3s) motivates
classifying bytes into masks and compacting selected positions into output.
Our x86 scanner already processes 64-byte blocks using AVX2 masks. On Atlas,
we tested replacing its eight byte-mask table expansions with four AVX-512
`vpcompressd` operations, keeping the existing boundary rules and capacity
fallback. One variant compressed directly into memory; another compressed
into a register and used a masked store of exactly the selected positions.

The Qwen3.5-4B FineWeb profile attributed 7.39% of sampled native encoding
cycles to the scanner, 47.47% to piece lookup/cache handling and 35.31% to
BPE. These are cycle samples for this workload, not consumer wall-time shares.
Even eliminating the scanner would cap this profile's speedup at about 1.08×.

Four balanced whole-process blocks per workload, 100 passes per process,
measured the following median milliseconds per pass on the same EPYC 9124:

| Complete encoding | AVX2 baseline | Compress to memory | Compress to register |
| --- | ---: | ---: | ---: |
| 256 decisions | 0.661 | 1.063 | 0.659 |
| 1,024 FineWeb-Edu documents | 21.071 | 27.430 | 21.240 |
| 1,024 Pleias documents | 10.516 | 12.840 | 10.510 |

Register compaction improved boundary-only measurements by about 1–2%, but
complete encoding remained around parity: paired geometric-mean speedups
were 1.000×, 0.995× and 1.004× respectively. Direct-memory compaction was
22–61% slower for complete encoding. Both prototypes were removed; production
assembly and the consumer dependency stay unchanged. The measured next target
is piece lookup/cache handling and BPE, rather than wider boundary emission.

All 144 process-final token/boundary digests matched their workload baselines.
The direct-memory prototype also passed 13 Rust tests, 45 native callers and
the six-target assembly audit; the register variant received corpus checks
only. Neither result establishes general AVX-512 performance or a consumer
speedup. [Complete receipt and samples](../benchmarks/results/scanner-compaction-epyc9124.json).

The bounded Rust probe separates complete encoding from boundary generation:

```sh
nix-shell --run 'cargo build --release --example native_scan_probe'
nix-shell -p perf util-linux --run 'perf record -e cycles:u -F 1999 -- taskset -c 8 target/release/examples/native_scan_probe /path/to/tokenizer.json /path/to/corpus.bin encode 400'
```

Its corpus format is repeated little-endian `u32` byte lengths followed by the
document bytes: at most 4,096 documents and 16 MiB total. Use `pieces` instead
of `encode` to measure boundary generation. Each pass creates fresh scratch
with a 4 MiB memo budget and the default piece cache; an optional final `0`
argument disables the memo. Tokenizer loading and the length-prefixed output digest
are outside timing; scratch allocation and destruction are inside. Output
vectors are reused across passes. The probe does not include Python, batch
workers, rendering, packing or model execution.

## Lookup, BPE and batch startup

The follow-up FineWeb profile sampled 48.35% of native cycles in piece
lookup/cache handling and 35.43% in BPE. Kernel experiments did not establish
a consumer gain: a cheaper key comparison measured around parity in four
consumer blocks; prefetching improved native text encoding but slowed decision
encoding. Smaller caches and eight-worker pools also failed the adoption
check. Those changes were removed; their observations remain in the
[follow-up receipt](../benchmarks/results/lookup-followup-epyc9124.json).

The retained change reduces pool initialization cost. Wakeup calibration had
two fixed 2 ms settling waits. Each now uses the existing 200 µs spin cap,
with all six calibration rounds retained. Pool creation measured
4.198 → 0.582 ms, 7.214×, in four balanced process blocks with 31 constructor
trials per process. Loading and destruction are outside constructor timing.

Against `6d78e24`, the same consumer at `9d5c28a` measured:

| First batch workload | Baseline ms | Candidate ms | Speedup |
| --- | ---: | ---: | ---: |
| 1,024 FineWeb-Edu documents | 33.601 | 30.130 | 1.115× |
| 1,024 Pleias documents | 18.305 | 14.785 | 1.238× |
| 256 decision questions | 4.186 | 4.215 | 0.993× |

Four ABBA/BAAB blocks, three fresh-tokenizer samples per process, affinity
8–15, Rust 1.98.1, Clang 21 and CPython 3.13.15. Times are means of block
medians; speedups are geometric means of paired ratios. Every text block
improved: FineWeb 1.093–1.136×, Pleias 1.226–1.252×. Every token and packed-array
digest matched. The gain comes from initializing the first batch, rather than
faster lookup or BPE. Decision preparation showed no improvement.

The measured wheel pair's executable section differs only in six immediate-value
bytes; lookup and BPE code and their addresses are identical. The final change
passed 13 Rust tests, 45 native callers, 90 protected-page callers and 54 Python
batch, snapshot, boundary and threading checks.

The rebuilt production Nix environment independently confirmed the first-batch
gain. Two ABBA/BAAB blocks per input size, three samples per process at 1,024
records and two at 8,192 records:

| Production input | Records | Baseline ms | Candidate ms | Speedup |
| --- | ---: | ---: | ---: | ---: |
| FineWeb-Edu | 1,024 | 33.559 | 29.748 | 1.128× |
| Pleias | 1,024 | 18.243 | 14.726 | 1.239× |
| FineWeb-Edu | 8,192 | 237.741 | 234.270 | 1.015× |
| Pleias | 8,192 | 112.973 | 110.588 | 1.022× |

The longer streams amortize initialization, so their gain is smaller. These
measurements establish a startup improvement, not higher sustained BPE
throughput. All cross-build token and packing digests matched; the updated
consumer passed 157 CPU tests with 19 GPU skips. Its profiling helper accepts
`--text-rows 8192 --text-root /path/to/text` for the longer comparison.

Reproduce constructor measurements with the bounded Rust probe:

```sh
nix-shell --run 'cargo build --release --example batch_startup_probe'
nix-shell -p util-linux --run 'taskset -c 8-15 target/release/examples/batch_startup_probe /path/to/tokenizer.json 31'
```

The native scanner probe also accepts a final CPU tier after `MEMO_MIB`:
`auto`, `scalar`, `avx2` or `avx512`. The last requires the `avx512` Cargo feature.

## Workloads and reproduction

The measured consumer performs Qwen3.5-4B decision scoring and text preprocessing.
Its application source and decision dataset are not distributed with this fork.
Benchmarks load tokenizer files only and use no GPU or model weights.
A decision workload encodes each rendered prompt and validates its
answer-letter extensions. Text workloads measure encoding and Python list
construction for FineWeb-Edu and Pleias SYNTH, excluding NumPy conversion.

The optional corpus exporter requires that consumer and its datasets. For a
local checkout, set `CONSUMER_CHECKOUT`, `MODEL_DIRECTORY`, `CASES`, `FINEWEB`, and
`PLEIAS` to their corresponding paths before running:

```sh
mkdir -p build/readout
DEV=CPU "$CONSUMER_CHECKOUT/.env/bin/typed-decisions-run" python tools/bench/readout-corpus.py \
  --project "$CONSUMER_CHECKOUT" \
  --model "$MODEL_DIRECTORY" \
  --cases "$CASES" \
  --fineweb "$FINEWEB" \
  --pleias "$PLEIAS" \
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
typed-decisions `34da9d5` (consumer source).

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
passed 138 CPU tests with 19 GPU skips.

## Consumer Qwen rendering (2026-10-20)

The consumer now renders the pinned Qwen3.5 template directly for its two
plain-text system/user messages. An exact source hash and built-in message
types gate this path; other templates and shapes retain the Jinja sandbox.
This is a consumer rendering improvement, with the native tokenizer unchanged.

Against consumer `aaf5f87`, candidate `4421339` uses four ABBA/BAAB blocks,
three fresh-tokenizer samples per process and affinity 8–15:

| 256 questions | Jinja | Direct text | Speedup |
| --- | ---: | ---: | ---: |
| Messages and rendering | 16.495 ms | 0.988 ms | **16.70×** |
| Complete prompt preparation | 20.067 ms | 4.111 ms | **4.88×** |

Times are means of block medians; speedups are geometric means of paired
ratios. Preparation improves 4.833–4.926× across blocks. Rendered strings and
prepared token hashes match throughout. A separate audit matches 24,576
prompts byte-for-byte against the complete Jinja template across three formats
and both option orders. Warm Python allocation peaks fall from 0.661 to
0.325 MB for rendering and 0.933 to 0.618 MB for complete preparation.

The [receipt](../benchmarks/results/consumer-chat-render-epyc9124.json) retains
all 16 processes, 96 timed observations, source/output hashes, profiles and
the audit. The consumer's full CPU suite passed 154 tests with 19 GPU skips;
17 renderer-focused tests also passed.
No model inference or GPU training throughput is established by this study.

## Consumer buffer reservation follow-up (2026-10-20)

The consumer now initially reserves one token slot per four characters,
rounded up, with the existing exact-size retry if needed. Compared with
`4421339`'s one-slot-per-character reservation, candidate `cf6908c` reduces
initial capacity by 75% on the measured original JSONL prefixes. Both fit
without retries. This is a size estimate; correctness remains independent of
the character/token ratio.

Two ABBA/BAAB whole-process blocks, three fresh-tokenizer samples per process,
and affinity 8–15 retain throughput while reducing traced allocation peaks:

| 1,024 documents | Previous reservation | Smaller reservation |
| --- | ---: | ---: |
| FineWeb preprocessing | 33.734 ms | 33.361 ms |
| Pleias preprocessing | 18.373 ms | 18.248 ms |
| FineWeb Python/NumPy peak | 36.79 MB | **22.99 MB** |
| Pleias Python/NumPy peak | 11.29 MB | **7.16 MB** |

Times are means of paired block medians. Differences of about 1% establish
retained throughput. Peak traced allocations fall 37.5% and 36.6%, restoring
the earlier serial path's levels. These are separate warm allocation profiles,
including unused NumPy capacity and excluding Rust allocations, not resident
memory measurements. Token and packed-array hashes match in every sample.

The [receipt](../benchmarks/results/consumer-buffer-memory-epyc9124.json)
retains all eight paired processes, 96 timed observations, source/output
hashes and warm profiles. The final combined consumer at `9d5c28a` passed
157 CPU tests with 19 GPU skips and 22 final renderer/buffer-focused tests.
Its source fingerprinting also preserves generic Jinja behavior for unusual
source strings and rejects template subclass spoofing. The pinned-Qwen render
audit again matches all 24,576 prompts byte-for-byte.
