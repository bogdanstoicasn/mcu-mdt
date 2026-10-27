"""The target MCU as the tool sees it, built once from build_info.yaml and read-only after.

Everything about the part comes from the build (build_system/ writes build_info.yaml): the
description file (ATDF/SVD), the memory map when the build has one, the breakpoint and watchpoint
counts, and the ELF. Nothing about a part is hardcoded here.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from pc_tool import MdtError, device_description, elf_symbols

log = logging.getLogger(__name__)

MCU_DB = Path(__file__).parent / "mcu_db"
BUILD_INFO_KEYS = ("platform", "mcu", "mcu_db", "port", "baudrate", "uart_idle", "breakpoints", "watchpoints", "elf")


class TargetError(MdtError):
    """build_info.yaml, the description file or the ELF given cannot be used."""


class Registers:
    """Every register of the part, looked up by name or by address. The first match in file order wins."""

    def __init__(self, peripherals: tuple[device_description.Peripheral, ...]) -> None:
        self._all = [register for peripheral in peripherals for register in peripheral.registers]
        self._qualified: dict[str, device_description.Register] = {}
        self._bare: dict[str, device_description.Register] = {}
        # PERIPH_A_B is (PERIPH_A, B) before (PERIPH, A_B): the longest peripheral name wins.
        for register in sorted(self._all, key=lambda r: -len(r.peripheral)):
            self._qualified.setdefault(f"{register.peripheral}_{register.name}".upper(), register)
        for register in self._all:
            self._bare.setdefault(register.name.upper(), register)

    def __len__(self) -> int:
        return len(self._all)

    def by_name(self, name: str) -> device_description.Register | None:
        """PERIPHERAL_REGISTER or a bare REGISTER, any case; NAME[3] is NAME3."""
        key = re.sub(r"\[(\w+)\]", r"\1", name).upper()
        return self._qualified.get(key) or self._bare.get(key)

    def at(self, address: int) -> device_description.Register | None:
        """The register whose bytes include *address*."""
        return next((r for r in self._all if r.address <= address < r.address + r.size), None)


@dataclass(frozen=True)
class Target:
    mcu: str
    platform: str
    port: str
    baudrate: int
    uart_idle: bool
    segments: tuple[device_description.Segment, ...]
    peripherals: tuple[device_description.Peripheral, ...]
    registers: Registers
    symbols: dict[str, elf_symbols.Symbol]
    breakpoints: int
    watchpoints: int
    firmware: device_description.Segment | None   # the flash the running image occupies, if known
    build_info: dict                              # as read, for the session log

    def segment(self, kind: str, address: int, length: int) -> device_description.Segment | None:
        """The first memory segment of *kind* holding all of [address, address + length)."""
        return next((s for s in self.segments if s.kind == kind and s.holds(address, length)), None)

    def segments_of(self, kind: str) -> list[device_description.Segment]:
        return [s for s in self.segments if s.kind == kind]


def load_target(build_info: str | Path, elf: str | Path | None = None) -> Target:
    """Build the Target from *build_info*; *elf* replaces the ELF it names (a user project's firmware)."""
    path = Path(build_info)
    info = _read_build_info(path)
    description = device_description.read_description(MCU_DB / info["mcu_db"], info["mcu"])
    segments = _build_segments(info.get("memory")) or description.segments

    if elf is not None and not Path(elf).is_file():
        raise TargetError(f"--elf {elf}: no such file")
    elf_path = Path(elf) if elf is not None else path.resolve().parent / info["elf"]
    symbols, firmware = {}, None
    if elf_path.is_file():
        ram = [(s.start, s.start + s.size) for s in segments if s.kind == "ram"]
        symbols = elf_symbols.ram_symbols(str(elf_path), info["platform"], ram)
        log.info("Loaded %d symbol(s) from %s", len(symbols), elf_path)
        firmware = _firmware(str(elf_path), segments)
    else:
        log.warning("Firmware ELF %s not found: no symbols, and flash writes and erases are not checked "
                    "against the running image. Give the ELF you flashed with --elf <file>.", elf_path)

    return Target(
        mcu=info["mcu"], platform=info["platform"], port=info["port"], baudrate=int(info["baudrate"]),
        uart_idle=bool(info["uart_idle"]), segments=tuple(segments), peripherals=description.peripherals,
        registers=Registers(description.peripherals), symbols=symbols,
        breakpoints=int(info["breakpoints"]), watchpoints=int(info["watchpoints"]),
        firmware=firmware, build_info=info,
    )


def _read_build_info(path: Path) -> dict:
    try:
        info = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raise TargetError(f"Config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise TargetError(f"Failed to parse YAML '{path}': {exc}") from exc
    missing = [key for key in BUILD_INFO_KEYS if key not in info]
    if missing:
        raise TargetError(f"{path} has no {', '.join(missing)}: it is missing or comes from an older build. "
                          f"Rebuild with: make MCU=<part>")
    return info


def _build_segments(memory: dict | None) -> list[device_description.Segment]:
    """The build's memory map (STM32); it replaces the description file's segments. A region's name is its kind."""
    return [device_description.Segment(name.upper(), name, int(region["origin"]), int(region["size"]),
                                       int(region["page"]) if region.get("page") else None)
            for name, region in (memory or {}).items()]


def _firmware(elf_path: str, segments: list[device_description.Segment]) -> device_description.Segment | None:
    """The flash the ELF's image occupies, with the erase page of the segment it starts in."""
    flash = [s for s in segments if s.kind == "flash"]
    extent = elf_symbols.image_extent(elf_path, [(s.start, s.start + s.size) for s in flash])
    if extent is None:
        log.warning("Firmware range unknown (no ELF or no load segment in flash): "
                    "flash writes and erases are not checked against the running image.")
        return None
    start, end = extent
    page = next((s.page for s in flash if s.holds(start)), None)
    return device_description.Segment("firmware", "flash", start, end - start, page)
