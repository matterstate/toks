# Qwen readout tokenization

The consumer is `typed-decisions`: Qwen3.5-4B decision scoring and text-training
preprocessing on Atlas (AMD EPYC 9124, Linux x86-64, CPython 3.13). These checks
load tokenizer files only. They do not load model weights or use the GPU.

The current [validation policy](../validation.md) uses reviewed Rust snapshots
and pinned external oracles. The C reference used in historical checks below
has been retired; existing measurement receipts are preserved.

Two paths matter:

- A decision question encodes its rendered chat prompt, then re-encodes the
  prompt with each answer letter appended to check the one-token readout.
- Text preprocessing calls `encode_batch` with 1,024 documents, then converts
  the returned lists to NumPy arrays. The benchmark measures tokenization and
  Python list construction; it excludes the NumPy conversion.

## Inputs

`tools/rust-port/readout-corpus.py` freezes 256 rendered training questions and
1,024 documents each from FineWeb-Edu and Pleias SYNTH. It uses the application's
chat template, answer letters and tokenizer configuration. Text documents are
the first 1,024 nonempty inputs of at most 65,536 UTF-8 bytes among the first
4,096 source rows. Source rows over 1 MiB fail preparation.

The measured Qwen snapshot is `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`.
The corpus is 6,821,217 bytes, SHA-256
`66f20155468079c24fe68640ec911e594911f7684329a1364ae7e199de60a082`.
It contains 74,929 decision-prompt tokens, 1,027,272 FineWeb-Edu tokens and
336,377 Pleias tokens. Corpus text stays under `build/`.

Prepare it with the consumer's locked environment:

```sh
DEV=CPU ../typed-decisions-baseline/.env/bin/typed-decisions-run python tools/rust-port/readout-corpus.py \
  --project ../typed-decisions-baseline \
  --model ../typed-decisions-baseline/model-cache/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --cases "$HOME/data/decisions/synth_verified_reasoning_v1/train_00.jsonl" \
  --fineweb "$HOME/data/text/fineweb_edu.jsonl" --pleias "$HOME/data/text/pleias_synth.jsonl" \
  --out build/readout/corpus.json
```

Create `build/readout` first. The helper imports the consumer's prompt code;
input data and model files must already exist locally.

## Measurement

`tools/rust-port/readout-bench.py` tests single-document encoding, answer-letter
validation, buffer output, and batches of 32 and 1,024 text documents. Each
sample starts with a new tokenizer; tokenizer loading, output buffers and
answer-code preparation are outside timing. Lazy caches and worker creation
are inside timing. Each dataset is processed once per sample, in source order.
The digest includes every returned token and each document's token count.

Run the same benchmark script against isolated baseline and candidate wheels:

```sh
nix-shell -p util-linux --run 'taskset -c 8-15 build/test-env/bin/python tools/rust-port/readout-bench.py --corpus build/readout/corpus.json --out build/readout/run.json --repetitions 3'
```

Keep the compiler, Python, build profile and CPU affinity identical between
variants. The JSON stores raw timings, input/tokenizer/native-module hashes,
output digests and affinity. Alternate whole baseline and candidate processes
in ABBA/BAAB blocks; repeated samples within a process are not independent
observations. Compare complete digests before interpreting timings.

## Native batch dispatch

The Python adapter now uses the existing native worker pool for batches of
32–4,096 inputs totaling 1–64 MiB. The pool has at most four participants,
including the caller, and retains its workers between calls. Smaller batches
use the serial encoder. The core's measured cost model decides how much work
to distribute within the pool.

The owned Rust wrapper keeps the tokenizer alive until workers have joined,
reserves separate output buffers, retries short capacities once, and exposes
only initialized results. Python input snapshots remain alive across the
GIL release. Padding is applied after encoding, in original input order.
Forked Python processes use serial encoding for inherited tokenizers; a new
child-local tokenizer can create its own pool.

## Atlas results, 2026-10-20

Both variants use Rust 1.98.1, GCC 16.2.0 for native assembly, the `python`
profile (optimization level 3, thin LTO, one codegen unit, unwind), and the
default portable CPU target.
The baseline is `e16b816`. CPU affinity is 8–15. Test jobs finished before the
five ABBA/BAAB blocks ran. Each process has three samples per cell; times below
are means of block medians, with paired geometric-mean ratios. Ratios above
one favor the candidate. All observations are retained in
[the full receipt](receipts/readout-parallel-epyc9124.json).

| Workload | Method | Baseline ms | Candidate ms | Speedup |
| --- | --- | ---: | ---: | ---: |
| 256 decision prompts | encode | 1.36 | 1.43 | 0.95× |
| 256 decision prompts | encode into buffer | 1.08 | 1.08 | 0.99× |
| 256 decision prompts | full answer-letter validation | 3.11 | 3.08 | 1.01× |
| 1,024 FineWeb-Edu documents | single calls | 35.41 | 35.36 | 1.00× |
| 1,024 FineWeb-Edu documents | batches of 32 | 35.57 | 35.33 | 1.01× |
| 1,024 FineWeb-Edu documents | one batch | 33.70 | 21.80 | 1.55× |
| 1,024 Pleias documents | single calls | 18.07 | 18.07 | 1.00× |
| 1,024 Pleias documents | batches of 32 | 18.01 | 17.68 | 1.02× |
| 1,024 Pleias documents | one batch | 17.12 | 13.10 | 1.31× |

The initial encode-only estimate is sensitive to one candidate process whose
three samples were 1.99, 1.42 and 2.15 ms. No observations were discarded.
A decision-only follow-up used three further ABBA/BAAB blocks with 15 samples
per process and did not reproduce that loss:

| 256 decision prompts | Baseline ms | Candidate ms | Speedup |
| --- | ---: | ---: | ---: |
| encode | 1.36 | 1.34 | 1.01× |
| encode into buffer | 1.06 | 1.07 | 1.00× |
| full answer-letter validation | 3.09 | 3.07 | 1.01× |

The follow-up's encode ratios span 1.00–1.03×; these small differences do not
establish a readout speedup. Its [complete receipt](receipts/readout-decisions-epyc9124.json)
retains every timing and digest. Pass `--workload decisions --repetitions 15`
to reproduce that subset.

The large-batch ratios span 1.53–1.57× for FineWeb-Edu and 1.28–1.34× for
Pleias across the five blocks. The improvement uses additional CPU workers;
this is a preprocessing wall-time result, not a GPU training or inference
speedup. The corpus and host are fixed, so these small-block measurements do
not establish performance on other data or architectures.

## Correctness

All before/after token-stream digests match. A separate direct comparison with
Hugging Face tokenizers 0.23.2 matches all 2,304 inputs and 1,438,578 tokens.

Validation includes:

- Four new Rust tests: algorithm/flag parity, pool lifetime and thread transfer,
  error recovery and limits, and a normalization expansion requiring retry.
  The eight existing owned-API tests also pass.
- All 45 native C callers pass in automatic, scalar and both protected-page
  geometries. All 122 pinned tokenizer fixtures were available.
- Ten focused Python cases pass, including mutable inputs, Unicode and added
  tokens, order, left/right padding, supported truncation, extended encodings,
  concurrent callers and use after fork.
- The broad Python run passed 339 cases and skipped 44 optional cases. Its
  version check initially lacked installed package metadata; the installed-wheel
  version check plus the ten batch cases then passed together (11 checks).
- Wheel and source archive builds pass; the source archive includes the new
  Rust module.

## Integer-list follow-up

A warm profile of 256 repeated FineWeb-Edu batches on `e865559` attributed
23.06% of sampled user cycles to `Tokenizer::int_list` and 12.16% to list
destruction. Prefetching cached integer objects did not help in preliminary
measurements and was removed.

The retained change keeps the integer-cache slice and the private CPython
list's slot pointer outside the token loop. A borrowed handle copies each
cached object pointer before acquiring the list's owned reference. Each
output entry still owns a reference. List allocation remains before the
cache lock so cyclic GC can reenter the tokenizer; exact integer construction
cannot invoke callbacks or resize the private list. Other interpreter layouts
retain the existing list setter.

The same toolchain, corpus and affinity were used for four ABBA/BAAB blocks
against `e865559`, with seven samples per cell in each process. Tests and
builds finished before timing. All 1,008 timed samples, module hashes and output
digests are retained in [the receipt](receipts/readout-int-list-epyc9124.json).

Cargo's preserved build-script outputs identify GCC as the native-assembly
compiler for both this experiment and the earlier batch experiment. The
earlier Clang attribution recorded the available tool rather than the selected
compiler. Rebuilding `e865559` under the measured shell reproduced its native
module byte for byte. These measurements use `CC=gcc`. The Nix shell was
corrected to use Clang's stdenv before the C reference was retired.

| Workload | Method | Baseline ms | Candidate ms | Speedup |
| --- | --- | ---: | ---: | ---: |
| 256 decision prompts | encode | 1.379 | 1.359 | 1.014× |
| 256 decision prompts | encode into buffer | 1.082 | 1.089 | 0.994× |
| 256 decision prompts | full answer-letter validation | 3.102 | 2.970 | 1.044× |
| 1,024 FineWeb-Edu documents | single calls | 35.028 | 34.511 | 1.015× |
| 1,024 FineWeb-Edu documents | batches of 32 | 34.957 | 34.698 | 1.008× |
| 1,024 FineWeb-Edu documents | one batch | 21.706 | 21.432 | 1.013× |
| 1,024 Pleias documents | single calls | 17.676 | 17.641 | 1.002× |
| 1,024 Pleias documents | batches of 32 | 17.721 | 17.563 | 1.009× |
| 1,024 Pleias documents | one batch | 13.121 | 12.977 | 1.011× |

Answer-letter validation improves in all four blocks (1.022–1.072×). Plain
decision encoding and single-call Pleias results vary around parity. The
buffer path is unchanged in source and its small measured loss is included.
These are tokenizer timings on one host, not model inference latency.

All token-stream digests match. A fresh direct Hugging Face comparison again
matches all 2,304 Qwen inputs and 1,438,578 tokens. New regression checks verify
that repeated cached IDs acquire and release exactly one reference per list
entry, and that piece offsets beyond the vocabulary-sized cache match the
Hugging Face pre-tokenizer. The focused ownership, reentrancy, threading and
batch checks pass (22 tests).

The installed-wheel suite passes 344 tests with 43 skips for unsupported or
optional oracle cases. Its expected fork test emits one deprecation warning.

After the Nix compiler correction, a Clang-built candidate also passes those
22 focused checks and all nine Qwen output-digest checks against the same
Hugging Face oracle. All 30 API checks pass with the independently rebuilt
Clang C reference. Its timings were ignored because tests were running.

## DeepInfer reference

DeepSeek's [DeepInfer Q&A](https://github.com/deepseek-ai/DeepInfer/blob/main/doc/inference_deployment_qa.md)
and [recipe tokenizer](https://github.com/deepseek-ai/deepseek-recipe/blob/935817c66f5d6e64838f419692545f06787e485f/deepseek-recipe-encoding/src/tokenizer.rs)
separate template-inserted special tokens from ordinary text and batch-encode
the ordinary regions. The useful direction here is batching independent work.
Changing how the Qwen template recognizes special-token spellings would change
our input semantics and needs a separate compatibility evaluation.
