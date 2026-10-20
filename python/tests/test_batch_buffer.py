"""Flat batch output preserves IDs and never exposes partial writes on errors."""

from array import array
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise

import pytest
import toks
from conftest import tok_path
from test_regression import MODELS, SNAPSHOT


def encode(tokenizer: toks.Tokenizer, texts: list, **options) -> list[list[int]]:
    output = array("I", [0]) * sum(tokenizer.encode_bound(4 * len(text)) for text in texts)
    offsets = tokenizer.encode_batch_into(texts, output, **options)
    assert offsets[0] == 0
    assert len(offsets) == len(texts) + 1
    return [list(output[start:end]) for start, end in pairwise(offsets)]


@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("container", [str, lambda s: s.encode(), lambda s: bytearray(s.encode())])
def test_batch_buffer_matches_lists(gpt2: toks.Tokenizer, large: bool, container) -> None:
    texts = [container(f"Record {i}: café 中文 😀 <|endoftext|>\n" * (400 if large else 1)) for i in range(64)]
    texts += [container(""), container("a")]
    for options in ({}, {"add_special_tokens": False, "added_tokens": "none"}, {"continuation": True}):
        assert encode(gpt2, texts, **options) == gpt2.encode_batch(texts, **options)


def test_batch_buffer_capacity_errors_and_aliasing(gpt2: toks.Tokenizer) -> None:
    output = array("I", [0xFFFFFFFF]) * 8
    offsets = gpt2.encode_batch_into(["hello world " * 32], output)
    assert offsets[-1] > len(output)
    assert gpt2.encode_batch_into(["hello world " * 32], array("I")) == offsets
    assert list(output) == [0xFFFFFFFF] * 8
    with pytest.raises((TypeError, BufferError)):
        gpt2.encode_batch_into(["hello"], bytes(32))
    with pytest.raises(TypeError):
        gpt2.encode_batch_into(["hello"], array("d", [0]) * 8)
    with pytest.raises((ValueError, BufferError)):
        gpt2.encode_batch_into(["hello"], memoryview(output)[::2])
    with pytest.raises(ValueError, match="overlaps"):
        gpt2.encode_batch_into([memoryview(output).cast("B")], output)
    with pytest.raises(TypeError):
        gpt2.encode_batch_into(["hello", object()], output)
    with pytest.raises(TypeError):
        gpt2.encode_batch_into("hello", output)
    with pytest.raises(ValueError, match="4096"):
        gpt2.encode_batch_into([""] * 4097, output)
    assert list(output) == [0xFFFFFFFF] * 8
    assert gpt2.encode_batch_into([], output) == [0]
    assert gpt2.encode_batch_into(["", ""], output) == [0, 0, 0]
    assert list(output) == [0xFFFFFFFF] * 8


def test_batch_buffer_unaligned_output_and_tail(gpt2: toks.Tokenizer) -> None:
    texts = ["hello world", "é😀", ""]
    expected = gpt2.encode_batch(texts)
    count = sum(map(len, expected))
    storage = bytearray(b"\xff" * (4 * (count + 2) + 1))
    output = memoryview(storage)[1:].cast("i")
    offsets = gpt2.encode_batch_into(texts, output)
    assert [list(output[a:b]) for a, b in pairwise(offsets)] == expected
    assert storage[0] == 255
    assert list(output[count:]) == [-1, -1]


def test_batch_buffer_concurrent_callers(gpt2: toks.Tokenizer) -> None:
    texts = [f"Document {i}: hello world\n" * 1200 for i in range(40)]
    expected = gpt2.encode_batch(texts)
    with ThreadPoolExecutor(max_workers=3) as executor:
        assert list(executor.map(lambda _: encode(gpt2, texts), range(3))) == [expected] * 3


@pytest.mark.parametrize("name", MODELS)
def test_batch_buffer_frozen_outputs(name: str) -> None:
    tokenizer = toks.Tokenizer.from_file(tok_path(name))
    for case in MODELS[name]["encodings"]:
        options = {key: case[key] for key in ("added_tokens", "add_special_tokens")}
        expected = case["batch_ids"]
        output = array("I", [0]) * sum(map(len, expected))
        offsets = tokenizer.encode_batch_into(SNAPSHOT["texts"], output, **options)
        assert len(offsets) == len(expected) + 1
        assert offsets[-1] == len(output)
        assert [list(output[a:b]) for a, b in pairwise(offsets)] == expected
