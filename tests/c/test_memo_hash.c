/* Forced collisions in the Rust test-degenerate build: test_memo.inc. */
#define TOKS_TEST_DEGEN(x) ((x) & 0u)               /* core.h; every piece cache one bucket too */
#define MT_DEGEN 1
#include "core.h"
#define MT_NAME "test_memo_hash"
#include "test_memo.inc"
