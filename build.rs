use std::{env, fs};
fn main() {
    let isa = match env::var("CARGO_CFG_TARGET_ARCH").unwrap().as_str() {
        "aarch64" => "arm64",
        "x86_64" => "x86_64",
        a => panic!("unsupported architecture: {a}"),
    };
    let dir = format!("native/asm/{isa}");
    let mut asm = cc::Build::new();
    asm.include("native/core").include("include").include(&dir);
    for entry in fs::read_dir(&dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_some_and(|x| x == "S") {
            asm.file(path);
        }
    }
    if isa == "x86_64" && env::var_os("CARGO_FEATURE_AVX512").is_some() {
        asm.file("native/asm/experimental/k5_avx512.S")
            .file("native/asm/experimental/k6_avx512.S");
    }
    asm.compile("toks_asm");
    println!("cargo:rerun-if-changed=native/asm");
    println!("cargo:rerun-if-changed=native/core/layout.h");
}
