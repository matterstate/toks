# Qwen readout tokenization

The consumer is `typed-decisions`: Qwen3.5-4B decision scoring and text-training
preprocessing on Atlas (AMD EPYC 9124, Linux x86-64, CPython 3.13). These checks
load tokenizer files only. They do not load model weights or use the GPU.

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

## DeepInfer reference

DeepSeek's [DeepInfer Q&A](https://github.com/deepseek-ai/DeepInfer/blob/main/doc/inference_deployment_qa.md)
and [recipe tokenizer](https://github.com/deepseek-ai/deepseek-recipe/blob/935817c66f5d6e64838f419692545f06787e485f/deepseek-recipe-encoding/src/tokenizer.rs)
separate template-inserted special tokens from ordinary text and batch-encode
the ordinary regions. The useful direction here is batching independent work.
Changing how the Qwen template recognizes special-token spellings would change
our input semantics and needs a separate compatibility evaluation.
