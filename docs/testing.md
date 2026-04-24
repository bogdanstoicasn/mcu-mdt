# MCU-MDT — Testing

## Philosophy

MCU-MDT sits at the boundary between a host-side Python tool and bare-metal firmware
running on constrained hardware. This creates two fundamentally different testing
domains that must stay separate: things that can be verified without hardware, and
things that only make sense against a real MCU.

The unit suite must be fast, deterministic, and runnable anywhere with no hardware
attached. Hardware tests exist only for behaviour that cannot be faked — actual UART
framing, real interrupt timing, MCU memory access, and event delivery end-to-end.


## Test Runner — PyMDTest

The project uses a custom runner (`test/pymdtest.py`) — not pytest. It auto-discovers
any file matching `test_*.py`, runs every function whose name starts with `test_`, and
supports parameterized cases via `@parametrize`. Assertions use `assert_eq` from
`test/common/asserts.py`.

```bash
python3 -m test.pymdtest              # all categories
python3 -m test.pymdtest unit         # unit only
python3 -m test.pymdtest hardware     # hardware only (skips if MDT_PORT unset)
```

Do not use `pytest` directly — `@parametrize` is not compatible with it.


## Unit Tests (`test/unit/`)

No serial port, no MCU, no hardware dependencies. 126 tests total.

### `test_crc.py` — 3 tests

Validates the CRC-CCITT (0x1021) implementation against `binascii.crc_hqx` as a
trusted reference. Covers the standard `123456789` → `0x29B1` known vector, empty
input, and a stress run of 1000 randomly generated inputs at varying lengths. This is
the foundation — a wrong CRC breaks the entire protocol silently.

### `test_protocol.py` — 24 tests

Validates packet construction and parsing end-to-end. Covers serialization,
deserialization, round-trip consistency, the fixed 18-byte size invariant, CRC
integrity, multi-packet flags (`SEQ_PRESENT`, `LAST_PACKET`), NACK detection, and
address encoding/decoding in little-endian. Effectively proves the host and MCU speak
the same wire format before any hardware is involved.

### `test_parser.py` — 13 tests

Validates the CLI parser — the layer that converts user input like
`WATCHPOINT 0 ENABLED 0x20000100` into a structured `Command` object. Covers all
command types, memory types, control value mapping, address and length parsing, hex
data decoding, and invalid input rejection. Parameterized across all control values
for both breakpoints and watchpoints.

### `test_validator.py` — 44 tests

Validates the command validation layer that checks a parsed command against MCU
metadata before it is sent. Covers memory boundary checks (RAM, Flash, EEPROM),
register access permissions (read-only, write-only, read-write), breakpoint and
watchpoint ID range validation, and dispatch routing. Ensures the tool refuses
commands that are protocol-valid but wrong for the specific target.


## Hardware Tests (`test/hardware/`)

Require a real MCU flashed with the MDT firmware. 42 tests total. Every test skips
gracefully with `[SKIP]` if `MDT_PORT` is not set.

```bash
MDT_PORT=/dev/ttyACM0 python3 -m test.pymdtest hardware
MDT_PORT=/dev/ttyUSB0 MDT_PLATFORM=stm32 python3 -m test.pymdtest hardware
```

Configuration via environment variables:

| Variable | Default | Description |
|---|---|---|
| `MDT_PORT` | _(unset)_ | Serial port — if absent all hardware tests skip |
| `MDT_BAUD` | `19200` | Baud rate |
| `MDT_TIMEOUT` | `2.0` | Per-packet read timeout in seconds |
| `MDT_PLATFORM` | `avr` | `avr` or `stm32` — selects SRAM/Flash base addresses |

These are loaded once at module import time into a frozen `HWConfig` dataclass
(`HW = HWConfig.from_env()`). All tests access `HW.port`, `HW.baud`, etc.

### Link health — 7 tests

Ping round-trip, 18-byte response size invariant, START/END framing bytes, CRC
validity, CMD_ID echo, ACK flag set, STATUS_ERROR flag clear. These are the baseline —
if any of these fail, nothing else in the suite is meaningful.

### Memory read — 4 tests

SRAM read ACK, 4-byte data field, Flash read structural validity (ACK or NACK, but
always a well-formed packet), MEM_ID echo. Flash read tests do not assert an ACK
because some MCU variants may reject a Flash read at address 0 — the test only
requires the response to be structurally valid.

### Memory write / readback — 8 tests

Write ACK, write-then-read-back with `0xCAFEBABE`, all-zeros, all-ones, adjacent word
non-aliasing, and four parameterized patterns (`0xDEADBEEF`, `0x01020304`,
`0xAA55AA55`, `0x00FF00FF`). Non-aliasing test writes two different patterns to
adjacent 4-byte slots and reads both back to confirm there is no bleed between words.

### Register access — 2 tests

`READ_REG` at a known SRAM address returns a structurally valid packet. `WRITE_REG` +
`READ_REG` round-trip via SRAM verifies the first byte matches what was written.

### Protocol robustness — 6 tests

Bad CRC triggers NACK, NACK itself has a valid CRC, recovery after bad packet (next
PING still ACKs), resync after truncated send (half-packet timeout), NACK echoes SEQ
byte of the bad request, unknown CMD_ID (`0xFF`) sets STATUS_ERROR.

### Breakpoints — 4 tests

All six control values ACKed when parameterized (ENABLED/DISABLED on slots 0-3,
RESET on slot 0, NEXT on slot 1), invalid slot (99) NACKed, enable-then-disable
sequence both ACKed, RESET ACKed standalone.

### Watchpoints — 6 tests

DISABLE ACKed for all 4 slots (parameterized), ENABLE on aligned SRAM address ACKed
(then disabled immediately to avoid polluting other tests), RESET ACKed, MASK on
active slot ACKed, MASK on inactive slot NACKed, invalid slot NACKed.

### Event packets — 3 tests

Bad-CRC packet produces NACK then FAILED_PACKET event with EVENT flag set and
`cmd_id == 0`. All received packets (NACK + event) pass structural validation (size,
framing, CRC). `rx_worker` routing test starts the background thread, sends a bad
packet, asserts the NACK arrives in `response_queue` and the event (if emitted) arrives
in `event_queue`.

### Chunked transfers — 2 tests

`execute_command()` splits a 16-byte write into 4 × 4-byte packets and all are ACKed.
8-byte chunked write followed by single-word readback verifies the payload landed in
SRAM correctly.

### Stress — 2 tests

20 consecutive PINGs all ACKed (catches state machine corruption under load). 10
interleaved write/read pairs with distinct patterns at the same address, each
verified (catches buffer aliasing and ring-buffer issues under rapid I/O).


## Known Issues

Four hardware tests currently fail against the firmware:

- **`test_hw_bad_crc_triggers_nack`** and **`test_hw_nack_seq_mirrors_request_seq`** —
  `is_nack_packet()` on the PC side expects `cmd_id == 0` in the NACK, but the
  firmware echoes the original `cmd_id`. One side needs to agree on the NACK format.

- **`test_hw_failed_packet_event_has_event_flag`** and
  **`test_hw_rx_worker_routes_event_to_event_queue`** — cascade from the above. The
  FAILED_PACKET event is only queued after the NACK is sent; on AVR poll mode it may
  not be delivered before the test's read timeout expires.


## What Is Not Tested Yet

**Unit:**
- `event.py` threading — `rx_worker`, `event_poll_worker`, `event_listener` routing
  logic has no isolated unit coverage. Testable with a `FakeSerialLink` that replays
  injected byte sequences.
- `commander.py` — retry logic, timeout handling, and multi-packet assembly are only
  exercised indirectly in hardware tests.
- `loader.py` — `build_info.yaml` parsing is not tested. A missing key currently
  produces a `KeyError` at runtime rather than a clear error message.

**Hardware:**
- `RESET` command — implemented but no hardware test exists yet. Should verify the MCU
  responds to PING within a bounded time after reset.
- UART IDLE interrupt mode — all hardware tests run against the poll path. The
  interrupt-driven path (`MDT_FEATURE_UART_IDLE=1`) has no dedicated hardware test
  coverage. On STM32 this is the default mode.
- AVR vs STM32 parity — tests run against one platform at a time. No automated run
  compares results across both targets.
- Disconnect recovery — the `EIO` clean shutdown path is implemented but not covered
  by a test.


## Future Direction

**Short term (v1.x)**
- Fix the NACK format disagreement so the four failing hardware tests pass.
- `FakeSerialLink` fixture to unit test `rx_worker` routing without hardware.
- Hardware test for `RESET` — send, wait, ping, assert response.
- `loader.py` unit tests with valid and malformed `build_info.yaml` inputs.

**Medium term**
- Dedicated STM32 hardware test run with `MDT_FEATURE_UART_IDLE=1` to cover the
  interrupt-driven path explicitly.
- Run both AVR and STM32 hardware suites in CI using two MCUs on a USB hub.
- Fuzz the MCU packet parser — feed random byte sequences over UART, assert the MCU
  never hangs and always recovers.

**Long term**
- Renode-based firmware tests — the `.resc` script already exists for STM32F030F4.
  Automated MCU-side C coverage without physical hardware in CI.
- Property-based testing for the serializer/deserializer round-trip using
  `@parametrize` with generated inputs — assert `deserialize(serialize(cmd)) == cmd`
  across a wide range of command shapes and edge-case values.