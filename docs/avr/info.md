# AVR Platform

This document covers AVR-specific reference material: toolchain, HAL
details, and the supported MCU list. For build instructions, flashing,
and the user-project integration pattern see `docs/how-to-build.md`.


## Overview

The AVR HAL supports a wide range of ATmega microcontrollers using
USART0. Support is determined by the ATDF files in
`pc_tool/mcu_db/avr/` and the UART vector portability layer in
`hal_avr.c`. AVR hardware has no UART IDLE interrupt, so AVR builds
always run in poll mode regardless of the `MDT_USE_UART_IDLE` flag.


## Libraries required

* AVR Libc: https://github.com/avrdudes/avr-libc/
* AVR-GCC toolchain: https://gcc.gnu.org/wiki/avr-gcc


## HAL structure

The AVR HAL is a single file:

```
hal/avr/hal_avr.c    UART ISRs, ring buffer, SRAM/FLASH/EEPROM access
```

All HAL functions (`hal_uart_*`, `hal_read_memory`, `hal_write_memory`,
`hal_read_register`, `hal_write_register`, `hal_reset`) are implemented
directly in `hal_avr.c` with no intermediate wrapper layers.

Things to know about the AVR HAL:

* **USART0 is used exclusively** by the MDT UART driver. Do not touch it
  from application code.
* **Flash is on a separate Harvard bus.** Reads go through
  `pgm_read_byte()`, not plain pointer dereference. Flash writes are not
  supported on AVR.
* **EEPROM** reads use `eeprom_read_byte()` and writes use
  `eeprom_write_block()`.
* **Registers are memory-mapped** into SRAM space, so register access is
  just a 1-byte SRAM read or write.
* **No UART IDLE interrupt.** `hal_uart_set_idle_callback()` is a no-op
  stub; all RX processing happens inside `mcu_mdt_poll()`.
* **UART vectors are resolved at compile time.** For single-UART parts
  (ATmega328P, ATmega168) the vectors are `USART_RX_vect` and
  `USART_UDRE_vect`. For multi-UART parts (ATmega2560, ATmega1280) they
  are `USART0_RX_vect` and `USART0_UDRE_vect`. A portability block at
  the top of `hal_avr.c` picks the right names.


## Adding ATDF support for a new MCU

If your MCU is not in the supported list below you can add it:

1. Download the ATDF file from
   [Microchip Packs](https://packs.download.microchip.com/).
2. Drop it in `pc_tool/mcu_db/avr/atmega/`.
3. The PC tool picks it up automatically on next run.
4. If your MCU uses a different UART vector name, add it to the
   portability block in `hal_avr.c`.


## Supported MCUs

Support is based on USART0 availability and ATDF files. MCUs in the
list below work out of the box. MCUs not listed but with a compatible
USART0 setup may work with a minor tweak to the vector portability
block in `hal_avr.c`.

| MCU | MCU | MCU | MCU |
|-----|-----|-----|-----|
| ATmega48 | ATmega48A | ATmega48P | ATmega48PA |
| ATmega48PB | ATmega88 | ATmega88A | ATmega88P |
| ATmega88PA | ATmega88PB | ATmega128 | ATmega128A |
| ATmega128RFA1 | ATmega128RFR2 | ATmega162 | ATmega164A |
| ATmega164P | ATmega164PA | ATmega165A | ATmega165P |
| ATmega165PA | ATmega168 | ATmega168A | ATmega168P |
| ATmega168PA | ATmega168PB | ATmega169A | ATmega169P |
| ATmega169PA | ATmega256RFR2 | ATmega324A | ATmega324P |
| ATmega324PA | ATmega324PB | ATmega325 | ATmega325A |
| ATmega325P | ATmega325PA | ATmega328 | ATmega328P |
| ATmega328PB | ATmega329 | ATmega329A | ATmega329P |
| ATmega329PA | ATmega640 | ATmega644 | ATmega644A |
| ATmega644P | ATmega644PA | ATmega644RFR2 | ATmega645 |
| ATmega645A | ATmega645P | ATmega649 | ATmega649A |
| ATmega649P | ATmega1280 | ATmega1281 | ATmega1284 |
| ATmega1284P | ATmega1284RFR2 | ATmega2560 | ATmega2561 |
| ATmega2564RFR2 | ATmega3250 | ATmega3250A | ATmega3250P |
| ATmega3250PA | ATmega3290 | ATmega3290A | ATmega3290P |
| ATmega3290PA | ATmega6450 | ATmega6450A | ATmega6450P |
| ATmega6490 | ATmega6490A | ATmega6490P | ATmegaS128 |
| AT90CAN32 | AT90CAN64 | AT90CAN128 | |


## Watchpoints on AVR

`mcu_mdt_poll()` calls `mcu_mdt_watchpoint_check()` once per pass, so on
AVR the sampling rate equals main-loop frequency. If you need higher
sampling rate, call `mcu_mdt_watchpoint_check()` from a timer ISR:

```c
ISR(TIMER0_COMPA_vect) {
    mcu_mdt_watchpoint_check();
}
```


## Application notes

1. **Do not use USART0** in your application code. It is owned by the
   MDT UART driver.
2. **Avoid blocking calls.** `_delay_ms`, busy-wait loops, and similar
   will freeze breakpoint and watchpoint handling for their duration.
   Keep blocking sections short or restructure to cooperative polling.
3. **Baud rate is set at compile time** via `MDT_UART_BAUDRATE` in
   `mcu_mdt_config.h` (default 19200). The PC side must match with
   `MDT_BAUD=19200`.
4. **No flash write support.** The MCU returns an error for FLASH writes
   and ERASE commands. EEPROM is the only writable persistent memory on
   AVR.