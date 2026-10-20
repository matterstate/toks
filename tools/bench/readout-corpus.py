"""Freeze representative Qwen decision prompts and training-text inputs for readout-bench.py."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--fineweb", type=Path, required=True)
    parser.add_argument("--pleias", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project.resolve()))
    from decisions.engine import ReadoutPrompts, prompt_messages
    from decisions.evaluate import load_cases

    prompts = ReadoutPrompts.load(str(args.model.resolve()))
    cases, _ = load_cases(args.cases)
    rows = []
    for case in cases[:256]:
        question = case.request.questions[0]
        codes = prompts.codes[: len(question.values)]
        text = prompts.template.render(
            prompt_messages("ours", case.request.state, question, codes)
        )
        rows.append({"text": text, "codes": codes})
    corpus = {"model": str(args.model.resolve()), "decisions": rows}
    for name, path in (("fineweb_edu", args.fineweb), ("pleias_synth", args.pleias)):
        texts = []
        with path.open("rb") as source:
            for _ in range(4096):
                line = source.readline((1 << 20) + 1)
                if not line:
                    break
                if len(line) > 1 << 20:
                    raise ValueError(f"{path}: source row exceeds 1 MiB")
                text = json.loads(line)["text"]
                if 0 < len(text.encode()) <= 65536:
                    texts.append(text)
                if len(texts) == 1024:
                    break
        if len(texts) != 1024:
            raise ValueError(
                f"{path}: fewer than 1024 eligible documents in the first 4096 rows"
            )
        corpus[name] = texts
    source = json.dumps(corpus, ensure_ascii=False).encode()
    assert len(rows) <= 256
    assert len(source) <= 16 << 20
    args.out.write_bytes(source)
    print(
        json.dumps(
            {
                "sha256": hashlib.sha256(source).hexdigest(),
                "bytes": len(source),
                "counts": {
                    key: len(corpus[key])
                    for key in ("decisions", "fineweb_edu", "pleias_synth")
                },
            }
        )
    )


if __name__ == "__main__":
    main()
