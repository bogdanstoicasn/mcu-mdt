"""
TEMPORARY: the new target model answers like the old loader (deleted with pc_tool/loader.py in phase 3)

For every ATDF/SVD in pc_tool/mcu_db: every register name (qualified, bare, NAME[i], lower case,
unknown names) resolves to the same address, every address from each register's start to start+4
finds the same register, and the ATDF memory segments are equal. For the golden fixtures' builds,
load_target agrees with ConfigLoader on memory, limits, firmware range and watchable symbols.

Two differences are deliberate:
- bug 2: ATDF sizes are bytes, so a 16-bit AVR register now covers 2 addresses. The old reader
  divided them by 8 and lost the high byte.
- ATDF rw="RW" is writable. The old check ("write" in "rw") made those registers read-only; only the
  megaAVR 0-series files (not supported parts) use rw on registers.
"""

from pathlib import Path

from pc_tool import device_description, target_model
from pc_tool.loader import ConfigLoader, load_mcu_metadata
from pc_tool.parser import resolve_register_address
from pc_tool.validator import _find_register
from test.common.asserts import assert_eq
from test.pymdtest import parametrize

_DB = target_model.MCU_DB
_FILES = sorted(_DB.rglob("*.atdf")) + sorted(_DB.rglob("*.svd"))
_GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "fixtures"


@parametrize("path", [(p,) for p in _FILES])
def test_description_answers_like_the_old_loader(path):
    mcu = path.stem.lower()
    meta = load_mcu_metadata(mcu, str(path.relative_to(_DB)))
    description = device_description.read_description(path, mcu)
    registers = target_model.Registers(description.peripherals)

    if path.suffix == ".atdf":
        old = {k: (v["start"], v["size"], v["type"], int(v["pagesize"], 0) if v["pagesize"] else None)
               for k, v in meta["memories"].items()}
        assert_eq({s.name: (s.start, s.size, s.kind, s.page) for s in description.segments}, old, file=path.name)

    names = {"NOPE", "X_Y_Z", "PORT", "_", "USART0_UDR0", "GPIOA_", "TIM1_CCR[9]"}
    for module, entry in meta["modules"].items():
        for group in entry["register_groups"].values():
            for name in group["registers"]:
                names |= {name, f"{module}_{name}", name.lower(), f"{module}_{name}".lower()}
    wrong = [n for n in sorted(names)
             if resolve_register_address(n, meta) != getattr(registers.by_name(n), "address", None)]
    assert_eq(wrong, [], file=path.name, what="names resolving differently")

    wrong = []
    for register in registers._all:
        for address in range(register.address - 1, register.address + 5):
            found = _find_register(meta, address)
            old = None if found is None else (found[3], found[4], "write" in (found[2].get("rw") or "read-write").lower())
            new = registers.at(address)
            new = None if new is None else (new.address, new.address + new.size, new.writable)
            if old != new and not _avr_wider_register(path, old, new) and not _atdf_rw_fixed(path, old, new):
                wrong.append(f"0x{address:X}: old {old} new {new}")
    assert_eq(wrong[:5], [], file=path.name, what="addresses finding a different register")


def _atdf_rw_fixed(path, old, new) -> bool:
    """The same ATDF register, read-only before only because rw="RW" failed the old check."""
    return path.suffix == ".atdf" and old is not None and new is not None and old[:2] == new[:2] and new[2] and not old[2]


def _avr_wider_register(path, old, new) -> bool:
    """Bug 2: the same AVR register, now 2 bytes wide (and its high byte found where nothing was)."""
    if path.suffix != ".atdf" or new is None or new[1] - new[0] != 2:
        return False
    # nothing found before, or a register inside the widened one's 2 bytes (some files also list
    # the high byte separately; the 16-bit register now matches first)
    return old is None or new[0] <= old[0] < new[1]


@parametrize("part", [(p.name,) for p in sorted(_GOLDEN.iterdir())])
def test_load_target_agrees_with_config_loader(part):
    info = _GOLDEN / part / "build_info.yaml"
    old = ConfigLoader(str(info))
    new = target_model.load_target(info)
    old_mem = {name: (seg["start"], seg["size"], seg["type"]) for name, seg in old.mcu_metadata["memories"].items()}
    assert_eq({s.name: (s.start, s.size, s.kind) for s in new.segments}, old_mem, part=part)
    assert_eq((new.breakpoints, new.watchpoints), tuple(old.mcu_metadata["limits"].values()), part=part)
    fw = old.mcu_metadata["firmware"]
    assert_eq((new.firmware.start, new.firmware.start + new.firmware.size, new.firmware.page),
              (fw["start"], fw["end"], fw["page_size"]), part=part)
    assert_eq({n: s.address for n, s in new.symbols.items()}, {n: s.address for n, s in old.elf_symbols.items()},
              part=part)
