# ===== AVR Platform Makefile =====
# Called from root Makefile with MCU, PORT variables

# Compiler and tools
CC := avr-gcc
AR := avr-ar
OBJCOPY := avr-objcopy

# Directories
SRC_DIR := ../../src
HAL_DIR := .
BUILD_DIR := ../../build
INC_DIR := ../../inc

# Output
LIB_NAME := libmcu_mdt_avr.a
LIB_PATH := $(BUILD_DIR)/$(LIB_NAME)

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
CFLAGS += -I$(INC_DIR) -I$(HAL_DIR)
CFLAGS += -DF_CPU=16000000UL
CFLAGS += -DPLATFORM_AVR

# Targets
.PHONY: all clean

all: $(BUILD_DIR) $(LIB_PATH)
	@echo "AVR library built successfully: $(LIB_PATH)"

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

clean:
	@echo "Cleaning AVR build..."
	@rm -f $(BUILD_DIR)/*.o
	@rm -f $(LIB_PATH)
	@if [ -d $(BUILD_DIR) ] && [ -z "$$(ls -A $(BUILD_DIR))" ]; then rmdir $(BUILD_DIR); fi