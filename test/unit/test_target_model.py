"""
TARGET MODEL TESTS (pc_tool/target_model.py): what the tool takes from the build

The tool has no per-part tables: build_info.yaml names the description file, gives the memory map
and the breakpoint/watchpoint counts, and the ELF gives the symbols and the firmware range.

Coverage:
1. load_target: memory map, limits, firmware range, peripherals from the description file
2. Errors: missing or incomplete build_info.yaml, an --elf that does not exist
3. The ELF: the build's or the one given; no ELF means no symbols and no firmware range
4. Register lookups: qualified and bare names, NAME[i], longest peripheral first, by address
"""

import tempfile
from pathlib import Path

import yaml

from pc_tool import device_description, target_model
from pc_tool.target_model import TargetError
from test.common.asserts import assert_eq
from test.common.tiny_elf import elf_with_segments

_F0_MEMORY = {"flash": {"origin": 0x08000000, "size": 16384, "page": 1024}, "ram": {"origin": 0x20000000, "size": 4096}}


def _build_dir(tmp: Path, segments: list, **overrides) -> Path:
    """A build directory with a build_info.yaml (F030F4 unless overridden) and an ELF of *segments*."""
    info = {"platform": "STM32", "mcu": "f030f4", "mcu_db": "stm32/cortex-m0/STM32F0x0.svd", "port": "/dev/null",
            "baudrate": 19200, "uart_idle": True, "breakpoints": 6, "watchpoints": 2,
            "elf": "mcu_mdt_example.elf", "memory": _F0_MEMORY}
    info.update(overrides)
    info = {key: value for key, value in info.items() if value is not None}
    (tmp / "mcu_mdt_example.elf").write_bytes(elf_with_segments(segments))
    (tmp / "build_info.yaml").write_text(yaml.safe_dump(info))
    return tmp / "build_info.yaml"


def _raises(error, call) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"{error.__name__} not raised")


# ---------------------------------------------------------------- 1. load_target

def test_target_takes_memory_limits_and_firmware_from_the_build():
    with tempfile.TemporaryDirectory() as tmp:
        # code at the start of flash, .data stored right after it, .bss only in RAM
        path = _build_dir(Path(tmp), [(0x08000000, 0x08000000, 0xB60, 0xB60), (0x20000000, 0x08000B60, 0x1C, 0x1C),
                                      (0x2000001C, 0x2000001C, 0, 0xD0)])
        target = target_model.load_target(path)
    assert_eq([(s.name, s.kind, s.start, s.size, s.page) for s in target.segments],
              [("FLASH", "flash", 0x08000000, 16384, 1024), ("RAM", "ram", 0x20000000, 4096, None)])
    assert_eq((target.breakpoints, target.watchpoints, target.baudrate, target.uart_idle), (6, 2, 19200, True))
    assert_eq((target.firmware.start, target.firmware.size, target.firmware.page), (0x08000000, 0xB7C, 1024))
    assert_eq(target.segment("ram", 0x20000FFC, 4).name, "RAM")
    assert_eq(target.segment("ram", 0x20000FFE, 4), None)                     # runs past the end


def test_peripherals_come_from_the_description_file():
    with tempfile.TemporaryDirectory() as tmp:
        target = target_model.load_target(_build_dir(Path(tmp), []))
    usart1 = next(p for p in target.peripherals if p.name == "USART1")
    assert_eq(usart1.base, 0x40013800)
    assert_eq(target.registers.by_name("USART1_BRR").address, 0x4001380C)


def test_avr_memory_comes_from_the_atdf_when_the_build_has_no_map():
    with tempfile.TemporaryDirectory() as tmp:
        target = target_model.load_target(_build_dir(Path(tmp), [], platform="AVR", mcu="atmega328p",
                                                     mcu_db="avr/atmega/ATmega328P.atdf", memory=None))
    assert_eq({s.kind for s in target.segments} >= {"flash", "ram", "eeprom"}, True)
    assert_eq(target.segment("ram", 0x08FC, 4).name, "IRAM")


# ---------------------------------------------------------------- 2. errors

def test_missing_or_incomplete_build_info_is_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        message = _raises(TargetError, lambda: target_model.load_target(Path(tmp) / "build_info.yaml"))
        assert "not found" in message, message
        path = _build_dir(Path(tmp), [], mcu_db=None, breakpoints=None)
        message = _raises(TargetError, lambda: target_model.load_target(path))
    assert "mcu_db" in message and "breakpoints" in message and "make MCU=" in message, message


def test_an_elf_given_that_does_not_exist_is_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), [])
        message = _raises(TargetError, lambda: target_model.load_target(path, Path(tmp) / "typo.elf"))
    assert "typo.elf" in message, message


# ---------------------------------------------------------------- 3. the ELF

def test_the_elf_given_replaces_the_example():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), [(0x08000000, 0x08000000, 0x100, 0x100)])
        user_elf = Path(tmp) / "mcu_mdt_user.elf"
        user_elf.write_bytes(elf_with_segments([(0x08000000, 0x08000000, 0x2000, 0x2000)]))
        assert_eq(target_model.load_target(path).firmware.size, 0x100)
        assert_eq(target_model.load_target(path, user_elf).firmware.size, 0x2000)


def test_no_elf_or_no_flash_image_means_no_symbols_and_no_firmware_range():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), [(0x20000000, 0x20000000, 0x10, 0x10)])     # RAM only
        assert_eq(target_model.load_target(path).firmware, None)
        (Path(tmp) / "mcu_mdt_example.elf").unlink()                             # e.g. after make lib
        target = target_model.load_target(path)
    assert_eq((target.symbols, target.firmware), ({}, None))


# ---------------------------------------------------------------- 4. register lookups

def _registers(*registers: tuple[str, str, int, int]) -> target_model.Registers:
    by_peripheral: dict[str, list] = {}
    for peripheral, name, address, size in registers:
        by_peripheral.setdefault(peripheral, []).append(
            device_description.Register(peripheral, name, address, size, True))
    return target_model.Registers(tuple(device_description.Peripheral(p, regs[0].address, "", tuple(regs))
                                        for p, regs in by_peripheral.items()))


def test_register_names_qualified_bare_and_indexed():
    regs = _registers(("TIM1", "CCMR1_Output", 0x40012C18, 4), ("TIM1_CH", "X", 0x40012C80, 4),
                      ("GPIOA", "ODR", 0x48000014, 4), ("GPIOB", "ODR", 0x48000414, 4), ("DMA", "CH3", 0x40020030, 4))
    assert_eq(regs.by_name("tim1_ccmr1_output").address, 0x40012C18)          # any case
    assert_eq(regs.by_name("TIM1_CH_X").address, 0x40012C80)                  # longest peripheral first
    assert_eq(regs.by_name("ODR").address, 0x48000014)                        # bare: first in file order
    assert_eq(regs.by_name("GPIOB_ODR").address, 0x48000414)
    assert_eq(regs.by_name("DMA_CH[3]").address, 0x40020030)                  # NAME[i] spelling
    assert_eq(regs.by_name("DMA_CH[9]"), None)                                # no such element
    assert_eq(regs.by_name("NOPE"), None)


def test_register_at_an_address_covers_all_its_bytes():
    regs = _registers(("USART", "UBRR0", 0xC4, 2), ("USART", "UDR0", 0xC6, 1))
    assert_eq([getattr(regs.at(a), "name", None) for a in (0xC3, 0xC4, 0xC5, 0xC6, 0xC7)],
              [None, "UBRR0", "UBRR0", "UDR0", None])
