"""
BUILD SYSTEM GENERATOR TESTS FOR MCU-MDT (STEP 2: AVR)

Checks build_system/generate.py without a toolchain: resolution, leaf overrides,
validation, the two rendered files and write-if-changed.
test/firmware/check_avr_parts.py is the toolchain check.
"""

import re
import tempfile
from pathlib import Path

from build_system.generate import (
    DescriptorError,
    generate,
    render_build_mk,
    render_target_header,
    resolve,
    write_if_changed,
)
from test.common.asserts import assert_eq
from test.unit.test_build_system_descriptors import _avr_nodes


def _raises(fn, *args, match: str) -> None:
    try:
        fn(*args)
    except DescriptorError as exc:
        assert match in str(exc), f"{match!r} not in {exc}"
        return
    raise AssertionError(f"{fn.__name__}{args} did not raise")


def _defines(header: str) -> dict:
    return dict(re.findall(r"^#define[ \t]+(\w+)[ \t]+(.+?)[ \t]*$", header, re.M))


def _make_vars(build_mk: str) -> dict:
    return dict(re.findall(r"^(\w+) := (.*)$", build_mk, re.M))


def test_every_avr_node_renders_both_files():
    for part in sorted(_avr_nodes()):
        target = resolve(part)
        make = _make_vars(render_build_mk(target))
        assert_eq(make["TARGET_MCU"], part)
        assert make["CFLAGS"].startswith(f"-mmcu={part} "), make["CFLAGS"]
        assert make["LDFLAGS"].startswith(f"-mmcu={part} "), make["LDFLAGS"]
        assert_eq(make["BUILD_DIR"], f"build/{part}")
        assert_eq(make["TARGET_BAUDRATE"], "19200")
        assert_eq(_defines(render_target_header(target))["MDT_TARGET_MCU"], f'"{part}"')


def test_defaults_reach_the_header():
    assert_eq(_defines(render_target_header(resolve("atmega328p"))), {
        "PLATFORM_AVR": "1", "MDT_TARGET_MCU": '"atmega328p"',
        "F_CPU": "16000000UL", "MDT_FEATURE_UART_IDLE": "0", "MDT_UART_BAUDRATE": "19200",
        "MDT_BUFFER_SIZE": "64", "MDT_MAX_BREAKPOINTS": "4", "MDT_MAX_WATCHPOINTS": "4",
    })


def test_part_lookup_is_case_insensitive():
    assert_eq(resolve("ATmega328P")["part"], "atmega328p")


def test_leaf_overrides_win_and_are_typed():
    config = resolve("atmega2560", ["f_cpu=8000000UL", "baudrate=0x9600", "buffer_size=128",
                                    "watchpoints=8", "port=/dev/ttyUSB0", "uart_idle=off"])["config"]
    assert_eq((config["f_cpu"], config["baudrate"], config["buffer_size"], config["watchpoints"],
               config["port"], config["uart_idle"]),
              (8000000, 38400, 128, 8, "/dev/ttyUSB0", False))


def test_rejects_what_cannot_be_built():
    _raises(resolve, "atmega8", match="unsupported part")
    _raises(resolve, "atmega328p", ["foo=1"], match="unknown setting")
    _raises(resolve, "atmega328p", ["f_cpu"], match="unknown setting")
    _raises(resolve, "atmega328p", ["f_cpu=fast"], match="not a valid int")
    _raises(resolve, "atmega328p", ["uart_idle=maybe"], match="not a valid bool")
    _raises(resolve, "atmega328p", ["uart_idle=1"], match="not supported on avr")
    _raises(resolve, "atmega328p", ["buffer_size=48"], match="buffer_size")
    _raises(resolve, "atmega328p", ["breakpoints=0"], match="breakpoints")
    _raises(resolve, "atmega328p", ["watchpoints=9"], match="watchpoints")
    _raises(resolve, "atmega328p", ["baudrate=0"], match="baudrate")


def test_write_if_changed_keeps_the_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "f.h"
        assert write_if_changed(path, "a")
        assert not write_if_changed(path, "a")
        assert write_if_changed(path, "b")
        assert_eq(path.read_text(), "b")


def test_generate_writes_both_files():
    with tempfile.TemporaryDirectory() as tmp:
        out = generate("atmega328p", ["f_cpu=8000000"], Path(tmp))
        assert_eq(sorted(p.name for p in out.iterdir()), ["build.mk", "mdt_target.h"])
        assert_eq(_defines((out / "mdt_target.h").read_text())["F_CPU"], "8000000UL")
