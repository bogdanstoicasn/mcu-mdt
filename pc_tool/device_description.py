"""Read a part's description file into its peripherals, registers and memory segments.

The format is picked by the file suffix:

    .atdf   Microchip ATDF (AVR). Register sizes are in bytes; addresses are data-space addresses.
    .svd    CMSIS-SVD (any Arm vendor), read by the rules of the CMSIS-SVD specification:
            derivedFrom on peripherals, clusters and registers (by name in the same scope, or by
            a full PERIPH.CLUSTER.REG path); dim with NAME[%s] arrays or %s + dimIndex labels;
            cluster and register names joined with "_" (CH0_CTRL); size and access inherited
            device -> peripheral -> cluster -> register; a register that reuses a name inside an
            alternateGroup becomes NAME_GROUP.

Only what the tool uses is kept: peripherals (name, base address, description), their registers
(absolute address, size in bytes, whether writable) and, from an ATDF, the memory segments.
"""

import copy
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pc_tool import MdtError

log = logging.getLogger(__name__)

_SVD_DEFAULT_PROPERTIES = {"size": "32", "access": "read-write"}   # when no level of the file says


class DescriptionError(MdtError):
    """The description file is missing, of an unknown type, malformed, or for another part."""


@dataclass(frozen=True, slots=True)
class Register:
    peripheral: str           # qualified names are PERIPHERAL_NAME
    name: str                 # cluster and array parts already joined: CH0_CTRL
    address: int
    size: int                 # bytes
    writable: bool


@dataclass(frozen=True, slots=True)
class Peripheral:
    name: str                 # SVD: the peripheral (USART1). ATDF: the module (USART)
    base: int                 # SVD: baseAddress. ATDF: the lowest register address
    description: str
    registers: tuple[Register, ...]


@dataclass(frozen=True, slots=True)
class Segment:
    name: str
    kind: str                 # flash, ram, eeprom, ... as the build or the ATDF names it
    start: int
    size: int
    page: int | None = None   # flash erase page, when known

    def holds(self, address: int, length: int = 1) -> bool:
        return self.start <= address and address + length <= self.start + self.size


@dataclass(frozen=True, slots=True)
class Description:
    peripherals: tuple[Peripheral, ...]
    segments: tuple[Segment, ...]     # an SVD has none: the build's memory map provides them


def read_description(path: Path, mcu: str) -> Description:
    """Read the description file at *path* for the part *mcu*."""
    readers = {".atdf": _read_atdf, ".svd": _read_svd}
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise DescriptionError(f"No parser for '{path.name}': known file types are {', '.join(readers)}")
    if not path.is_file():
        raise DescriptionError(f"MCU description file not found: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise DescriptionError(f"Invalid {path.suffix[1:].upper()} XML in '{path}': {exc}") from exc
    return reader(root, mcu)


def _writable(access: str | None) -> bool:
    """SVD: read-only / read-write / write-only / writeOnce... ATDF: R / RW / W. Unknown: writable."""
    if access is None:
        return True
    access = access.lower()
    return "write" in access or access in ("rw", "w")


def _number(text: str | None, default: int = 0) -> int:
    """An SVD scaledNonNegativeInteger (0x1F, 31, #11111, 4k) or an ATDF number; *default* if absent or bad."""
    if not text:
        return default
    text = text.strip()
    scale = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30, "t": 1 << 40}.get(text[-1:].lower(), 1)
    if scale > 1:
        text = text[:-1]
    try:
        return (int(text[1:], 2) if text.startswith("#") else int(text, 0)) * scale
    except ValueError:
        return default


# ATDF

def _read_atdf(root: ET.Element, mcu: str) -> Description:
    device = root.find("devices/device")
    if device is None:
        raise DescriptionError("ATDF missing <device> element")
    found = device.get("name", "").lower()
    if found != mcu.lower():
        raise DescriptionError(f"ATDF device mismatch: expected '{mcu.lower()}', found '{found}'")

    segments = {}
    for seg in root.iterfind(".//memory-segment"):
        if seg.get("name"):
            page = seg.get("pagesize")
            segments[seg.get("name")] = Segment(seg.get("name"), seg.get("type"), _number(seg.get("start")),
                                                _number(seg.get("size")), _number(page) if page else None)

    modules: dict[str, Peripheral] = {}                  # a repeated module replaces the earlier one
    for module in root.iterfind(".//modules/module"):
        name = module.get("name")
        if not name:
            continue
        groups: dict[str, dict[str, Register]] = {}
        for group in module.iterfind(".//register-group"):
            if not group.get("name"):
                continue
            base = _number(group.get("offset"))
            groups[group.get("name")] = {
                reg.get("name"): Register(name, reg.get("name"), base + _number(reg.get("offset")),
                                          _number(reg.get("size"), 1), _writable(reg.get("rw")))
                for reg in group.iterfind(".//register") if reg.get("name")
            }
        registers = tuple(reg for regs in groups.values() for reg in regs.values())
        modules[name] = Peripheral(name, min((r.address for r in registers), default=0),
                                   module.get("caption") or "", registers)
    return Description(tuple(modules.values()), tuple(segments.values()))


# SVD

def _read_svd(root: ET.Element, mcu: str) -> Description:
    for element in root.iter():                          # namespaced files: <svd:register> -> <register>
        element.tag = element.tag.rsplit("}", 1)[-1]
    return Description(_SvdReader(root).peripherals(), ())


class _SvdReader:
    """One SVD file. Kept as a class only to share the peripheral index and device defaults."""

    def __init__(self, root: ET.Element) -> None:
        self._by_name: dict[str, ET.Element] = {}        # a repeated name replaces the earlier one
        for element in root.iter("peripheral"):
            if element.findtext("name"):
                self._by_name[element.findtext("name")] = element
        self._defaults = _properties(root, _SVD_DEFAULT_PROPERTIES)

    def peripherals(self) -> tuple[Peripheral, ...]:
        out = []
        for name, element in self._by_name.items():
            source = self._by_name.get(element.get("derivedFrom"), element)
            base = _number(element.findtext("baseAddress") or source.findtext("baseAddress"))
            description = element.findtext("description") or source.findtext("description") or ""
            properties = _properties(element, _properties(source, self._defaults))
            block = self._registers_block(element)
            for label, step in _dim(element):
                pname = _dim_name(name, label)
                registers: dict[str, Register] = {}
                if block is not None:
                    self._walk(block, pname, base + step, "", properties, registers)
                out.append(Peripheral(pname, base + step, description, tuple(registers.values())))
        return tuple(out)

    def _registers_block(self, peripheral: ET.Element) -> ET.Element | None:
        """A peripheral's <registers>: its own, else the one of the peripheral it derives from."""
        block = peripheral.find("registers")
        if block is None and peripheral.get("derivedFrom") in self._by_name:
            source = self._by_name[peripheral.get("derivedFrom")]
            if source is not peripheral:
                return self._registers_block(source)
        return block

    def _walk(self, container: ET.Element, peripheral: str, address: int, prefix: str,
              properties: dict, out: dict[str, Register]) -> None:
        for child in container:
            if child.tag not in ("register", "cluster"):
                continue
            child = self._derived(child, container)
            name = child.findtext("name")
            if not name:
                continue
            child_properties = _properties(child, properties)
            offset = _number(child.findtext("addressOffset"))
            for label, step in _dim(child):
                full = prefix + _dim_name(name, label)
                if child.tag == "cluster":
                    self._walk(child, peripheral, address + offset + step, full + "_", child_properties, out)
                    continue
                group = child.findtext("alternateGroup")
                key = f"{full}_{group}" if full in out and group else full
                out[key] = Register(peripheral, key, address + offset + step,
                                    max(1, _number(child_properties["size"], 32) // 8),
                                    _writable(child_properties["access"]))

    def _derived(self, element: ET.Element, scope: ET.Element, depth: int = 0) -> ET.Element:
        """*element* with what it derives from filled in; what it states itself wins."""
        reference = element.get("derivedFrom")
        if not reference:
            return element
        source = self._find(reference, scope)
        if source is None or depth > 8:
            log.warning("SVD: '%s' derives from '%s', which was not found; using it as written",
                        element.findtext("name"), reference)
            return element
        merged = copy.deepcopy(self._derived(source, scope, depth + 1))
        merged.attrib.pop("derivedFrom", None)
        own_tags = {child.tag for child in element}
        own_items = bool(own_tags & {"register", "cluster"})
        for child in list(merged):
            is_item = child.tag in ("register", "cluster")
            if (is_item and own_items) or (not is_item and child.tag in own_tags):
                merged.remove(child)                     # the derived element states its own
        for child in element:
            merged.append(copy.deepcopy(child))
        return merged

    def _find(self, reference: str, scope: ET.Element) -> ET.Element | None:
        """A register or cluster named in a derivedFrom: a sibling name, or a PERIPH.CLUSTER.REG path."""
        if "." not in reference:
            return next((c for c in scope if c.tag in ("register", "cluster") and c.findtext("name") == reference),
                        None)
        peripheral, *path = reference.split(".")
        node = self._registers_block(self._by_name[peripheral]) if peripheral in self._by_name else None
        for part in path:
            if node is None:
                return None
            node = next((c for c in node if c.tag in ("register", "cluster") and c.findtext("name") == part), None)
        return node


def _properties(element: ET.Element, inherited: dict) -> dict:
    """The register properties (size, access) of *element*: its own where it states them, else *inherited*."""
    return {key: element.findtext(key) or value for key, value in inherited.items()}


def _dim(element: ET.Element) -> list[tuple[str | None, int]]:
    """(index label, byte offset) of every element of a <dim> array; [(None, 0)] when not an array."""
    dim = element.findtext("dim")
    if dim is None:
        return [(None, 0)]
    count, increment = _number(dim), _number(element.findtext("dimIncrement"))
    labels = _dim_labels(element.findtext("dimIndex"), count)
    return [(label, position * increment) for position, label in enumerate(labels)]


def _dim_labels(text: str | None, count: int) -> list[str]:
    """<dimIndex> ("0,1,5", "2-4", "A-D") as labels; 0..count-1 when absent or inconsistent."""
    labels: list[str] = []
    if text:
        text = text.strip()
        numbers = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
        letters = re.fullmatch(r"([A-Za-z])\s*-\s*([A-Za-z])", text)
        if "," in text:
            labels = [part.strip() for part in text.split(",") if part.strip()]
        elif numbers:
            labels = [str(i) for i in range(int(numbers[1]), int(numbers[2]) + 1)]
        elif letters:
            labels = [chr(c) for c in range(ord(letters[1]), ord(letters[2]) + 1)]
    if len(labels) != count:
        if labels:
            log.warning("SVD dimIndex '%s' does not match dim=%d; using 0..%d.", text, count, count - 1)
        labels = [str(i) for i in range(count)]
    return labels


def _dim_name(name: str, label: str | None) -> str:
    """Put an array index into a name: X[%s] / X%s -> X3; a name without %s gets it appended."""
    if label is None:
        return name
    name = name.replace("[%s]", "%s")
    return name.replace("%s", label) if "%s" in name else name + label
