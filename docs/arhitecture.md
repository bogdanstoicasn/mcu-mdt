# Architecture

## Purpose

This document describes the high-level architecture of the **MCU Debug Tool (MDT)** project. It explains the design goals, layering, module responsibilities, and data flow between the PC-side tool and the MCU-side firmware library.

The goal of this architecture is to provide a **portable, deterministic, and extensible UART-based memory debugger** that can be reused across multiple MCU families with minimal platform-specific code.


## Design Goals

- **Portability**: Core logic is platform-agnostic C; MCU-specific details are isolated in HAL layers.
- **Determinism**: No dynamic memory allocation, bounded buffers, predictable execution.
- **Minimal MCU Complexity**: MCU firmware performs only binary protocol handling and memory access.
- **PC-Side Intelligence**: Parsing, validation, YAML handling, and user interaction live entirely on the PC.
- **Single Entry Point**: MCU exposes a minimal public API with a single polling function.
- **Non-blocking Operation**: UART I/O is byte-oriented and cooperative.
- **Zero-cost when idle**: when nothing is happening, `mcu_mdt_poll()` does almost nothing —
  overhead scales with actual debugger activity, not constant.
- **No trust assumption**: MCU validates every packet on its own (CRC, START/END, length) —
  a bad packet gets dropped, MCU state is not affected.


## Core Principles

- Portable C code with HAL abstraction
- No MCU-side complexity
- Deterministic behavior
- Everything is statically allocated — buffers, breakpoint state, event state — all known at
  compile time, no surprises at runtime.


## System Overview

The system consists of two main components:
```
+--------------------+        UART        +---------------------+
| PC Debug Tool      | <---------------> | MCU Firmware (MDT)  |
|                    |                   |                     |
| - CLI              |                   | - Protocol Engine   |
| - YAML Command DB  |                   | - Command Dispatch  |
| - Validation       |                   | - Memory Access     |
| - Serialization    |                   | - HAL Abstraction   |
+--------------------+                   +---------------------+
```


## PC-Side Architecture

### Responsibilities

The PC tool is responsible for:

- Parsing user input (CLI commands)
- Handling CLI-only commands (HELP, EXIT, CLEAR, HISTORY)
- Loading and interpreting `commands.yaml`
- Validating command parameters and memory ranges
- Serializing commands into binary packets
- UART communication with the target MCU

The MCU **never** parses text or YAML.

### Layering
```
CLI
 ├── CLI Commands (local-only)
 ├── Validator
 │    ├── Command schema validation
 │    ├── Memory range validation (ATDF-based)
 ├── Protocol Encoder/Decoder
 └── UART Transport
```

### Validation Model

- CLI-only commands are handled immediately and never sent over UART.
- Protocol commands follow a strict flow:
```
parse -> validate -> serialize -> send
```

- Memory validation maps logical memory types (RAM / FLASH / EEPROM) to ATDF memory segments.
- FLASH writes are rejected by default unless explicitly enabled.


## Protocol Design Rationale

- **Why fixed packet size (18 bytes)** — no variable-length parsing needed on the MCU side, buffer
  size is known at compile time, overflow is easy to detect. Downside is that short commands
  (like PING) still use 18 bytes but that's an acceptable tradeoff.

- **Why CRC16 and not something simpler** — a plain checksum misses a lot of multi-bit errors that
  are pretty common on UART lines. CRC8 was an option but CRC16 catches much more for just 1 extra
  byte. Catches all single/double bit errors and burst errors up to 16 bits.

- **START/END bytes on top of CRC** — even if CRC somehow passes on a corrupted packet (very
  unlikely but possible), the missing framing bytes will catch it. Also makes resync easy —
  just wait for 0xAA and start fresh, no need to reset the connection.

- **Little-endian for address and length fields** — both AVR and ARM Cortex-M0 are little-endian
  natively so no byte swapping needed on either side.

- **4 bytes of data per packet, larger transfers are split** — keeps the packet size fixed.
  The PC handles the chunking, the MCU just processes packets one at a time using the sequence
  number to track order.

- **Events are unsolicited packets from the MCU** — the MCU can tell the PC something happened
  (breakpoint hit, buffer overflow) without waiting to be asked. Same 18-byte format, just with
  the EVENT flag set so the PC knows it's not a command response.


## Memory Safety

- **Buffer fencing** — there are `uint32_t` sentinel values (0xA5A5A5A5) placed before and after
  the receive buffer inside `mdt_buffer_t`. Every call to `mcu_mdt_poll()` checks them. If either
  is corrupted it means something wrote outside the buffer — probably a stack overflow or a bad
  pointer. When this happens a `BUFFER_OVERFLOW` event is sent to the PC and the buffer resets.
  Better to know about it than to silently process garbage.

- **Fencing is internal, not a public feature** — it's tied to the buffer struct and not something
  the HAL or user code needs to know about. Just an internal safety net.

- **No dynamic allocation anywhere** — `malloc` is never called. Everything is statically allocated.
  The linker knows the exact RAM usage at build time.


## Breakpoint Design

- **Why software breakpoints and not hardware** — ARM has FPB, AVR has OCD, but both need a
  physical debug probe over JTAG or SWD. MDT only needs UART which every MCU has. Much more
  portable.

- **How it works** — user adds `MDT_BREAKPOINT(id)` in their code where they want to pause.
  When hit, the MCU sends a breakpoint event to the PC and enters a loop calling `mcu_mdt_poll()`
  until the user resumes. While paused, the PC can still read/write memory normally.

- **MCU stays responsive while paused** — because the breakpoint loop keeps calling
  `mcu_mdt_poll()`, UART RX/TX ISRs are still running and commands still get processed.
  The MCU is "paused" from the application's perspective but not from the debugger's perspective.

- **NEXT command** — sets a flag inside the breakpoint struct that causes the loop to exit on the
  next poll. Basically a "resume" button.

- **Hit counter** — each breakpoint keeps track of how many times it was triggered. Useful for
  catching unexpected re-entry into a code path without staring at the PC tool output.

- **Breakpoints start disabled automatically** — they're declared as `static volatile` so they
  land in `.bss` which the C runtime zeroes before `main()`. No init function needed, they're
  always off at startup.

- **Why cooperative polling and not interrupts for everything** — `mcu_mdt_poll()` is called by
  the user in their main loop. This means the debugger has no hidden background activity, no
  surprise preemption, easy to reason about timing. The cost is that `delay()` or any blocking
  call will freeze the debugger temporarily but that's a known and acceptable tradeoff.


## HAL Contract

- **What the HAL must provide**:
  - `hal_uart_rx` — non-blocking, returns 0 if no byte ready
  - `hal_uart_tx` — safe to call from main loop
  - `hal_uart_tx_ready` — true if TX buffer has space
  - `hal_read_memory` / `hal_write_memory` — return 1 on success, 0 on failure

- **What the HAL keeps to itself** — IRQ setup, ring buffer internals, clock config. The core
  engine doesn't care how bytes get moved, just that the contract above is met.

- **Adding a new platform** — implement the 5 HAL functions, write a UART driver with ISR-driven
  ring buffers, add startup file + linker script + Makefile. The `src/` folder never changes.


## Build System

- **Three levels** — root Makefile picks the platform, platform Makefile picks the core (e.g.
  cortex-m0), core Makefile does the actual build. Only `MCU` and `PORT` flow downward.
  `INCLUDES` is exported as absolute paths from the root so `-I` flags work everywhere.

- **Automatic header dependency tracking** — `-MMD -MP` generates a `.d` file next to each `.o`.
  Change a header, everything that includes it recompiles automatically.

- **`src_` and `hal_` prefixes on object files** — avoids silent overwrites if a file with the
  same name exists in both `src/` and `hal/` (e.g. both having a `uart.c`).

- **Ships as a `.a`** — user gets the static library plus two headers. The build directory also
  contains a ready-to-use Makefile that picks up any `.c` files the user drops next to `main.c`.


## Implementation Notes (to expand later)

- **`volatile` on breakpoints and event union** — accessed from main context, can be preempted.
  Without `volatile` the compiler might cache stale values in registers.

- **`__attribute__((noinline))` on `mdt_breakpoint_trigger`** — keeps it as a real stack frame,
  shows up properly in a backtrace if a probe is connected alongside MDT.

- **`mdt_event_t` union** — type and data packed into one `uint32_t`. The `raw == 0` idle check
  works without any locking because of the cooperative execution model.

- **Sequence number field** — used now for multi-packet chunking, but the field is there for
  future use too (retransmit, out-of-order detection).