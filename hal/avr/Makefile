# ===== AVR Platform Makefile =====
# Called from root Makefile with MCU, PORT variables

# Compiler and tools
CC := avr-gcc
AR := avr-ar
OBJCOPY := avr-objcopy

# Directories
SRC_DIR := ../../src
HAL_DIR := .
BASE_HAL_DIR := ../
BUILD_DIR := ../../build
INC_DIR := ../../inc
EXAMPLES_DIR := ../../examples/avr

# Output
LIB_NAME := libmcu_mdt_avr.a
LIB_PATH := $(BUILD_DIR)/$(LIB_NAME)
HEX_NAME := mcu_mdt_example.hex
ELF_NAME := mcu_mdt_example.elf

# Source files
SRC_FILES := $(wildcard $(SRC_DIR)/*.c)
HAL_FILES := $(wildcard $(HAL_DIR)/*.c)

# Object files (placed in build directory)
SRC_OBJS := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SRC_FILES))
HAL_OBJS := $(patsubst $(HAL_DIR)/%.c,$(BUILD_DIR)/%.o,$(HAL_FILES))
ALL_OBJS := $(SRC_OBJS) $(HAL_OBJS)

# Compiler flags
CFLAGS := -mmcu=$(MCU)
CFLAGS += -Wall -Wextra -Os
CFLAGS += -I$(INC_DIR) -I$(HAL_DIR) -I$(BASE_HAL_DIR)
CFLAGS += -DF_CPU=16000000UL
CFLAGS += -DPLATFORM_AVR

# Linker flags
LDFLAGS := -mmcu=$(MCU)

# Targets
.PHONY: all clean flash

all: $(BUILD_DIR) $(LIB_PATH) copy_files build_example
	@echo "Build complete!"
	@echo "Library: $(BUILD_DIR)/$(LIB_NAME)"
	@echo "Example: $(BUILD_DIR)/$(HEX_NAME)"

$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# Compile src/*.c files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c
	@echo "Compiling $<..."
	@$(CC) $(CFLAGS) -c $< -o $@

# Compile hal/avr/*.c files
$(BUILD_DIR)/%.o: $(HAL_DIR)/%.c
	@echo "Compiling $<..."
	@$(CC) $(CFLAGS) -c $< -o $@

# Create static library
$(LIB_PATH): $(ALL_OBJS)
	@echo "Creating library $@..."
	@$(AR) rcs $@ $(ALL_OBJS)

# Copy required files to build directory
copy_files:
	@echo "Copying header and example files..."
	@cp $(INC_DIR)/mcu_mdt.h $(BUILD_DIR)/
	@cp $(INC_DIR)/mcu_mdt_config.h $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/main.c $(BUILD_DIR)/
	@cp $(EXAMPLES_DIR)/Makefile $(BUILD_DIR)/Makefile.example

# Build example application
build_example:
	@echo "Building example application..."
	@cd $(BUILD_DIR) && $(CC) $(CFLAGS) -c main.c -o main.o
	@cd $(BUILD_DIR) && $(CC) $(LDFLAGS) main.o -L. -lmcu_mdt_avr -o $(ELF_NAME)
	@cd $(BUILD_DIR) && $(OBJCOPY) -O ihex -R .eeprom $(ELF_NAME) $(HEX_NAME)
	@echo "Example built: $(BUILD_DIR)/$(HEX_NAME)"

# Flash to MCU
flash: all
	@echo "Flashing to $(MCU) on $(PORT)..."
	avrdude -c arduino -p $(MCU) -P $(PORT) -b 115200 -U flash:w:$(BUILD_DIR)/$(HEX_NAME):i

clean:
	@echo "Cleaning AVR build..."
	@rm -f $(BUILD_DIR)/*.o
	@rm -f $(BUILD_DIR)/*.a
	@rm -f $(BUILD_DIR)/*.elf
	@rm -f $(BUILD_DIR)/*.hex
	@rm -f $(BUILD_DIR)/*.h
	@rm -f $(BUILD_DIR)/*.c
	@rm -f $(BUILD_DIR)/Makefile.example
	@if [ -d $(BUILD_DIR) ] && [ -z "$$(ls -A $(BUILD_DIR))" ]; then rmdir $(BUILD_DIR); fi