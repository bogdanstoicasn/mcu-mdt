# ===== mcu-mdt build =====
# make MCU=<part> [all | clean | flash | <other command of the platform>]    make wipe | clean_logs | help
# Optional settings, defaults in build_system/: PORT F_CPU BAUDRATE BUFFER_SIZE BREAKPOINTS WATCHPOINTS UART_IDLE
#
# build_system/generate.py turns the part's YAML plus those settings into build/<part>/build.mk
# (included below), mdt_target.h (force-included into every .c), memory.ld (when the part
# describes its memory) and build_info.yaml (PC tool). It rewrites a file only when its content
# changes, so it runs on every make. Nothing in here is platform specific: a new platform is YAML only.

SETTINGS := PORT F_CPU BAUDRATE BUFFER_SIZE BREAKPOINTS WATCHPOINTS UART_IDLE

.PHONY: all clean wipe clean_logs help

ifneq ($(filter-out wipe clean_logs help,$(or $(MAKECMDGOALS),all)),)
ifndef MCU
$(error MCU is not set. Example: make MCU=atmega328p)
endif
GEN_DIR := $(shell python3 build_system/generate.py $(MCU) $(foreach s,$(SETTINGS),$(if $($(s)),$(s)=$($(s)))))
ifneq ($(.SHELLSTATUS),0)
$(error build_system/generate.py failed, see the message above)
endif
include $(GEN_DIR)/build.mk

CFLAGS      += -MMD -MP -I$(INC_DIR) -I$(HAL_DIR) -I$(BUILD_DIR) -include $(BUILD_DIR)/mdt_target.h
OBJS        := $(patsubst %.c,$(BUILD_DIR)/%.o,$(filter-out $(STARTUP),$(wildcard $(SRC_DIR)/*.c $(HAL_DIR)/*.c)))
STARTUP_OBJ := $(STARTUP:%.c=$(BUILD_DIR)/%.o)
MAIN        := $(EXAMPLE:%.c=$(BUILD_DIR)/%.o)
LIB_A       := $(BUILD_DIR)/lib$(LIB).a
IMAGES      := $(addprefix $(IMAGE).,$(OUTPUTS))

# Builds the library and the example, then puts what a user project needs next to them.
all: $(IMAGES)
	@cp $(DIST_FILES) $(BUILD_DIR)/
	@cp $(DIST_MAKEFILE) $(BUILD_DIR)/Makefile.example

# build.mk is a prerequisite so changed flags rebuild; mdt_target.h is tracked by the .d files.
$(BUILD_DIR)/%.o: %.c $(BUILD_DIR)/build.mk
	@mkdir -p $(@D)
	@echo "  CC  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

$(LIB_A): $(OBJS)
	@echo "  AR  $@"
	@rm -f $@ && $(AR) rcs $@ $^

# The startup file (vector table, reset handler) belongs to the program, not the library.
$(IMAGE).elf: $(STARTUP_OBJ) $(MAIN) $(LIB_A)
	@echo "  LD  $@"
	@$(CC) $(LDFLAGS) $(STARTUP_OBJ) $(MAIN) -L$(BUILD_DIR) -l$(LIB) $(LDLIBS) -o $@
	@$(SIZE) $@

$(IMAGES): $(IMAGE).%: $(IMAGE).elf
	@echo "  OBJCOPY $@"
	@$(OBJCOPY) $(OBJCOPY_FLAGS_$*) $< $@

-include $(OBJS:.o=.d) $(STARTUP_OBJ:.o=.d) $(MAIN:.o=.d)

# Platform commands (flash, erase, ...) come from the YAML; each runs on a fresh build.
.PHONY: $(COMMANDS)
$(COMMANDS): all
	$(CMD_$@)

clean:
	rm -rf $(BUILD_DIR)
endif

wipe:
	rm -rf build

clean_logs:
	rm -rf logs

help:
	@sed -n '2,3p' Makefile | cut -c3-
