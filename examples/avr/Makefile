# ===== Example Makefile =====
# This Makefile links the example with the pre-built library
# Usage: make MCU=atmega328p PORT=/dev/ttyACM0

# Compiler and tools
CC := avr-gcc
OBJCOPY := avr-objcopy
SIZE := avr-size

# MCU settings (can be overridden)
MCU ?= atmega328p
F_CPU ?= 16000000UL
PORT ?= /dev/ttyACM0

# Files
TARGET := mcu_mdt_example
MAIN_SRC := main.c
LIB_NAME := libmcu_mdt_avr.a

# Output files
ELF := $(TARGET).elf
HEX := $(TARGET).hex

# Compiler flags
CFLAGS := -mmcu=$(MCU)
CFLAGS += -DF_CPU=$(F_CPU)
CFLAGS += -Wall -Wextra -Os
CFLAGS += -std=gnu99

# Linker flags
LDFLAGS := -mmcu=$(MCU)
LDFLAGS += -L. -lmcu_mdt_avr

# Targets
.PHONY: all clean flash size

all: $(HEX) size

# Compile main.c
main.o: $(MAIN_SRC) mcu_mdt.h
	@echo "Compiling $(MAIN_SRC)..."
	$(CC) $(CFLAGS) -c $(MAIN_SRC) -o main.o

# Link with library
$(ELF): main.o $(LIB_NAME)
	@echo "Linking..."
	$(CC) $(LDFLAGS) main.o -o $(ELF)

# Create hex file
$(HEX): $(ELF)
	@echo "Creating hex file..."
	$(OBJCOPY) -O ihex -R .eeprom $(ELF) $(HEX)

# Show size
size: $(ELF)
	@echo "Program size:"
	$(SIZE) --format=avr --mcu=$(MCU) $(ELF)

# Flash to MCU
flash: $(HEX)
	@echo "Flashing to $(MCU) on $(PORT)..."
	avrdude -c arduino -p $(MCU) -P $(PORT) -b 115200 -U flash:w:$(HEX):i

# Clean build files
clean:
	@echo "Cleaning..."
	@rm -f *.o $(ELF) $(HEX)