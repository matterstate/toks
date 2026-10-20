# Validation

Rust is the only tokenizer implementation. The C tokenizer and its build,
mutation, fuzz-campaign and migration runners have been retired. The C ABI test
callers, shared assembly, layout declarations and pinned table data remain.
Historical C source and campaign commands are available in revision `17ec6e9`.

## Regression checks

`python/tests/data/regression.json` freezes outputs from the working Rust
revision `17ec6e9`, after its pinned external-oracle suite passed. The fixture
records tokenizer-file SHA-256 values, 270 single-input and 270 batch outputs,
135 piece-boundary sequences and 567 allocation bounds across nine models.
It covers BPE, WordPiece, Unigram, normalization, Unicode, added tokens,
templates and batch padding. The fixture distinguishes ALBERT's padded batch
outputs from single-input outputs.

Run the fast Python regression and boundary checks against an installed wheel:

```sh
build/python-env/bin/python -m pytest -q -p no:cacheprovider \
  python/tests/test_regression.py python/tests/test_api.py \
  python/tests/test_int_list.py python/tests/test_rust_boundary.py \
  python/tests/test_threads.py python/tests/test_batch.py
```

Build and installation commands are in [CI](ci.md). Missing local model fixtures
are reported as skips. CI fetches and verifies every pinned fixture before
testing; missing critical models fail the native gate.

Snapshots preserve behavior, including possible existing mistakes. The full
Python suite therefore also compares against pinned Hugging Face 0.23.2,
tiktoken and transformers oracles. Keep these independent checks when changing
tokenization semantics or updating model files. Review any snapshot change
against the external oracle, explain the change, and include its tokenizer hash
and baseline revision. The test suite has no automatic snapshot-update mode.

`make test`, `make test-scalar` and `make test-guard` exercise the Rust library
through the owned Rust API and C ABI, including allocation failures, malformed
inputs, forced hash collisions, concurrency and protected-page bounds. Recorded
loader-fuzz failures under `tests/fuzz/regress/` are replayed by `test_load`
against Rust. Retiring the old C campaigns does not imply Rust sanitizer or
coverage-guided fuzzing coverage.

## Performance canaries

Compare a candidate against a known-working Rust build using the same compiler,
profile, CPU target, host, affinity, tokenizer files and corpus. Keep frozen
token streams or their complete length-prefixed digests. Validate outputs
outside timing and reject mismatches before interpreting speed.

`tools/bench/compare.py --baseline <e2e> --candidate <e2e>` alternates native
Rust callers in ABBA/BAAB blocks. `--golden <golden.json>` also checks an existing
reviewed stream receipt. The [Qwen readout canary](performance.md) compares
isolated installed wheels and covers actual decision validation
and training-text preprocessing with complete output digests.

Report every measured cell and regression. Repeated samples in one process are
not independent observations; compare whole paired blocks. Shared CI runners
do not enforce timing thresholds. Controlled-host canaries establish tokenizer
wall time, not GPU training or end-to-end inference latency.
