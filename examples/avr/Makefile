# ===== AVR Example Makefile =====
# Usage: make MCU=atmega328p PORT=/dev/ttyACM0

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

PORT ?= /dev/ttyACM0

# Toolchain
CC := avr-gcc
OBJCOPY := avr-objcopy
CFLAGS := -mmcu=$(MCU) -Os -Wall -I../../inc
LDFLAGS := -mmcu=$(MCU)

# Source files
SRC := main.c
OBJ := $(SRC:.c=.o)

# Path to prebuilt library
LIB_DIR := ../../build/$(MCU)
LIB := $(LIB_DIR)/libmcu_mdt.a

# Output files
ELF := main.elf
HEX := main.hex

.PHONY: all clean flash

all: $(HEX)
	@echo "Build complete: $(HEX)"

# Compile
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Link with the prebuilt library
$(ELF): $(OBJ) $(LIB)
	$(CC) $(LDFLAGS) $^ -o $@

# Generate HEX file
$(HEX): $(ELF)
	$(OBJCOPY) -O ihex $< $@

# Flash target
flash: $(HEX)
	@echo "Flashing $(HEX) to $(MCU) via $(PORT)..."
	avrdude -c arduino -p $(MCU) -P $(PORT) -U flash:w:$(HEX):i
	@echo "Flash complete."

clean:
	rm -f $(OBJ) $(ELF) $(HEX)
