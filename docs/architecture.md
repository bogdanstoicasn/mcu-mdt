# Architecture

## Purpose

This document describes the high-level architecture of the **MCU Debug Tool (MDT)** project. It explains the design goals, layering, module responsibilities, and data flow between the PC-side tool and the MCU-side firmware library.

The goal of this architecture is to provide a **portable, deterministic, and extensible UART-based memory debugger** that can be reused across multiple MCU families with minimal platform-specific code.


## Design Goals

- **Portability**: Core logic is platform-agnostic C; MCU-specific details are isolated in HAL layers.
- **Determinism**: No dynamic memory allocation, bounded buffers, predictable execution.
- **Minimal MCU Complexity**: MCU firmware performs only binary protocol handling and memory access.
- **PC-Side Intelligence**: Parsing, validation, YAML handling, and user interaction live entirely on the PC.
- **Single Entry Point**: MCU exposes a minimal public API (check `mcu_mdt.h` for the exposed functions).
- **Non-blocking Operation**: UART I/O is byte-oriented and cooperative.
- **Zero-cost when idle**: when nothing is happening, `mcu_mdt_poll()` does almost nothing.
  Overhead scales with actual debugger activity, not constant.
- **No trust assumption**: MCU validates every packet on its own (CRC, START/END, length).
  A bad packet gets dropped, MCU state is not affected.


## Core Principles

- Portable C code with HAL abstraction
- No MCU-side complexity
- Deterministic behavior
- Everything is statically allocated (buffers, breakpoint state, watchpoint state, event state),
  all known at compile time, no surprises at runtime.


## System Overview

The system consists of two main components:
```
+---------------------+        UART        +---------------------+
| PC tool (pc_tool/)  | <---------------> | MCU Firmware (MDT)  |
|                     |                   |                     |
| - Prompt / scripts  |                   | - Protocol Engine   |
| - Part description  |                   | - Command Dispatch  |
|   (ATDF / SVD, ELF) |                   | - Memory Access     |
| - Command rules     |                   | - Breakpoints       |
| - Wire protocol     |                   | - Watchpoints       |
| - Event handling    |                   | - HAL Abstraction   |
+---------------------+                   +---------------------+
```


## PC-Side Architecture

The PC tool (`pc_tool/`) does everything the firmware doesn't. It reads the part's description
and the build, parses what you type, refuses what would hurt the MCU, and talks the wire
protocol. The MCU never parses text.

### Modules

Twelve flat modules in four layers. A module imports only modules from the layers below it,
and `test/unit/test_layers.py` fails if one doesn't.

| Layer | Module | Job |
|---|---|---|
| app | `cli_main.py` | Arguments, logging, connect, run, shut down, exit status |
| | `debug_session.py` | One path for every line: parse, check, send, show. Prompt and script mode |
| | `user_console.py` | The prompt (history, TAB), HELP, the packet box, the event line, the log handlers |
| transport | `event_pump.py` | Reader thread that decodes and routes every packet; the event poller in UART-idle mode |
| | `command_client.py` | Sends one command: a packet per word, waits for each reply, retries |
| | `serial_link.py` | The port (any pyserial URL), framed reads, locked writes, the reply queue |
| domain | `command_rules.py` | Accepts a command for this target, or says why not |
| | `command_parser.py` | One line to one `Command`, by `configs/commands.yaml` |
| | `target_model.py` | The `Target`: memory, peripherals, registers, symbols, slot counts, firmware range |
| | `device_description.py` | Reads an ATDF or SVD into peripherals, registers and memory segments |
| | `elf_symbols.py` | RAM symbols and the flash image range of the ELF |
| protocol | `wire_protocol.py` | Ids, flags, offsets, `encode`/`decode`, CRC, events |

The domain modules don't print and don't start threads. They return values or raise an error
whose message is meant for the user; every such error derives from `pc_tool.MdtError`.

### One command, start to finish

```
line ──▶ command_parser.parse ──▶ command_rules.check ──▶ command_client.run ──▶ user_console.packet
         CommandError (2)         CommandError (3)        NoReplyError (4)
```

`EXIT`, `HELP` and `CLEAR` are `local: true` in `commands.yaml` and stop after parsing.

The client holds the link lock for a whole exchange, so the event poll can't slip a packet in
between. Each packet waits for the reply that echoes its command id, sequence and address. A
NACK, a timeout or a reply with a bad CRC means a resend, three sends at most.

### Threads

- **main**: the prompt or the script, and every command.
- **reader** (`event_pump`): reads every packet, decodes it, queues replies for the client and
  hands events to the console. If the port fails (unplugged adapter), it wakes the main thread,
  which shuts down normally.
- **poller** (UART-idle mode only): sends a CMD_ID 0 packet every 0.5 s so the MCU can report
  its events.

Both stop through a `threading.Event`. The link is closed on every way out.

### What the rules check

- READ_MEM / WRITE_MEM: the whole range lies in one segment of the right kind (RAM, flash,
  EEPROM) of this part, and the data length matches.
- READ_REG / WRITE_REG: the address is one of the part's registers; a write needs a writable one.
- BREAKPOINT / WATCHPOINT: the slot exists in the firmware that was built (`build_info.yaml`).
- WATCHPOINT ENABLED: the 4 watched bytes are in RAM or on a register. The MCU reads them on
  every sample, and an unmapped address faults an STM32. An unaligned address is allowed (the MCU
  reads byte by byte) but warned about.
- Flash writes and erases stay off the running firmware (next section).

### Output and logging

Every module logs to `logging.getLogger(__name__)`, below the `pc_tool` logger. `cli_main`
gives that logger two handlers:

- **the log file** `logs/mdt_<mcu>_<date>_<time>.log`: everything, as
  `[HH:MM:SS] [LEVEL](code): message`, between a session header and footer.
- **the console**: warnings and errors (`WARN:  ...`, `ERROR: ... (code)`), plus the lines
  marked for the user.

Script mode turns the console off; the log file still gets everything. The packet box and the
event line are written by `user_console`, one write each.

Error codes: **1** the session can't start (build, port, script file), **2** the line doesn't
parse, **3** the target refuses it, **4** no reply from the MCU, **5** the serial port failed.


## MCU-Side Architecture

### Public API (`mcu_mdt.h`)

```c
void mcu_mdt_init(void);             /* initialize UART, register IDLE callback if available */
void mcu_mdt_poll(void);             /* poll mode: report events, drain RX (no-op in interrupt mode) */
MDT_BREAKPOINT(id);                  /* macro: trigger a software breakpoint */
```

`src/` never changes between platforms. All platform differences live in `hal/`.

### Module Responsibilities

| Module                    | Responsibility                                              |
|---------------------------|-------------------------------------------------------------|
| `mcu_mdt.c`               | Poll loop, byte framing, buffer management, event send/receive |
| `mcu_mdt_protocol.c`      | CRC16, packet validation, command dispatch table            |
| `mcu_mdt_breakpoints.c`   | Breakpoint state, trigger loop, NEXT/DISABLE/RESET control  |
| `mcu_mdt_watchpoint.c`    | Watchpoint state, memory sampling, change detection         |
| `hal/<platform>/hal_*.c`  | UART init/ISR/ring buffer, memory read/write                |

### Execution Flow

**Poll mode (AVR, or STM32 without IDLE interrupt):**
```
main loop
  └── mcu_mdt_poll()
        ├── 1. report one pending event if TX idle (samples watchpoints)
        ├── 2. fence + overflow guard
        └── 3. drain RX ring buffer → mdt_process_byte()
```

**Interrupt mode (STM32 with IDLE interrupt):**
```
USART1_IRQHandler
  ├── RXNE → rb_push(rx_buffer)
  ├── IDLE → set pending_flag, trigger PendSV
  └── TXE  → rb_pop(tx_buffer) → USART1->tdr

PendSV_Handler (lowest priority)
  └── idle_callback() → mdt_process_pending()
        └── drain RX ring buffer → mdt_process_byte()

main loop
  └── mcu_mdt_poll()   (no-op in interrupt mode: events go out in the CMD_ID=0 poll reply)
```


## HAL Architecture

### Design

Each platform has a single `hal_*.c` file that directly implements `mcu_mdt_hal.h`. There are no
intermediate wrapper layers, the `hal_*` functions are the only entry points.

```
inc/mcu_mdt_hal.h          - contract (12 functions)
hal/avr/hal_avr.c          - AVR implementation (UART ISRs + SRAM/FLASH/EEPROM access)
hal/stm32/cortex-m0/hal_stm.c  - M0 implementation (UART ISRs + SRAM/FLASH access + flash write)
hal/stm32/cortex-m3/hal_stm.c  - M3 implementation (UART ISRs + SRAM/FLASH access + flash write)
```

The `uart.h` files in each STM32 target carry all peripheral register struct definitions and bit
masks. They are included only by `hal_stm.c`, they are not part of the public interface.

### HAL Contract

```c
void    hal_uart_init(void);
uint8_t hal_uart_tx_buf(const uint8_t *buf, uint8_t len);
uint8_t hal_uart_rx(uint8_t *byte);
uint8_t hal_uart_tx_ready(void);
uint8_t hal_uart_tx_empty(void);
uint8_t hal_uart_rx_overflow(void);
void    hal_uart_set_idle_callback(void (*cb)(void));  /* no-op stub on AVR */

uint8_t hal_read_memory(uint8_t zone, uint32_t address, uint8_t *buf, uint16_t len);
uint8_t hal_write_memory(uint8_t zone, uint32_t address, const uint8_t *buf, uint16_t len);
uint8_t hal_read_register(uint32_t address, uint8_t *buf);
uint8_t hal_write_register(uint32_t address, const uint8_t *buf);

void    hal_reset(void);  /* drains TX, then resets MCU; does not return */
```

### Platform Differences

| Feature                  | AVR                         | Cortex-M0                   | Cortex-M3                   |
|---------------------------|------------------------------|--------------------------------|--------------------------------|
| Address space             | Harvard (separate flash bus) | Von Neumann (unified)          | Von Neumann (unified)          |
| Flash read                | `pgm_read_byte()` required   | Plain pointer dereference      | Plain pointer dereference      |
| Flash write               | Not supported (architecture) | Half-word (16-bit) only        | Half-word (16-bit) only        |
| Flash erase               | Not supported (architecture) | 1 KB or 2 KB pages             | 1 KB or 2 KB pages             |
| XL-density dual-bank      | N/A                          | N/A                            | F103xF/xG (bank 2: 0x08080000)|
| UART IDLE interrupt       | Not available                | Available, used                | Available, used                |
| RX processing             | Poll loop (`mcu_mdt_poll`)   | PendSV → `mdt_process_pending` | PendSV → `mdt_process_pending` |
| Register width            | 8-bit (1-byte access)        | 32-bit (4-byte access)         | 32-bit (4-byte access)         |

1. Create `hal/<platform>/hal_<name>.c` implementing all 12 HAL functions directly.
2. Add a `Makefile`, copy the nearest existing one and adjust toolchain flags.
3. Add startup file and linker script if bare-metal (STM32-style).
4. `src/` is never touched.


## Protocol Design Rationale

- **Why fixed packet size (18 bytes)**: no variable-length parsing needed on the MCU side, buffer
  size is known at compile time, overflow is easy to detect. Short commands (PING) still use 18
  bytes but that is an acceptable tradeoff for simplicity.

- **Why CRC16 and not something simpler**: a plain checksum misses many multi-bit errors common
  on UART lines. CRC16 catches all single/double bit errors and burst errors up to 16 bits for
  just 1 extra byte over CRC8.

- **START/END bytes on top of CRC**: provides a second integrity layer. Also makes resync trivial:
  just wait for 0xAA and start fresh, no reset needed.

- **Little-endian for all multi-byte fields**. AVR and ARM Cortex-M are both little-endian
  natively, so no byte swapping is needed on either side.

- **4 bytes of data per packet, larger transfers split**: keeps packet size fixed. The PC handles
  chunking; the MCU processes one packet at a time using the sequence number to track order.

- **Events are unsolicited packets from the MCU**: same 18-byte format, EVENT flag set, CMD_ID=0.
  The PC's reader thread hands them to the console, so they never wait behind a command reply.


## Firmware Protection

The PC tool won't let you erase or overwrite the firmware that is running. `target_model` reads
the protected range from the ELF: the span of its load segments that fall in flash (code,
read-only data and the initial values of `.data`), which is exactly what objcopy writes to the
`.bin`/`.hex`. The erase page comes from the flash segment of the memory map (the build's for
STM32, the ATDF's for AVR).

`command_rules` uses it twice:

- **FLASH write**: a write whose bytes `[address, address + len)` touch the image is rejected.
- **ERASE**: the whole page holding `address` is checked against the image.

The ELF is the one named in `build_info.yaml`, or the one you give with `--elf`. If it is missing,
or nothing of it loads into flash, the tool warns that flash writes and erases are not checked.


## Part Descriptions and Register Names

`device_description` reads the part's description file (`mcu_db` in `build_info.yaml`) into
peripherals and their registers (address, size in bytes, writable or not), plus the ATDF memory
segments.

- **SVD** is read by the CMSIS-SVD rules, so any vendor's file works (STM32, NXP MCX, ...):
  `derivedFrom` on peripherals, clusters and registers; `dim` arrays (`NAME[%s]` and `%s` with
  `dimIndex`); cluster and register names joined with `_` (`CH0_CTRL`); size and access inherited
  device → peripheral → cluster → register, 32-bit read-write when no level says; a register in an
  `alternateGroup` that reuses a name becomes `NAME_GROUP`.
- **ATDF** sizes are in bytes, so a 16-bit AVR register (`UBRR0`) covers both its addresses.

READ_REG and WRITE_REG take a hex address or a name, any case:

1. **Qualified** `PERIPHERAL_REGISTER` (`USART1_BRR`, `TIM1_CCMR1_Output`). When peripheral
   names overlap, the longest one wins: `TIM1_CH_X` is register `X` of `TIM1_CH` if it exists.
2. **Bare** `REGISTER` (`UDR0`): the first register with that name, in file order. AVR names
   are unique, so this is the usual form there.

`NAME[3]` is the same as `NAME3`.


## Memory Safety

- **Buffer fencing**: `uint32_t` sentinel values (0xA5A5A5A5) are placed before and after the
  receive buffer inside `mdt_buffer_t`. Every `mcu_mdt_poll()` call checks them. If either is
  corrupted, a `BUFFER_OVERFLOW` event is sent and the buffer resets.

- **RX overflow detection**: if the ring buffer fills before the poll loop drains it, the HAL
  sets an overflow flag. `mcu_mdt_poll()` checks this flag and fires a `BUFFER_OVERFLOW` event.

- **No dynamic allocation anywhere**: `malloc` is never called. The linker knows exact RAM usage
  at build time.


## Breakpoint Design

- **Software, not hardware**. ARM FPB and AVR OCD both require a physical debug probe over JTAG
  or SWD. MDT only needs UART, which every MCU has.

- **How it works**: `MDT_BREAKPOINT(id)` is placed in user code. When hit, the MCU sends a
  `BREAKPOINT_HIT` event and enters a spin loop calling `mcu_mdt_poll()` (poll mode) or processing
  RX via PendSV (interrupt mode) until the PC sends `NEXT` or `DISABLED`.

- **MCU stays responsive while paused**. UART ISRs keep running; the MCU is paused from the
  application's perspective but the debugger can still read/write memory normally.

- **Hit counter**: each breakpoint counts triggers. Useful for catching unexpected re-entry.

- **Breakpoints start disabled**: `.bss` zero-initialization handles this; no init call needed.
  This is also the recovery path from a hung breakpoint: a power cycle clears `bp_state` and
  the MCU resumes normal execution on the next boot.

### Design rationale: no hardware timeout

The breakpoint spin loop has no timeout, and that's on purpose. The MCU does
not run a watchdog or timer-based countdown that would automatically release a
held breakpoint. I came to this decision for three reasons.

**1. The MCU cannot claim a peripheral.** This whole project is built around
the idea that the user keeps every peripheral on their MCU. The PC tool only
needs UART, and UART is the only piece of hardware MDT takes. If I added a
timeout I would have to claim SysTick on Cortex-M or TIMER0 on AVR, and that
would conflict with FreeRTOS (which uses SysTick for its scheduler tick on
basically every Cortex-M port), with `millis()` style timing on AVR, with PWM
on TIMER0 pins, and with any user code that just wants to use the timer for
its own thing. So a timeout costs the user a peripheral, which breaks the
core promise of the tool.

**2. Breakpoint control belongs to the user.** The PC tool also does not
auto-disable breakpoints on exit. I considered adding that, but it would
teach the user that the debugger cleans up after them, which is only true on
a clean exit. If the PC crashes or the cable is yanked the auto-disable
never runs, so the user would have learned the wrong habit. Instead the PC
tool warns at `BREAKPOINT N ENABLED` time and the user disables the slot
themselves.

**3. A silent timeout would be worse than no timeout.** Imagine a 60-second
timeout. The user sets a breakpoint, walks away to think for two minutes,
comes back. The MCU is now running again, but the user does not know that.
They read state believing it is paused state, and they are now debugging
phantom values. A loud failure where the MCU is obviously stuck and the user
has to power-cycle is much safer than a quiet failure where the MCU silently
resumed.

The three reasons above are independent, and any one of them is enough on
its own. Together they uniquely point at the current design: a busy-wait spin
loop the user owns, recovery by power-cycle if the link breaks.

Power-cycle recovery is clean because `bp_state` lives in `.bss` and zeroes
itself on every cold boot. There is no recovery script to run and no flash
state to clear. The user pulls the USB cable, plugs it back in, and the
breakpoints are gone.

A future v1.1 could add a SysTick-based timeout that calls `hal_reset()`
after some configurable silence, but it would have to be opt-in. The user
must agree to give up a peripheral before MDT is allowed to claim one.


## Watchpoint Design

- **How it works**: whenever events are polled (every `mcu_mdt_poll()` pass in poll mode, every
  CMD_ID=0 poll from the PC in interrupt mode), `mdt_watchpoint_take_change()` reads, for each
  active slot, 4 bytes byte-by-byte from the watched address, applies the mask, and compares
  against the stored snapshot. On a difference it reports one `WATCHPOINT_HIT` (old = snapshot,
  new = current) and updates the snapshot. Nothing is queued: several changes between two
  samples collapse into one event.

- **Byte-by-byte read**: `mdt_read_u32()` reads 4 bytes individually to avoid undefined behaviour
  from unaligned pointer casts and hardware alignment faults on Cortex-M0.

- **Mask support**: each watchpoint has a 32-bit mask. Only bits set in the mask are compared.
  Default mask is `0xFFFFFFFF` (all bits). Use `WATCHPOINT MASK` to narrow to specific bits.

- **Up to 8 watchpoints**: the active set is tracked by a `uint8_t` bitmask, limiting the
  maximum to 8. Set with `make ... WATCHPOINTS=` (default: 4); the PC tool takes the same
  count from `build_info.yaml`.

- **Unaligned addresses are allowed**: the byte-by-byte read is safe at any address. The PC
  tool logs a warning for unaligned addresses but does not reject them.


## Build System

- **Description, then build**: `build_system/` describes every part as a YAML tree (root,
  platform trunk, family branch, part node; see `build_system/README.md`). On every `make`,
  `build_system/generate.py` turns the part's description plus the command-line settings into
  `build/<mcu>/build.mk`, `mdt_target.h`, `memory.ld` and `build_info.yaml`. One root Makefile,
  with no platform knowledge, does the build from `build.mk`.

- **Automatic header dependency tracking**: `-MMD -MP` generates a `.d` file next to each `.o`.
  Change a header, everything that includes it recompiles automatically.

- **Objects mirror the source tree** (`build/<mcu>/src/...`, `build/<mcu>/hal/...`), so files
  with the same name in `src/` and `hal/` never overwrite each other.

- **Memory layout from the part**: each STM32 core has one `linker.ld` that includes the
  generated `memory.ld` (flash and RAM regions with the node's sizes); the same sizes reach the
  C code (`MDT_FLASH_*`, `MDT_RAM_*`) and the PC tool (`build_info.yaml`).

- **Ships as a `.a`**: user gets the static library plus two headers (`mcu_mdt.h`,
  `mdt_target.h`) and a ready-to-use `Makefile.example`.


## Testing

`docs/testing.md` has the details. In short:

```bash
python3 -m test.pymdtest              # everything that needs no board
python3 -m test.pymdtest golden       # the whole tool against a fake MCU, about 25 seconds
MCU=F030F4 python3 -m test.pymdtest hardware   # needs a board, or Renode
```


## Known Issues

- None