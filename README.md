# toks

Matterstate's private Rust fork of [bitemyapp/toks](https://github.com/bitemyapp/toks),
derived from [Actual Computer's toks](https://github.com/actual-computer/toks).
The default branch is `main`.

A Rust tokenizer core with NEON/AVX2 assembly, an owned Rust API, a C ABI and a
PyO3 Python package. Reviewed snapshots and pinned external oracles check token
IDs and behavior. The core remains mostly unsafe Rust; the owned API manages
model and scratch lifetimes.

## Build and test

Enter the development environment with `nix-shell`, then run:

```sh
cargo build --locked --release
python3 tools/ci/fetch_tokenizers.py
tools/ci/test.sh
make test-guard
uv build --wheel python --python 3.13
```

`make` also copies the native libraries into `build/<os>-<isa>/` for C callers.
CI runs on Linux x86-64. Linux x86-64 and macOS arm64 have been exercised;
Windows support is incomplete. See [CI](docs/ci.md) for installed-wheel checks.

## Layout

| Path | Contents |
| --- | --- |
| `src/` | Rust library, owned API and worker pool |
| `native/` | Assembly, internal layout headers and pinned oracle data |
| `include/` | Public C ABI |
| `python/` | Python package, PyO3 crate and package tests |
| `tests/` | Rust integration tests, C ABI callers and fixtures |
| `tools/` | Validation, oracle and benchmark helpers |
| `benchmarks/` | Corpus manifest and current performance receipts |
| `docs/` | Current architecture, API, validation and performance guides |

See the [documentation index](docs/README.md), [Python API](python/README.md),
[tool guide](tools/README.md) and [contribution guide](CONTRIBUTING.md).
[Measured Qwen performance](docs/performance.md) covers decision scoring and
text preprocessing; it does not establish end-to-end inference throughput.

The code is Apache-2.0; see [LICENSE](LICENSE), [NOTICE](NOTICE),
[LICENSING.md](LICENSING.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
Inherited tags preserve their original licensing; `v0.3.2` is the upstream C
release, not a release of this Rust fork.
