from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

from pc_tool.common.enums import MCUPlatforms
from pc_tool.common.elf_symbols import load_elf_symbols
from pc_tool.common.logger import MDTLogger


# ---------------------------------------------------------------------------
# Shared data model
# ---------------------------------------------------------------------------

@dataclass
class MemorySegment:
    name:     str
    start:    int
    size:     int
    mem_type: str
    pagesize: str | None = None


@dataclass
class MCUMetadata:
    """Normalised MCU metadata produced by every platform loader."""
    device:       str
    architecture: str | None
    family:       str | None
    peripherals:  dict = field(default_factory=dict)
    modules:      dict = field(default_factory=dict)
    memories:     dict = field(default_factory=dict)
    interrupts:   dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Back-compat: validator.py and commander.py receive a plain dict."""
        return {
            "device":       self.device,
            "architecture": self.architecture,
            "family":       self.family,
            "peripherals":  self.peripherals,
            "modules":      self.modules,
            "memories":     self.memories,
            "interrupts":   self.interrupts,
        }


# ---------------------------------------------------------------------------
# Abstract base: every platform parser implements this interface
# ---------------------------------------------------------------------------

class _PlatformLoader(ABC):
    """Strategy interface for per-platform MCU metadata parsers."""

    @abstractmethod
    def load(self, mcu_name: str, db_root: str) -> MCUMetadata:
        """Return an MCUMetadata for *mcu_name*, sourcing data from *db_root*."""


# ---------------------------------------------------------------------------
# ATDF (AVR) parser
# ---------------------------------------------------------------------------

class _ATDFLoader(_PlatformLoader):
    """Parse Microchip ATDF files for AVR devices."""

    def load(self, mcu_name: str, db_root: str) -> MCUMetadata:
        mcu_lower = mcu_name.lower()
        atdf_path = self._find_file(mcu_lower, db_root)
        root      = self._parse_xml(atdf_path)
        device    = self._validate_device(root, mcu_lower)

        meta = MCUMetadata(
            device       = mcu_lower,
            architecture = device.get("architecture"),
            family       = device.get("family"),
        )

        self._parse_memories(root, meta)
        self._parse_modules(root, meta)
        self._parse_interrupts(root, meta)
        self._parse_peripherals(root, meta)
        return meta

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_file(mcu_name: str, db_root: str) -> str:
        for dirpath, _, files in os.walk(db_root):
            for fname in files:
                if fname.lower().endswith(".atdf") and \
                        os.path.splitext(fname)[0].lower() == mcu_name:
                    return os.path.join(dirpath, fname)
        raise FileNotFoundError(
            f"ATDF file for MCU '{mcu_name}' not found in {db_root}"
        )

    @staticmethod
    def _parse_xml(path: str) -> ET.Element:
        try:
            return ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Invalid ATDF XML in '{path}': {exc}") from exc

    @staticmethod
    def _validate_device(root: ET.Element, mcu_name: str) -> ET.Element:
        device = root.find("devices/device")
        if device is None:
            raise ValueError("ATDF missing <device> element")
        found = device.get("name", "").lower()
        if found != mcu_name:
            raise ValueError(
                f"ATDF device mismatch: expected '{mcu_name}', found '{found}'"
            )
        return device

    @staticmethod
    def _parse_memories(root: ET.Element, meta: MCUMetadata) -> None:
        for mem in root.findall(".//memory-segment"):
            name = mem.get("name")
            if not name:
                continue
            meta.memories[name] = {
                "start":    int(mem.get("start", "0"), 0),
                "size":     int(mem.get("size",  "0"), 0),
                "type":     mem.get("type"),
                "pagesize": mem.get("pagesize"),
            }

    @staticmethod
    def _parse_modules(root: ET.Element, meta: MCUMetadata) -> None:
        for module in root.findall(".//modules/module"):
            mod_name = module.get("name")
            if not mod_name:
                continue

            mod_entry: dict = {
                "caption":        module.get("caption"),
                "instances":      [],
                "register_groups": {},
            }

            for inst in module.findall(".//instance"):
                inst_data: dict = {"name": inst.get("name")}
                for rg in inst.findall(".//register-group"):
                    inst_data.update({
                        "register_group": rg.get("name-in-module"),
                        "offset":         rg.get("offset"),
                        "address_space":  rg.get("address-space"),
                    })
                mod_entry["instances"].append(inst_data)

            for rg in module.findall(".//register-group"):
                rg_name = rg.get("name")
                if not rg_name:
                    continue
                mod_entry["register_groups"][rg_name] = {
                    "name_in_module": rg.get("name-in-module"),
                    "caption":        rg.get("caption"),
                    "offset":         rg.get("offset"),
                    "registers":      _ATDFLoader._parse_registers(rg),
                }

            meta.modules[mod_name] = mod_entry

    @staticmethod
    def _parse_registers(rg_elem: ET.Element) -> dict:
        registers: dict = {}
        for reg in rg_elem.findall(".//register"):
            reg_name = reg.get("name")
            if not reg_name:
                continue
            registers[reg_name] = {
                "caption":   reg.get("caption"),
                "offset":    reg.get("offset"),
                "size":      reg.get("size"),
                "mask":      reg.get("mask"),
                "rw":        reg.get("rw"),
                "bitfields": _ATDFLoader._parse_bitfields(reg),
            }
        return registers

    @staticmethod
    def _parse_bitfields(reg_elem: ET.Element) -> dict:
        bitfields: dict = {}
        for bf in reg_elem.findall(".//bitfield"):
            bf_name = bf.get("name")
            if not bf_name:
                continue
            values: dict = {}
            for val in bf.findall(".//value"):
                val_name = val.get("name")
                if val_name:
                    values[val_name] = {
                        "caption": val.get("caption"),
                        "value":   val.get("value"),
                    }
            bitfields[bf_name] = {
                "caption": bf.get("caption"),
                "mask":    bf.get("mask"),
                "values":  values,
            }
        return bitfields

    @staticmethod
    def _parse_interrupts(root: ET.Element, meta: MCUMetadata) -> None:
        for intr in root.findall(".//interrupts/interrupt"):
            name = intr.get("name")
            if name:
                meta.interrupts[name] = {
                    "index":           intr.get("index"),
                    "caption":         intr.get("caption"),
                    "module_instance": intr.get("module-instance"),
                }

    @staticmethod
    def _parse_peripherals(root: ET.Element, meta: MCUMetadata) -> None:
        for periph in root.findall(".//peripherals/module"):
            pname = periph.get("name")
            if not pname or pname in meta.peripherals:
                continue
            meta.peripherals[pname] = {
                "caption":   periph.get("caption"),
                "instances": [
                    {"name": inst.get("name")}
                    for inst in periph.findall(".//instance")
                ],
            }


# ---------------------------------------------------------------------------
# SVD (STM32) parser
# ---------------------------------------------------------------------------

# Family fallback: 4-char suffix → (core subfolder, shared SVD filename)
_STM32_FAMILY_MAP: dict[str, tuple[str, str]] = {
    "f030": ("cortex-m0", "STM32F0x0.svd"),
    "f031": ("cortex-m0", "STM32F0x1.svd"),
    "f042": ("cortex-m0", "STM32F0x2.svd"),
    "f051": ("cortex-m0", "STM32F0x1.svd"),
    "f072": ("cortex-m0", "STM32F0x2.svd"),
    "f103": ("cortex-m3", "STM32F103.svd"),
}

_STM32_FLASH_BASE = 0x0800_0000
_STM32_RAM_BASE   = 0x2000_0000


class _SVDLoader(_PlatformLoader):
    """Parse ARM SVD files for STM32 devices."""

    def load(self, mcu_name: str, db_root: str) -> MCUMetadata:
        mcu_lower = mcu_name.lower()
        if not mcu_lower.startswith("stm32"):
            mcu_lower = "stm32" + mcu_lower

        svd_path   = self._find_svd(mcu_lower, db_root)
        yaml_path  = Path(svd_path).with_suffix(".yaml")
        mem_data   = load_configs(str(yaml_path)) if yaml_path.is_file() else None

        root, ns   = self._parse_xml(svd_path)
        find       = _SVDXmlHelper(root, ns)

        meta = MCUMetadata(
            device       = mcu_lower,
            architecture = find.text("cpu/name"),
            family       = find.text("name"),
        )

        self._parse_memories(mcu_lower, mem_data, meta)
        self._parse_peripherals(find, meta)
        return meta

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_svd(mcu_lower: str, db_root: str) -> str:
        # 1. Exact match
        for dirpath, _, files in os.walk(db_root):
            for fname in files:
                if fname.lower().endswith(".svd") and \
                        os.path.splitext(fname)[0].lower() == mcu_lower:
                    return os.path.join(dirpath, fname)

        # 2. Family fallback
        prefix = mcu_lower[5:9]
        if prefix in _STM32_FAMILY_MAP:
            subfolder, svd_fname = _STM32_FAMILY_MAP[prefix]
            candidate = os.path.join(db_root, "stm32", subfolder, svd_fname)
            if os.path.isfile(candidate):
                return candidate

        raise FileNotFoundError(
            f"SVD file for MCU '{mcu_lower}' not found in {db_root}"
        )

    @staticmethod
    def _parse_xml(path: str) -> tuple[ET.Element, dict]:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Invalid SVD XML in '{path}': {exc}") from exc

        ns: dict = {}
        if root.tag.startswith("{"):
            uri = root.tag.split("}")[0].strip("{")
            ns  = {"svd": uri}
        return root, ns

    @staticmethod
    def _parse_memories(
        mcu_lower: str,
        mem_data: dict | None,
        meta: MCUMetadata,
    ) -> None:
        if not mem_data:
            return

        variant = mem_data.get("variants", {}).get(mcu_lower, {})

        flash_size = variant.get("flash")
        ram_size   = variant.get("ram")
        flash_page = variant.get("flash_page")

        if flash_size:
            meta.memories["FLASH"] = {
                "start":    _STM32_FLASH_BASE,
                "size":     flash_size,
                "type":     "flash",
                "pagesize": str(flash_page) if flash_page else None,
            }
        if ram_size:
            meta.memories["RAM"] = {
                "start":    _STM32_RAM_BASE,
                "size":     ram_size,
                "type":     "ram",
                "pagesize": None,
            }

    @staticmethod
    def _parse_peripherals(find: "_SVDXmlHelper", meta: MCUMetadata) -> None:
        # Index all peripheral elements for derivedFrom resolution
        periph_elems: dict[str, ET.Element] = {
            name: elem
            for elem in find.all(".//peripheral")
            if (name := find.text_of(elem, "name"))
        }

        def resolve(elem: ET.Element) -> ET.Element:
            base = elem.get("derivedFrom")
            return periph_elems.get(base, elem) if base else elem

        for pname, p_elem in periph_elems.items():
            base_elem = resolve(p_elem)
            base_addr = _parse_int(find.text_of(p_elem, "baseAddress"))
            caption   = (
                find.text_of(p_elem, "description")
                or find.text_of(base_elem, "description")
                or ""
            )
            base_hex  = hex(base_addr)

            meta.peripherals[pname] = {
                "caption":   caption,
                "instances": [{"name": pname}],
            }
            meta.modules[pname] = {
                "caption":   caption,
                "instances": [{
                    "name":           pname,
                    "offset":         base_hex,
                    "register_group": pname,
                    "address_space":  "data",
                }],
                "register_groups": {
                    pname: {
                        "name_in_module": pname,
                        "caption":        caption,
                        "offset":         base_hex,
                        "registers":      _SVDLoader._parse_registers(
                            base_elem, find
                        ),
                    }
                },
            }

            for intr in find.children(p_elem, "interrupt"):
                int_name = find.text_of(intr, "name")
                if int_name and int_name not in meta.interrupts:
                    meta.interrupts[int_name] = {
                        "index":           find.text_of(intr, "value"),
                        "caption":         find.text_of(intr, "description"),
                        "module_instance": pname,
                    }

        for intr in find.all(".//interrupts/interrupt"):
            int_name = find.text_of(intr, "name")
            if int_name and int_name not in meta.interrupts:
                meta.interrupts[int_name] = {
                    "index":           find.text_of(intr, "value"),
                    "caption":         find.text_of(intr, "description"),
                    "module_instance": None,
                }

    @staticmethod
    def _parse_registers(base_elem: ET.Element, find: "_SVDXmlHelper") -> dict:
        registers: dict = {}
        for reg in find.children(base_elem, "registers/register"):
            reg_name = find.text_of(reg, "name")
            if not reg_name:
                continue

            reg_offset = _parse_int(find.text_of(reg, "addressOffset"))
            reg_size   = _parse_int(find.text_of(reg, "size") or "32", default=32)
            reg_rw     = find.text_of(reg, "access") or "read-write"
            reg_mask   = find.text_of(reg, "resetMask")

            registers[reg_name] = {
                "caption":   find.text_of(reg, "description"),
                "offset":    str(reg_offset),
                "size":      str(reg_size),
                "mask":      reg_mask,
                "rw":        reg_rw,
                "bitfields": _SVDLoader._parse_bitfields(reg, find),
            }

        return registers

    @staticmethod
    def _parse_bitfields(reg_elem: ET.Element, find: "_SVDXmlHelper") -> dict:
        bitfields: dict = {}
        for bf in find.children(reg_elem, "fields/field"):
            bf_name = find.text_of(bf, "name")
            if not bf_name:
                continue

            bit_range = find.text_of(bf, "bitRange")
            if not bit_range:
                lsb       = _parse_int(find.text_of(bf, "bitOffset"))
                width     = _parse_int(find.text_of(bf, "bitWidth") or "1", default=1)
                bit_range = f"[{lsb + width - 1}:{lsb}]"

            values: dict = {}
            for val in find.children(bf, "enumeratedValues/enumeratedValue"):
                val_name = find.text_of(val, "name")
                if val_name:
                    values[val_name] = {
                        "caption": find.text_of(val, "description"),
                        "value":   find.text_of(val, "value"),
                    }

            bitfields[bf_name] = {
                "caption": find.text_of(bf, "description"),
                "mask":    bit_range,
                "values":  values,
            }

        return bitfields


# ---------------------------------------------------------------------------
# SVD XML helper — abstracts namespace-aware findtext / findall
# ---------------------------------------------------------------------------

class _SVDXmlHelper:
    """Thin wrapper that handles optional XML namespaces transparently."""

    def __init__(self, root: ET.Element, ns: dict) -> None:
        self._root = root
        self._ns   = ns

    def text(self, path: str) -> str | None:
        try:
            return self._root.findtext(path, namespaces=self._ns)
        except TypeError:
            return self._root.findtext(path)

    def all(self, path: str) -> list[ET.Element]:
        try:
            return self._root.findall(path, namespaces=self._ns)
        except TypeError:
            return self._root.findall(path)

    def text_of(self, elem: ET.Element, path: str) -> str | None:
        try:
            return elem.findtext(path, namespaces=self._ns)
        except TypeError:
            return elem.findtext(path)

    def children(self, elem: ET.Element, path: str) -> list[ET.Element]:
        try:
            return elem.findall(path, namespaces=self._ns)
        except TypeError:
            return elem.findall(path)


# ---------------------------------------------------------------------------
# Platform loader registry — add new platforms here, nothing else changes
# ---------------------------------------------------------------------------

_PLATFORM_LOADERS: dict[str, _PlatformLoader] = {
    MCUPlatforms.AVR: _ATDFLoader(),
    MCUPlatforms.STM: _SVDLoader(),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_configs(file_path: str) -> dict:
    """Load and return the contents of a YAML file as a dict."""
    try:
        with open(file_path, "r") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        MDTLogger.error(f"Config file not found: {file_path}")
        return {}
    except yaml.YAMLError as exc:
        MDTLogger.error(f"Failed to parse YAML '{file_path}'", code=str(exc))
        return {}


def load_platforms(folder_path: str) -> dict:
    """Walk *folder_path* recursively and collect all platform YAML files."""
    platforms: dict = {}

    for yaml_path in _iter_yaml_files(folder_path):
        data = load_configs(yaml_path)
        platform_name = data.get("platform_name")
        if not platform_name:
            raise ValueError(
                f"Missing 'platform_name' key in platform file: {yaml_path}"
            )
        platforms[platform_name] = data

    return platforms


def load_mcu_metadata(mcu_name: str, mcu_platform: str) -> dict:
    """
    Dispatch to the correct platform loader and return metadata as a plain dict
    (for backwards compatibility with validator.py and commander.py).

    Raises
    ------
    NotImplementedError  If the platform has no loader registered yet.
    ValueError           If the platform string is not recognised.
    """
    platform = mcu_platform.lower()
    loader   = _PLATFORM_LOADERS.get(platform)

    if loader is None:
        if platform == MCUPlatforms.PIC:
            raise NotImplementedError("PIC platform support is not implemented yet")
        raise ValueError(f"Unsupported MCU platform: '{platform}'")

    return loader.load(mcu_name, db_root="pc_tool/mcu_db").to_dict()


# ---------------------------------------------------------------------------
# Top-level ConfigLoader — used by main.py
# ---------------------------------------------------------------------------

class ConfigLoader:
    """
    Load all configuration data needed to drive an MCU-MDT session.

    Parameters
    ----------
    build_info_path:  Path to the project's build_info.yaml.
    commands_path:    Path to commands.yaml (default matches repo layout).
    platforms_path:   Directory that contains per-platform YAML configs.
    """

    def __init__(
        self,
        build_info_path: str,
        commands_path:   str = "pc_tool/configs/commands.yaml",
        platforms_path:  str = "pc_tool/configs/platforms",
    ) -> None:
        self.yaml_build_data    = load_configs(build_info_path)
        self.yaml_command_data  = load_configs(commands_path)
        self.yaml_platform_data = load_platforms(platforms_path)

        mcu      = self.yaml_build_data.get("mcu")
        platform = self.yaml_build_data.get("platform", "")

        self.mcu_metadata = load_mcu_metadata(mcu, platform)
        self.elf_symbols  = self._load_elf(build_info_path)

    # ------------------------------------------------------------------

    def _load_elf(self, build_info_path: str) -> dict:
        elf_rel = self.yaml_build_data.get("elf")
        if not elf_rel:
            MDTLogger.info(
                "No 'elf' key in build_info.yaml — symbol resolution disabled. "
                "Add 'elf: path/to/firmware.elf' to enable watchpoint symbol lookup."
            )
            return {}

        build_dir = os.path.dirname(os.path.abspath(build_info_path))
        elf_path  = os.path.normpath(os.path.join(build_dir, elf_rel))
        platform  = self.yaml_build_data.get("platform", "")
        symbols   = load_elf_symbols(elf_path, platform)
        MDTLogger.info(f"Loaded {len(symbols)} symbol(s) from {elf_path}")
        return symbols


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _iter_yaml_files(folder: str) -> Iterator[str]:
    """Yield all .yaml / .yml file paths found recursively under *folder*."""
    for dirpath, _, files in os.walk(folder):
        for fname in files:
            if fname.endswith((".yaml", ".yml")):
                yield os.path.join(dirpath, fname)


def _parse_int(text: str | None, default: int = 0) -> int:
    """Convert a hex/decimal string to int, returning *default* on failure."""
    if not text:
        return default
    try:
        return int(text.strip(), 0)
    except ValueError:
        return default