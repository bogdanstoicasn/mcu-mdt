"""
BUILD SYSTEM GENERATOR TESTS FOR MCU-MDT

Checks build_system/generate.py without a toolchain: resolution and merging, leaf
overrides, validation, the rendered files and write-if-changed.
test/firmware/check_parts.py is the toolchain check.
"""

import re
import tempfile
from pathlib import Path

from build_system.generate import (
    DescriptorError,
    _make_value,
    generate,
    merge,
    parse_bytes,
    placeholders,
    render,
    render_build_info,
    render_build_mk,
    render_memory_ld,
    render_target_header,
    resolve,
    write_if_changed,
)
from test.common.asserts import assert_eq
from test.unit.test_build_system_descriptors import _nodes


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
    return dict(re.findall(r"^([\w-]+) := (.*)$", build_mk, re.M))


# ---------------------------------------------------------------- merging and rendering rules

def test_merge_maps_merge_lists_append_values_replace():
    base = {"flags": {"compile": ["-Os"], "link": ["-a"]}, "lib": "x", "memory": {"flash": {"origin": 0}}}
    deeper = {"flags": {"compile": ["-mcpu=cortex-m0"]}, "lib": "y", "memory": {"flash": {"size": 16}}}
    assert_eq(merge(base, deeper), {"flags": {"compile": ["-Os", "-mcpu=cortex-m0"], "link": ["-a"]},
                                    "lib": "y", "memory": {"flash": {"origin": 0, "size": 16}}})


def test_merge_rejects_a_value_of_another_shape():
    _raises(merge, {"flags": {"compile": []}}, {"flags": "-Os"}, match="flags")
    _raises(merge, {"files": ["a"]}, {"files": {"b": 1}}, match="files")


def test_render_fills_known_placeholders_only():
    values = {"mcu": "f030f4", "image": "build/f030f4/x"}
    assert_eq(render("st-flash write {image}.bin; -p {mcu}", values, "t"), "st-flash write build/f030f4/x.bin; -p f030f4")
    assert_eq(render("cmd || { echo fail; exit 1; }", values, "t"), "cmd || { echo fail; exit 1; }")
    _raises(render, "{nope}", values, "commands.flash", match="unknown placeholder {nope}")


def test_make_values_escape_dollar_and_hash():
    assert_eq(_make_value("echo $HOME # x"), r"echo $$HOME \# x")


def test_sizes_accept_bytes_hex_and_suffixes():
    assert_eq([parse_bytes(v, "t") for v in (16384, "0x4000", "16K", "1M")], [16384, 16384, 16384, 1048576])
    _raises(parse_bytes, "16 KB", "memory.flash.size", match="is not a size")


# ---------------------------------------------------------------- AVR

def test_every_avr_node_renders():
    for part in sorted(_nodes("avr")):
        target = resolve(part)
        make = _make_vars(render_build_mk(target))
        assert make["CFLAGS"].startswith(f"-mmcu={part} "), make["CFLAGS"]
        assert make["LDFLAGS"].startswith(f"-mmcu={part} "), make["LDFLAGS"]
        assert_eq((make["BUILD_DIR"], make["OUTPUTS"], make["STARTUP"]), (f"build/{part}", "hex", ""))
        assert f" -p {part} " in make["CMD_flash"] and f"build/{part}/mcu_mdt_example.hex" in make["CMD_flash"]
        assert_eq(_defines(render_target_header(target))["MDT_TARGET_MCU"], f'"{part}"')
        assert_eq(target["memory"], {})      # AVR sizes stay in the ATDF and avr-libc


def test_avr_defaults_reach_the_header():
    assert_eq(_defines(render_target_header(resolve("atmega328p"))), {
        "PLATFORM_AVR": "1", "MDT_TARGET_MCU": '"atmega328p"',
        "F_CPU": "16000000UL", "MDT_FEATURE_UART_IDLE": "0", "MDT_UART_BAUDRATE": "19200",
        "MDT_BUFFER_SIZE": "64", "MDT_MAX_BREAKPOINTS": "4", "MDT_MAX_WATCHPOINTS": "4",
    })


def test_header_carries_the_static_asserts():
    header = render_target_header(resolve("atmega328p"))
    for macro in ("MDT_BUFFER_SIZE", "MDT_MAX_BREAKPOINTS", "MDT_MAX_WATCHPOINTS"):
        assert f"_Static_assert({macro} <= " in header or f"_Static_assert(({macro} & " in header, macro


def test_build_info_follows_the_leaf():
    assert_eq(render_build_info(resolve("ATmega328P", ["PORT=/dev/ttyUSB0", "BAUDRATE=38400", "BREAKPOINTS=8"])),
              "platform: AVR\nmcu: atmega328p\nmcu_db: avr/atmega/ATmega328P.atdf\nport: /dev/ttyUSB0\n"
              "baudrate: 38400\nuart_idle: false\nbreakpoints: 8\nwatchpoints: 4\nelf: mcu_mdt_example.elf\n")


# ---------------------------------------------------------------- STM32 F0

def test_f0_node_merges_trunk_branch_and_node():
    target = resolve("F030F4")
    make = _make_vars(render_build_mk(target))
    assert_eq(target["platform"], "stm32")
    assert_eq(make["HAL_DIR"], "hal/stm32/cortex-m0")
    assert_eq(make["STARTUP"], "hal/stm32/cortex-m0/startup_stm32f030xx.c")
    assert_eq(make["OUTPUTS"], "bin hex")
    assert_eq(make["LDLIBS"], "-lgcc")
    for flag in ("-mthumb", "-mcpu=cortex-m0"):          # trunk + branch, compile and link
        assert flag in make["CFLAGS"].split() and flag in make["LDFLAGS"].split(), flag
    assert "-Thal/stm32/cortex-m0/linker.ld" in make["LDFLAGS"].split()
    assert "-Wl,-Map=build/f030f4/mcu_mdt_example.map" in make["LDFLAGS"].split()
    assert_eq(make["CMD_flash"], "st-flash write build/f030f4/mcu_mdt_example.bin 0x08000000")
    assert_eq(make["COMMANDS"], "flash erase flash-recover")
    assert "verify_image build/f030f4/mcu_mdt_example.elf" in make["CMD_flash-recover"]


def test_f0_memory_reaches_header_linker_and_host():
    target = resolve("f070rb")
    defines = _defines(render_target_header(target))
    assert_eq((defines["MDT_FLASH_ORIGIN"], defines["MDT_FLASH_SIZE"], defines["MDT_FLASH_PAGE_SIZE"],
               defines["MDT_RAM_ORIGIN"], defines["MDT_RAM_SIZE"], defines["MDT_FEATURE_UART_IDLE"], defines["F_CPU"]),
              ("0x08000000UL", "0x20000UL", "0x800UL", "0x20000000UL", "0x4000UL", "1", "8000000UL"))
    assert "    flash (rx) : ORIGIN = 0x08000000, LENGTH = 128K\n" in render_memory_ld(target)
    assert "    ram (rwx) : ORIGIN = 0x20000000, LENGTH = 16K\n" in render_memory_ld(target)
    info = render_build_info(target)
    assert "mcu_db: stm32/cortex-m0/STM32F0x0.svd\n" in info
    assert "  flash: {origin: 0x08000000, size: 131072, page: 2048}\n" in info
    assert "  ram: {origin: 0x20000000, size: 16384}\n" in info


def test_f0_densities_match_the_datasheets():
    memory = {part: resolve(part)["memory"] for part in _nodes("stm32")}
    sizes = {part: (m["flash"]["size"] // 1024, m["ram"]["size"] // 1024, m["flash"]["page"] // 1024)
             for part, m in memory.items()}
    assert_eq(sizes, {
        "f030f4": (16, 4, 1), "f030k6": (32, 4, 1), "f030c6": (32, 4, 1), "f030c8": (64, 8, 1), "f030r8": (64, 8, 1),
        "f030cc": (256, 32, 2), "f030rc": (256, 32, 2), "f070f6": (32, 6, 1), "f070c6": (32, 6, 1),
        "f070cb": (128, 16, 2), "f070rb": (128, 16, 2),
    })


def test_f0_poll_mode_is_allowed():
    assert_eq(resolve("f030f4", ["UART_IDLE=0"])["config"]["uart_idle"], False)


# ---------------------------------------------------------------- leaf and validation

def test_part_lookup_is_case_insensitive():
    assert_eq(resolve("ATmega328P")["part"], "atmega328p")
    assert_eq(resolve("f030F4")["part"], "f030f4")


def test_leaf_overrides_win_and_are_typed():
    config = resolve("atmega2560", ["F_CPU=8000000UL", "baudrate=0x9600", "buffer_size=128",
                                    "watchpoints=8", "port=/dev/ttyUSB0", "uart_idle=off"])["config"]
    assert_eq((config["f_cpu"], config["baudrate"], config["buffer_size"], config["watchpoints"],
               config["port"], config["uart_idle"]),
              (8000000, 38400, 128, 8, "/dev/ttyUSB0", False))


def test_placeholders_follow_the_leaf():
    values = placeholders(resolve("f030f4", ["PORT=/dev/ttyUSB1"]))
    assert_eq((values["port"], values["flash_origin"], values["ram_size"]), ("/dev/ttyUSB1", "0x08000000", "4096"))


def test_rejects_what_cannot_be_built():
    _raises(resolve, "atmega8", match="unsupported part")
    _raises(resolve, "f103c8", match="unsupported part")
    _raises(resolve, "atmega328p", ["foo=1"], match="unknown setting")
    _raises(resolve, "atmega328p", ["f_cpu"], match="unknown setting")
    _raises(resolve, "atmega328p", ["f_cpu=fast"], match="not a valid int")
    _raises(resolve, "atmega328p", ["uart_idle=maybe"], match="not a valid bool")
    _raises(resolve, "atmega328p", ["uart_idle=1"], match="not supported on avr")
    _raises(resolve, "atmega328p", ["buffer_size=48"], match="buffer_size")
    _raises(resolve, "atmega328p", ["breakpoints=0"], match="breakpoints")
    _raises(resolve, "atmega328p", ["watchpoints=9"], match="watchpoints")
    _raises(resolve, "atmega328p", ["baudrate=0"], match="baudrate")


# ---------------------------------------------------------------- output files

def test_write_if_changed_keeps_the_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "f.h"
        assert write_if_changed(path, "a")
        assert not write_if_changed(path, "a")
        assert write_if_changed(path, "b")
        assert_eq(path.read_text(), "b")


def test_generate_writes_the_files_each_target_needs():
    with tempfile.TemporaryDirectory() as tmp:
        avr = generate("atmega328p", ["f_cpu=8000000"], Path(tmp) / "avr")
        assert_eq(sorted(p.name for p in avr.iterdir()), ["build.mk", "build_info.yaml", "mdt_target.h"])
        assert_eq(_defines((avr / "mdt_target.h").read_text())["F_CPU"], "8000000UL")
        stm = generate("f030f4", [], Path(tmp) / "stm")
        assert_eq(sorted(p.name for p in stm.iterdir()), ["build.mk", "build_info.yaml", "mdt_target.h", "memory.ld"])
