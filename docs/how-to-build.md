# How to Build

This document covers how to build, flash, and integrate MCU-MDT firmware on
all supported platforms (AVR and STM32 Cortex-M0; STM32 Cortex-M3 returns when it
moves to `build_system/`).
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
make MCU=atmega328p PORT=/dev/ttyACM0     # AVR
make MCU=F030F4     PORT=/dev/ttyUSB0     # STM32 Cortex-M0
```

The part name alone picks the platform; `PLATFORM=` is accepted and ignored. Append
`flash` to the same invocation to program the board:

```bash
make MCU=atmega328p PORT=/dev/ttyACM0 flash
make MCU=F030F4 flash
```


## Build variables

The root `Makefile` runs `build_system/generate.py`, which reads the part's YAML
descriptors (`build_system/`, see its README) plus the variables below and writes, in
`build/<mcu>/` (the part name in lower case):

* `build.mk`: toolchain, flags, sources, output formats, platform commands
* `mdt_target.h`: `F_CPU`, baud rate, buffer size, breakpoints, watchpoints and, on
  STM32, the flash/RAM layout; force-included into every C file
* `memory.ld`: the linker's flash and RAM regions (STM32)
* `build_info.yaml`: what the PC tool needs

Defaults live in the YAML; the variables below override them for one build. Only
parts listed in `build_system/<platform>/tree_branch_*.yaml` can be built.

| Variable | Required? | Default | Where used | Purpose |
|---|---|---|---|---|
| `MCU` | yes | none | all | Target part (`atmega328p`, `F030F4`, ...), case-insensitive. It picks the platform and the part's memory layout. |
| `PORT` | no | `/dev/ttyACM0` | flash target, build_info | Serial port. Only matters for `flash` and gets written into `build_info.yaml` for the PC tool. |
| `F_CPU` | no | 16 MHz (AVR), 8 MHz (STM32) | UART baud divisor, delay calculations | CPU frequency. Must match the actual clock the firmware runs at, otherwise the UART baud rate is wrong. |
| `UART_IDLE` | no | `1` (STM32), `0` (AVR) | STM32 only | Selects packet processing mode. Explained below. |
| `BAUDRATE` | no | `19200` | all | MDT UART baud rate; also written into `build_info.yaml` so the PC tool uses it. |
| `BUFFER_SIZE` | no | `64` | all | Ring buffer size: 32, 64 or 128. |
| `BREAKPOINTS`, `WATCHPOINTS` | no | `4` | all | Maximum breakpoints / watchpoints, 1 to 8; the PC tool takes the same numbers from `build_info.yaml`. |


## The `UART_IDLE` flag (STM32 only)

This is the one user-visible mode toggle in the build system. It picks how
the firmware handles inbound UART traffic.

```bash
make MCU=F030F4 PORT=/dev/ttyUSB0               # interrupt mode (default)
make MCU=F030F4 PORT=/dev/ttyUSB0 UART_IDLE=0   # poll mode
```

The build writes the value as `MDT_FEATURE_UART_IDLE` (0 or 1) into
`mdt_target.h`, which every translation unit includes. The library declares the macro mandatory:

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

AVR has no USART IDLE interrupt, so its descriptor declares the feature
unsupported and `UART_IDLE=1` on AVR is rejected with an error.


## The `F_CPU` flag

The default is 16 MHz on AVR (matches Arduino Uno and Nano) and 8 MHz on
STM32 (matches HSI on reset, before any PLL setup). Override it if your
firmware configures a different clock:

```bash
make MCU=F030F4     F_CPU=48000000UL   # HSI x6 via PLL
make MCU=atmega328p F_CPU=8000000UL
```

A wrong `F_CPU` is the most common reason for a non-responsive board. The
UART baud divisor is computed as `F_CPU / MDT_UART_BAUDRATE`, so a 2x
mismatch gives a 2x wrong baud rate and every byte gets corrupted. If
nothing is responding, double-check `F_CPU` first.


## Build output

Each build lands in `build/<mcu>/` (lower case). One directory per part, never
overwritten across MCUs. Objects mirror the source tree inside it (`src/`, `hal/`,
`examples/`). The rest follows the same shape on every platform:

```
build/<mcu>/
├── libmcu_mdt_<platform>.a   # static library (the actual artifact)
├── mcu_mdt.h                 # public header (3 functions + the BREAKPOINT macro)
├── mdt_target.h              # settings this library was built with (generated)
├── mcu_mdt_example.elf       # example application linked against the library
├── mcu_mdt_example.hex       # ready to flash
├── mcu_mdt_example.bin       # ready to flash (STM32)
├── mcu_mdt_example.map       # linker map (STM32)
├── Makefile.example          # drop-in user Makefile (see below)
├── main.c                    # minimal example main
├── build.mk                  # generated Make variables
└── build_info.yaml           # what the PC tool needs (see below)
```

STM32 builds also include `linker.ld`, the generated `memory.ld` and
`startup_stm32f030xx.c`, needed when linking your own project against the library.

### `build_info.yaml`

Written by the generator from the YAML and the settings. The PC tool reads it to:

* Load the part's SVD or ATDF (`mcu_db`, relative to `pc_tool/mcu_db/`) for register
  name resolution.
* Talk at the right speed (`baudrate`) and decide whether to send periodic event-poll
  packets (`uart_idle: true` means yes).
* Accept only the breakpoint and watchpoint slots the firmware has.
* Check memory accesses against the part's memory map (`memory`, STM32; AVR takes it
  from the ATDF).
* Enforce firmware self-protection: the PC tool reads the flash range the firmware
  occupies from the ELF (`elf`) and refuses writes and erases that overlap it.

Example (STM32 F030F4):

```yaml
platform: STM32
mcu: f030f4
mcu_db: stm32/cortex-m0/STM32F0x0.svd
port: /dev/ttyUSB0
baudrate: 19200
uart_idle: true
breakpoints: 4
watchpoints: 4
elf: mcu_mdt_example.elf
memory:
  flash: {origin: 0x08000000, size: 16384, page: 1024}
  ram: {origin: 0x20000000, size: 4096}
```


## Flashing

### AVR

```bash
make MCU=atmega328p PORT=/dev/ttyACM0 flash
```

Uses `avrdude` with the Arduino bootloader protocol at 115200 baud. If
your board uses a different programmer (USBasp, dragon, ...) or baud rate,
edit `commands.flash` in `build_system/avr/tree_trunk.yaml`.

### STM32

```bash
make MCU=F030F4 flash            # st-flash write <bin> 0x08000000
make MCU=F030F4 erase            # OpenOCD mass erase, connecting under reset
make MCU=F030F4 flash-recover    # erase + flash + verify through OpenOCD, for a sleeping or locked core
```

The commands come from `commands:` in the platform's YAML (the flash origin from the
part's memory map). `flash` uses `st-flash` to write the binary to flash at `0x08000000`. Note:
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
make MCU=<mcu> clean                   # remove build/<mcu>/ only
make wipe                              # remove the entire build/ directory
make clean_logs                        # remove logs/ (PC tool session logs)
```

`wipe` and `clean_logs` do not require `MCU`.


## Using the library in your own project

Every build directory ships everything you need for a downstream build:
the static library, the public headers, and a ready-to-use
`Makefile.example`. The workflow is:

1. `cd build/<mcu>/`
2. `mv Makefile.example Makefile`
3. Drop your `.c` files into the directory next to `main.c`.
4. `make MCU=<mcu> PORT=<port>`. Every `.c` in the directory is picked up
   automatically.

The MDT source tree never needs to be touched by your application build.

### Minimal `main.c` for poll mode (AVR, or STM32 with `UART_IDLE=0`)

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

### Minimal `main.c` for STM32 interrupt mode (`UART_IDLE=1`, default)

```c
#include "mcu_mdt.h"

int main(void)
{
    mcu_mdt_init();              /* registers the IDLE callback automatically */

    while (1) {
        /* application code runs freely. UART is handled by ISR + PendSV.
         * mcu_mdt_poll() is NOT required here. Events are reported when
         * the PC polls. */
    }
}
```

Watchpoints in interrupt mode need nothing extra: they are sampled
whenever the PC polls for events (about every 0.5 s).


## Verifying the build

Once flashed and the board is running, connect with the PC tool:

```bash
python3 mcu_mdt.py build/<mcu>/build_info.yaml
PING
```

An ACK response means the firmware boots, the UART is wired correctly,
the baud rate matches, and the protocol is intact. If `PING` fails, see
`docs/troubleshooting.md`.

## Containerized build (Docker)

If you would rather not install the toolchains on your host, the `scripts/`
directory ships a `Dockerfile` and a `docker-compose.yaml` that provide the
full environment (both toolchains, the flashing tools, and the Python runtime
with all dependencies). This is also the most reliable way to get a known-good
build on a machine where the host toolchain versions are uncertain.

The image is based on Ubuntu 24.04 and installs everything the project needs:
`make` and `build-essential`, the AVR toolchain (`gcc-avr`, `avr-libc`,
`avrdude`), the ARM toolchain (`gcc-arm-none-eabi`, `binutils-arm-none-eabi`,
`st-flash`, `openocd`), and the Python packages `pyserial`, `pyyaml`, and
`pyelftools`.

### Services

The compose file defines four services, all built from the same image.

| Service | Purpose |
|---|---|
| `dev` | Interactive shell with the full toolchain. Run any `make` command by hand. |
| `build-avr` | One-shot AVR build. Defaults to `atmega328p`, override with the `MCU` variable. |
| `build-stm32` | One-shot STM32 build. Defaults to `F030F4`, override with the `MCU` variable. |
| `tool` | Runs the PC-side debugger against a built firmware. Needs the serial adapter forwarded. |

### Usage

```bash
# Interactive shell (run anything inside)
docker compose run --rm dev
docker compose run --rm dev make MCU=atmega328p

# One-shot builds
docker compose run --rm build-avr
MCU=atmega2560 docker compose run --rm build-avr
docker compose run --rm build-stm32
MCU=F030F4 docker compose run --rm build-stm32

# Run the PC tool against a built firmware
MCU=F030F4 docker compose run --rm tool
```

The project root is mounted live into the container, so edits on the host take
effect immediately with no rebuild of the image. Build output lands in the same
`build/<mcu>/` directory on the host as a native build would, through a shared
volume.

### Plain Docker without compose

If you prefer not to use compose, build the image and run it directly. Note the
build context is the project root, with the Dockerfile under `scripts/`.

```bash
docker build -t mcu-mdt -f scripts/Dockerfile .
docker run --rm -it -v "$PWD":/workspace mcu-mdt make MCU=F030F4
```

### Forwarding the serial adapter

Building firmware needs no hardware, so the build services do not forward any
USB device. Flashing or running the PC tool from inside a container does need
the adapter, which is why the `tool` service forwards `/dev/ttyUSB0` and the
`dev` service has a commented-out `devices:` block you can enable. Adjust the
device path to match your board (for example `/dev/ttyACM0` for an AVR board).

One caveat worth knowing: forwarding a USB serial adapter into a container is
reliable on a bare-metal Linux host but flaky inside a virtual machine, because
it adds a second passthrough hop on top of the VM's own USB forwarding. If the
adapter does not appear inside the container, run the flashing step and the PC
tool directly on the host instead. Building in the container and
flashing/talking to the board from the host is a perfectly good split.

### Host installer alternative

If you do want the toolchains on the host rather than in a container, the same
`scripts/` directory has an `install.sh` that installs the equivalent packages
on Ubuntu 22.04 and 24.04.

```bash
./scripts/install.sh --avr --stm32 --dev
```

Each flag is optional and pulls in one toolchain group. The base Python runtime
is always installed. Run `./scripts/install.sh --help` for the full list.