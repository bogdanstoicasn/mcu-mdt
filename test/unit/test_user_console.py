"""
USER CONSOLE TESTS (pc_tool/user_console.py)

Coverage:
1. The console shows warnings and errors (with their code) and the lines marked for the user,
   nothing in script mode, and never plain INFO records
2. The log file gets every record in the [HH:MM:SS] [LEVEL](code): message format
3. The packet box and the event line
4. Bug 5: the history lives in the home directory, not inside the installed package
"""

import contextlib
import io
import logging
import re
import tempfile
from pathlib import Path

from pc_tool import user_console, wire_protocol
from pc_tool.wire_protocol import Command, CommandId, EventType, MemType
from test.common.asserts import assert_eq


def _console() -> user_console.Console:
    return user_console.Console(history_file=Path(tempfile.gettempdir()) / "mdt-test-history")


def _shown(console: user_console.Console, *records: tuple[int, str, dict]) -> str:
    """What the console handler prints for (level, message, extra) records."""
    logger = logging.getLogger("pc_tool.test_console")
    handler = user_console.ConsoleHandler(console)
    saved = logger.level, logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            for level, message, extra in records:
                logger.log(level, message, extra=extra)
    finally:
        logger.removeHandler(handler)
        logger.level, logger.propagate = saved
    return out.getvalue()


# ---------------------------------------------------------------- 1. the console

def test_console_lines():
    shown = _shown(_console(),
                   (logging.ERROR, "Unknown command: NOPE", user_console.error_extra(3)),
                   (logging.WARNING, "Watch address 0x20000101 is not 4-byte aligned", {}),
                   (logging.INFO, "Validating READ_MEM command", {}),           # file only
                   (logging.INFO, "Exiting...", user_console.Console.SHOW),
                   (logging.INFO, "Debugger closed.", user_console.Console.SUCCESS))
    assert_eq(shown.splitlines(), ["ERROR: Unknown command: NOPE (3)", "WARN:  Watch address 0x20000101 is not 4-byte aligned",
                                   "Exiting...", "OK:    Debugger closed."])


def test_script_mode_shows_nothing():
    console = _console()
    console.quiet = True
    assert_eq(_shown(console, (logging.ERROR, "boom", user_console.error_extra(2))), "")


# ---------------------------------------------------------------- 2. the log file

def test_log_file_format():
    logger = logging.getLogger("pc_tool")
    before = list(logger.handlers)
    with tempfile.TemporaryDirectory() as tmp:
        path = user_console.start_log_file("f103c8", log_dir=tmp)
        handler = next(h for h in logger.handlers if h not in before)
        saved = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            logging.getLogger("pc_tool.x").error("Unknown command: %s", "NOPE", extra=user_console.error_extra(3))
            logging.getLogger("pc_tool.x").info("Script complete.")
        finally:
            logger.setLevel(saved)
            logger.removeHandler(handler)
            handler.close()
        assert re.fullmatch(r".*/mdt_f103c8_\d{8}_\d{6}\.log", path), path
        lines = Path(path).read_text().splitlines()
    assert_eq([re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in lines],
              ["[ERROR](3): Unknown command: NOPE", "[INFO]: Script complete."])


# ---------------------------------------------------------------- 3. packets and events

def test_packet_box():
    raw = wire_protocol.encode(Command(name="READ_MEM", id=CommandId.READ_MEM, mem=MemType.RAM, address=0x20000000,
                                       length=4, data=b"\x01\x02\x03\x04"))
    reply = bytearray(raw)
    reply[wire_protocol.Offset.FLAGS] |= wire_protocol.Flag.ACK_NACK
    reply[15:17] = wire_protocol.crc16(bytes(reply[1:15])).to_bytes(2, "little")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        _console().packet(wire_protocol.decode(bytes(reply)))
    lines = out.getvalue().splitlines()
    assert_eq(lines[0], "┌─ Received Packet " + "─" * 45)
    assert_eq(lines[1:4], ["│  Status   : [ACK]", "│  Command  : READ_MEM (0x01)",
                           "│  Flags    : 0x07  MEM_ID_PRESENT | LENGTH_PRESENT | ACK_NACK"])
    assert_eq(lines[8], "│  Data     : 01 02 03 04")
    assert_eq(lines[10], f"│  raw      : {bytes(reply).hex()}")
    assert_eq(lines[-1], "└" + "─" * 63)


def test_event_line_redraws_the_prompt():
    event = wire_protocol.Event(EventType.INTERNAL_MDT_EVENT_BREAKPOINT_HIT, 2, 0, 0, 5)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        _console().event(event)
    assert out.getvalue().startswith("\r\033[K[Event] INTERNAL_MDT_EVENT_BREAKPOINT_HIT (slot=2, hit_count=5)\n> ")


# ---------------------------------------------------------------- 4. bug 5

def test_history_lives_in_the_home_directory():
    assert_eq(user_console.HISTORY_FILE, Path.home() / ".mcu_mdt_history")
    if user_console.readline is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        history = Path(tmp) / "history"
        console = user_console.Console(history_file=history)
        user_console.readline.add_history("PING")
        console.close()
        assert "PING" in history.read_text()
