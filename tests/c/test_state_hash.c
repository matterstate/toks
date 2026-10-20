/* Forced collisions across all Rust caches: test_state.inc. */
#define TOKS_TEST_DEGEN(x) ((x) & 0u)
#include "core.h"
#define ST_NAME "test_state_hash"
#define ST_DEGEN 1
#include "test_state.inc"
