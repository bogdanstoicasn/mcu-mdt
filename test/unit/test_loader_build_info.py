"""
PC TOOL: WHAT IT TAKES FROM THE BUILD (build_info.yaml)

The host side has no per-part tables: the build (build_system/) names the description
file, provides the memory map and the breakpoint/watchpoint counts, and the ELF gives the
firmware range. These tests pin that contract without a toolchain or a board.

Coverage:
1. Description file chosen by build_info's mcu_db, parser by file type
2. ConfigLoader: required keys, memory map, limits, firmware range from the ELF
3. load_image_extent on a hand-built ELF (code + .data initialisers, RAM-only segment ignored)
4. Watchable symbols: inside the part's RAM on every platform; AVR's ELF data-space offset stripped
"""

import tempfile
from pathlib import Path

from pc_tool.common.elf_symbols import load_elf_symbols, load_image_extent
from pc_tool.loader import ConfigLoader, load_mcu_metadata
from test.common.asserts import assert_eq
from test.common.tiny_elf import elf_with_segments as _elf32
from test.common.tiny_elf import elf_with_symbols as _elf32_symbols

_F0 = {"flash": {"origin": 0x08000000, "size": 16384, "page": 1024}, "ram": {"origin": 0x20000000, "size": 4096}}


def _build_dir(tmp: Path, info: dict, segments: list) -> str:
    (tmp / "mcu_mdt_example.elf").write_bytes(_elf32(segments))
    lines = [f"{k}: {v}" for k, v in info.items() if k != "memory"]
    if "memory" in info:
        lines.append("memory:")
        lines += [f"  {name}: {r}" for name, r in info["memory"].items()]
    (tmp / "build_info.yaml").write_text("\n".join(lines) + "\n")
    return str(tmp / "build_info.yaml")


def _f0_info(**overrides) -> dict:
    info = {"platform": "STM32", "mcu": "f030f4", "mcu_db": "stm32/cortex-m0/STM32F0x0.svd",
            "port": "/dev/null", "baudrate": 19200, "uart_idle": "true", "breakpoints": 6, "watchpoints": 2,
            "elf": "mcu_mdt_example.elf", "memory": _F0}
    info.update(overrides)
    return info


# ---------------------------------------------------------------- 1. description file

def test_description_file_comes_from_the_build():
    meta = load_mcu_metadata("f030f4", "stm32/cortex-m0/STM32F0x0.svd")
    assert_eq((meta["device"], meta["family"]), ("f030f4", "STM32F0x0"))   # no vendor prefix added
    assert "USART1" in meta["modules"]
    meta = load_mcu_metadata("atmega328p", "avr/atmega/ATmega328P.atdf")
    assert_eq(meta["memories"]["FLASH"]["size"], 0x8000)


def test_unknown_description_file_type_or_path_is_an_error():
    for mcu_db, error in (("stm32/x.txt", ValueError), ("stm32/missing.svd", FileNotFoundError)):
        try:
            load_mcu_metadata("x", mcu_db)
        except error:
            continue
        raise AssertionError(f"{mcu_db} did not raise {error.__name__}")


# ---------------------------------------------------------------- 2. ConfigLoader

def test_loader_takes_memory_limits_and_firmware_from_the_build():
    with tempfile.TemporaryDirectory() as tmp:
        # code at the start of flash, .data stored right after it, .bss only in RAM
        path = _build_dir(Path(tmp), _f0_info(), [(0x08000000, 0x08000000, 0xB60, 0xB60),
                                                  (0x20000000, 0x08000B60, 0x1C, 0x1C),
                                                  (0x2000001C, 0x2000001C, 0, 0xD0)])
        loader = ConfigLoader(path)
        meta = loader.mcu_metadata
        assert_eq(meta["memories"], {
            "FLASH": {"start": 0x08000000, "size": 16384, "type": "flash", "pagesize": "0x400"},
            "RAM":   {"start": 0x20000000, "size": 4096, "type": "ram", "pagesize": None},
        })
        assert_eq(meta["limits"], {"breakpoints": 6, "watchpoints": 2})
        assert_eq(meta["firmware"], {"start": 0x08000000, "end": 0x08000B7C, "size": 0xB7C, "page_size": 1024})


def test_loader_rejects_an_old_or_incomplete_build_info():
    with tempfile.TemporaryDirectory() as tmp:
        info = _f0_info()
        del info["mcu_db"], info["breakpoints"]
        path = _build_dir(Path(tmp), info, [])
        try:
            ConfigLoader(path)
        except ValueError as exc:
            assert "mcu_db" in str(exc) and "breakpoints" in str(exc) and "make MCU=" in str(exc), str(exc)
            return
        raise AssertionError("an incomplete build_info.yaml was accepted")


def test_loader_takes_the_elf_given_instead_of_the_example():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), _f0_info(), [(0x08000000, 0x08000000, 0x100, 0x100)])
        user_elf = Path(tmp) / "mcu_mdt_user.elf"
        user_elf.write_bytes(_elf32([(0x08000000, 0x08000000, 0x2000, 0x2000)]))
        assert_eq(ConfigLoader(path).mcu_metadata["firmware"]["end"], 0x08000100)
        assert_eq(ConfigLoader(path, elf_path=str(user_elf)).mcu_metadata["firmware"]["end"], 0x08002000)


def test_loader_without_the_example_elf_has_no_symbols_and_no_firmware_range():
    with tempfile.TemporaryDirectory() as tmp:     # e.g. after make lib, which links no example
        path = _build_dir(Path(tmp), _f0_info(), [])
        (Path(tmp) / "mcu_mdt_example.elf").unlink()
        loader = ConfigLoader(path)
        assert_eq(loader.elf_symbols, {})
        assert "firmware" not in loader.mcu_metadata


def test_loader_rejects_a_missing_elf_given_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), _f0_info(), [])
        try:
            ConfigLoader(path, elf_path=str(Path(tmp) / "typo.elf"))
        except FileNotFoundError:
            return
        raise AssertionError("a missing --elf was accepted")


def test_loader_without_a_flash_image_records_no_firmware_range():
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_dir(Path(tmp), _f0_info(), [(0x20000000, 0x20000000, 0x10, 0x10)])
        assert "firmware" not in ConfigLoader(path).mcu_metadata


# ---------------------------------------------------------------- 3. image extent

def test_image_extent_spans_code_and_data_initialisers_in_flash():
    with tempfile.TemporaryDirectory() as tmp:
        elf = Path(tmp) / "a.elf"
        elf.write_bytes(_elf32([(0, 0, 0xBD4, 0xBD4), (0x800100, 0xBD4, 0x36, 0x36), (0x800136, 0x800136, 0, 0xC6)]))
        assert_eq(load_image_extent(str(elf), [(0, 0x8000)]), (0, 0xC0A))      # AVR-like: .data LMA after .text
        assert_eq(load_image_extent(str(elf), [(0x8000, 0x10000)]), None)       # nothing loads there
        assert_eq(load_image_extent(str(elf), []), None)


# ---------------------------------------------------------------- 4. watchable symbols

def _watchable(platform: str, symbols: list, ram: list) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        elf = Path(tmp) / "a.elf"
        elf.write_bytes(_elf32_symbols(symbols))
        return {name: info.address for name, info in load_elf_symbols(str(elf), platform, ram).items()}


def test_only_ram_symbols_are_watchable_on_any_platform():
    symbols = [("counter", 0x20000010, 4), ("table", 0x00001000, 4), ("gpio", 0x40000000, 4)]
    for platform in ("STM32", "NXP"):      # a platform the PC tool has never heard of behaves the same
        assert_eq(_watchable(platform, symbols, [(0x20000000, 0x20001000)]), {"counter": 0x20000010},
                  platform=platform)


def test_avr_symbols_lose_the_data_space_offset_and_flash_stays_out():
    symbols = [("ticks", 0x800100, 2), ("progmem_table", 0x150, 4), ("eeprom_cfg", 0x810000, 4)]
    assert_eq(_watchable("AVR", symbols, [(0x100, 0x900)]), {"ticks": 0x100})


def test_no_ram_range_means_no_watchable_symbols():
    assert_eq(_watchable("STM32", [("counter", 0x20000010, 4)], []), {})
