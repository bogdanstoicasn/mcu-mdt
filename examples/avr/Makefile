# ===== MCU MDT Example Makefile =====
# Drop this in your project directory alongside main.c (or any .c files)
# Usage: make MCU=atmega328p PORT=/dev/ttyACM0

# ── User configuration ──

MCU   ?= atmega328p
PORT  ?= /dev/ttyACM0
F_CPU ?= 16000000UL

# Add your own source files here, or leave as wildcard to grab all .c in this dir
USER_SRCS := $(wildcard *.c)

# Toolchain

CC      := avr-gcc
OBJCOPY := avr-objcopy

# Paths

LIB := libmcu_mdt_avr.a

# Output files

ELF := mcu_mdt_user.elf
HEX := mcu_mdt_user.hex

# Flags

CFLAGS  := -mmcu=$(MCU)
CFLAGS  += -Wall -Wextra -Os
CFLAGS  += -ffunction-sections -fdata-sections
CFLAGS  += -DF_CPU=$(F_CPU)
CFLAGS  += -I.

LDFLAGS := -mmcu=$(MCU)
LDFLAGS += -Wl,--gc-sections

# Object files

OBJS := $(USER_SRCS:.c=.o)
DEPS := $(OBJS:.o=.d)

# Rules

.PHONY: all clean flash

all: $(HEX)
	@echo "Built: $(HEX)"

-include $(DEPS)

%.o: %.c
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

$(ELF): $(OBJS) $(LIB)
	@echo "  LD  $(ELF)"
	@$(CC) $(LDFLAGS) $(OBJS) -L. -lmcu_mdt_avr -o $@

$(HEX): $(ELF)
	@echo "  HEX $(HEX)"
	@$(OBJCOPY) -O ihex -R .eeprom $< $@

flash: all
	@test -f $(HEX) || { echo "ERROR: $(HEX) not found"; exit 1; }
	avrdude -c arduino -p $(MCU) -P $(PORT) -b 115200 -U flash:w:$(HEX):i

clean:
	@rm -f $(OBJS) $(DEPS) $(ELF) $(HEX)
	@echo "Cleaned."