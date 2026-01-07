# ===== Root Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p

ifndef PLATFORM
$(error PLATFORM is not set. Example: PLATFORM=avr)
endif

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

# Public include directories (exported to sub-makefiles)
INCLUDES := -I$(CURDIR)/inc -I$(CURDIR)/hal
export INCLUDES

# Optional: Port
PORT ?= /dev/ttyACM0

PLATFORM_MAKE := hal/$(PLATFORM)/Makefile

ifeq ("$(wildcard $(PLATFORM_MAKE))","")
$(error Unsupported PLATFORM '$(PLATFORM)'. No file '$(PLATFORM_MAKE)')
endif

.PHONY: all clean

BUILD_INFO_FILE := ./build/$(MCU)/build_info.yaml

all:
	@echo "Building for PLATFORM=$(PLATFORM), MCU=$(MCU)"
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT)

flash:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) flash

clean:
	@$(MAKE) -C hal/$(PLATFORM) MCU=$(MCU) PORT=$(PORT) clean