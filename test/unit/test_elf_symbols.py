"""
ELF TESTS (pc_tool/elf_symbols.py), on ELF files built in memory

Coverage:
1. image_extent: code + .data initialisers in flash; RAM-only segments and empty ranges ignored
2. ram_symbols: only RAM data objects are watchable, on any platform; AVR's data-space offset removed
3. narrow_symbol_hint: a variable narrower than the 4 sampled bytes gets a MASK hint
"""

import tempfile
from pathlib import Path

from pc_tool import elf_symbols
from test.common.asserts import assert_eq
from test.common.tiny_elf import elf_with_segments, elf_with_symbols


def _file(content: bytes, tmp: str) -> str:
    path = Path(tmp) / "a.elf"
    path.write_bytes(content)
    return str(path)


def test_image_extent_spans_code_and_data_initialisers_in_flash():
    with tempfile.TemporaryDirectory() as tmp:
        elf = _file(elf_with_segments([(0, 0, 0xBD4, 0xBD4), (0x800100, 0xBD4, 0x36, 0x36),
                                       (0x800136, 0x800136, 0, 0xC6)]), tmp)
        assert_eq(elf_symbols.image_extent(elf, [(0, 0x8000)]), (0, 0xC0A))   # AVR-like: .data LMA after .text
        assert_eq(elf_symbols.image_extent(elf, [(0x8000, 0x10000)]), None)  # nothing loads there
        assert_eq(elf_symbols.image_extent(elf, []), None)


def _watchable(platform: str, symbols: list, ram: list) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        found = elf_symbols.ram_symbols(_file(elf_with_symbols(symbols), tmp), platform, ram)
        return {name: (s.address, s.size) for name, s in found.items()}


def test_only_ram_symbols_are_watchable_on_any_platform():
    symbols = [("counter", 0x20000010, 4), ("table", 0x00001000, 4), ("gpio", 0x40000000, 4)]
    for platform in ("STM32", "NXP"):          # a platform the tool has never heard of behaves the same
        assert_eq(_watchable(platform, symbols, [(0x20000000, 0x20001000)]), {"counter": (0x20000010, 4)},
                  platform=platform)


def test_avr_symbols_lose_the_data_space_offset_and_flash_stays_out():
    symbols = [("ticks", 0x800100, 2), ("progmem_table", 0x150, 4), ("eeprom_cfg", 0x810000, 4)]
    assert_eq(_watchable("AVR", symbols, [(0x100, 0x900)]), {"ticks": (0x100, 2)})


def test_no_ram_range_or_no_file_means_no_watchable_symbols():
    assert_eq(_watchable("STM32", [("counter", 0x20000010, 4)], []), {})
    assert_eq(elf_symbols.ram_symbols("/nonexistent.elf", "STM32", [(0, 1)]), {})


def test_narrow_symbol_hint():
    assert_eq(elf_symbols.narrow_symbol_hint(elf_symbols.Symbol("word", 0x20000000, 4)), None)
    hint = elf_symbols.narrow_symbol_hint(elf_symbols.Symbol("flag", 0x20000004, 1))
    assert "uint8_t" in hint and "MASK 0x000000FF" in hint, hint
