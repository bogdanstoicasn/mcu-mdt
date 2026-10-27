"""What the firmware ELF tells the tool: the RAM variables it can watch, and the flash its image occupies."""

import logging
from dataclasses import dataclass

from elftools.elf.elffile import ELFFile

log = logging.getLogger(__name__)

# avr-gcc puts the data space (RAM, registers) at this offset in the ELF to keep it apart from flash
# at 0; the MCU sees the address without it. Other toolchains use the real address.
AVR_DATA_OFFSET = 0x800000


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    address: int              # as the MCU sees it (AVR data-space offset removed)
    size: int                 # bytes, 0 when the ELF does not say


def ram_symbols(elf_path: str, platform: str, ram_ranges: list[tuple[int, int]]) -> dict[str, Symbol]:
    """The data objects of the ELF that live in RAM (the [start, end) *ram_ranges*): what can be watched.

    Flash, EEPROM and peripheral symbols are left out: they cannot change, or must not be sampled.
    """
    if not ram_ranges:
        log.warning("No RAM region known for this part: watchpoint symbol lookup disabled.")
        return {}
    try:
        with open(elf_path, "rb") as file:
            table = ELFFile(file).get_section_by_name(".symtab")
            if table is None:
                log.warning("No .symtab in %s — compile without -s (or add -g) to keep the symbol table.", elf_path)
                return {}
            symbols = {}
            for sym in table.iter_symbols():
                raw, size = sym.entry.st_value, sym.entry.st_size
                if sym.entry.st_info.type != "STT_OBJECT" or (raw == 0 and size == 0):
                    continue
                address = _mcu_address(raw, platform)
                if address is not None and any(start <= address < end for start, end in ram_ranges):
                    symbols[sym.name] = Symbol(sym.name, address, size)
            return symbols
    except FileNotFoundError:
        log.warning("ELF file not found: %s", elf_path)
    except Exception as exc:                              # a damaged ELF must not stop the session
        log.warning("Failed to parse ELF symbols: %s", exc)
    return {}


def image_extent(elf_path: str, flash_ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    """[first, last) of what the ELF loads into flash: the firmware image, None if unknown.

    Load segments are placed by their physical address (LMA), so .data initialisers stored after the
    code count too: exactly what objcopy writes to the .bin/.hex.
    """
    if not flash_ranges:
        return None
    try:
        with open(elf_path, "rb") as file:
            spans = [(seg["p_paddr"], seg["p_paddr"] + seg["p_filesz"]) for seg in ELFFile(file).iter_segments()
                     if seg["p_type"] == "PT_LOAD" and seg["p_filesz"]
                     and any(start <= seg["p_paddr"] < end for start, end in flash_ranges)]
    except (OSError, ValueError) as exc:
        log.warning("Cannot read the firmware range from %s: %s", elf_path, exc)
        return None
    if not spans:
        return None
    return min(start for start, _ in spans), max(end for _, end in spans)


def narrow_symbol_hint(symbol: Symbol) -> str | None:
    """The warning for watching a variable narrower than the 4 bytes the MCU samples, or None."""
    if not 0 < symbol.size < 4:
        return None
    type_name = {1: "uint8_t", 2: "uint16_t"}.get(symbol.size, f"{symbol.size}-byte")
    mask = {1: 0xFF, 2: 0xFFFF}.get(symbol.size, 0xFFFFFFFF)
    return (f"'{symbol.name}' is {type_name} at 0x{symbol.address:08X}. MCU reads 4 bytes — adjacent variables "
            f"will be included. Suggested: WATCHPOINT <id> MASK 0x{mask:08X}")


def _mcu_address(raw: int, platform: str) -> int | None:
    """The MCU's address for an ELF symbol address; None for an AVR symbol outside the data space."""
    if platform.lower() == "avr":
        return raw - AVR_DATA_OFFSET if raw >= AVR_DATA_OFFSET else None
    return raw
