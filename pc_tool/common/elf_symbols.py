from dataclasses import dataclass

from pc_tool.common.enums import MCUPlatforms
from pc_tool.common.logger import MDTLogger

try:
    from elftools.elf.elffile import ELFFile
    _ELFTOOLS_AVAILABLE = True
except ImportError:
    _ELFTOOLS_AVAILABLE = False

# AVR ELF encodes SRAM addresses with this offset — strip it before sending
AVR_SRAM_OFFSET = 0x800000

# AVR SRAM typically starts at 0x60 (ATmega) or 0x100 (larger devices)
# after stripping the offset. Flash symbols have raw_addr < AVR_SRAM_OFFSET.
AVR_SRAM_MIN = 0x60



@dataclass
class SymbolInfo:
    name:    str
    address: int   # address to send to MCU (AVR offset stripped, STM32 as-is)
    size:    int   # size in bytes from ELF (0 = unknown)
    mask:    int   # suggested 32-bit watch mask based on size


def _is_ram_symbol_avr(raw_addr: int) -> bool:
    """AVR: RAM symbols have the 0x800000 offset applied in the ELF."""
    return raw_addr >= AVR_SRAM_OFFSET


def _in_ranges(addr: int, ranges) -> bool:
    """True if addr falls in one of the [start, end) ranges."""
    return any(start <= addr < end for start, end in ranges)


def load_elf_symbols(elf_path: str, platform: str, ram_ranges=()) -> dict[str, SymbolInfo]:
    """
    Parse the .symtab of an ELF file and return a dict of symbol name -> SymbolInfo.
    Only data symbols (STT_OBJECT) that live in RAM are included — flash/const
    symbols are silently skipped since they cannot change and cannot be watched.
    *ram_ranges*: the part's RAM as [start, end) pairs (from the build's memory map);
    used where the address alone does not say RAM (STM32).
    Returns empty dict if ELF has no symbol table or pyelftools is missing.
    """
    if not _ELFTOOLS_AVAILABLE:
        MDTLogger.warning(
            "pyelftools not installed — symbol resolution unavailable. "
            "Install with: pip install pyelftools"
        )
        return {}

    plat = platform.lower()
    symbols: dict[str, SymbolInfo] = {}

    try:
        with open(elf_path, "rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab")
            if symtab is None:
                MDTLogger.warning(
                    f"No .symtab in {elf_path} — compile without -s "
                    f"(or add -g) to keep the symbol table."
                )
                return {}

            for sym in symtab.iter_symbols():
                if sym.entry.st_info.type != "STT_OBJECT":
                    continue

                raw_addr = sym.entry.st_value
                size     = sym.entry.st_size

                # Skip the null symbol
                if raw_addr == 0 and size == 0:
                    continue

                if plat == MCUPlatforms.AVR:
                    if not _is_ram_symbol_avr(raw_addr):
                        continue  # flash / EEPROM symbol, not watchable
                    addr = raw_addr - AVR_SRAM_OFFSET

                elif plat == MCUPlatforms.STM:
                    if not _in_ranges(raw_addr, ram_ranges):
                        continue  # flash / peripheral symbol, not watchable
                    addr = raw_addr  # STM32 ELF addresses are already correct

                else:
                    # Unknown platform — include everything, let the user decide
                    addr = raw_addr

                symbols[sym.name] = SymbolInfo(
                    name=sym.name,
                    address=addr,
                    size=size,
                    mask=_size_to_mask(size),
                )

    except FileNotFoundError:
        MDTLogger.warning(f"ELF file not found: {elf_path}")
    except Exception as exc:
        MDTLogger.warning(f"Failed to parse ELF symbols: {exc}")

    return symbols


def load_image_extent(elf_path: str, flash_ranges) -> tuple[int, int] | None:
    """Return [first, last) of what the ELF loads into flash: the firmware image.

    Uses the load segments' physical addresses (LMA), so .data initialisers stored
    after the code count too; that is exactly what objcopy writes to .bin/.hex.
    *flash_ranges*: the part's flash as [start, end) pairs. None if unknown.
    """
    if not _ELFTOOLS_AVAILABLE or not flash_ranges:
        return None
    try:
        with open(elf_path, "rb") as f:
            spans = [
                (seg["p_paddr"], seg["p_paddr"] + seg["p_filesz"])
                for seg in ELFFile(f).iter_segments()
                if seg["p_type"] == "PT_LOAD" and seg["p_filesz"] and _in_ranges(seg["p_paddr"], flash_ranges)
            ]
    except (OSError, ValueError) as exc:
        MDTLogger.warning(f"Cannot read the firmware range from {elf_path}: {exc}")
        return None
    if not spans:
        return None
    return min(start for start, _ in spans), max(end for _, end in spans)


def resolve_symbol(name: str, symbols: dict[str, SymbolInfo]) -> SymbolInfo | None:
    """Look up a symbol by name. Returns None if not found."""
    return symbols.get(name)


def check_watchpoint_alignment(sym: SymbolInfo) -> None:
    """
    Warn if the symbol is smaller than 4 bytes — the MCU always reads 4 bytes
    so adjacent variables will be included in the snapshot.
    The suggested MASK command is printed to help the user filter only the
    relevant bits.
    """
    if sym.size > 0 and sym.size < 4:
        type_str = {1: "uint8_t", 2: "uint16_t"}.get(sym.size, f"{sym.size}-byte")
        MDTLogger.warning(
            f"'{sym.name}' is {type_str} at 0x{sym.address:08X}. "
            f"MCU reads 4 bytes — adjacent variables will be included. "
            f"Suggested: WATCHPOINT <id> MASK 0x{_size_to_mask(sym.size):08X}"
        )


def _size_to_mask(size: int) -> int:
    """Return a LSB-aligned mask for a given byte size."""
    masks = {1: 0x000000FF, 2: 0x0000FFFF, 4: 0xFFFFFFFF}
    return masks.get(size, 0xFFFFFFFF)
