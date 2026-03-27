# ===== AVR Platform Makefile =====
# Called from root Makefile with MCU, PORT variables

# Toolchain
CC      := avr-gcc
AR      := avr-ar
OBJCOPY := avr-objcopy

# Directories
SRC_DIR      := ../../src
INC_DIR      := ../../inc
HAL_DIR      := .
BASE_HAL_DIR := ../
BUILD_DIR    := ../../build/$(MCU)
EXAMPLES_DIR := ../../examples/avr

# Output
LIB_NAME := libmcu_mdt_avr.a
LIB_PATH := $(BUILD_DIR)/$(LIB_NAME)
ELF_NAME := mcu_mdt_example.elf
HEX_NAME := mcu_mdt_example.hex

# Source files
SRC_FILES := $(wildcard $(SRC_DIR)/*.c)
HAL_FILES := $(wildcard $(HAL_DIR)/*.c)

# Object files
SRC_OBJS := $(patsubst $(SRC_DIR)/%.c, $(BUILD_DIR)/src_%.o, $(SRC_FILES))
HAL_OBJS := $(patsubst $(HAL_DIR)/%.c, $(BUILD_DIR)/hal_%.o, $(HAL_FILES))
ALL_OBJS := $(SRC_OBJS) $(HAL_OBJS)

# Dependency files
DEPS := $(SRC_OBJS:.o=.d) $(HAL_OBJS:.o=.d)

# F_CPU default (can be overridden)
F_CPU ?= 16000000UL

# Compiler flags
CFLAGS  := -mmcu=$(MCU)
CFLAGS  += -Wall -Wextra -Os
CFLAGS  += -ffunction-sections
CFLAGS  += -fdata-sections
CFLAGS  += -MMD -MP
CFLAGS  += $(INCLUDES)
CFLAGS  += -I$(HAL_DIR) -I$(BASE_HAL_DIR) -I$(SRC_DIR)
CFLAGS  += -DF_CPU=$(F_CPU)
CFLAGS  += -DPLATFORM_AVR

# Linker flags
LDFLAGS  := -mmcu=$(MCU)
LDFLAGS  += -Wl,--gc-sections
LDFLAGS  += -Wl,--print-gc-sections   # optional but very useful

# Example objects
EXAMPLE_OBJ := $(BUILD_DIR)/main.o
EXAMPLE_ELF := $(BUILD_DIR)/$(ELF_NAME)
EXAMPLE_HEX := $(BUILD_DIR)/$(HEX_NAME)

# ── Targets ──

.PHONY: all clean flash

all: $(BUILD_DIR) $(LIB_PATH) copy_files build_example $(BUILD_DIR)/build_info.yaml
	@echo "Build complete!"
	@echo "  Library : $(BUILD_DIR)/$(LIB_NAME)"
	@echo "  Hex     : $(EXAMPLE_HEX)"

# Build directory
$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# Dependency files
-include $(DEPS)

# Compile src/
$(BUILD_DIR)/src_%.o: $(SRC_DIR)/%.c
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile HAL
$(BUILD_DIR)/hal_%.o: $(HAL_DIR)/%.c
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

# Static library
$(LIB_PATH): $(ALL_OBJS)
	@echo "  AR  $@"
	@$(AR) rcs $@ $(ALL_OBJS)

# Copy distribution files
copy_files: $(BUILD_DIR)
	@echo "  COPY headers & example"
	@cp $(INC_DIR)/mcu_mdt.h        $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_config.h $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/main.c      $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/Makefile    $(BUILD_DIR)/Makefile.example

# Compile example
$(EXAMPLE_OBJ): $(BUILD_DIR)/main.c
	@echo "  CC  main.c"
	@$(CC) $(CFLAGS) -c $< -o $@

# Link example
build_example: $(EXAMPLE_OBJ) $(LIB_PATH)
	@echo "  LD  $(ELF_NAME)"
	@$(CC) $(CFLAGS) $(LDFLAGS) $(EXAMPLE_OBJ) -L$(BUILD_DIR) -lmcu_mdt_avr -o $(EXAMPLE_ELF)
	@$(OBJCOPY) -O ihex -R .eeprom $(EXAMPLE_ELF) $(EXAMPLE_HEX)
	@echo "  HEX $(EXAMPLE_HEX)"

# Build info
$(BUILD_DIR)/build_info.yaml: $(BUILD_DIR)
	@echo "platform: AVR" > $@
	@echo "mcu: $(MCU)"  >> $@
	@echo "port: $(PORT)" >> $@

flash: all
	@test -f $(EXAMPLE_HEX) || \
		{ echo "ERROR: Hex not found, build failed?"; exit 1; }
	@echo "Flashing $(MCU) on $(PORT)..."
	avrdude -c arduino -p $(MCU) -P $(PORT) -b 115200 -U flash:w:$(EXAMPLE_HEX):i

clean:
	@echo "Cleaning AVR build ($(MCU))..."
	@rm -rf $(BUILD_DIR)