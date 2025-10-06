# ===== Root Makefile =====
# Usage: make PLATFORM=avr MCU=atmega328p

ifndef PLATFORM
$(error PLATFORM is not set. Example: PLATFORM=avr)
endif

ifndef MCU
$(error MCU is not set. Example: MCU=atmega328p)
endif

PLATFORM_MAKE := hal/$(PLATFORM)/Makefile

ifeq ("$(wildcard $(PLATFORM_MAKE))","")
$(error Unsupported PLATFORM '$(PLATFORM)'. No file '$(PLATFORM_MAKE)')
endif

.PHONY: all clean

all:
	@$(MAKE) -f $(PLATFORM_MAKE) MCU=$(MCU)

clean:
	@$(MAKE) -f $(PLATFORM_MAKE) MCU=$(MCU) clean