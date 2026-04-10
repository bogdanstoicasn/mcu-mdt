# ===== Root Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p [F_CPU=16000000UL]

# Targets that do NOT require PLATFORM/MCU
NO_CONFIG_TARGETS := wipe help clean_logs

# Returns non-empty ONLY if at least one goal REQUIRES config
REQUIRES_CONFIG := $(filter-out $(NO_CONFIG_TARGETS),$(MAKECMDGOALS))

# Only enforce configuration if target requires it
ifneq ($(REQUIRES_CONFIG),)

ifndef PLATFORM
$(error PLATFORM is not set. Example: PLATFORM=avr)
endif

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

endif

# Public include directories (exported to sub-makefiles)
INCLUDES := -I$(CURDIR)/inc -I$(CURDIR)/hal
export INCLUDES

# Optional: Port
PORT ?= /dev/ttyACM0

PLATFORM_MAKE := hal/$(PLATFORM)/Makefile

# Only check platform file when configuration is required
ifneq ($(REQUIRES_CONFIG),)
ifeq ("$(wildcard $(PLATFORM_MAKE))","")
$(error Unsupported PLATFORM '$(PLATFORM)'. No file '$(PLATFORM_MAKE)')
endif
endif

.PHONY: all clean flash wipe clean_logs help

BUILD_INFO_FILE := ./build/$(MCU)/build_info.yaml

# Helper: only pass F_CPU if defined
F_CPU_ARG := $(if $(F_CPU),F_CPU=$(F_CPU))

all:
	@echo "Building for PLATFORM=$(PLATFORM), MCU=$(MCU)"
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) $(F_CPU_ARG)

flash:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) $(F_CPU_ARG) flash

clean:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) $(F_CPU_ARG) clean

wipe:
	@echo "Removing all build artifacts..."
	@rm -rf build
	@echo "All build artifacts removed."

clean_logs:
	@echo "Removing logs..."
	@rm -rf logs
	@echo "Logs removed."

help:
	@echo ""
	@echo "Build usage:"
	@echo "  make PLATFORM=<platform> MCU=<mcu> [F_CPU=...]"
	@echo "  make PLATFORM=<platform> MCU=<mcu> flash [F_CPU=...]"
	@echo "  make PLATFORM=<platform> MCU=<mcu> clean"
	@echo ""
	@echo "Maintenance:"
	@echo "  make wipe        Remove ALL build artifacts"
	@echo "  make clean_logs  Remove all session log files"
	@echo ""