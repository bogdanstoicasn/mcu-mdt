# ===== MCU MDT Example Makefile =====
# Drop this in your project directory alongside main.c (or any .c files)
# Usage: make MCU=F030F4 PORT=/dev/ttyUSB0

# ── User configuration ──

MCU   ?= F030F4
PORT  ?= /dev/ttyUSB0
F_CPU ?= 48000000UL

# Add your own source files here, or leave as wildcard to grab all .c in this dir
USER_SRCS := $(wildcard *.c)

# Toolchain

CC      := arm-none-eabi-gcc
OBJCOPY := arm-none-eabi-objcopy
SIZE    := arm-none-eabi-size

# Paths

LIB           := libmcu_mdt_stm32.a
LINKER_SCRIPT := linker.ld
STARTUP       := startup_stm32f030xx.c

# Output

ELF := mcu_mdt_user.elf
BIN := mcu_mdt_user.bin
HEX := mcu_mdt_user.hex

# Flags

CPU_FLAGS := -mcpu=cortex-m0 -mthumb

CFLAGS  := $(CPU_FLAGS)
CFLAGS  += -Wall -Wextra -Os
CFLAGS  += -ffunction-sections -fdata-sections
CFLAGS  += -ffreestanding -nostdlib
CFLAGS  += -DF_CPU=$(F_CPU)
CFLAGS  += -DPLATFORM_STM32
CFLAGS  += -DMCU=$(MCU)
CFLAGS  += -I.

LDFLAGS := $(CPU_FLAGS)
LDFLAGS += -T$(LINKER_SCRIPT)
LDFLAGS += -Wl,--gc-sections
LDFLAGS += -nostdlib
LDFLAGS += -DMCU=$(MCU)

# Object files

STARTUP_OBJ := startup.o
OBJS        := $(USER_SRCS:.c=.o)
DEPS        := $(OBJS:.o=.d)

# Targets

.PHONY: all clean flash

all: $(HEX)
	@$(SIZE) $(ELF)
	@echo "Built: $(HEX)"

-include $(DEPS)

# Compile user sources
%.o: %.c
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

# Compile startup separately: no -Wall/-Wextra, just bare metal flags
$(STARTUP_OBJ): $(STARTUP)
	@echo "  CC  startup"
	@$(CC) $(CPU_FLAGS) -ffreestanding -nostdlib -c $< -o $@

# Link: startup must come before user objects so the vector table lands first
$(ELF): $(STARTUP_OBJ) $(OBJS) $(LIB)
	@echo "  LD  $(ELF)"
	@$(CC) $(LDFLAGS) $(STARTUP_OBJ) $(OBJS) -L. -lmcu_mdt_stm32 -lgcc -o $@

$(BIN): $(ELF)
	@$(OBJCOPY) -O binary $< $@

$(HEX): $(ELF) $(BIN)
	@echo "  HEX $(HEX)"
	@$(OBJCOPY) -O ihex $< $@

flash: all
	@test -f $(BIN) || { echo "ERROR: $(BIN) not found"; exit 1; }
	@echo "Flashing $(MCU) via ST-Link..."
	st-flash write $(BIN) 0x08000000

clean:
	@rm -f $(OBJS) $(DEPS) $(STARTUP_OBJ) $(ELF) $(BIN) $(HEX)
	@echo "Cleaned."