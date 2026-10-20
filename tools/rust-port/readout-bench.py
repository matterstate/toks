"""Measure Qwen readout validation and batched training-text tokenization."""

import argparse
import array
import hashlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

import toks
import toks._toks as native


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--workload",
        choices=("decisions", "fineweb_edu", "pleias_synth"),
        action="append",
    )
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 31:
        parser.error("repetitions must be 1..31")
    with args.corpus.open("rb") as file:
        source = file.read((16 << 20) + 1)
    if len(source) > 16 << 20:
        parser.error("corpus exceeds 16 MiB")
    corpus = json.loads(source)
    directory = Path(corpus["model"])
    definition = json.loads((directory / "tokenizer.json").read_bytes())
    config = json.loads((directory / "tokenizer_config.json").read_bytes())
    fields = ("content", "single_word", "lstrip", "rstrip", "normalized", "special")
    present = {token["content"] for token in definition["added_tokens"]}
    for key, token in sorted(
        config.get("added_tokens_decoder", {}).items(), key=lambda item: int(item[0])
    ):
        if token["content"] not in present:
            definition["added_tokens"].append(
                {"id": int(key), **{field: token[field] for field in fields}}
            )
            present.add(token["content"])
    definition = json.dumps(definition)
    rows = []
    for name in args.workload or ("decisions", "fineweb_edu", "pleias_synth"):
        texts = corpus[name]
        if not 1 <= len(texts) <= 1024:
            parser.error(f"{name} must contain 1..1024 inputs")
        methods = (
            ("encode", "encode_into", "validate")
            if name == "decisions"
            else ("encode", "batch32", "batch1024")
        )
        for method in methods:
            samples, digests = [], []
            for _ in range(args.repetitions):
                tokenizer = toks.Tokenizer.from_str(definition)
                digest = hashlib.sha256()
                values = (
                    [row["text"] for row in texts] if name == "decisions" else texts
                )
                output = array.array("I", [0]) * tokenizer.encode_bound(
                    max(len(text.encode()) for text in values)
                )
                code_ids = (
                    {
                        code: tokenizer.encode(code, add_special_tokens=False)[0]
                        for row in texts
                        for code in row["codes"]
                    }
                    if method == "validate"
                    else {}
                )
                start = time.perf_counter_ns()
                if method.startswith("batch"):
                    count = int(method[5:])
                    results = []
                    for first in range(0, len(values), count):
                        results.extend(
                            tokenizer.encode_batch(
                                values[first : first + count], add_special_tokens=False
                            )
                        )
                elif method == "encode_into":
                    results = []
                    for text in values:
                        count = tokenizer.encode_into(
                            text, output, add_special_tokens=False
                        )
                        results.append(output[:count])
                else:
                    results = []
                    for index, text in enumerate(values):
                        ids = tokenizer.encode(text, add_special_tokens=False)
                        if method == "validate":
                            for code in texts[index]["codes"]:
                                if tokenizer.encode(
                                    text + code, add_special_tokens=False
                                ) != ids + [code_ids[code]]:
                                    raise ValueError(
                                        f"answer code {code!r} changed tokenization"
                                    )
                        results.append(ids)
                samples.append(time.perf_counter_ns() - start)
                for ids in results:
                    digest.update(len(ids).to_bytes(8, "little"))
                    digest.update(array.array("I", ids).tobytes())
                digests.append(digest.hexdigest())
            assert len(set(digests)) == 1
            rows.append(
                {
                    "workload": name,
                    "method": method,
                    "documents": len(values),
                    "bytes": sum(len(text.encode()) for text in values),
                    "tokens": sum(len(ids) for ids in results),
                    "sha256": digests[0],
                    "samples_ns": samples,
                    "median_ns": statistics.median(samples),
                }
            )
            print(json.dumps(rows[-1]), flush=True)
    report = {
        "host": platform.platform(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "corpus_sha256": hashlib.sha256(source).hexdigest(),
        "tokenizer_sha256": hashlib.sha256(definition.encode()).hexdigest(),
        "module_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "protocol": "fresh tokenizer per sample; loading and output validation outside timing; ordered stream",
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
