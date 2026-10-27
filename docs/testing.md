# Testing

Five categories. The first three run anywhere. The hardware tests need a board or an emulator and
skip when `MCU` is not set; the simulation tests start an emulator themselves and skip when
`MDT_SIM` is not set.

| Category | Where | Cases | What it needs |
|---|---|---|---|
| unit | `test/unit/` | 276 | nothing |
| integration | `test/integration/` | 27 | nothing |
| golden | `test/golden/` | 60 | nothing (about 2 minutes) |
| hardware | `test/hardware/` | 53 | a board flashed with the MDT firmware, or Renode |
| simulation | `test/simulation/` | 29 | Renode or simavr, and the part's toolchain (about 2 minutes per part) |


## Running them

The runner is our own (`test/pymdtest.py`), not pytest: its `@parametrize` is not pytest's.
It runs every `test_*` function of every `test_*.py`, and the argument is a substring of the
module name, so a single file works too.

```bash
python3 -m test.pymdtest                  # everything (hardware skips without MCU)
python3 -m test.pymdtest unit
python3 -m test.pymdtest golden
python3 -m test.pymdtest test_command_rules
MCU=F030F4 python3 -m test.pymdtest hardware
```

Tests run with the `pc_tool` logger muted. A test that checks a warning uses
`logged_warnings()` from `test/common/asserts.py`.

Building every part listed in `build_system/` needs the toolchains, not a board:

```bash
python3 test/firmware/check_parts.py -j 8
```


## Unit tests

One file per module, no serial port, no threads left behind.

| File | Covers |
|---|---|
| `test_wire_protocol.py` | CRC against `binascii.crc_hqx`, encode/decode round trips, flags, bad size/fences/CRC, NACKs, event decoding and the event line |
| `test_wire_contract.py` | The C headers against the Python side: packet size, offsets, flags, command ids, event types, zones, control values, and `commands.yaml` |
| `test_device_description.py` | SVD by the CMSIS rules on small inline files (derivedFrom, dim, clusters, inherited size/access, alternate groups, namespaces), an NXP MCXA256 excerpt, ATDF segments and 16-bit registers |
| `test_elf_symbols.py` | Flash image range, watchable RAM symbols (AVR offset removed), the hint for narrow variables |
| `test_target_model.py` | Loading `build_info.yaml` (memory map, limits, firmware range, `--elf`), its errors, register lookups by name and address |
| `test_command_parser.py` | Every parameter type, counts, choices that belong to their own command, registers and symbols by name, the optional WATCHPOINT value |
| `test_command_rules.py` | Memory ranges, firmware protection for writes and erases, registers, slots, watch addresses |
| `test_serial_link.py` | Opening (loop://, a device that never appears), framing and resync, no busy wait, startup sync, the lock |
| `test_command_client.py` | One packet per word, reply matching, retries, NoReplyError, a corrupted reply resent |
| `test_event_pump.py` | Routing, corrupted packets, UART-idle polling, the startup drain, an unplugged adapter |
| `test_user_console.py` | Console and log file lines, the packet box, the event line, the history file |
| `test_layers.py` | Every module is in the layer table and imports only lower layers |
| `test_cli_main.py` | Arguments; a lost link keeps waking the prompt until the session shuts down |
| `test_build_system_*.py` | The part descriptions in `build_system/` and the files generated from them |

The transport tests use `FakeSerialPort` from `test/common/fake_mcu.py`: a pyserial-like port
wired to the fake MCU in the same process. Small targets come from `make_target()` in
`test/common/target_fixtures.py`.


## Integration tests

`test_debug_session.py` drives the real session, rules, client, link and event pump on the
in-process fake MCU. Only the serial port is fake. It checks every command's packets and
replies, long reads and writes, refused lines that send nothing, local commands, a watchpoint
event, and how scripts stop.


## Golden tests

The whole tool, run the way a user runs it (`mcu_mdt.py <build_info> --script ...`), against
`test/common/fake_mcu.py` on a TCP socket. The fake answers like `src/mcu_mdt.c` and imports
nothing from `pc_tool`, so it can't drift with the code it tests.

- `test_golden.py`: for three parts (ATmega328P, F030F4, F103C8), a script that uses every
  command plus 17 one-line error scripts. The contract kept exactly is in
  `test/golden/expected/`: every packet on the wire, every WARNING/ERROR line, and how the
  script ended. INFO wording is free to change. The parts' `build_info.yaml` and ELF are frozen
  in `test/golden/fixtures/`.
- `test_exit_status.py`: exit status 0 or 1, the link closed and the log footer written.
- `test_install.py`: `pip install` into a fresh venv and run the installed `mcu-mdt`. Catches
  data files missing from the package.

After a deliberate change, record the new contract and read the diff before committing it:

```bash
python3 -m test.golden.record
git diff test/golden/expected
```


## Hardware tests

53 cases on a real MCU: link health, memory reads and writes, registers, bad packets and
NACKs, breakpoints, watchpoints, event packets, chunked transfers, and stress (20 PINGs, 10
fast write/read pairs).

The settings come from `build/<mcu>/build_info.yaml`; these override them:

| Variable | Default | |
|---|---|---|
| `MCU` | unset | the part (`F030F4`); without it every hardware test skips |
| `MDT_PORT` | from `build_info.yaml` | any pyserial port: `/dev/ttyUSB0`, `COM3`, `socket://localhost:3456` |
| `MDT_BAUD` | from `build_info.yaml` | |
| `MDT_TIMEOUT` | 2.0 | seconds per reply |
| `MDT_PLATFORM` | from `build_info.yaml` | `avr` or `stm32` |

### Without a board: Renode

The STM32 firmware runs in [Renode](https://renode.io) with USART1 on a TCP socket.

```bash
# F103: both modes (Renode's STM32F1 USART has the IDLE interrupt)
make MCU=F103C8
renode --disable-gui test/simulators/stm32f103.resc          # USART1 on localhost:3456
MCU=F103C8 MDT_PORT=socket://localhost:3456 python3 -m test.pymdtest hardware

# F030: poll mode only (Renode's STM32F0 USART has no IDLE interrupt)
make MCU=F030F4 UART_IDLE=0
renode --disable-gui test/simulators/stm32f030.resc
MCU=F030F4 MDT_PORT=socket://localhost:3456 python3 -m test.pymdtest hardware
```

F0 interrupt mode (`UART_IDLE=1`) still needs a real board. Renode doesn't come back from a
RESET command, so restart it after one.


## Simulation tests

The PC tool against real firmware in an emulator, with nothing mocked. The firmware is
`test/firmware/validation_main.c`, linked against the part's library like a user project. It gives
the tool things to look at: a counter that changes on every pass, one that changes slowly right
before the firmware hits breakpoint 0, a word that never changes, 1- and 2-byte variables, a
function-local static. A TCP proxy (`test/common/fault_proxy.py`) sits between tool and emulator
when a test damages the line.

```bash
MDT_SIM=f103c8     python3 -m test.pymdtest simulation    # Renode, UART-idle mode
MDT_SIM=f030f4     python3 -m test.pymdtest simulation    # Renode, poll mode
MDT_SIM=atmega328p python3 -m test.pymdtest simulation    # simavr
```

Renode comes from `renode` on PATH or `RENODE=<path>`. simavr needs `gcc`, `libsimavr-dev` and
`libelf-dev`: the tests build `test/simulators/avr_uart_tcp.c`, a small bridge that puts the AVR's
UART0 on a TCP socket and runs the simulation in real time. Building the firmware runs
`make MCU=<part> lib` (F030F4 with `UART_IDLE=0`), which regenerates `build/<part>/`. Run one part at a
time: on a small machine two emulators starve each other and the tool's timeouts.

- `test_emulated_mcu.py`: long writes read back at every length and offset; symbols and local
  statics; the firmware image read back and protected; every UART register; both bytes of a 16-bit
  AVR register; watchpoints (changes, MASK, DISABLED, RESET, a quiet word, a register); a breakpoint
  the firmware hits, held while commands still work, NEXT and DISABLED; corrupted, dropped, late,
  noisy, doubled and byte-by-byte replies; an unplugged cable; 240 commands with events flowing; stale
  events drained at the next start.
- `test_emulated_cli.py`: the real `mcu_mdt.py` on a pseudo-terminal: TAB completion, history, up
  arrow, Ctrl-C and Ctrl-D; an event arriving while a line is half typed; CPU use while idle; an
  unplugged cable at the prompt; a corrupted reply in a script; exit status.

Renode models no flash controller for the STM32 parts, so the flash erase/write test skips there.
Watching a register in a simulation test has to keep the 4 sampled bytes off a register that
changes when read: UBRR0's four bytes on the ATmega328P include UDR0, and sampling it eats the
commands coming in.

The hardware suite also runs against these emulators (`MDT_PORT=socket://localhost:<port>`), with the
example firmware: the validation firmware hits breakpoint 0, which the hardware suite doesn't expect.


## Not covered yet

- RESET: nothing checks that the MCU answers again after it. Renode doesn't come back from one.
- AVR and STM32 side by side: the hardware suite runs one part at a time.
- The prompt itself (readline editing, TAB completion) is checked by hand only.
