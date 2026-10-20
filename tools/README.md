# Tools

Run development commands in the repository's `nix-shell`.

- `ci/fetch_tokenizers.py` fetches and verifies pinned test fixtures.
- `ci/test.sh` runs native and scalar Rust checks. `ci/suites.py` rejects
  incomplete logs, zero reported counts and skipped critical tokenizers.
- `rust-port/test.py` compiles the C ABI callers against Rust; it does not build
  a C tokenizer.
- `rust-port/bench.py` and `rust-port/report.py` compare known-working and
  candidate Rust builds with complete output checks.
- `rust-port/readout-corpus.py` and `rust-port/readout-bench.py` prepare and
  measure the Qwen readout and training-text workloads.

See [validation](../docs/validation.md) for snapshot review and canary rules.

The upstream C release, mutation, Windows CI and README generation runners are
retired. Their last complete tree is `17ec6e9`. Historical reports, raw receipts,
charts, regression inputs and table parsers remain for auditability.

Older benchmark callers under `bench/` use pre-staged corpora. The default
`build/text` must match `bench/corpus.sha256`; `TOKS_BENCH_TEXT` selects a custom
directory whose actual hashes are recorded in receipts. Corpus files are never
downloaded or copied implicitly.

The optional `bench/gigatoken` comparator requires an independently supplied
source tree at `build/third-party/gigatoken`. Historical receipts used commit
`fac0114b37120ec8a76362e9ee8e1c742aaafaef`. That project requires nightly Rust,
Cargo's `-Z profile-rustflags` and a Python development environment for PyO3;
the normal library build and tests do not depend on it. Build its standalone
manifest with an appropriate toolchain and `CARGO_TARGET_DIR=build/giga-target`,
or supply an existing comparator with `GIGA_BIN` (`GIGA` for parallel runners).
Record the compiler, source revision and binary hashes when measuring it.
