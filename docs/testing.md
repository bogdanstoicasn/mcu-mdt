# MCU-MDT — Testing

## Overview

MCU-MDT testing splits across three layers: unit, integration, and hardware. Unit and
integration tests run anywhere with no hardware attached. Hardware tests require a real
MCU flashed with the MDT firmware.

**214 tests total, 214 passing.**


## Test Runner — PyMDTest

The project uses a custom runner (`test/pymdtest.py`), not pytest. It auto-discovers
any file matching `test_*.py`, runs every function whose name starts with `test_`, and
expands `@parametrize` cases. Assertions come from `test/common/asserts.py`.

```bash
python3 -m test.pymdtest              # everything
python3 -m test.pymdtest unit         # unit only
python3 -m test.pymdtest integration  # integration only
python3 -m test.pymdtest hardware     # hardware only (skips if MDT_PORT unset)
```

Don't use pytest directly — `@parametrize` is not compatible with it.


## Unit Tests (`test/unit/`) — 120 cases

No serial port, no MCU, no external dependencies.

### `test_crc.py` — 3 cases

CRC-CCITT (0x1021) validated against `binascii.crc_hqx`. Covers the `123456789` →
`0x29B1` standard vector, empty input, and 1000 random inputs at varying lengths. A
wrong CRC breaks the protocol silently, so this runs first.

### `test_protocol.py` — 37 cases

Packet construction and parsing end-to-end: serialization, deserialization,
round-trips, the 18-byte size invariant, CRC integrity, multi-packet flags
(`SEQ_PRESENT`, `LAST_PACKET`), NACK detection, and little-endian address
encoding/decoding. Parameterized across several command shapes and addresses.

### `test_parser.py` — 23 cases

CLI parser layer: converts strings like `WATCHPOINT 0 ENABLED 0x20000100` into
`Command` objects. Covers all command types, memory type mapping, control value
mapping, hex data decoding, and invalid input rejection. Parameterized across all
control values for both breakpoints and watchpoints.

### `test_validator.py` — 57 cases

Validation against MCU metadata before a command hits the wire: memory boundary
checks (RAM, Flash, EEPROM), register access permissions (read-only, write-only,
read-write), breakpoint and watchpoint slot range validation, and dispatch routing.
Parameterized across valid and invalid slot IDs.


## Integration Tests (`test/integration/`) — 41 cases

End-to-end pipeline through `MockUART` — a perfect in-memory loopback — with no
real serial port. Exercises the full parse → validate → serialize → transmit →
receive → deserialize path for every command type, plus multi-packet chunking,
event packet structure, and error handling.

### End-to-end commands — 8 cases

PING, READ_MEM, WRITE_MEM, READ_REG, WRITE_REG, BREAKPOINT, WATCHPOINT, and
packet validation after loopback. Each runs the full pipeline and checks the
deserialized response.

### Chunked transfers — 3 cases

A 16-byte write splits into four 4-byte packets. Verifies all are ACKed, that a
single-chunk write is marked `LAST_PACKET`, and that addresses increment correctly
across chunks.

### Validation gating — 5 cases

Out-of-range read, invalid breakpoint ID, unaligned watchpoint address, write to a
non-existent register — all rejected before anything hits the wire. Valid command
passes through cleanly.

### MCU response handling — 5 cases

ACK recognized as valid, NACK recognized correctly, corrupted response fails
`validate_command_packet`, truncated response fails, wrong start byte fails.

### Pipeline invariants — 1 case

Exactly one packet written to UART per command.

### Event packets — 6 cases

`EVENT_PACKET` flag set, event not mistaken for NACK, breakpoint slot ID carried in
`SEQ`, event type in `DATA`, CRC valid. `BUFFER_OVERFLOW` recognized from the
`EventType` enum.

### Field fidelity — 13 cases

Parameterized address/mem/length triples, data patterns, and sequence numbers —
round-trip through serialize → deserialize and confirm each field is preserved
exactly.


## Hardware Tests (`test/hardware/`) — 53 cases

Require a real MCU with MDT firmware. Every test skips with `[SKIP]` if `MDT_PORT`
is not set.

```bash
MDT_PORT=/dev/ttyACM0 python3 -m test.pymdtest hardware
MDT_PORT=/dev/ttyUSB0 MDT_BAUD=19200 MDT_PLATFORM=stm32 python3 -m test.pymdtest hardware
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `MDT_PORT` | _(unset)_ | Serial port — absent means all hardware tests skip |
| `MDT_BAUD` | `19200` | Baud rate |
| `MDT_TIMEOUT` | `2.0` | Per-packet read timeout in seconds |
| `MDT_PLATFORM` | `avr` | `avr` or `stm32` — selects SRAM/Flash base addresses |

These are loaded once at module import time into `HW = HWConfig.from_env()`.

### Link health — 7 cases

Ping round-trip, 18-byte response invariant, START/END framing, CRC validity,
CMD_ID echo, ACK flag set, STATUS_ERROR clear. If any of these fail the rest of
the suite is meaningless.

### Memory read — 4 cases

SRAM read ACK, 4-byte data field, MEM_ID echo, Flash read structural validity.
Flash does not assert ACK — some variants reject address 0 — only that the packet
is well-formed.

### Memory write/readback — 8 cases

Write ACK, then write-and-read-back: `0xCAFEBABE`, all-zeros, all-ones, adjacent
word non-aliasing (two different patterns at adjacent addresses, both verified), and
four parameterized patterns (`0xDEADBEEF`, `0x01020304`, `0xAA55AA55`, `0x00FF00FF`).

### Register access — 2 cases

`READ_REG` at a known SRAM address returns a structurally valid packet.
`WRITE_REG` + `READ_REG` round-trip verifies the first byte of the written value
reads back correctly.

### Protocol robustness — 6 cases

Bad CRC triggers NACK, that NACK has a valid CRC, recovery (next PING still ACKs),
resync after a truncated send, NACK echoes the SEQ byte of the bad request, unknown
CMD_ID `0xFF` sets STATUS_ERROR.

### Breakpoints — 4 cases

Six control values parameterized across slots (ENABLED/DISABLED on slots 0–3, RESET
on slot 0, NEXT on slot 1) — all ACKed. Invalid slot 99 NACKed. Enable-then-disable
sequence both ACKed. RESET standalone ACKed.

### Watchpoints — 6 cases

DISABLE ACKed for all 4 slots (parameterized). ENABLE on aligned SRAM address ACKed,
disabled immediately after. RESET ACKed. MASK on active slot ACKed. MASK on inactive
slot NACKed. Invalid slot NACKed.

### Event packets — 3 cases

Bad-CRC packet produces a NACK and then a FAILED_PACKET event with EVENT flag set and
`cmd_id == 0`. All received packets pass structural validation. `rx_worker` routing
test starts the background thread, sends a bad packet, and confirms the NACK lands in
`response_queue` and the event (if emitted) in `event_queue`.

### Chunked transfers — 2 cases

`execute_command()` splits a 16-byte write into 4 × 4-byte packets — all ACKed.
8-byte chunked write followed by a single-word readback verifies the payload landed
in SRAM correctly.

### Stress — 2 cases

20 consecutive PINGs all ACKed (catches state machine corruption under load). 10
interleaved write/read pairs with distinct patterns at the same address, each verified
(catches buffer aliasing and ring-buffer issues under rapid I/O).


## What Is Not Tested Yet

**Unit/integration:**
- `event.py` threading — `rx_worker`, `event_poll_worker`, `event_listener` routing
  logic has no isolated unit coverage yet. A `FakeSerialLink` that replays injected
  byte sequences would cover this without hardware.
- `commander.py` — retry logic, timeout handling, and multi-packet assembly are only
  exercised indirectly through hardware tests.
- `loader.py` — `build_info.yaml` parsing is untested. A missing key produces a
  `KeyError` at runtime instead of a clear error.

**Hardware:**
- `RESET` command — implemented, no hardware test. Should verify the MCU responds to
  PING within a bounded time after reset.
- UART IDLE interrupt mode — all hardware tests run the poll path. The
  interrupt-driven path (`MDT_FEATURE_UART_IDLE=1`) has no dedicated coverage; on
  STM32 this is the default mode.
- AVR vs STM32 parity — tests run one platform at a time, no automated cross-target
  comparison.
- Disconnect recovery — the `EIO` clean-shutdown path in `rx_worker` is implemented
  but not tested.


## Future Direction

Short term: `FakeSerialLink` fixture to unit-test `rx_worker` routing without
hardware; hardware test for `RESET`; `loader.py` unit tests with valid and malformed
`build_info.yaml`.

Medium term: dedicated STM32 run with `MDT_FEATURE_UART_IDLE=1`; both AVR and STM32
hardware suites in CI on a USB hub; fuzz the MCU packet parser over UART.

Long term: Renode-based firmware tests using the existing `stm32f030.resc` script;
property-based round-trip testing for the serializer/deserializer.