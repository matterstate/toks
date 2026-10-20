# Tools

Run development commands in the repository's `nix-shell`.

| Tool | Purpose |
| --- | --- |
| `ci/fetch_tokenizers.py` | Fetch and verify pinned tokenizer fixtures |
| `ci/test.sh` | Native/scalar checks and complete-log validation |
| `ci/test-native.py` | Compile C ABI callers against Rust and record results |
| `bench/corpora.py` | Materialize frozen public benchmark corpora |
| `bench/compare.py`, `bench/report.py` | Paired Rust baseline/candidate comparisons |
| `bench/readout-corpus.py`, `bench/readout-bench.py` | Qwen readout and training-text workloads |
| `oracle/unigram.py` | Compare Rust with the pinned HF Unigram oracle |
| `gen/` | Regenerate pinned native test data and ABI includes |

See [validation](../docs/validation.md), [performance](../docs/performance.md)
and [CI](../docs/ci.md) for supported workflows.

Other native benchmark callers require explicitly staged corpora and, where
applicable, external comparator binaries. They are optional diagnostics rather
than CI dependencies. Their output is local build data; generated reports
should be written under `build/` and only reviewed measurements retained in
`benchmarks/results/`.
