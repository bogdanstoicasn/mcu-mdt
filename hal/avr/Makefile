# ===== AVR Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

# Toolchain
AVR_GCC := avr-gcc
AR := avr-ar
AVR_SIZE := avr-size

CFLAGS := -mmcu=$(MCU) -Os -Wall -Wextra -std=gnu11
CFLAGS += -DPLATFORM_AVR

# Directories
SRC_DIR := ../../src
INC_DIR := ../../inc
BUILD_DIR := build/$(MCU)

SRC := $(wildcard $(SRC_DIR)/*.c)
OBJ := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SRC))

LIB := $(BUILD_DIR)/libmcu_mdt.a

.PHONY: all clean

all: $(LIB)
	@echo "Static library built: $(LIB)"

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Compile C files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(AVR_GCC) $(CFLAGS) -I$(INC_DIR) -c $< -o $@

# Build static library
$(LIB): $(OBJ)
	$(AR) rcs $@ $^
	$(AVR_SIZE) $@

clean:
	rm -rf $(BUILD_DIR)
