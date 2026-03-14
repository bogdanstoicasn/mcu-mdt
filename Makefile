# ===== Root Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p

# Targets that do NOT require PLATFORM/MCU
NO_CONFIG_TARGETS := wipe help

# Only enforce configuration if target requires it
ifneq ($(filter $(NO_CONFIG_TARGETS),$(MAKECMDGOALS)),wipe)
ifneq ($(filter $(NO_CONFIG_TARGETS),$(MAKECMDGOALS)),help)

ifndef PLATFORM
$(error PLATFORM is not set. Example: PLATFORM=avr)
endif

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

endif
endif

# Public include directories (exported to sub-makefiles)
INCLUDES := -I$(CURDIR)/inc -I$(CURDIR)/hal
export INCLUDES

# Optional: Port
PORT ?= /dev/ttyACM0

PLATFORM_MAKE := hal/$(PLATFORM)/Makefile

# Only check platform file when configuration is required
ifneq ($(filter $(NO_CONFIG_TARGETS),$(MAKECMDGOALS)),wipe)
ifneq ($(filter $(NO_CONFIG_TARGETS),$(MAKECMDGOALS)),help)
ifeq ("$(wildcard $(PLATFORM_MAKE))","")
$(error Unsupported PLATFORM '$(PLATFORM)'. No file '$(PLATFORM_MAKE)')
endif
endif
endif

.PHONY: all clean flash wipe help

BUILD_INFO_FILE := ./build/$(MCU)/build_info.yaml

all:
	@echo "Building for PLATFORM=$(PLATFORM), MCU=$(MCU)"
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT)

flash:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) flash

clean:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) clean

wipe:
	@echo "Removing all build artifacts..."
	@rm -rf build
	@echo "All build artifacts removed."

help:
	@echo ""
	@echo "Build usage:"
	@echo "  make PLATFORM=<platform> MCU=<mcu>"
	@echo "  make PLATFORM=<platform> MCU=<mcu> flash"
	@echo "  make PLATFORM=<platform> MCU=<mcu> clean"
	@echo ""
	@echo "Maintenance:"
	@echo "  make wipe      Remove ALL build artifacts"
	@echo ""