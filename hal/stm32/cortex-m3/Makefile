# ===== STM32 Cortex-M3 Makefile =====
# Called from hal/stm32/Makefile (router) with MCU, PORT variables
# Lives at: hal/stm32/cortex-m3/Makefile

# Toolchain
CC := arm-none-eabi-gcc
AR := arm-none-eabi-ar
OBJCOPY := arm-none-eabi-objcopy
SIZE := arm-none-eabi-size

# Directories
SRC_DIR := ../../../src
INC_DIR := ../../../inc
HAL_DIR := .
BASE_HAL_DIR := ../../
STM_HAL_DIR := ../
BUILD_DIR := ../../../build/$(MCU)
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
STARTUP_FILE     := $(HAL_DIR)/startup_stm32f103xx.c

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

# CPU flags (Cortex-M3)
CPU_FLAGS := -mcpu=cortex-m3 -mthumb

# MCU -> linker script define mapping
# Preprocesses linker.ld with -DMCU_<name> so #ifdef works correctly
# We also group by density to avoid redundant linker scripts for each MCU variant
MCU_NORM := $(MCU)
MCU_NORM := $(patsubst F103C%,F103x%,$(MCU_NORM))
MCU_NORM := $(patsubst F103R%,F103x%,$(MCU_NORM))
MCU_NORM := $(patsubst F103T%,F103x%,$(MCU_NORM))
MCU_NORM := $(patsubst F103V%,F103x%,$(MCU_NORM))
MCU_NORM := $(patsubst F103Z%,F103x%,$(MCU_NORM))

# MCU -> linker script define mapping.
# Also sets FLASH_PAGE_SIZE (injected as -D into all C files) and
# FLASH_XL_DENSITY (set only for XL-density parts with dual flash banks).
#
# Page sizes per RM0008 Tables 4-8:
#   1 KB — low density  (F103x4, F103x6)
#   1 KB — medium density (F103x8, F103xB)
#   2 KB — high density (F103xC/D/E), XL density (F103xF/G), connectivity (F105/F107)
# XL density (F103xF, F103xG) also requires FLASH_XL_DENSITY for dual-bank support.
FLASH_XL_DENSITY :=

ifeq ($(MCU_NORM),F103x4)
  MCU_LD_DEFINE   := -DMCU_F103x4
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU_NORM),F103x6)
  MCU_LD_DEFINE   := -DMCU_F103x6
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU_NORM),F103x8)
  MCU_LD_DEFINE   := -DMCU_F103x8
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU_NORM),F103xB)
  MCU_LD_DEFINE   := -DMCU_F103xB
  FLASH_PAGE_SIZE := 0x400
else ifeq ($(MCU_NORM),F103xC)
  MCU_LD_DEFINE   := -DMCU_F103xC
  FLASH_PAGE_SIZE := 0x800
else ifeq ($(MCU_NORM),F103xD)
  MCU_LD_DEFINE   := -DMCU_F103xD
  FLASH_PAGE_SIZE := 0x800
else ifeq ($(MCU_NORM),F103xE)
  MCU_LD_DEFINE   := -DMCU_F103xE
  FLASH_PAGE_SIZE := 0x800
else ifeq ($(MCU_NORM),F103xF)
  MCU_LD_DEFINE    := -DMCU_F103xF
  FLASH_PAGE_SIZE  := 0x800
  FLASH_XL_DENSITY := 1
else ifeq ($(MCU_NORM),F103xG)
  MCU_LD_DEFINE    := -DMCU_F103xG
  FLASH_PAGE_SIZE  := 0x800
  FLASH_XL_DENSITY := 1
else
  $(error Unsupported MCU '$(MCU)' — add mapping in cortex-m3/Makefile)
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
CFLAGS  += -I$(INC_DIR)
CFLAGS  += $(INCLUDES)
CFLAGS  += -I$(HAL_DIR) -I$(STM_HAL_DIR)
CFLAGS  += -DPLATFORM_STM32
CFLAGS  += -DFLASH_PAGE_SIZE=$(FLASH_PAGE_SIZE)UL
ifneq ($(FLASH_XL_DENSITY),)
CFLAGS  += -DFLASH_XL_DENSITY
endif

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

# ── Targets ───────────────────────────────────────────────────────────────────

.PHONY: all clean flash

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

# Compile HAL (cortex-m3/*.c)
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
copy_files: $(BUILD_DIR)
	@echo "  COPY headers & example"
	@cp $(INC_DIR)/mcu_mdt.h        $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_config.h $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_hal.h    $(BUILD_DIR)/
	@cp $(INC_DIR)/ring_buffer.h    $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/main.c      $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/Makefile    $(BUILD_DIR)/Makefile.example
	@cp $(LINKER_SCRIPT)            $(BUILD_DIR)/linker.ld
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

# Build info
# Build info — depends on the linked binary so firmware addresses are accurate
$(BUILD_DIR)/build_info.yaml: $(EXAMPLE_BIN)
	$(eval FW_START := 0x08000000)
	$(eval FW_SIZE  := $(shell wc -c < $(EXAMPLE_BIN) | tr -d ' '))
	$(eval FW_END   := $(shell printf "0x%08x" $$(( $(FW_START) + $(FW_SIZE) ))))
	@echo "platform: STM32"                                    > $@
	@echo "core: cortex-m3"                                   >> $@
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
	st-flash write $(EXAMPLE_BIN) 0x08000000

clean:
	@echo "Cleaning cortex-m3 build ($(MCU))..."
	@rm -rf $(BUILD_DIR)