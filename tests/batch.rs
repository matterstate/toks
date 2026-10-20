use toks::{BatchEncoder, EncodeFlags as F, ScratchOptions, Tier, Tokenizer};

#[test]
fn batch_matches_serial_across_algorithms_and_flags() {
    let models: &[&[u8]] = &[
        include_bytes!("data/compile/nosplit.json"),
        include_bytes!("data/spm/llamalike.json"),
        include_bytes!("data/unigram/bound_bf_meta.json"),
        br###"{"pre_tokenizer":{"type":"BertPreTokenizer"},"decoder":{"type":"WordPiece","prefix":"##","cleanup":true},"model":{"type":"WordPiece","unk_token":"[UNK]","continuing_subword_prefix":"##","max_input_chars_per_word":100,"vocab":{"[UNK]":0,"hello":1,"world":2,"a":3}}}"###,
    ];
    let texts: Vec<_> = (0..96)
        .map(|index| format!("hello world {index}: café 中文 😀\n").repeat(index))
        .collect();
    let mut inputs: Vec<_> = texts.iter().map(String::as_bytes).collect();
    inputs.extend([b"\xff\0\xf0\x9f".as_slice(), b"".as_slice()]);
    for model in models {
        for tier in [Tier::Auto, Tier::Scalar] {
            let tokenizer = Tokenizer::from_bytes(model, tier).unwrap();
            let mut serial = tokenizer.encoder(ScratchOptions::default()).unwrap();
            let mut batch = tokenizer.batch_encoder(ScratchOptions::default()).unwrap();
            for flags in [
                F::ALL,
                F::NONSPECIAL,
                F::NONE,
                F::NO_POSTPROCESS,
                F::CONTINUATION,
                F::NO_PAD,
            ] {
                let expected: Vec<_> = inputs
                    .iter()
                    .map(|text| serial.encode(text, flags).unwrap())
                    .collect();
                assert_eq!(batch.encode(&inputs, flags).unwrap(), expected);
                assert_eq!(batch.encode(&inputs, flags).unwrap(), expected);
            }
        }
    }
}

#[test]
fn batch_outlives_tokenizer_and_can_move_between_threads() {
    let tokenizer =
        Tokenizer::from_bytes(include_bytes!("data/compile/nosplit.json"), Tier::Auto).unwrap();
    let mut batch = tokenizer.batch_encoder(ScratchOptions::default()).unwrap();
    drop(tokenizer);
    let mut batch = std::thread::spawn(move || {
        assert_eq!(
            batch.encode(&[b"hi", b""], F::ALL).unwrap(),
            [vec![104, 105], vec![]]
        );
        batch
    })
    .join()
    .unwrap();
    assert_eq!(batch.encode(&[b"hi"], F::ALL).unwrap(), [vec![104, 105]]);
}

#[test]
fn batch_rejects_limits_and_invalid_flags_then_recovers() {
    let tokenizer =
        Tokenizer::from_bytes(include_bytes!("data/compile/nosplit.json"), Tier::Scalar).unwrap();
    let mut batch = tokenizer.batch_encoder(ScratchOptions::default()).unwrap();
    assert_eq!(
        batch
            .encode(&vec![b"".as_slice(); BatchEncoder::TEXTS_MAX + 1], F::ALL)
            .unwrap_err()
            .code,
        -9
    );
    let text = vec![b'a'; 65536];
    let texts = vec![text.as_slice(); BatchEncoder::BYTES_MAX / text.len() + 1];
    assert_eq!(batch.encode(&texts, F::ALL).unwrap_err().code, -9);
    assert_eq!(
        batch
            .encode(&[b"a"], F::from_bits(u32::MAX))
            .unwrap_err()
            .code,
        -10
    );
    assert!(batch.encode(&[], F::ALL).unwrap().is_empty());
    assert_eq!(batch.encode(&[b"a"], F::ALL).unwrap(), [vec![97]]);
}

#[test]
fn batch_retries_when_normalization_exceeds_initial_capacity() {
    let source = std::str::from_utf8(include_bytes!("data/compile/nosplit.json"))
        .unwrap()
        .replace(
            "\"normalizer\": null",
            "\"normalizer\": {\"type\":\"NFKC\"}",
        );
    let tokenizer = Tokenizer::from_bytes(source.as_bytes(), Tier::Scalar).unwrap();
    let text = "ﷺ".repeat(64);
    let mut serial = tokenizer.encoder(ScratchOptions::default()).unwrap();
    let expected = serial.encode(text.as_bytes(), F::ALL).unwrap();
    assert!(expected.len() > text.len() + 64);
    let mut batch = tokenizer.batch_encoder(ScratchOptions::default()).unwrap();
    assert_eq!(
        batch.encode(&[b"", text.as_bytes()], F::ALL).unwrap(),
        [vec![], expected]
    );
}
