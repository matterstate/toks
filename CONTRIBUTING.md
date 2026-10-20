# Contributing

Changes to this private fork target `main` in `matterstate/toks`. Keep each
change focused and preserve upstream authorship and notices. Contributions to
this fork use Apache-2.0; this fork adds no separate relicensing grant.

## Validation

Run commands in the Nix shell described in [README.md](README.md).

```sh
python3 tools/ci/fetch_tokenizers.py
tools/ci/test.sh
make test-guard
```

For Python binding changes, build the wheel and run the fast installed-wheel
regressions in [validation](docs/validation.md). Core, kernel and tokenizer-file
changes also need the full oracle suite described in [CI](docs/ci.md); CI runs
that suite on every push. Report failures and missing optional fixtures.

Supported tokenizers must match the reviewed regression snapshots and pinned
Hugging Face oracle. Investigate changed IDs before merging; never automatically
refresh snapshots from the candidate. See [validation](docs/validation.md).

A performance claim needs paired measurements: host, load, tokenizer, corpus,
chunk size, cache state, build flags, commands and complete results. Keep
correctness checks outside timed sections and report regressions too.

Use a known-working Rust revision for performance comparisons. Update
`include/toks.h` and its ABI version when changing the public C ABI.
