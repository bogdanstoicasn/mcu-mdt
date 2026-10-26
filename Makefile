# ===== mcu-mdt build =====
# Usage: make MCU=<part> [PORT=...] [F_CPU=...] [BAUDRATE=...] [BUFFER_SIZE=...]
#                        [BREAKPOINTS=...] [WATCHPOINTS=...] [MDT_USE_UART_IDLE=0|1]
#        make MCU=<part> flash | clean
#
# What a part is built with lives in build_system/ (YAML). On every run, build_system/generate.py
# turns it plus the settings above into build/<part>/build.mk (included below) and
# build/<part>/mdt_target.h (force-included into every C file). Both are rewritten only when
# their content changes, so a changed setting rebuilds exactly what it affects.

NO_CONFIG_TARGETS := wipe help clean_logs
REQUIRES_CONFIG := $(filter-out $(NO_CONFIG_TARGETS),$(or $(MAKECMDGOALS),all))

.PHONY: all clean flash erase flash-recover wipe clean_logs help

ifeq ($(PLATFORM),stm32)
# shortcut: STM32 still builds with hal/stm32/*/Makefile; this branch goes when STM32 moves to build_system/.
ifndef MCU
$(error MCU is not set. Example: make PLATFORM=stm32 MCU=F030F4)
endif
INCLUDES := -I$(CURDIR)/inc
export INCLUDES
PORT ?= /dev/ttyACM0
all flash erase flash-recover clean:
	@$(MAKE) -C hal/stm32 MCU=$(MCU) PORT=$(PORT) $(if $(F_CPU),F_CPU=$(F_CPU)) $@

else ifneq ($(REQUIRES_CONFIG),)
ifndef MCU
$(error MCU is not set. Example: make MCU=atmega328p)
endif

# The leaf: settings given on the command line (or environment) override the YAML defaults.
LEAF := $(if $(PORT),port=$(PORT)) $(if $(F_CPU),f_cpu=$(F_CPU)) $(if $(BAUDRATE),baudrate=$(BAUDRATE)) \
        $(if $(BUFFER_SIZE),buffer_size=$(BUFFER_SIZE)) $(if $(BREAKPOINTS),breakpoints=$(BREAKPOINTS)) \
        $(if $(WATCHPOINTS),watchpoints=$(WATCHPOINTS)) $(if $(MDT_USE_UART_IDLE),uart_idle=$(MDT_USE_UART_IDLE))

GEN_DIR := $(shell python3 build_system/generate.py $(MCU) $(LEAF))
ifneq ($(.SHELLSTATUS),0)
$(error build_system/generate.py failed for MCU=$(MCU), see the message above)
endif
BUILD_MK := $(GEN_DIR)/build.mk
include $(BUILD_MK)

TARGET_HEADER := $(BUILD_DIR)/mdt_target.h
LIB_PATH      := $(BUILD_DIR)/lib$(LIB).a
ELF_PATH      := $(BUILD_DIR)/$(ELF)
HEX_PATH      := $(BUILD_DIR)/$(HEX)

CFLAGS += -MMD -MP -I$(INC_DIR) -I$(HAL_DIR) -include $(TARGET_HEADER)

SRC_OBJS    := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/src_%.o,$(wildcard $(SRC_DIR)/*.c))
HAL_OBJS    := $(patsubst $(HAL_DIR)/%.c,$(BUILD_DIR)/hal_%.o,$(wildcard $(HAL_DIR)/*.c))
EXAMPLE_OBJ := $(BUILD_DIR)/main.o

# Shipped next to the library so a user project can take build/<part>/ as is.
DIST_FILES := $(addprefix $(BUILD_DIR)/,$(DIST_HEADERS) $(DIST_EXAMPLE_MAIN) Makefile.example $(DIST_EMPTY) build_info.yaml)

all: $(HEX_PATH) $(DIST_FILES)

-include $(SRC_OBJS:.o=.d) $(HAL_OBJS:.o=.d) $(EXAMPLE_OBJ:.o=.d)

# build.mk is a prerequisite so that changed flags rebuild; mdt_target.h comes in through the .d files.
$(BUILD_DIR)/src_%.o: $(SRC_DIR)/%.c $(BUILD_MK)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/hal_%.o: $(HAL_DIR)/%.c $(BUILD_MK)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

$(EXAMPLE_OBJ): $(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAIN) $(BUILD_MK)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

$(LIB_PATH): $(SRC_OBJS) $(HAL_OBJS)
	@echo "  AR  $@"
	@rm -f $@
	@$(AR) rcs $@ $^

$(ELF_PATH): $(EXAMPLE_OBJ) $(LIB_PATH) $(BUILD_MK)
	@echo "  LD  $@"
	@$(CC) $(CFLAGS) $(LDFLAGS) $(EXAMPLE_OBJ) -L$(BUILD_DIR) -l$(LIB) -o $@
	@$(SIZE) $@

$(HEX_PATH): $(ELF_PATH)
	@echo "  HEX $@"
	@$(OBJCOPY) $(HEX_FLAGS) $< $@

$(addprefix $(BUILD_DIR)/,$(DIST_HEADERS)): $(BUILD_DIR)/%: $(INC_DIR)/%
	@cp $< $@

$(BUILD_DIR)/$(DIST_EXAMPLE_MAIN): $(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAIN)
	@cp $< $@

$(BUILD_DIR)/Makefile.example: $(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAKEFILE)
	@cp $< $@

$(addprefix $(BUILD_DIR)/,$(DIST_EMPTY)):
	@touch $@

# Read by the PC tool: python3 mcu_mdt.py build/<part>/build_info.yaml
$(BUILD_DIR)/build_info.yaml: $(BUILD_MK)
	@printf 'platform: %s\nmcu: %s\nport: %s\nbaudrate: %s\nelf: %s\n' \
		"$(shell echo $(TARGET_PLATFORM) | tr a-z A-Z)" "$(TARGET_MCU)" "$(PORT)" "$(TARGET_BAUDRATE)" "$(ELF)" > $@

# shortcut: avrdude command line; becomes per-platform data when STM32 moves to build_system/.
flash: all
	$(FLASH_TOOL) -c $(FLASH_PROGRAMMER) -p $(TARGET_MCU) -P $(PORT) -b $(FLASH_PROGRAMMER_BAUD) -U flash:w:$(HEX_PATH):i

clean:
	@echo "Cleaning $(BUILD_DIR)"
	@rm -rf $(BUILD_DIR)

erase flash-recover:
	$(error '$@' exists only for STM32 (make PLATFORM=stm32 ...))
endif

wipe:
	@echo "Removing all build artifacts..."
	@rm -rf build

clean_logs:
	@echo "Removing logs..."
	@rm -rf logs

help:
	@echo ""
	@echo "Build usage:"
	@echo "  make MCU=<part> [PORT=...] [F_CPU=...] [BAUDRATE=...] [BUFFER_SIZE=...]"
	@echo "                  [BREAKPOINTS=...] [WATCHPOINTS=...] [MDT_USE_UART_IDLE=0|1]"
	@echo "  make MCU=<part> flash"
	@echo "  make MCU=<part> clean"
	@echo "  Supported parts and defaults: build_system/ (AVR); STM32: add PLATFORM=stm32"
	@echo ""
	@echo "STM32 recovery (needs openocd):"
	@echo "  make PLATFORM=stm32 MCU=<mcu> erase          Mass-erase under reset"
	@echo "  make PLATFORM=stm32 MCU=<mcu> flash-recover  Erase + flash a stuck/asleep board"
	@echo ""
	@echo "Maintenance:"
	@echo "  make wipe        Remove ALL build artifacts"
	@echo "  make clean_logs  Remove all session log files"
	@echo ""
