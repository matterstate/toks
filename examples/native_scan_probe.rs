use std::{error::Error, fs::File, hint::black_box, io::Read, time::Instant};
use toks::{EncodeFlags, ScratchOptions, Tier, Tokenizer};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    if !(5..=7).contains(&args.len()) {
        return Err(
            "usage: native_scan_probe TOKENIZER CORPUS encode|pieces PASSES [MEMO_MIB] [auto|scalar|avx2|avx512]".into(),
        );
    }
    let mut source = Vec::new();
    File::open(&args[2])?
        .take((16 << 20) + 1)
        .read_to_end(&mut source)?;
    if source.len() > 16 << 20 {
        return Err("corpus exceeds 16 MiB".into());
    }
    let passes: u32 = args[4].parse()?;
    if !(1..=1000).contains(&passes) {
        return Err("passes must be in 1..1000".into());
    }
    if !["encode", "pieces"].contains(&args[3].as_str()) {
        return Err("mode must be encode or pieces".into());
    }
    let memo_mib: u16 = args.get(5).map_or(Ok(4), |value| value.parse())?;
    if memo_mib > 128 {
        return Err("memo budget exceeds 128 MiB".into());
    }
    let tier = match args.get(6).map_or("avx2", String::as_str) {
        "auto" => Tier::Auto,
        "scalar" => Tier::Scalar,
        "avx2" => Tier::Avx2,
        "avx512" => Tier::Avx512,
        _ => return Err("invalid CPU tier".into()),
    };
    let mut texts = Vec::new();
    let mut position = 0usize;
    while position < source.len() {
        let header = source
            .get(position..position + 4)
            .ok_or("truncated length")?;
        let length = u32::from_le_bytes(header.try_into()?) as usize;
        position += 4;
        let text = source
            .get(position..position + length)
            .ok_or("truncated text")?;
        texts.push(text);
        position += length;
        if texts.len() > 4096 {
            return Err("corpus exceeds 4096 texts".into());
        }
    }
    assert_eq!(position, source.len());
    if texts.is_empty() {
        return Err("corpus has no texts".into());
    }
    let tokenizer = Tokenizer::from_file(&args[1], tier)?;
    let mut outputs = vec![Vec::new(); texts.len()];
    let flags = EncodeFlags::NO_POSTPROCESS;
    let start = Instant::now();
    for _ in 0..passes {
        let mut encoder = tokenizer.encoder(ScratchOptions {
            memo_mib: Some(memo_mib),
            cache_mib: 0,
        })?;
        for (text, output) in texts.iter().zip(&mut outputs) {
            if args[3] == "encode" {
                encoder.encode_to(text, flags, output)?;
            } else {
                encoder.pieces_to(text, EncodeFlags::ALL, output)?;
            }
            black_box(&output);
        }
    }
    let elapsed = start.elapsed().as_nanos();
    let mut digest = 0xcbf29ce484222325u64;
    let mut count = 0u64;
    for output in &outputs {
        count += output.len() as u64;
        for value in std::iter::once(output.len() as u32).chain(output.iter().copied()) {
            for byte in value.to_le_bytes() {
                digest = (digest ^ u64::from(byte)).wrapping_mul(0x100000001b3);
            }
        }
    }
    println!("mode={} passes={passes} texts={} source_bytes={} values={count} elapsed_ns={elapsed} digest={digest:016x}", args[3], texts.len(), source.len());
    Ok(())
}
