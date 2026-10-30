"""
DEBUG SESSION TESTS (pc_tool/debug_session.py): the whole pipeline on an in-process fake MCU

A line goes through the real parser, rules, client, link and event pump; the fake MCU answers
like the firmware. Nothing is mocked but the serial port.

Coverage:
1. Every command reaches the wire as the right packets, and its replies are shown
2. Long reads and writes are split into words; what is written reads back
3. A line the parser or the rules refuse sends nothing
4. Local commands: EXIT ends the session, HELP and CLEAR don't
5. A watchpoint on RAM reports the change as an event
6. Scripts: comments and local commands skipped, the first error stops the script
"""

import tempfile
import time
from pathlib import Path

from pc_tool import (
    command_client,
    command_parser,
    debug_session,
    event_pump,
    serial_link,
    user_console,
    wire_protocol,
)
from pc_tool.command_parser import CommandError
from pc_tool.wire_protocol import CommandId, EventType, MemType, WatchpointControl
from test.common.asserts import assert_eq, logged_warnings
from test.common.fake_mcu import FakeSerialPort
from test.common.target_fixtures import firmware, flash, make_target, ram, usart1
from test.pymdtest import parametrize

SPECS = command_parser.load_specs()
TARGET = make_target(segments=[ram(), flash()], peripherals=[usart1()], firmware=firmware())


class _Console(user_console.Console):
    """Keeps what would be shown."""

    def __init__(self):
        super().__init__(history_file=Path(tempfile.gettempdir()) / "mdt-test-history")
        self.packets, self.events, self.helps, self.clears = [], [], 0, 0

    def packet(self, packet):
        self.packets.append(packet)

    def event(self, event):
        self.events.append(event)

    def help(self, specs):
        self.helps += 1

    def clear(self):
        self.clears += 1


class _Session:
    """A session on a fresh fake MCU; use with `with`."""

    def __init__(self, answer=None, uart_idle=False):
        self.port = FakeSerialPort(answer=answer)
        self.console = _Console()
        self.link = serial_link.SerialLink("fake")
        self.link.open(self.port)
        self.pump = event_pump.EventPump(self.link, uart_idle, on_event=self.console.event)
        client = command_client.CommandClient(self.link, reply_timeout=0.2)
        self.session = debug_session.DebugSession(TARGET, SPECS, client, self.console)

    def __enter__(self):
        self.pump.start()
        return self

    def __exit__(self, *exc):
        self.pump.stop()
        self.link.close()

    def sent(self, polls=False) -> list[wire_protocol.Packet]:
        packets = [wire_protocol.decode(raw) for raw in self.port.written]
        return packets if polls else [p for p in packets if p.cmd_id != 0]


# ---------------------------------------------------------------- 1. every command

@parametrize("line,cmd_id,mem,address,data", [
    ("PING",                             CommandId.PING,       None,                       0,          bytes(4)),
    ("READ_MEM RAM 0x20000100 4",        CommandId.READ_MEM,   MemType.RAM,                0x20000100, bytes(4)),
    ("WRITE_MEM RAM 0x20000100 4 CAFE0102", CommandId.WRITE_MEM, MemType.RAM,              0x20000100,
     bytes.fromhex("CAFE0102")),
    ("READ_REG USART1_BRR",              CommandId.READ_REG,   None,                       0x40013808, bytes(4)),
    ("WRITE_REG USART1_DR 000000FF",     CommandId.WRITE_REG,  None,                       0x40013804,
     bytes.fromhex("000000FF")),
    ("RESET",                            CommandId.RESET,      None,                       0,          bytes(4)),
    ("BREAKPOINT 1 ENABLED",             CommandId.BREAKPOINT, 1,                          1,          bytes(4)),
    ("WATCHPOINT 0 ENABLED 0x20000100",  CommandId.WATCHPOINT, WatchpointControl.ENABLED,  0,
     (0x20000100).to_bytes(4, "little")),
    ("WATCHPOINT 0 RESET",               CommandId.WATCHPOINT, WatchpointControl.RESET,    0,          bytes(4)),
])
def test_every_command_reaches_the_wire_and_its_reply_is_shown(line, cmd_id, mem, address, data):
    with _Session() as s:
        assert_eq(s.session.run_line(line), True)
    sent = s.sent()
    assert_eq([(p.cmd_id, p.mem_id, p.address, p.data) for p in sent], [(cmd_id, mem, address, data)], line=line)
    assert_eq([(r.cmd_id, r.is_ack, r.is_error) for r in s.console.packets], [(cmd_id, True, False)], line=line)


# ---------------------------------------------------------------- 2. words

def test_a_long_write_reads_back_word_by_word():
    with _Session() as s:
        s.session.run_line("WRITE_MEM RAM 0x20000200 10 00112233445566778899")
        s.console.packets.clear()
        s.session.run_line("READ_MEM RAM 0x20000200 10")
    assert_eq([p.address for p in s.sent()[-3:]], [0x20000200, 0x20000204, 0x20000208])
    data = b"".join(r.data for r in s.console.packets)
    assert_eq(data[:10], bytes.fromhex("00112233445566778899"))


def test_erase_fills_the_page():
    with _Session() as s:
        s.session.run_line("WRITE_MEM ERASE 0x08004000 1 00")
        s.console.packets.clear()
        s.session.run_line("READ_MEM FLASH 0x08004010 4")
    assert_eq(s.console.packets[0].data, b"\xFF" * 4)


# ---------------------------------------------------------------- 3. refused lines

@parametrize("line,code", [
    ("NOPE", 3),
    ("READ_MEM RAM zz 4", 2),                   # no symbols in this target
    ("READ_MEM RAM 0x20004FFC 8", 3),           # past the end of RAM
    ("WRITE_MEM FLASH 0x08000000 4 00000000", 3),   # the running firmware
    ("BREAKPOINT 9 ENABLED", 3),
    ("WATCHPOINT 0 ENABLED", 3),
    ("WATCHPOINT 0 MASK", 3),                  # would set the mask to 0
    ("READ_REG 0x50000000", 3),
])
def test_a_refused_line_sends_nothing(line, code):
    with _Session() as s:
        try:
            s.session.run_line(line)
        except CommandError as exc:
            assert_eq(exc.code, code, line=line)
        else:
            raise AssertionError(f"{line!r} was accepted")
    assert_eq(s.port.written, [], line=line)


def test_no_reply_raises_after_the_retries():
    with _Session(answer=lambda request: b"") as s:
        try:
            s.session.run_line("PING")
        except command_client.NoReplyError as exc:
            assert_eq(str(exc), "Ping failed after 3 attempts.")
        else:
            raise AssertionError("no NoReplyError")
    assert_eq(len(s.port.written), 3)


# ---------------------------------------------------------------- 4. local commands

def test_local_commands_never_leave_the_pc():
    with _Session() as s:
        assert_eq([s.session.run_line(line) for line in ("help", "CLEAR", "  ", "EXIT")], [True, True, True, False])
    assert_eq((s.port.written, s.console.helps, s.console.clears), ([], 1, 1))


# ---------------------------------------------------------------- 5. events

def test_a_watchpoint_reports_the_change():
    with _Session(uart_idle=True) as s:
        s.session.run_line("WATCHPOINT 0 ENABLED 0x20000100")
        s.session.run_line("WRITE_MEM RAM 0x20000100 4 01020304")
        deadline = time.monotonic() + 3
        while not s.console.events and time.monotonic() < deadline:
            time.sleep(0.05)
    assert_eq(len(s.console.events), 1)
    event = s.console.events[0]
    assert_eq((event.kind, event.slot, event.data), (EventType.INTERNAL_MDT_EVENT_WATCHPOINT_HIT, 0, 0x04030201))


# ---------------------------------------------------------------- 6. scripts

def _script(s: _Session, text: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.txt"
        path.write_text(text)
        return s.session.run_script(str(path))


def test_a_script_runs_every_line():
    with _Session() as s, logged_warnings("pc_tool.debug_session") as warnings:
        ok = _script(s, "# a comment\n\nPING\nHELP\nREAD_MEM RAM 0x20000100 4\n")
    assert_eq(ok, True)
    assert_eq([p.cmd_id for p in s.sent()], [CommandId.PING, CommandId.READ_MEM])
    assert_eq(warnings, ["Skipping PC-only command at line 4: HELP"])


@parametrize("bad_line,why", [
    ("NOPE", "Script aborted: parse error at line 2: 'NOPE'"),
    ("BREAKPOINT 9 ENABLED", "Script aborted: validation failed at line 2: 'BREAKPOINT 9 ENABLED'"),
])
def test_the_first_error_stops_the_script(bad_line, why):
    with _Session() as s, logged_warnings("pc_tool.debug_session") as errors:
        ok = _script(s, f"PING\n{bad_line}\nRESET\n")
    assert_eq(ok, False)
    assert_eq([p.cmd_id for p in s.sent()], [CommandId.PING])        # RESET never sent
    assert_eq(errors[-1], why)


def test_no_reply_stops_the_script():
    with _Session(answer=lambda request: b"") as s, logged_warnings("pc_tool.debug_session") as errors:
        ok = _script(s, "PING\nRESET\n")
    assert_eq(ok, False)
    assert_eq(errors[-1], "Script aborted: no reply at line 1: 'PING'")
    assert_eq({wire_protocol.decode(raw).cmd_id for raw in s.port.written}, {CommandId.PING})


def test_a_missing_script_file_fails():
    with _Session() as s:
        assert_eq(s.session.run_script("/no/such/script.txt"), False)
