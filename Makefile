# ===== Root Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p

ifndef PLATFORM
$(error PLATFORM is not set. Example: PLATFORM=avr)
endif

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

# Optional: Port
PORT ?= /dev/ttyACM0

PLATFORM_MAKE := hal/$(PLATFORM)/Makefile

ifeq ("$(wildcard $(PLATFORM_MAKE))","")
$(error Unsupported PLATFORM '$(PLATFORM)'. No file '$(PLATFORM_MAKE)')
endif

.PHONY: all clean

BUILD_INFO_FILE := build_info.yaml

all:
	@$(MAKE) -f $(PLATFORM_MAKE) MCU=$(MCU) PORT=$(PORT)
	@echo "platform: $(PLATFORM)" > $(BUILD_INFO_FILE)
	@echo "mcu: $(MCU)" >> $(BUILD_INFO_FILE)
	@echo "port: $(PORT)" >> $(BUILD_INFO_FILE)

clean:
	@$(MAKE) -f $(PLATFORM_MAKE) MCU=$(MCU) PORT=$(PORT) clean
