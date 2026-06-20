# ===== STM32 Cortex-M0 Makefile =====
# Called from hal/stm32/Makefile (router) with MCU, PORT variables
# Lives at: hal/stm32/cortex-m0/Makefile

# Toolchain
CC      := arm-none-eabi-gcc
AR      := arm-none-eabi-ar
OBJCOPY := arm-none-eabi-objcopy
SIZE    := arm-none-eabi-size

# Directories
SRC_DIR      := ../../../src
INC_DIR      := ../../../inc
HAL_DIR      := .
BASE_HAL_DIR := ../../
STM_HAL_DIR  := ../
BUILD_DIR    := ../../../build/$(MCU)
EXAMPLES_DIR := ../../../examples/stm32

# Output
LIB_NAME := libmcu_mdt_stm32.a
LIB_PATH := $(BUILD_DIR)/$(LIB_NAME)
ELF_NAME := mcu_mdt_example.elf
BIN_NAME := mcu_mdt_example.bin
HEX_NAME := mcu_mdt_example.hex

# Linker script & startup (live alongside this Makefile)
LINKER_SCRIPT    := $(CURDIR)/linker.ld
LINKER_SCRIPT_PP := $(BUILD_DIR)/linker_pp.ld
STARTUP_FILE     := $(HAL_DIR)/startup_stm32f030xx.c

# Source files
SRC_FILES := $(wildcard $(SRC_DIR)/*.c)
HAL_FILES := $(wildcard $(HAL_DIR)/*.c)

# Object files: prefixed to avoid collision if filenames overlap across src/ and hal/
SRC_OBJS    := $(patsubst $(SRC_DIR)/%.c, $(BUILD_DIR)/src_%.o, $(SRC_FILES))
HAL_OBJS    := $(patsubst $(HAL_DIR)/%.c, $(BUILD_DIR)/hal_%.o, $(HAL_FILES))
STARTUP_OBJ := $(BUILD_DIR)/startup.o
ALL_OBJS    := $(SRC_OBJS) $(HAL_OBJS) $(STARTUP_OBJ)

# Dependency files
DEPS := $(SRC_OBJS:.o=.d) $(HAL_OBJS:.o=.d)

# CPU flags (Cortex-M0)
CPU_FLAGS := -mcpu=cortex-m0 -mthumb

# MCU -> linker script define mapping
# Preprocesses linker.ld with -DMCU_<name> so #ifdef works correctly
# FLASH_PAGE_SIZE: 0x400 (1 KB) for F030x4/x6/x8 and F070x6
#                  0x800 (2 KB) for F030xC and F070xB
ifeq ($(MCU),F030F4)
  MCU_LD_DEFINE   := -DMCU_F030F4
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F030F6)
  MCU_LD_DEFINE   := -DMCU_F030F6
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F030C6)
  MCU_LD_DEFINE   := -DMCU_F030C6
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F030F8)
  MCU_LD_DEFINE   := -DMCU_F030F8
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F030C8)
  MCU_LD_DEFINE   := -DMCU_F030C8
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F030CC)
  MCU_LD_DEFINE   := -DMCU_F030CC
  FLASH_PAGE_SIZE := 0x800
else ifeq ($(MCU),F070F6)
  MCU_LD_DEFINE   := -DMCU_F070F6
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU),F070CB)
  MCU_LD_DEFINE   := -DMCU_F070CB
  FLASH_PAGE_SIZE := 0x800
else ifeq ($(MCU),F070RB)
  MCU_LD_DEFINE   := -DMCU_F070RB
  FLASH_PAGE_SIZE := 0x800
else
  $(error Unsupported MCU '$(MCU)' — add mapping in cortex-m0/Makefile)
endif

# CPU frequency (can be overridden from command line)
F_CPU ?= 8000000UL

# Compiler flags
CFLAGS  := $(CPU_FLAGS)
CFLAGS  += -Wall -Wextra -Os
CFLAGS  += -ffunction-sections
CFLAGS  += -fdata-sections
CFLAGS  += -ffreestanding -nostdlib
CFLAGS  += -MMD -MP
CFLAGS  += $(INCLUDES)
CFLAGS  += -I$(HAL_DIR) -I$(STM_HAL_DIR)
CFLAGS  += -DPLATFORM_STM32
CFLAGS  += -DFLASH_PAGE_SIZE=$(FLASH_PAGE_SIZE)UL

# MDT_USE_UART_IDLE: default 1 on this target (hardware supports IDLE interrupt).
# Override with: make MDT_USE_UART_IDLE=0 to use poll mode instead.
MDT_USE_UART_IDLE ?= 1
CFLAGS += -DMDT_FEATURE_UART_IDLE=$(MDT_USE_UART_IDLE)
CFLAGS  += -DF_CPU=$(F_CPU)

# Linker flags: use preprocessed linker script
LDFLAGS  := $(CPU_FLAGS)
LDFLAGS  += -T$(LINKER_SCRIPT_PP)
LDFLAGS  += -Wl,--gc-sections
LDFLAGS  += -nostdlib

# Example objects
EXAMPLE_OBJ := $(BUILD_DIR)/main.o
EXAMPLE_ELF := $(BUILD_DIR)/$(ELF_NAME)
EXAMPLE_BIN := $(BUILD_DIR)/$(BIN_NAME)
EXAMPLE_HEX := $(BUILD_DIR)/$(HEX_NAME)

# TARGETS

.PHONY: all clean flash flash-recover erase

all: $(BUILD_DIR) $(LINKER_SCRIPT_PP) $(LIB_PATH) copy_files build_example $(BUILD_DIR)/build_info.yaml
	@echo "Build complete!"
	@echo "  Library : $(LIB_PATH)"
	@echo "  Hex     : $(EXAMPLE_HEX)"

# Build directory
$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# Preprocess linker script: resolves #ifdef MCU_<name> into plain ld syntax
$(LINKER_SCRIPT_PP): $(LINKER_SCRIPT) | $(BUILD_DIR)
	@echo "  PP  linker.ld -> linker_pp.ld"
	@$(CC) -E -P -x c $(MCU_LD_DEFINE) $< -o $@

# Dependency files
-include $(DEPS)

# Compile src/
$(BUILD_DIR)/src_%.o: $(SRC_DIR)/%.c | $(LINKER_SCRIPT_PP)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile HAL (cortex-m0/*.c)
$(BUILD_DIR)/hal_%.o: $(HAL_DIR)/%.c | $(LINKER_SCRIPT_PP)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile startup
$(STARTUP_OBJ): $(STARTUP_FILE) | $(LINKER_SCRIPT_PP)
	@echo "  CC  startup"
	@$(CC) $(CPU_FLAGS) -ffreestanding -nostdlib -c $< -o $@

# Static library
$(LIB_PATH): $(ALL_OBJS)
	@echo "  AR  $@"
	@$(AR) rcs $@ $(ALL_OBJS)

# Copy distribution files
copy_files: $(BUILD_DIR) $(LINKER_SCRIPT_PP)
	@echo "  COPY headers & example"
	@cp $(INC_DIR)/mcu_mdt.h        $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_config.h $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_hal.h    $(BUILD_DIR)/
	@cp $(INC_DIR)/ring_buffer.h    $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/main.c      $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/Makefile    $(BUILD_DIR)/Makefile.example
	@cp $(LINKER_SCRIPT_PP)         $(BUILD_DIR)/linker.ld
	@cp $(STARTUP_FILE)             $(BUILD_DIR)/

# Compile example
$(EXAMPLE_OBJ): $(BUILD_DIR)/main.c | $(LINKER_SCRIPT_PP)
	@echo "  CC  main.c"
	@$(CC) $(CFLAGS) -c $< -o $@

# Link example
build_example: $(EXAMPLE_OBJ) $(LIB_PATH) $(LINKER_SCRIPT_PP)
	@echo "  LD  $(ELF_NAME)"
	@$(CC) $(EXAMPLE_OBJ) -L$(BUILD_DIR) -lmcu_mdt_stm32 $(LDFLAGS) -lgcc -o $(EXAMPLE_ELF)
	@$(OBJCOPY) -O binary $(EXAMPLE_ELF) $(EXAMPLE_BIN)
	@$(OBJCOPY) -O ihex   $(EXAMPLE_ELF) $(EXAMPLE_HEX)
	@$(SIZE) $(EXAMPLE_ELF)

# Build info — depends on the linked binary so firmware addresses are accurate
$(BUILD_DIR)/build_info.yaml: $(EXAMPLE_BIN)
	$(eval FW_START := 0x08000000)
	$(eval FW_SIZE  := $(shell wc -c < $(EXAMPLE_BIN) | tr -d ' '))
	$(eval FW_END   := $(shell printf "0x%08x" $$(( $(FW_START) + $(FW_SIZE) ))))
	@echo "platform: STM32"                                    > $@
	@echo "core: cortex-m0"                                   >> $@
	@echo "mcu: $(MCU)"                                       >> $@
	@echo "port: $(PORT)"                                     >> $@
	@echo "elf: $(ELF_NAME)"                                  >> $@
	@echo "uart_idle: $(MDT_USE_UART_IDLE)"                   >> $@
	@echo "flash_page_size: $(FLASH_PAGE_SIZE)"               >> $@
	@echo "firmware_start_address: $(FW_START)"               >> $@
	@echo "firmware_end_address: $(FW_END)"                   >> $@
	@echo "firmware_size: $(FW_SIZE)"                         >> $@

flash: all
	@test -f $(EXAMPLE_BIN) || \
		{ echo "ERROR: Binary not found, build failed?"; exit 1; }
	@echo "Flashing $(MCU) via ST-Link..."
	@st-flash write $(EXAMPLE_BIN) 0x08000000 || \
		{ echo ""; \
		  echo "Flash failed to connect. The core may be asleep (WFI) or locked."; \
		  echo "Try one of:"; \
		  echo "  make PLATFORM=stm32 MCU=$(MCU) flash-recover   # erase under reset, then flash"; \
		  echo "  make PLATFORM=stm32 MCU=$(MCU) erase           # mass-erase only"; \
		  echo "  or set BOOT0=1, reset the board, and flash again"; \
		  exit 1; }

# OpenOCD config for this core (used by erase / flash-recover)
OPENOCD_IFACE ?= interface/stlink.cfg
OPENOCD_TARGET := target/stm32f0x.cfg

# Mass-erase the whole chip, halting the core from reset first so a sleeping
# or locked core (e.g. a WFI main loop) can still be reached.
erase:
	@command -v openocd >/dev/null || \
		{ echo "ERROR: openocd not found. Install it (apt install openocd)."; exit 1; }
	@echo "Mass-erasing $(MCU) via OpenOCD (connect under reset)..."
	openocd -f $(OPENOCD_IFACE) -f $(OPENOCD_TARGET) \
		-c "init; reset halt; stm32f0x mass_erase 0; reset; shutdown"

# Recover a board that st-flash can no longer connect to: erase under reset,
# then program the freshly built image, all through OpenOCD.
flash-recover: all
	@command -v openocd >/dev/null || \
		{ echo "ERROR: openocd not found. Install it (apt install openocd)."; exit 1; }
	@test -f $(EXAMPLE_BIN) || \
		{ echo "ERROR: Binary not found, build failed?"; exit 1; }
	@echo "Recovering $(MCU): erase + flash via OpenOCD (connect under reset)..."
	openocd -f $(OPENOCD_IFACE) -f $(OPENOCD_TARGET) \
		-c "init; reset halt; stm32f0x mass_erase 0; \
		    flash write_image erase $(EXAMPLE_ELF); \
		    verify_image $(EXAMPLE_ELF); reset run; shutdown"

clean:
	@echo "Cleaning cortex-m0 build ($(MCU))..."
	@rm -rf $(BUILD_DIR)