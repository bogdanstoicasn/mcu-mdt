# AVR Platform

## Overview

The AVR HAL supports a wide range of ATmega microcontrollers. Support is
determined by the last table of this document.

## Libraries required

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

Optional — override CPU frequency (default is 16MHz):
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
| OS      | Port             |
|---------|------------------|
| Linux   | `/dev/ttyACM0`   |
| Linux   | `/dev/ttyUSB0`   |
| macOS   | `/dev/cu.usbmodem*` |
| Windows | `COM3`, `COM4`... |


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
        mcu_mdt_poll();

        // your application code here
        MDT_BREAKPOINT(0); // optional breakpoint
    }
}
```


## Cleaning
```bash
make PLATFORM=avr MCU=atmega328p clean   # removes build/atmega328p/
make wipe                                 # removes entire build/ directory
```


## Adding ATDF Support for a New MCU

If your MCU is not in the supported list below, you can add support by:

1. Downloading the ATDF file for your MCU from [Microchip Packs](https://packs.download.microchip.com/)
2. Placing it in `pc_tool/mcu_db/avr/`
3. The PC tool will pick it up automatically on next run
4. Update the `uart.c` file if your MCU has a different UART register layout (e.g. ATtiny series)


## Supported MCUs

Support is based on uart configuration and ATDF files. If your MCU is in the list below, it should work out of the box. If it's not,
but has a similar UART setup to a supported MCU, it might work with a minor tweak to `uart.c`. If it's not in the list and has a very different UART setup, it will require more work to add support.

| MCU | MCU | MCU | MCU |
|-----|-----|-----|-----|
| ATtiny441 | ATtiny841 | ATtiny1634 | ATmega48 |
| ATmega48A | ATmega48P | ATmega48PA | ATmega48PB |
| ATmega88 | ATmega88A | ATmega88P | ATmega88PA |
| ATmega88PB | ATmega128 | ATmega128A | ATmega128RFA1 |
| ATmega128RFR2 | ATmega162 | ATmega164A | ATmega164P |
| ATmega164PA | ATmega165A | ATmega165P | ATmega165PA |
| ATmega168 | ATmega168A | ATmega168P | ATmega168PA |
| ATmega168PB | ATmega169A | ATmega169P | ATmega169PA |
| ATmega256RFR2 | ATmega324A | ATmega324P | ATmega324PA |
| ATmega325 | ATmega325A | ATmega325P | ATmega325PA |
| ATmega328 | ATmega328P | ATmega328PB | ATmega329 |
| ATmega329A | ATmega329P | ATmega329PA | ATmega640 |
| ATmega644 | ATmega644A | ATmega644P | ATmega644PA |
| ATmega644RFR2 | ATmega645 | ATmega645A | ATmega645P |
| ATmega649 | ATmega649A | ATmega649P | ATmega1280 |
| ATmega1281 | ATmega1284 | ATmega1284P | ATmega1284RFR2 |
| ATmega2560 | ATmega2561 | ATmega2564RFR2 | ATmega3250 |
| ATmega3250A | ATmega3250P | ATmega3250PA | ATmega3290 |
| ATmega3290A | ATmega3290P | ATmega3290PA | ATmega6450 |
| ATmega6450A | ATmega6450P | ATmega6490 | ATmega6490A |
| ATmega6490P | ATmegaS128 | AT90CAN32 | AT90CAN64 |
| AT90CAN128 | | | |

## Notes

1. Don't use USART0 for your application code, as it's used by the debugger.