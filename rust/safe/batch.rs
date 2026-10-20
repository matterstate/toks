use super::{capacity, count, reserve, EncodeFlags, Error, ScratchOptions, Tokenizer};
use crate::src::par::par;
use std::ptr::{self, NonNull};

/// An owned batch worker pool. Calls require exclusive access; the pool keeps
/// the immutable tokenizer alive until all workers have been joined.
pub struct BatchEncoder {
    pointer: NonNull<par::toks_par>,
    tokenizer: Tokenizer,
    process_id: u32,
}

// Moving an idle pool transfers ownership; workers only access its arena.
unsafe impl Send for BatchEncoder {}

impl Tokenizer {
    pub fn batch_encoder(&self, options: ScratchOptions) -> Result<BatchEncoder, Error> {
        let mut pointer = ptr::null_mut();
        count(unsafe { par::toks_par_create(&mut pointer, self.ptr(), 0, options.bits()?) })?;
        let pointer = NonNull::new(pointer).ok_or_else(|| Error::new(-11))?;
        Ok(BatchEncoder {
            pointer,
            tokenizer: self.clone(),
            process_id: std::process::id(),
        })
    }
}

impl BatchEncoder {
    pub const TEXTS_MAX: usize = 4096;
    pub const BYTES_MAX: usize = 64 << 20;

    pub fn encode(&mut self, texts: &[&[u8]], flags: EncodeFlags) -> Result<Vec<Vec<u32>>, Error> {
        if self.process_id != std::process::id() {
            return Err(Error::new(-10));
        }
        if texts.len() > Self::TEXTS_MAX {
            return Err(Error::new(-9));
        }
        let mut size_bytes = 0usize;
        for text in texts {
            size_bytes = size_bytes
                .checked_add(text.len())
                .ok_or_else(|| Error::new(-9))?;
            if size_bytes > Self::BYTES_MAX {
                return Err(Error::new(-9));
            }
        }
        assert!(texts.len() <= Self::TEXTS_MAX);
        assert!(size_bytes <= Self::BYTES_MAX);
        let mut outputs = Vec::new();
        let mut items = Vec::new();
        reserve(&mut outputs, texts.len())?;
        reserve(&mut items, texts.len())?;
        for text in texts {
            let mut output = Vec::<u32>::new();
            let bound = capacity(self.tokenizer.encode_bound(text.len() as u64))?;
            reserve(&mut output, bound.min(text.len().saturating_add(64)))?;
            items.push(par::toks_par_item {
                text: text.as_ptr().cast(),
                len: text.len() as u64,
                out: output.as_mut_ptr(),
                cap: output.capacity() as u64,
                n: 0,
            });
            outputs.push(output);
        }
        for _ in 0..2 {
            count(unsafe {
                par::toks_par_encode_batch(
                    self.pointer.as_ptr(),
                    items.as_mut_ptr(),
                    items.len() as u64,
                    flags.bits(),
                )
            })?;
            let mut complete = true;
            for (item, output) in items.iter_mut().zip(&mut outputs) {
                let written = count(item.n)?;
                if written > output.capacity() {
                    reserve(output, written)?;
                    item.out = output.as_mut_ptr();
                    item.cap = output.capacity() as u64;
                    complete = false;
                }
            }
            if complete {
                for (item, output) in items.iter().zip(&mut outputs) {
                    let written = count(item.n)?;
                    assert!(written <= output.capacity());
                    // Each worker initialized exactly this prefix. No vector
                    // exposes a partial result if any item failed.
                    unsafe { output.set_len(written) };
                }
                return Ok(outputs);
            }
        }
        Err(Error::new(-8))
    }
}

impl Drop for BatchEncoder {
    fn drop(&mut self) {
        // A forked child has no copies of the worker threads to join. Its
        // inherited arena is reclaimed by the OS when the child exits.
        if self.process_id == std::process::id() {
            unsafe { par::toks_par_destroy(self.pointer.as_ptr()) };
        }
    }
}
