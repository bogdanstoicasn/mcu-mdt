# ===== STM32 Platform Makefile =====
# Called from root Makefile with MCU, PORT variables

# Toolchain
CC := arm-none-eabi-gcc
AR := arm-none-eabi-ar
OBJCOPY := arm-none-eabi-objcopy
SIZE := arm-none-eabi-size

# Directories
SRC_DIR := ../../src
HAL_DIR := .
BASE_HAL_DIR := ../
BUILD_DIR := ../../build/$(MCU)
INC_DIR := ../../inc
EXAMPLES_DIR := ../../examples/stm32

# Output
LIB_NAME := libmcu_mdt_stm32.a
LIB_PATH := $(BUILD_DIR)/$(LIB_NAME)
ELF_NAME := mcu_mdt_example.elf
BIN_NAME := mcu_mdt_example.bin
HEX_NAME := mcu_mdt_example.hex

# Linker script & startup
LINKER_SCRIPT := $(HAL_DIR)/linker.ld
STARTUP_FILE := $(HAL_DIR)/startup_stm32f030xx.s

# Source files
SRC_FILES := $(wildcard $(SRC_DIR)/*.c)
HAL_FILES := $(wildcard $(HAL_DIR)/*.c)

# Object files
SRC_OBJS := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SRC_FILES))
HAL_OBJS := $(patsubst $(HAL_DIR)/%.c,$(BUILD_DIR)/%.o,$(HAL_FILES))
STARTUP_OBJ := $(BUILD_DIR)/startup.o
ALL_OBJS := $(SRC_OBJS) $(HAL_OBJS) $(STARTUP_OBJ)

# CPU flags (Cortex-M0)
CPU_FLAGS := -mcpu=cortex-m0 -mthumb

# Compiler flags
CFLAGS := $(CPU_FLAGS)
CFLAGS += -Wall -Wextra -Os
CFLAGS += -ffreestanding -nostdlib
CFLAGS += -I$(INC_DIR) -I$(HAL_DIR) -I$(BASE_HAL_DIR)
CFLAGS += -DPLATFORM_STM32

# Linker flags
LDFLAGS := $(CPU_FLAGS)
LDFLAGS += -T$(LINKER_SCRIPT)
LDFLAGS += -Wl,--gc-sections
LDFLAGS += -nostdlib

# Targets
.PHONY: all clean flash

all: $(BUILD_DIR) $(LIB_PATH) copy_files build_example
	@echo "Build complete!"
	@echo "Library: $(LIB_PATH)"
	@echo "Example: $(BUILD_DIR)/$(HEX_NAME)"
	@echo "platform: STM32" > $(BUILD_DIR)/build_info.yaml
	@echo "mcu: $(MCU)" >> $(BUILD_DIR)/build_info.yaml
	@echo "port: $(PORT)" >> $(BUILD_DIR)/build_info.yaml

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# Compile src
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c
	@echo "Compiling $<..."
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile HAL
$(BUILD_DIR)/%.o: $(HAL_DIR)/%.c
	@echo "Compiling $<..."
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile startup
$(STARTUP_OBJ): $(STARTUP_FILE)
	@echo "Compiling startup..."
	@$(CC) $(CPU_FLAGS) -c $< -o $@

# Create static library
$(LIB_PATH): $(ALL_OBJS)
	@echo "Creating library..."
	@$(AR) rcs $@ $(ALL_OBJS)

# Copy files
copy_files:
	@echo "Copying headers and example..."
	@cp $(INC_DIR)/mcu_mdt.h $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_config.h $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/main.c $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/Makefile $(BUILD_DIR)/Makefile.example

# Build example
build_example:
	@echo "Building example..."
	@cd $(BUILD_DIR) && $(CC) $(CFLAGS) -c main.c -o main.o
	@cd $(BUILD_DIR) && $(CC) main.o -L. -lmcu_mdt_stm32 $(LDFLAGS) -o $(ELF_NAME)
	@cd $(BUILD_DIR) && $(OBJCOPY) -O binary $(ELF_NAME) $(BIN_NAME)
	@cd $(BUILD_DIR) && $(OBJCOPY) -O ihex $(ELF_NAME) $(HEX_NAME)
	@$(SIZE) $(BUILD_DIR)/$(ELF_NAME)

# Flash (example using ST-Link)
flash: all
	@echo "Flashing to $(MCU)..."
	st-flash write $(BUILD_DIR)/$(BIN_NAME) 0x08000000

clean:
	@echo "Cleaning STM32 build..."
	@rm -rf $(BUILD_DIR)/*
	@if [ -d $(BUILD_DIR) ] && [ -z "$$(ls -A $(BUILD_DIR))" ]; then rmdir $(BUILD_DIR); fi