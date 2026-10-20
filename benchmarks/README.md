# Benchmark data

`corpora.json` pins the public corpus sources materialized by
`tools/bench/corpora.py`. `results/` retains the complete receipts supporting the
current [Qwen performance measurements](../docs/performance.md).

Receipts retain the measured source revisions, binary hashes, input/output
digests and timing observations. Local paths are normalized to placeholders:
`<tokenizer-checkout>`, `<consumer-checkout>`, `<model-cache>`, `<data-root>`,
`<home>` and `<nix-store>`. Different historical tokenizer worktrees share the
same placeholder; source revisions and hashes distinguish their builds.
These paths describe measurement provenance, not runnable commands.

Consumer application code and decision datasets are not distributed here.
Consumer measurements include application work such as JSON parsing, array
construction and prompt rendering; they are not native encoder throughput.
Corpus text and intermediate profiles stay under ignored `build/` directories.
