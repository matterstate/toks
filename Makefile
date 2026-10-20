.DEFAULT_GOAL := lib
CARGO ?= cargo
PYTHON ?= python3
JOBS ?= 8
CARGO_TARGET_DIR ?= target
RUST_TARGET ?=
FEATURES ?=
MACHINE := $(if $(RUST_TARGET),$(RUST_TARGET),$(shell uname -m))
OS := $(if $(RUST_TARGET),$(if $(findstring darwin,$(RUST_TARGET)),macos,linux),$(if $(filter Darwin,$(shell uname -s)),macos,linux))
ISA := $(if $(filter arm64% aarch64%,$(MACHINE)),arm64,x86_64)
BUILD_DIR ?= build/$(OS)-$(ISA)
RUST_FLAGS := $(if $(RUST_TARGET),--target $(RUST_TARGET)) $(if $(FEATURES),--features $(FEATURES))
RUST_OUT := $(CARGO_TARGET_DIR)/$(if $(RUST_TARGET),$(RUST_TARGET)/)release
SHLIB := $(if $(filter macos,$(OS)),libtoks.dylib,libtoks.so)
TEST_FLAGS := $(if $(findstring avx512,$(FEATURES)),--avx512)
COMMA := ,

ifneq ($(TARGET),)
$(error Use RUST_TARGET=<Rust triple> for cross builds)
endif
ifneq ($(findstring windows,$(RUST_TARGET)),)
$(error The OS and worker-pool port currently supports macOS and Linux)
endif

.PHONY: all lib test test-scalar test-guard asm asmcheck clean
all: lib
lib:
	$(CARGO) build --locked --release -p toks --target-dir $(CARGO_TARGET_DIR) $(RUST_FLAGS)
	@mkdir -p $(BUILD_DIR)
	cp $(RUST_OUT)/libtoks.a $(RUST_OUT)/$(SHLIB) $(BUILD_DIR)/

test: lib asmcheck
	$(CARGO) test --locked --release -p toks --lib --tests --target-dir $(CARGO_TARGET_DIR) $(RUST_FLAGS)
	$(PYTHON) tools/ci/test-native.py --lib $(BUILD_DIR)/libtoks.a --out $(BUILD_DIR)/tests --jobs $(JOBS) --print-logs $(TEST_FLAGS)

test-scalar:
	TOKS_TIER=scalar $(MAKE) test

test-guard:
	$(CARGO) rustc --locked -p toks --lib --crate-type staticlib --release --features test-guard$(if $(FEATURES),$(COMMA)$(FEATURES)) --target-dir $(BUILD_DIR)/guard
	$(PYTHON) tools/ci/test-native.py --guard 1 --lib $(BUILD_DIR)/guard/release/libtoks.a --out $(BUILD_DIR)/guard1 --jobs $(JOBS) --print-logs $(TEST_FLAGS)
	$(PYTHON) tools/ci/test-native.py --guard 2 --lib $(BUILD_DIR)/guard/release/libtoks.a --out $(BUILD_DIR)/guard2 --jobs $(JOBS) --print-logs $(TEST_FLAGS)

CPPFLAGS := -Iinclude -Inative/core -Inative/platform
ASM_CC ?= clang
ASM_CPPFLAGS := $(CPPFLAGS)
ASM_TRIPLES_arm64 := aarch64-apple-darwin aarch64-linux-gnu aarch64-windows-msvc
ASM_TRIPLES_x86_64 := x86_64-apple-darwin x86_64-linux-gnu x86_64-pc-windows-msvc
define ASMCHECK_TRIPLE
$(BUILD_DIR)/asmcheck/$(2)/%.o: %.S
	@mkdir -p $$(dir $$@)
	$(ASM_CC) --target=$(2) $(ASM_CPPFLAGS) -Inative/asm/$(1) -MMD -MP -c $$< -o $$@
ASMCHECK += $$(patsubst %.S,$(BUILD_DIR)/asmcheck/$(2)/%.o,$$(wildcard native/asm/$(1)/*.S tests/asm/$(1)/*.S))
endef
$(foreach i,arm64 x86_64,$(foreach t,$(ASM_TRIPLES_$(i)),$(eval $(call ASMCHECK_TRIPLE,$(i),$(t)))))

ASM_OBJECTS := $(patsubst %.S,$(BUILD_DIR)/asm/%.o,$(wildcard native/asm/$(ISA)/*.S))
$(BUILD_DIR)/asm/%.o: %.S
	@mkdir -p $(dir $@)
	$(ASM_CC) $(if $(RUST_TARGET),--target=$(RUST_TARGET)) $(ASM_CPPFLAGS) -Inative/asm/$(ISA) -MMD -MP -c $< -o $@
asm: $(ASM_OBJECTS)
asmcheck: $(ASMCHECK)
	@echo "asmcheck: $(words $(ASMCHECK)) objects (every .S x mach-o, elf, coff) assemble"
	@$(PYTHON) tests/abi/asm_regs_audit.py $(BUILD_DIR)/asmcheck $(firstword $(ASM_CC))

-include $(ASMCHECK:.o=.d) $(ASM_OBJECTS:.o=.d)

clean:
	$(CARGO) clean
	rm -rf build
