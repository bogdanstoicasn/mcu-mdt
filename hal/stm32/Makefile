# ===== STM32 Platform Router =====
# Called from root Makefile with MCU, PORT variables
# Example: make PLATFORM=stm32 MCU=F030F4

MCU_UPPER := $(shell echo $(MCU) | tr '[:lower:]' '[:upper:]')

# Map STM32 chip family prefix -> Cortex-M core subdirectory
ifneq ($(filter F0%,$(MCU_UPPER)),)
  CORE := cortex-m0
else ifneq ($(filter F1%,$(MCU_UPPER)),)
  CORE := cortex-m3
else
  $(error "Unsupported STM32 MCU family: $(MCU)")
endif

CORE_MAKE := $(CURDIR)/$(CORE)/Makefile

ifeq ("$(wildcard $(CORE_MAKE))","")
  $(error No Makefile at hal/stm32/$(CORE_MAKE) — core '$(CORE)' not yet implemented)
endif

.PHONY: all clean flash

all:
	@echo "STM32 router: MCU=$(MCU) -> $(CORE)"
	@$(MAKE) -C $(CORE) MCU=$(MCU) PORT=$(PORT)

flash:
	@$(MAKE) -C $(CORE) MCU=$(MCU) PORT=$(PORT) flash

clean:
	@$(MAKE) -C $(CORE) MCU=$(MCU) PORT=$(PORT) clean
