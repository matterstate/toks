"""Large training batches preserve serial IDs, ordering and Python ownership."""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import tokenizers
import toks


@pytest.mark.parametrize(
    "container",
    [
        str,
        lambda text: text.encode(),
        lambda text: bytearray(text.encode()),
        lambda text: memoryview(text.encode()),
    ],
)
def test_large_batch_matches_serial(
    gpt2: toks.Tokenizer, container: Callable[[str], object]
) -> None:
    texts = [
        f"Record {index}: café 中文 😀 <|endoftext|>\n" * 400 for index in range(64)
    ]
    inputs = [container(text) for text in texts]
    assert sum(len(text.encode()) for text in texts) > 1 << 20
    for options in (
        {},
        {"add_special_tokens": False, "added_tokens": "none"},
        {"continuation": True},
    ):
        expected = [gpt2.encode(text, **options) for text in inputs]
        assert gpt2.encode_batch(inputs, **options) == expected
        assert [
            encoding.ids for encoding in gpt2.encode_batch_ex(inputs, **options)
        ] == expected


@pytest.mark.parametrize("direction", ["Left", "Right"])
@pytest.mark.parametrize("padding", ["BatchLongest", {"Fixed": 32}])
def test_large_batch_padding_truncation_against_hugging_face(
    gpt2_path: str, direction: str, padding: str | dict[str, int]
) -> None:
    definition = json.loads(Path(gpt2_path).read_text())
    definition["padding"] = {
        "strategy": padding,
        "direction": direction,
        "pad_to_multiple_of": 8,
        "pad_id": 50256,
        "pad_type_id": 0,
        "pad_token": "<|endoftext|>",
    }
    definition["truncation"] = {
        "direction": "Right",
        "max_length": 24,
        "strategy": "LongestFirst",
        "stride": 0,
    }
    source = json.dumps(definition)
    tokenizer = toks.Tokenizer.from_str(source)
    oracle = tokenizers.Tokenizer.from_str(source)
    texts = [f"Document {index}: hello world\n" * 1200 for index in range(40)] + [
        "",
        "hello",
    ]
    assert sum(len(text.encode()) for text in texts) > 1 << 20
    expected = oracle.encode_batch(texts, add_special_tokens=False)
    assert tokenizer.encode_batch(texts, add_special_tokens=False) == [
        encoding.ids for encoding in expected
    ]
    actual = tokenizer.encode_batch_ex(texts, add_special_tokens=False)
    for left, right in zip(actual, expected, strict=True):
        assert left.ids == right.ids
        assert left.attention_mask == right.attention_mask
        assert left.type_ids == right.type_ids
        assert left.special_tokens_mask == right.special_tokens_mask


def test_shared_large_batch_pool_concurrent_callers_and_errors(
    gpt2: toks.Tokenizer,
) -> None:
    batches = [
        [f"Batch {batch}, row {index}: hello world\n" * 600 for index in range(64)]
        for batch in range(3)
    ]
    expected = [
        [gpt2.encode(text, add_special_tokens=False) for text in batch]
        for batch in batches
    ]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(
                lambda texts: gpt2.encode_batch(texts, add_special_tokens=False),
                batches,
            )
        )
    assert results == expected
    with pytest.raises(TypeError):
        gpt2.encode_batch(batches[0] + [object()])
    assert gpt2.encode_batch(batches[0], add_special_tokens=False) == expected[0]


def test_inherited_batch_pool_after_fork(gpt2_path: str) -> None:
    import multiprocessing

    context = multiprocessing.get_context("fork")
    tokenizer = toks.Tokenizer.from_file(gpt2_path)
    texts = [f"Document {index}: hello world\n" * 1200 for index in range(40)]
    expected = tokenizer.encode_batch(texts, add_special_tokens=False)
    receiving, sending = context.Pipe(duplex=False)

    def child() -> None:
        nonlocal tokenizer
        try:
            assert tokenizer.encode_batch(texts, add_special_tokens=False) == expected
            tokenizer = None
            sending.send(True)
        finally:
            sending.close()

    process = context.Process(target=child)
    process.start()
    sending.close()
    try:
        assert receiving.poll(15), "inherited worker pool blocked the child"
        assert receiving.recv() is True
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
        process.join(timeout=5)
        receiving.close()
