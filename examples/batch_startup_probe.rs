use std::{error::Error, hint::black_box, time::Instant};
use toks::{ScratchOptions, Tier, Tokenizer};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        return Err("usage: batch_startup_probe TOKENIZER TRIALS".into());
    }
    let trials: u32 = args[2].parse()?;
    if !(1..=1000).contains(&trials) {
        return Err("trials must be in 1..1000".into());
    }
    let tokenizer = Tokenizer::from_file(&args[1], Tier::Auto)?;
    let mut samples_ns = Vec::with_capacity(trials as usize);
    for _ in 0..trials {
        let start = Instant::now();
        let pool = tokenizer.batch_encoder(ScratchOptions::default())?;
        let elapsed_ns = start.elapsed().as_nanos();
        black_box(&pool);
        samples_ns.push(elapsed_ns);
        drop(pool);
    }
    assert_eq!(samples_ns.len(), trials as usize);
    println!("{samples_ns:?}");
    Ok(())
}
