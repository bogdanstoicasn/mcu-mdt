from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pc_tool.common.elf_symbols import load_elf_symbols, load_image_extent
from pc_tool.common.logger import MDTLogger

# Resolved at import time
_DB_ROOT: Path = Path(__file__).parent / "mcu_db"

# Shared data model
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


# Abstract base: every platform parser implements this interface
class _PlatformLoader(ABC):
    """Strategy interface for per-platform MCU metadata parsers."""

    @abstractmethod
    def load(self, mcu_name: str, path: str) -> MCUMetadata:
        """Return an MCUMetadata for *mcu_name*, parsed from the description file at *path*."""


# ATDF (AVR) parser
class _ATDFLoader(_PlatformLoader):
    """Parse Microchip ATDF files for AVR devices."""

    def load(self, mcu_name: str, path: str) -> MCUMetadata:
        """Parse the ATDF file at *path* (the build names it) into MCUMetadata for *mcu_name*."""
        mcu_lower = mcu_name.lower()
        root      = self._parse_xml(path)
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

    @staticmethod
    def _parse_xml(path: str) -> ET.Element:
        """Parse the ATDF XML file at *path* and return the root element."""
        try:
            return ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Invalid ATDF XML in '{path}': {exc}") from exc

    @staticmethod
    def _validate_device(root: ET.Element, mcu_name: str) -> ET.Element:
        """Find and validate the <device> element in the ATDF XML, ensuring it matches *mcu_name*."""
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
        """Parse <memory-segment> elements from the ATDF XML and populate meta.memories."""
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
        """Parse <module> elements from the ATDF XML and populate meta.modules."""
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
        """Parse <register> elements from a <register-group> and return a dict of register metadata."""
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
        """Parse <bitfield> elements from a <register> and return a dict of bitfield metadata."""
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
        """Parse <interrupt> elements from the ATDF XML and populate meta.interrupts."""
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
        """Parse <peripheral> elements from the ATDF XML and populate meta.peripherals."""
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


class _SVDLoader(_PlatformLoader):
    """Parse CMSIS-SVD files (any Arm vendor: ST, NXP, ...)."""

    def load(self, mcu_name: str, path: str) -> MCUMetadata:
        """Parse the SVD file at *path* (the build names it). Memory comes from the build, not the SVD.
        The device is the part as the build names it; the SVD's own name (a family) is `family`."""
        root, ns   = self._parse_xml(path)
        find       = _SVDXmlHelper(root, ns)

        meta = MCUMetadata(
            device       = mcu_name.lower(),
            architecture = find.text("cpu/name"),
            family       = find.text("name"),
        )

        self._parse_peripherals(find, meta)
        return meta

    @staticmethod
    def _parse_xml(path: str) -> tuple[ET.Element, dict]:
        """Parse the SVD XML file at *path* and return the root element along with any namespace mappings."""
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
    def _parse_peripherals(find: _SVDXmlHelper, meta: MCUMetadata) -> None:
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
    def _parse_registers(base_elem: ET.Element, find: _SVDXmlHelper) -> dict:
        """Parse a peripheral's registers into a flat ``name -> metadata`` dict.

        CMSIS-SVD ``<dim>`` arrays and ``<cluster>`` blocks are expanded so
        every element is an individually addressable register:

          AHBCLKCTRLSET[%s] (dim 4)      -> AHBCLKCTRLSET0 .. AHBCLKCTRLSET3
          CHANNEL[%s] cluster, reg CTRL  -> CHANNEL2_CTRL   (cluster instance 2)

        Offsets are relative to the peripheral base, as before.
        """
        registers: dict = {}
        regs_elem = next(iter(find.children(base_elem, "registers")), None)
        if regs_elem is None:
            return registers

        def add_register(reg: ET.Element, base_off: int, prefix: str) -> None:
            reg_name = find.text_of(reg, "name")
            if not reg_name:
                return

            reg_offset = _parse_int(find.text_of(reg, "addressOffset"))
            reg_size   = _parse_int(find.text_of(reg, "size") or "32", default=32)
            reg_rw     = find.text_of(reg, "access") or "read-write"
            reg_mask   = find.text_of(reg, "resetMask")

            for idx, step in _expand_dim(reg, find):
                registers[prefix + _dim_name(reg_name, idx)] = {
                    "caption":   find.text_of(reg, "description"),
                    "offset":    str(base_off + reg_offset + step),
                    "size":      str(reg_size),
                    "mask":      reg_mask,
                    "rw":        reg_rw,
                    "bitfields": _SVDLoader._parse_bitfields(reg, find),
                }

        def walk(container: ET.Element, base_off: int, prefix: str) -> None:
            for child in find.children(container, "*"):
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "register":
                    add_register(child, base_off, prefix)
                elif tag == "cluster":
                    c_name = find.text_of(child, "name") or ""
                    c_off  = _parse_int(find.text_of(child, "addressOffset"))
                    for idx, step in _expand_dim(child, find):
                        walk(child, base_off + c_off + step,
                             prefix + _dim_name(c_name, idx) + "_")

        walk(regs_elem, 0, "")
        return registers

    @staticmethod
    def _parse_bitfields(reg_elem: ET.Element, find: _SVDXmlHelper) -> dict:
        """Parse <field> elements from a <register> and return a dict of bitfield metadata."""
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


# SVD XML helper — abstracts namespace-aware findtext / findall
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

# Description-file parsers by file type; the build says which file a part uses (build_info: mcu_db)
_LOADERS_BY_SUFFIX: dict[str, _PlatformLoader] = {
    ".atdf": _ATDFLoader(),
    ".svd":  _SVDLoader(),
}


# Public helpers
def load_configs(file_path: str) -> dict:
    """Load and return the contents of a YAML file as a dict."""
    try:
        with open(file_path) as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        MDTLogger.error(f"Config file not found: {file_path}")
        return {}
    except yaml.YAMLError as exc:
        MDTLogger.error(f"Failed to parse YAML '{file_path}': {exc}", code=1)
        return {}


def load_mcu_metadata(mcu_name: str, mcu_db: str) -> dict:
    """
    Parse the description file of a part and return its metadata as a plain dict
    (for backwards compatibility with validator.py and commander.py).

    *mcu_db* is the file named in build_info.yaml, relative to pc_tool/mcu_db (or absolute).

    Raises
    ------
    FileNotFoundError  If the file does not exist.
    ValueError         If no parser handles the file type.
    """
    path   = _DB_ROOT / mcu_db
    loader = _LOADERS_BY_SUFFIX.get(path.suffix.lower())
    if loader is None:
        raise ValueError(f"No parser for '{mcu_db}': known file types are {', '.join(_LOADERS_BY_SUFFIX)}")
    if not path.is_file():
        raise FileNotFoundError(f"MCU description file not found: {path}")
    return loader.load(mcu_name, str(path)).to_dict()


# Top-level ConfigLoader — used by main.py

# Written by build_system/generate.py; an older build_info.yaml lacks some of these.
_BUILD_INFO_KEYS = ("platform", "mcu", "mcu_db", "port", "baudrate", "uart_idle",
                    "breakpoints", "watchpoints", "elf")


class ConfigLoader:
    """
    Load all configuration data needed to drive an MCU-MDT session.

    Everything about the target comes from build_info.yaml, written by the build from
    build_system/: the description file (ATDF/SVD), the memory map when the build has one,
    the breakpoint/watchpoint limits and the ELF. Nothing about a part is hardcoded here.

    Parameters
    ----------
    build_info_path:  Path to the project's build_info.yaml.
    commands_path:    Path to commands.yaml (default: the package's own, wherever it is run from).
    platforms_path:   Directory that contains per-platform YAML configs.
    """

    def __init__(
        self,
        build_info_path: str = "build/",
        commands_path:   str = str(Path(__file__).parent / "configs" / "commands.yaml"),
        platforms_path:  str = "pc_tool/configs/platforms",
    ) -> None:
        self.yaml_build_data    = load_configs(build_info_path)
        self.yaml_command_data  = load_configs(commands_path)

        info    = self.yaml_build_data
        missing = [key for key in _BUILD_INFO_KEYS if key not in info]
        if missing:
            raise ValueError(
                f"{build_info_path} has no {', '.join(missing)}: it is missing or comes from an "
                f"older build. Rebuild with: make MCU=<part>"
            )

        self.mcu_metadata = load_mcu_metadata(info["mcu"], info["mcu_db"])
        self._apply_build_memory()
        self.mcu_metadata["limits"] = {
            "breakpoints": int(info["breakpoints"]),
            "watchpoints": int(info["watchpoints"]),
        }
        elf_path          = os.path.join(os.path.dirname(os.path.abspath(build_info_path)), info["elf"])
        self.elf_symbols  = self._load_elf(elf_path)
        self._inject_firmware_info(elf_path)

    def _apply_build_memory(self) -> None:
        """Use the build's memory map (from build_system/) when it has one; it replaces the
        description file's segments. A region's name is its type: flash, ram, eeprom."""
        regions = self.yaml_build_data.get("memory") or {}
        if not regions:
            return
        self.mcu_metadata["memories"] = {
            name.upper(): {
                "start":    int(region["origin"]),
                "size":     int(region["size"]),
                "type":     name,
                "pagesize": hex(region["page"]) if region.get("page") else None,
            }
            for name, region in regions.items()
        }

    def _flash_segments(self) -> list[dict]:
        return [seg for seg in self.mcu_metadata.get("memories", {}).values() if seg.get("type") == "flash"]

    def _inject_firmware_info(self, elf_path: str) -> None:
        """Protect the running firmware: record the flash range the ELF loads.

        The validator uses it to reject writes and erases that would overwrite the
        firmware. The range is read from the ELF's load segments inside flash, so it is
        exactly what objcopy puts in the image (code, read-only data, .data initialisers).
        """
        flash = self._flash_segments()
        ranges = [(int(seg["start"]), int(seg["start"]) + int(seg["size"])) for seg in flash]
        extent = load_image_extent(elf_path, ranges)
        if extent is None:
            MDTLogger.warning(
                "Firmware range unknown (no ELF or no load segment in flash): "
                "flash writes and erases are not checked against the running image."
            )
            return

        start, end = extent
        page = next((seg.get("pagesize") for seg in flash
                     if int(seg["start"]) <= start < int(seg["start"]) + int(seg["size"])), None)
        self.mcu_metadata["firmware"] = {
            "start":     start,
            "end":       end,
            "size":      end - start,
            "page_size": int(page, 0) if isinstance(page, str) else page,
        }

    def _load_elf(self, elf_path: str) -> dict:
        """Load the watchable (RAM) symbols of the firmware ELF."""
        ram = [
            (int(seg["start"]), int(seg["start"]) + int(seg["size"]))
            for seg in self.mcu_metadata.get("memories", {}).values() if seg.get("type") == "ram"
        ]
        symbols = load_elf_symbols(elf_path, self.yaml_build_data["platform"], ram)
        MDTLogger.info(f"Loaded {len(symbols)} symbol(s) from {elf_path}")
        return symbols


# Internal utilities
def _iter_yaml_files(folder: str) -> Iterator[str]:
    """Yield all .yaml / .yml file paths found recursively under *folder*."""
    for dirpath, _, files in os.walk(folder):
        for fname in files:
            if fname.endswith((".yaml", ".yml")):
                yield os.path.join(dirpath, fname)



def _dim_indices(text: str | None, dim: int) -> list[str]:
    """Expand an SVD <dimIndex> (``0,1,2`` / ``0-3`` / ``A-D``) to labels.

    Falls back to ``0..dim-1`` when absent, malformed, or inconsistent with *dim*.
    """
    labels: list[str] = []
    if text:
        text = text.strip()
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
        a = re.fullmatch(r"([A-Za-z])\s*-\s*([A-Za-z])", text)
        if "," in text:
            labels = [s.strip() for s in text.split(",") if s.strip()]
        elif m:
            labels = [str(i) for i in range(int(m.group(1)), int(m.group(2)) + 1)]
        elif a:
            labels = [chr(c) for c in range(ord(a.group(1)), ord(a.group(2)) + 1)]
    if len(labels) != dim:
        if labels:
            MDTLogger.warning(
                f"SVD dimIndex '{text}' does not match dim={dim}; using 0..{dim - 1}."
            )
        labels = [str(i) for i in range(dim)]
    return labels


def _expand_dim(elem: ET.Element, find: _SVDXmlHelper) -> list[tuple[str | None, int]]:
    """Return ``(index_label, byte_offset)`` for every element of a <dim> array.

    An element without <dim> yields a single ``(None, 0)`` entry.
    """
    dim_txt = find.text_of(elem, "dim")
    if dim_txt is None:
        return [(None, 0)]
    dim = _parse_int(dim_txt)
    inc = _parse_int(find.text_of(elem, "dimIncrement"))
    labels = _dim_indices(find.text_of(elem, "dimIndex"), dim)
    return [(label, pos * inc) for pos, label in enumerate(labels)]


def _dim_name(name: str, idx: str | None) -> str:
    """Substitute an array index into an SVD name (``X[%s]`` / ``X%s`` -> ``X3``)."""
    if idx is None:
        return name
    name = name.replace("[%s]", "%s")
    return name.replace("%s", idx) if "%s" in name else name + idx

def _parse_int(text: str | None, default: int = 0) -> int:
    """Convert a hex/decimal string to int, returning *default* on failure."""
    if not text:
        return default
    try:
        return int(text.strip(), 0)
    except ValueError:
        return default
