# Architecture

## Purpose

This document describes the high-level architecture of the **MCU Debug Tool (MDT)** project. It explains the design goals, layering, module responsibilities, and data flow between the PC-side tool and the MCU-side firmware library.

The goal of this architecture is to provide a **portable, deterministic, and extensible UART-based memory debugger** that can be reused across multiple MCU families with minimal platform-specific code.


## Design Goals

- **Portability**: Core logic is platform-agnostic C; MCU-specific details are isolated in HAL layers.
- **Determinism**: No dynamic memory allocation, bounded buffers, predictable execution.
- **Minimal MCU Complexity**: MCU firmware performs only binary protocol handling and memory access.
- **PC-Side Intelligence**: Parsing, validation, YAML handling, and user interaction live entirely on the PC.
- **Single Entry Point**: MCU exposes a minimal public API (`mcu_mdt_init`, `mcu_mdt_poll`, `mcu_mdt_watchpoint_check`, `MDT_BREAKPOINT`).
- **Non-blocking Operation**: UART I/O is byte-oriented and cooperative.
- **Zero-cost when idle**: when nothing is happening, `mcu_mdt_poll()` does almost nothing —
  overhead scales with actual debugger activity, not constant.
- **No trust assumption**: MCU validates every packet on its own (CRC, START/END, length) —
  a bad packet gets dropped, MCU state is not affected.


## Core Principles

- Portable C code with HAL abstraction
- No MCU-side complexity
- Deterministic behavior
- Everything is statically allocated — buffers, breakpoint state, watchpoint state, event state —
  all known at compile time, no surprises at runtime.


## System Overview

The system consists of two main components:
```
+--------------------+        UART        +---------------------+
| PC Debug Tool      | <---------------> | MCU Firmware (MDT)  |
|                    |                   |                     |
| - CLI              |                   | - Protocol Engine   |
| - YAML Command DB  |                   | - Command Dispatch  |
| - Validation       |                   | - Memory Access     |
| - Serialization    |                   | - Breakpoints       |
| - Event handling   |                   | - Watchpoints       |
+--------------------+                   | - HAL Abstraction   |
                                         +---------------------+
```


## PC-Side Architecture

### Responsibilities

The PC tool is responsible for:

- Parsing user input (CLI commands)
- Handling CLI-only commands (HELP, EXIT, CLEAR, HISTORY)
- Loading and interpreting `commands.yaml`
- Validating command parameters and memory ranges against MCU metadata (ATDF/SVD)
- Serializing commands into binary packets
- Chunking transfers larger than 4 bytes into multiple packets
- UART communication with the target MCU
- Routing incoming packets to response or event queues

The MCU **never** parses text or YAML.

### Layering
```
CLI
 ├── CLI Commands (local-only)
 ├── Validator
 │    ├── Command schema validation
 │    ├── Memory range validation (ATDF / SVD based)
 │    ├── Breakpoint / watchpoint slot validation
 ├── Protocol Encoder/Decoder
 │    ├── Serialization (Command → 18-byte packet)
 │    ├── Deserialization (18-byte packet → CommandPacket)
 │    ├── CRC16 calculation and verification
 └── UART Transport
      ├── rx_worker thread (routes responses / events)
      └── execute_command (chunked send + response collection)
```

### Validation Model

- CLI-only commands are handled immediately and never sent over UART.
- Protocol commands follow a strict flow:
```
parse → validate → serialize → send → receive → verify
```

- Memory validation maps logical memory types (RAM / FLASH / EEPROM) to ATDF/SVD memory segments.
- FLASH writes are rejected by default unless explicitly enabled.
- Watchpoint addresses may be unaligned — the MCU reads 4 bytes byte-by-byte and is safe at any
  address. A warning is logged but the command is not rejected.


## MCU-Side Architecture

### Public API (`mcu_mdt.h`)

```c
void mcu_mdt_init(void);             /* initialize UART, register IDLE callback if available */
void mcu_mdt_poll(void);             /* call from main loop: flush events, drain RX, check watchpoints */
void mcu_mdt_watchpoint_check(void); /* sample all active watchpoints, fire event on change */
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
        ├── 1. flush pending event if TX idle
        ├── 2. fence + overflow guard
        ├── 3. drain RX ring buffer → mdt_process_byte()
        └── 4. mcu_mdt_watchpoint_check()
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
  └── mcu_mdt_poll()
        ├── 1. flush pending event if TX idle
        ├── 2. fence + overflow guard
        ├── 3. drain RX ring buffer (residual bytes between IDLE and poll)
        └── 4. mcu_mdt_watchpoint_check()
```


## HAL Architecture

### Design

Each platform has a single `hal_*.c` file that directly implements `mcu_mdt_hal.h`. There are no
intermediate wrapper layers — the `hal_*` functions are the only entry points.

```
inc/mcu_mdt_hal.h          ← contract (8 functions)
hal/avr/hal_avr.c          ← AVR implementation (UART ISRs + SRAM/FLASH/EEPROM access)
hal/stm32/cortex-m0/hal_stm.c  ← M0 implementation (UART ISRs + SRAM/FLASH access + flash write)
hal/stm32/cortex-m3/hal_stm.c  ← M3 implementation (UART ISRs + SRAM/FLASH access)
```

The `uart.h` files in each STM32 target carry all peripheral register struct definitions and bit
masks. They are included only by `hal_stm.c` — they are not part of the public interface.

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
```

### Platform Differences

| Feature                  | AVR                         | Cortex-M0                   | Cortex-M3                   |
|--------------------------|-----------------------------|-----------------------------|-----------------------------|
| Address space            | Harvard (separate flash bus)| Von Neumann (unified)       | Von Neumann (unified)       |
| Flash read               | `pgm_read_byte()` required  | Plain pointer dereference   | Plain pointer dereference   |
| Flash write              | Not supported               | Half-word (16-bit) only     | Not implemented             |
| UART IDLE interrupt      | Not available               | Available, used             | Available, used             |
| RX processing            | Poll loop (`mcu_mdt_poll`)  | PendSV → `mdt_process_pending` | PendSV → `mdt_process_pending` |
| Register width           | 8-bit (1-byte access)       | 32-bit (4-byte access)      | 32-bit (4-byte access)      |

### Adding a New Platform

1. Create `hal/<platform>/hal_<name>.c` implementing all 11 HAL functions directly.
2. Add a `Makefile` — copy the nearest existing one and adjust toolchain flags.
3. Add startup file and linker script if bare-metal (STM32-style).
4. `src/` is never touched.


## Protocol Design Rationale

- **Why fixed packet size (18 bytes)** — no variable-length parsing needed on the MCU side, buffer
  size is known at compile time, overflow is easy to detect. Short commands (PING) still use 18
  bytes but that is an acceptable tradeoff for simplicity.

- **Why CRC16 and not something simpler** — a plain checksum misses many multi-bit errors common
  on UART lines. CRC16 catches all single/double bit errors and burst errors up to 16 bits for
  just 1 extra byte over CRC8.

- **START/END bytes on top of CRC** — provides a second integrity layer. Also makes resync trivial —
  just wait for 0xAA and start fresh, no reset needed.

- **Little-endian for all multi-byte fields** — AVR and ARM Cortex-M are both little-endian
  natively, so no byte swapping is needed on either side.

- **4 bytes of data per packet, larger transfers split** — keeps packet size fixed. The PC handles
  chunking; the MCU processes one packet at a time using the sequence number to track order.

- **Events are unsolicited packets from the MCU** — same 18-byte format, EVENT flag set, CMD_ID=0.
  The PC `rx_worker` routes them to a separate event queue so they don't block command responses.


## Memory Safety

- **Buffer fencing** — `uint32_t` sentinel values (0xA5A5A5A5) are placed before and after the
  receive buffer inside `mdt_buffer_t`. Every `mcu_mdt_poll()` call checks them. If either is
  corrupted, a `BUFFER_OVERFLOW` event is sent and the buffer resets.

- **RX overflow detection** — if the ring buffer fills before the poll loop drains it, the HAL
  sets an overflow flag. `mcu_mdt_poll()` checks this flag and fires a `BUFFER_OVERFLOW` event.

- **No dynamic allocation anywhere** — `malloc` is never called. The linker knows exact RAM usage
  at build time.


## Breakpoint Design

- **Software, not hardware** — ARM FPB and AVR OCD both require a physical debug probe over JTAG
  or SWD. MDT only needs UART, which every MCU has.

- **How it works** — `MDT_BREAKPOINT(id)` is placed in user code. When hit, the MCU sends a
  `BREAKPOINT_HIT` event and enters a spin loop calling `mcu_mdt_poll()` (poll mode) or processing
  RX via PendSV (interrupt mode) until the PC sends `NEXT` or `DISABLED`.

- **MCU stays responsive while paused** — UART ISRs keep running; the MCU is paused from the
  application's perspective but the debugger can still read/write memory normally.

- **Hit counter** — each breakpoint counts triggers. Useful for catching unexpected re-entry.

- **Breakpoints start disabled** — `.bss` zero-initialization handles this; no init call needed.


## Watchpoint Design

- **How it works** — `mcu_mdt_watchpoint_check()` is called periodically (from `mcu_mdt_poll()`
  or a timer ISR). For each active slot it reads 4 bytes byte-by-byte from the watched address,
  applies the mask, and compares against the stored snapshot. On change it fires a
  `WATCHPOINT_HIT` event and updates the snapshot.

- **Byte-by-byte read** — `mdt_read_u32()` reads 4 bytes individually to avoid undefined behaviour
  from unaligned pointer casts and hardware alignment faults on Cortex-M0.

- **Mask support** — each watchpoint has a 32-bit mask. Only bits set in the mask are compared.
  Default mask is `0xFFFFFFFF` (all bits). Use `WATCHPOINT MASK` to narrow to specific bits.

- **Up to 8 watchpoints** — the active set is tracked by a `uint8_t` bitmask, limiting the
  maximum to 8. Configurable via `MDT_MAX_WATCHPOINTS` (default: 4).

- **Unaligned addresses are allowed** — the byte-by-byte read is safe at any address. The PC
  tool logs a warning for unaligned addresses but does not reject them.


## Build System

- **Three levels** — root Makefile picks the platform, platform Makefile picks the core (e.g.
  cortex-m0 vs cortex-m3), core Makefile does the actual build. Only `MCU` and `PORT` flow
  downward. `INCLUDES` is exported as absolute paths from the root so `-I` flags work everywhere.

- **Automatic header dependency tracking** — `-MMD -MP` generates a `.d` file next to each `.o`.
  Change a header, everything that includes it recompiles automatically.

- **`src_` and `hal_` prefixes on object files** — avoids silent overwrites if a file with the
  same name exists in both `src/` and `hal/`.

- **Linker script preprocessing** — the STM32 linker scripts use `#ifdef` to select flash/RAM
  sizes per MCU. The Makefile runs the C preprocessor over `linker.ld` before passing it to the
  linker, producing `linker_pp.ld` in the build directory.

- **Ships as a `.a`** — user gets the static library plus two headers (`mcu_mdt.h`,
  `mcu_mdt_config.h`) and a ready-to-use `Makefile.example`.


## Testing

Tests are split into three categories and run with the custom `PyMDTest` runner:

```bash
MDT_PORT=/dev/ttyACM0 python3 -m test.pymdtest   # all tests (unit + integration + hardware)
python3 -m test.pymdtest                           # unit + integration only (hardware skipped)
```

| Category    | Location                  | Requires hardware |
|-------------|---------------------------|-------------------|
| Unit        | `test/unit/`              | No                |
| Integration | `test/integration/`       | No                |
| Hardware    | `test/hardware/`          | Yes (MDT_PORT)    |

The `@parametrize` decorator is custom (`test/pymdtest.py`) and is not compatible with pytest.
Always use `python3 -m test.pymdtest` to run tests — not `pytest` directly.

Environment variables for hardware tests:

| Variable       | Default      | Description                        |
|----------------|--------------|------------------------------------|
| `MDT_PORT`     | unset        | Serial port (e.g. `/dev/ttyACM0`)  |
| `MDT_BAUD`     | 19200        | Baud rate                          |
| `MDT_TIMEOUT`  | 2.0          | Per-packet read timeout (seconds)  |
| `MDT_PLATFORM` | avr          | `avr` or `stm32`                   |


## Known Issues

- **4 hardware tests fail** against the current firmware:
  - `test_hw_bad_crc_triggers_nack` and `test_hw_nack_seq_mirrors_request_seq` — `is_nack_packet()`
    on the PC side requires `cmd_id == 0`, but the firmware echoes the original `cmd_id` in the
    NACK. One side needs to be fixed to agree on the NACK format.
  - `test_hw_failed_packet_event_has_event_flag` and `test_hw_rx_worker_routes_event_to_event_queue`
    — cascade from the above; the FAILED_PACKET event is only sent on the next `mcu_mdt_poll()`
    after the NACK, which may arrive after the test's read timeout on AVR poll mode.
