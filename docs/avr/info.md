# AVR Platform

## Overview

The AVR HAL supports a wide range of ATmega microcontrollers using USART0.
Support is determined by the ATDF files in `pc_tool/mcu_db/avr/` and the UART vector
portability layer in `hal_avr.c`.


## Libraries Required

- AVR Libc (https://github.com/avrdudes/avr-libc/)
- AVR-GCC toolchain (https://gcc.gnu.org/wiki/avr-gcc)


## Building

```bash
make PLATFORM=avr MCU=<mcu> PORT=<port>
```

Example:
```bash
make PLATFORM=avr MCU=atmega328p PORT=/dev/ttyACM0
```

Optional — override CPU frequency (default is 16 MHz):
```bash
make PLATFORM=avr MCU=atmega328p PORT=/dev/ttyACM0 F_CPU=8000000UL
```

Build output is placed in `build/<MCU>/`:
```
build/atmega328p/
├── libmcu_mdt_avr.a       # static library to link against
├── mcu_mdt.h              # public header
├── mcu_mdt_config.h       # configuration header
├── mcu_mdt_example.elf    # example binary
├── mcu_mdt_example.hex    # ready to flash
├── Makefile.example       # user Makefile for custom projects
├── main.c                 # example main
└── build_info.yaml        # platform/mcu/port metadata
```


## Flashing

```bash
make PLATFORM=avr MCU=atmega328p PORT=/dev/ttyACM0 flash
```

Uses `avrdude` with the Arduino bootloader protocol at 115200 baud. If your board uses a
different programmer or baud rate, edit the `flash` target in `hal/avr/Makefile`.

Common port values:

| OS      | Port                  |
|---------|-----------------------|
| Linux   | `/dev/ttyACM0`        |
| Linux   | `/dev/ttyUSB0`        |
| macOS   | `/dev/cu.usbmodem*`   |
| Windows | `COM3`, `COM4`, ...   |


## Using the Library in Your Own Project

After building, go to `build/<MCU>/` and rename `Makefile.example` to `Makefile`.
Drop your `.c` files alongside `main.c` and run:
```bash
make MCU=atmega328p PORT=/dev/ttyACM0
```

All `.c` files in the directory are picked up automatically. The library, headers, and
example are all self-contained in the build directory — no need to touch the MDT source tree.

Minimal `main.c`:
```c
#include "mcu_mdt.h"

int main(void) {
    mcu_mdt_init();

    while (1) {
        mcu_mdt_poll(); // drains UART RX, flushes events, checks watchpoints

        // your application code here
        MDT_BREAKPOINT(0); // optional breakpoint
    }
}
```

Watchpoints on AVR — call `mcu_mdt_watchpoint_check()` from `mcu_mdt_poll()` (done automatically)
or from a timer ISR if you need higher-frequency sampling:
```c
ISR(TIMER0_COMPA_vect) {
    mcu_mdt_watchpoint_check();
}
```


## Cleaning

```bash
make PLATFORM=avr MCU=atmega328p clean   # removes build/atmega328p/
make wipe                                 # removes entire build/ directory
```


## HAL Structure

The AVR HAL is a single file:

```
hal/avr/hal_avr.c    — UART ISRs, ring buffer, SRAM/FLASH/EEPROM access
```

All 11 HAL functions (`hal_uart_*`, `hal_read_memory`, `hal_write_memory`,
`hal_read_register`, `hal_write_register`) are implemented directly in `hal_avr.c`
with no intermediate wrapper layers.

Key AVR-specific details:
- USART0 is used exclusively by the MDT UART driver.
- Flash is on a separate Harvard bus — reads use `pgm_read_byte()`, not plain pointer dereference.
- EEPROM reads use `eeprom_read_byte()`, writes use `eeprom_write_block()`.
- Registers are memory-mapped into SRAM space — register access is a 1-byte SRAM read/write.
- There is no UART IDLE interrupt on AVR. `hal_uart_set_idle_callback()` is a no-op stub;
  all RX processing happens in `mcu_mdt_poll()`.
- UART vectors are resolved at compile time via portability defines:
  `USART_RX_vect` / `USART_UDRE_vect` for single-UART parts (ATmega328P, ATmega168),
  `USART0_RX_vect` / `USART0_UDRE_vect` for multi-UART parts (ATmega2560, ATmega1280).


## Adding ATDF Support for a New MCU

If your MCU is not in the supported list below, you can add support by:

1. Downloading the ATDF file for your MCU from [Microchip Packs](https://packs.download.microchip.com/).
2. Placing it in `pc_tool/mcu_db/avr/atmega/`.
3. The PC tool picks it up automatically on next run.
4. If your MCU uses a different UART vector name, add it to the portability block in `hal_avr.c`.


## Supported MCUs

Support is based on USART0 availability and ATDF files. MCUs in the list below work out of the
box. MCUs not in the list but with a compatible USART0 setup may work with a minor tweak to the
vector portability block in `hal_avr.c`.

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


## Notes

1. Do not use USART0 in your application code — it is owned by the MDT UART driver.
2. Blocking calls (`_delay_ms`, busy-wait loops) will freeze breakpoint and watchpoint handling
   for their duration. Keep blocking sections short or restructure to cooperative polling.
3. The baud rate is set at compile time via `MDT_UART_BAUDRATE` in `mcu_mdt_config.h`
   (default 19200). Match this on the PC side with `MDT_BAUD=19200`.
