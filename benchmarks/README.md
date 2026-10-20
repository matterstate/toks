# Benchmark data

`corpora.json` pins the public corpus sources materialized by
`tools/bench/corpora.py`. `results/` retains the complete receipts supporting the
current [Qwen performance measurements](../docs/performance.md).

Receipts describe the source revisions and paths used at measurement time;
those historical paths are provenance, not commands for the current layout.
Corpus text and intermediate profiles stay under ignored `build/` directories.
