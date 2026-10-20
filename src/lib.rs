#![allow(dead_code)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(non_upper_case_globals)]
#![allow(unused_assignments)]
#![allow(unused_mut)]

extern crate libc;

mod safe;
pub use safe::BatchEncoder;
pub use safe::{
    AddedToken, DecodeFlags, Decoder, EncodeFlags, Encoder, Error, Info, ScratchOptions, Template,
    Tier, Tokenizer,
};

mod core;
mod gen;
mod par;

mod atomic;
#[cfg(feature = "test-guard")]
mod guard;
mod platform;

/// Bring a valid table/cache line into the read cache before its queued lookup.
#[inline(always)]
unsafe fn prefetch_read(p: *const u8) {
    #[cfg(target_arch = "x86_64")]
    std::arch::x86_64::_mm_prefetch::<{ std::arch::x86_64::_MM_HINT_T0 }>(p.cast());
    #[cfg(target_arch = "aarch64")]
    std::arch::asm!("prfm pldl1keep, [{p}]", p = in(reg) p, options(readonly, nostack, preserves_flags));
}

/// Stack storage whose alignment is part of the assembly ABI.
#[repr(C, align(64))]
struct Aligned<T>(T);
impl<T> std::ops::Deref for Aligned<T> {
    type Target = T;
    fn deref(&self) -> &T {
        &self.0
    }
}
impl<T> std::ops::DerefMut for Aligned<T> {
    fn deref_mut(&mut self) -> &mut T {
        &mut self.0
    }
}
#[inline]
fn test_hash<T: Default>(value: T) -> T {
    if cfg!(feature = "test-degenerate") {
        T::default()
    } else {
        value
    }
}

/// Observe a word in caller-owned scratch that may not have been initialized yet.
///
/// The C ABI accepts a malloc buffer on the first scratch_init and rejects
/// unbound buffers in encode. An ordinary Rust integer load would propagate
/// uninitialized bytes into LLVM poison. An assembly output instead supplies an
/// arbitrary, defined integer, matching the hardware observation of the C ABI.
/// No reference to uninitialized storage is formed. The caller must ensure all
/// eight bytes are readable. This is used only until scratch binding is checked.
#[inline]
unsafe fn raw_header_word(p: *const u64) -> u64 {
    let v: u64;
    #[cfg(target_arch = "aarch64")]
    std::arch::asm!("ldr {v}, [{p}]", v = out(reg) v, p = in(reg) p, options(readonly, nostack, preserves_flags));
    #[cfg(target_arch = "x86_64")]
    std::arch::asm!("mov {v}, [{p}]", v = out(reg) v, p = in(reg) p, options(readonly, nostack, preserves_flags));
    v
}
