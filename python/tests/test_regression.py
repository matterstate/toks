"""Reviewed outputs from a known-working Rust revision, independent of the C implementation."""

import array
import hashlib
import json
from pathlib import Path

import pytest
import toks
from conftest import tok_path

SNAPSHOT = json.loads((Path(__file__).parent / "data/regression.json").read_bytes())
MODEL_NAMES = (
    "gpt2",
    "llama3",
    "qwen38",
    "gemma4",
    "o200k",
    "wp-bert-uncased",
    "uni_t5base",
    "uni_albert",
    "dg-exaone35",
)
MODELS = {model["name"]: model for model in SNAPSHOT["models"]}
assert len(SNAPSHOT["models"]) == len(MODEL_NAMES)
assert set(MODELS) == set(MODEL_NAMES)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_frozen_tokenizer_outputs(name):
    model = MODELS[name]
    path = tok_path(model["name"])
    assert SNAPSHOT["schema"] == 1
    assert (
        hashlib.sha256(Path(path).read_bytes()).hexdigest() == model["tokenizer_sha256"]
    )
    assert {
        (case["added_tokens"], case["add_special_tokens"])
        for case in model["encodings"]
    } == {
        (mode, special)
        for mode in ("all", "nonspecial", "none")
        for special in (False, True)
    }
    tokenizer = toks.Tokenizer.from_file(path)
    for count, expected in zip(SNAPSHOT["lengths"], model["bounds"], strict=True):
        assert tokenizer.encode_bound(count) == expected, (model["name"], count)
    for case in model["encodings"]:
        options = {key: case[key] for key in ("added_tokens", "add_special_tokens")}
        for text, expected in zip(SNAPSHOT["texts"], case["ids"], strict=True):
            assert tokenizer.encode(text, **options) == expected, (
                model["name"],
                text,
                options,
            )
        assert tokenizer.encode_batch(SNAPSHOT["texts"], **options) == case["batch_ids"]
    for case in model["pieces"]:
        for text, expected in zip(SNAPSHOT["texts"], case["ends"], strict=True):
            assert tokenizer.pieces(text, added_tokens=case["added_tokens"]) == expected


@pytest.mark.parametrize(
    "name",
    ("gpt2", "llama3", "qwen38", "dg-exaone35", "uni_t5base", "uni_albert", "gemma4"),
)
def test_encode_bound_covers_outputs(name):
    tokenizer = toks.Tokenizer.from_file(tok_path(name))
    texts = (
        "\ufdfa" * 64,
        "\U0001d160" * 64,
        "\u00e9\u0301 \u2460\u2474" * 50,
        " " * 777 + "x",
        "1 2 3 " * 300,
    )
    for text in texts:
        ids = tokenizer.encode(text)
        bound = tokenizer.encode_bound(len(text.encode()))
        assert len(ids) <= bound
        output = array.array("I", [0]) * bound
        count = tokenizer.encode_into(text, output)
        assert count == len(ids)
        assert list(output[:count]) == ids
