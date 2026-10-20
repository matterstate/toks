"""Ownership and uncached values in native integer-list construction."""

import sys

import pytest


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="CPython reference counts"
)
def test_cached_integer_list_owns_each_reference(gpt2):
    token = gpt2.encode("Hello")[0]
    assert token == 15496
    references = sys.getrefcount(token)
    output = gpt2.encode("Hello world\n" * 128)
    occurrences = output.count(token)
    assert occurrences == 128
    assert all(value is token for value in output if value == token)
    assert sys.getrefcount(token) == references + occurrences
    del output
    assert sys.getrefcount(token) == references


def test_piece_offsets_beyond_integer_cache(gpt2, gpt2_path):
    tokenizers = pytest.importorskip("tokenizers")
    text = "hello " * 10000
    oracle = tokenizers.Tokenizer.from_file(gpt2_path).pre_tokenizer.pre_tokenize_str(
        text
    )
    expected = [end for _, (_, end) in oracle]
    assert expected[-1] > gpt2.n_vocab
    assert gpt2.pieces(text) == expected
