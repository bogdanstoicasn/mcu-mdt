# How to Build

This document covers how to build, flash, and integrate MCU-MDT firmware on
all supported platforms (AVR, STM32 Cortex-M0, and STM32 Cortex-M3).
Platform-specific reference material (supported MCU lists, HAL notes,
processing-mode details) lives in `docs/avr/info.md` and
`docs/stm32/info.md`.


## Toolchain

| Platform | Required toolchain | Flashing tool |
|---|---|---|
| AVR | AVR-GCC + AVR Libc | `avrdude` |
| STM32 (M0, M3) | `arm-none-eabi-gcc` + binutils | `st-flash` from [stlink-org/stlink](https://github.com/stlink-org/stlink) |

Python 3.10+ is needed for the PC tool.


## Quick start

```bash
# AVR
make PLATFORM=avr   MCU=atmega328p PORT=/dev/ttyACM0

# STM32 Cortex-M0
make PLATFORM=stm32 MCU=F030F4     PORT=/dev/ttyUSB0

# STM32 Cortex-M3
make PLATFORM=stm32 MCU=F103C8     PORT=/dev/ttyUSB0
```

Append `flash` to the same invocation to program the board:

```bash
make PLATFORM=avr   MCU=atmega328p PORT=/dev/ttyACM0 flash
make PLATFORM=stm32 MCU=F030F4     PORT=/dev/ttyUSB0 flash
```


## Build variables

The build is driven entirely by command-line variables. The root `Makefile`
dispatches into `hal/<platform>/Makefile`, which (for STM32) dispatches
again into `hal/stm32/<core>/Makefile`. Only the variables in the table
below are user-facing. Everything else (`FLASH_PAGE_SIZE`,
`FLASH_XL_DENSITY`, `CPU_FLAGS`) is derived from `MCU` automatically.

| Variable | Required? | Default | Where used | Purpose |
|---|---|---|---|---|
| `PLATFORM` | yes | none | root Makefile | `avr` or `stm32`. Picks the HAL directory. |
| `MCU` | yes | none | all | Target part (`atmega328p`, `F030F4`, `F103C8`, ...). On STM32 this also drives the linker script preprocessing and the per-MCU `FLASH_PAGE_SIZE`. |
| `PORT` | no | `/dev/ttyACM0` | flash target, build_info | Serial port. Only matters for `flash` and gets written into `build_info.yaml` for the PC tool. |
| `F_CPU` | no | 16 MHz (AVR), 8 MHz (STM32) | UART baud divisor, delay calculations | CPU frequency. Must match the actual clock the firmware runs at, otherwise the UART baud rate is wrong. |
| `MDT_USE_UART_IDLE` | no | `1` (STM32), forced `0` (AVR) | STM32 only | Selects packet processing mode. Explained below. |


## The `MDT_USE_UART_IDLE` flag (STM32 only)

This is the one user-visible mode toggle in the build system. It picks how
the firmware handles inbound UART traffic.

```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0                       # interrupt mode (default)
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 MDT_USE_UART_IDLE=0   # poll mode
```

The Makefile injects the value as `-DMDT_FEATURE_UART_IDLE=<0|1>` into
every translation unit. `mcu_mdt_config.h` declares the macro mandatory:

```c
#ifndef MDT_FEATURE_UART_IDLE
#error "MDT_FEATURE_UART_IDLE must be defined by the build system."
#endif
```

This is on purpose: if the build system forgets to set the flag, the
source tree refuses to compile. That way a silently-wrong default cannot
sneak into a custom build.

| Value | Mode | What happens |
|---|---|---|
| `1` | Interrupt | USART1 IDLE interrupt triggers PendSV; packet processing runs in the ISR chain. `main()` runs freely. The PC tool sends a CMD_ID=0 poll every 500 ms so the MCU can flush events. |
| `0` | Poll | RXNE and TXE interrupts still drive the ring buffers, but packet processing happens inside `mcu_mdt_poll()`. `main()` has to call `mcu_mdt_poll()` regularly. Events fire opportunistically from the same call. |

Which one to use:

* Use `1` (the default) if `main()` calls blocking APIs (`HAL_Delay`,
  blocking I2C/SPI), if you run an RTOS, or if you simply do not want to
  think about it.
* Use `0` if you have a tight cooperative loop or want deterministic
  packet-processing timing.

The protocol on the wire is identical in both modes (same packets, same
CRC, same commands, same event format). The flag only controls who drives
the RX dispatch on the MCU side.

AVR is hardcoded to `MDT_USE_UART_IDLE=0` in `hal/avr/Makefile` because
the USART hardware has no IDLE interrupt. Setting the flag on the AVR
command line has no effect.


## The `F_CPU` flag

The default is 16 MHz on AVR (matches Arduino Uno and Nano) and 8 MHz on
STM32 (matches HSI on reset, before any PLL setup). Override it if your
firmware configures a different clock:

```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 F_CPU=48000000UL   # HSI x6 via PLL
make PLATFORM=stm32 MCU=F103C8 PORT=/dev/ttyUSB0 F_CPU=72000000UL   # HSE x9 via PLL
make PLATFORM=avr   MCU=atmega328p PORT=/dev/ttyACM0 F_CPU=8000000UL
```

A wrong `F_CPU` is the most common reason for a non-responsive board. The
UART baud divisor is computed as `F_CPU / MDT_UART_BAUDRATE`, so a 2x
mismatch gives a 2x wrong baud rate and every byte gets corrupted. If
nothing is responding, double-check `F_CPU` first.


## Build output

Each build lands in `build/<MCU>/`. One directory per part, never
overwritten across MCUs. The contents differ slightly by platform but
follow the same shape:

```
build/<MCU>/
├── libmcu_mdt_<platform>.a   # static library (the actual artifact)
├── mcu_mdt.h                 # public header (3 functions + the BREAKPOINT macro)
├── mcu_mdt_config.h          # configurable knobs (BAUDRATE, BUFFER_SIZE, ...)
├── mcu_mdt_example.elf       # example application linked against the library
├── mcu_mdt_example.hex       # ready to flash (AVR)
├── mcu_mdt_example.bin       # ready to flash (STM32)
├── Makefile.example          # drop-in user Makefile (see below)
├── main.c                    # minimal example main
└── build_info.yaml           # platform / mcu / port / firmware metadata for the PC tool
```

STM32 builds also include `mcu_mdt_hal.h`, `ring_buffer.h`, `linker.ld`,
and `startup_stm32f<family>.c`. These are needed when linking your own
project against the library.

### `build_info.yaml`

Generated automatically at link time. The PC tool reads it to:

* Decide which SVD or ATDF to load for register name resolution.
* Decide whether to send periodic event-poll packets (`uart_idle: 1`
  means yes).
* Enforce firmware self-protection. `firmware_start_address` and
  `firmware_end_address` come from `wc -c` on the linked `.bin` file and
  define the range the validator refuses to overwrite or erase. STM32
  only; AVR has no flash-write support, so these fields are absent.

Example (STM32 F030F4):

```yaml
platform: STM32
core: cortex-m0
mcu: F030F4
port: /dev/ttyUSB0
elf: mcu_mdt_example.elf
uart_idle: 1
flash_page_size: 0x400
firmware_start_address: 0x08000000
firmware_end_address:   0x080034a0
firmware_size:          13472
```


## Flashing

### AVR

```bash
make PLATFORM=avr MCU=atmega328p PORT=/dev/ttyACM0 flash
```

Uses `avrdude` with the Arduino bootloader protocol at 115200 baud. If
your board uses a different programmer (USBasp, dragon, ...) or baud rate,
edit the `flash` target in `hal/avr/Makefile`.

### STM32

```bash
make PLATFORM=stm32 MCU=F030F4 PORT=/dev/ttyUSB0 flash
```

Uses `st-flash` to write the binary to flash at `0x08000000`. Note:
`st-flash` performs a mass erase before writing, so anything already in
flash is gone. `PORT` is ignored for STM32 flashing because `st-flash`
finds the ST-Link by itself over USB.

### Picking a port

| OS | Typical port |
|---|---|
| Linux | `/dev/ttyACM0`, `/dev/ttyUSB0` |
| macOS | `/dev/cu.usbmodem*` |
| Windows | `COM3`, `COM4`, ... |


## Cleaning

```bash
make PLATFORM=<plat> MCU=<mcu> clean   # remove build/<MCU>/ only
make wipe                              # remove the entire build/ directory
make clean_logs                        # remove logs/ (PC tool session logs)
```

`wipe` and `clean_logs` do not require `PLATFORM` or `MCU`.


## Using the library in your own project

Every build directory ships everything you need for a downstream build:
the static library, the public headers, and a ready-to-use
`Makefile.example`. The workflow is:

1. `cd build/<MCU>/`
2. `mv Makefile.example Makefile`
3. Drop your `.c` files into the directory next to `main.c`.
4. `make MCU=<mcu> PORT=<port>`. Every `.c` in the directory is picked up
   automatically.

The MDT source tree never needs to be touched by your application build.

### Minimal `main.c` for poll mode (AVR, or STM32 with `MDT_USE_UART_IDLE=0`)

```c
#include "mcu_mdt.h"

int main(void)
{
    mcu_mdt_init();

    while (1) {
        mcu_mdt_poll();          /* drains RX, flushes events, samples watchpoints */

        /* your application code here */

        MDT_BREAKPOINT(0);       /* optional software breakpoint */
    }
}
```

### Minimal `main.c` for STM32 interrupt mode (`MDT_USE_UART_IDLE=1`, default)

```c
#include "mcu_mdt.h"

int main(void)
{
    mcu_mdt_init();              /* registers the IDLE callback automatically */

    while (1) {
        /* application code runs freely. UART is handled by ISR + PendSV.
         * mcu_mdt_poll() is NOT required here. Watchpoints can be sampled
         * from SysTick if you want continuous monitoring. */
    }
}
```

If you want watchpoints in interrupt mode, sample them from a periodic
source:

```c
void SysTick_Handler(void) { mcu_mdt_watchpoint_check(); }
```


## Verifying the build

Once flashed and the board is running, connect with the PC tool:

```bash
python3 mcu_mdt.py build/<MCU>/build_info.yaml
PING
```

An ACK response means the firmware boots, the UART is wired correctly,
the baud rate matches, and the protocol is intact. If `PING` fails, see
`docs/troubleshooting.md`.