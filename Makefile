# ===== mcu-mdt build =====
# make MCU=<part> [all | flash | clean]       make wipe | clean_logs | help
# Optional settings, defaults in build_system/: PORT F_CPU BAUDRATE BUFFER_SIZE BREAKPOINTS WATCHPOINTS UART_IDLE
#
# build_system/generate.py turns the part's YAML plus those settings into build/<part>/build.mk
# (included below), mdt_target.h (force-included into every .c) and build_info.yaml (PC tool).
# It rewrites a file only when its content changes, so it runs on every make.
# Nothing in here is platform specific: a new platform is YAML only.

SETTINGS := PORT F_CPU BAUDRATE BUFFER_SIZE BREAKPOINTS WATCHPOINTS UART_IDLE

.PHONY: all flash clean wipe clean_logs help

ifneq ($(filter-out wipe clean_logs help,$(or $(MAKECMDGOALS),all)),)
ifndef MCU
$(error MCU is not set. Example: make MCU=atmega328p)
endif
GEN_DIR := $(shell python3 build_system/generate.py $(MCU) $(foreach s,$(SETTINGS),$(if $($(s)),$(s)=$($(s)))))
ifneq ($(.SHELLSTATUS),0)
$(error build_system/generate.py failed, see the message above)
endif
include $(GEN_DIR)/build.mk

CFLAGS  += -MMD -MP -I$(INC_DIR) -I$(HAL_DIR) -include $(BUILD_DIR)/mdt_target.h
OBJS    := $(patsubst %.c,$(BUILD_DIR)/%.o,$(wildcard $(SRC_DIR)/*.c $(HAL_DIR)/*.c))
MAIN    := $(BUILD_DIR)/$(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAIN:.c=.o)
LIB_A   := $(BUILD_DIR)/lib$(LIB).a

# Builds the library and the example, then puts what a user project needs next to them.
all: $(BUILD_DIR)/$(HEX)
	@cp $(addprefix $(INC_DIR)/,$(DIST_HEADERS)) $(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAIN) $(BUILD_DIR)/
	@cp $(EXAMPLE_DIR)/$(DIST_EXAMPLE_MAKEFILE) $(BUILD_DIR)/Makefile.example
	@touch $(addprefix $(BUILD_DIR)/,$(DIST_EMPTY))

# build.mk is a prerequisite so changed flags rebuild; mdt_target.h is tracked by the .d files.
$(BUILD_DIR)/%.o: %.c $(BUILD_DIR)/build.mk
	@mkdir -p $(@D)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

$(LIB_A): $(OBJS)
	@echo "  AR  $@"
	@rm -f $@ && $(AR) rcs $@ $^

$(BUILD_DIR)/$(ELF): $(MAIN) $(LIB_A)
	@echo "  LD  $@"
	@$(CC) $(CFLAGS) $(LDFLAGS) $(MAIN) -L$(BUILD_DIR) -l$(LIB) -o $@
	@$(SIZE) $@

$(BUILD_DIR)/$(HEX): $(BUILD_DIR)/$(ELF)
	@echo "  HEX $@"
	@$(OBJCOPY) $(HEX_FLAGS) $< $@

-include $(OBJS:.o=.d) $(MAIN:.o=.d)

flash: all
	$(FLASH_CMD)

clean:
	rm -rf $(BUILD_DIR)
endif

wipe:
	rm -rf build

clean_logs:
	rm -rf logs

help:
	@sed -n '2,3p' Makefile | cut -c3-
