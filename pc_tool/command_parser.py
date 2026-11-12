"""One command line in, one Command out, by the parameter rules in configs/commands.yaml.

Names resolve against the Target: register names through its registers, symbols through the
ELF's RAM symbols. Whether the command is allowed on this part is command_rules' job.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from pc_tool import MdtError, elf_symbols, target_model, wire_protocol

log = logging.getLogger(__name__)

COMMANDS_YAML = Path(__file__).parent / "configs" / "commands.yaml"


class CommandError(MdtError):
    """A command the tool refuses. code 2: the line can't be parsed; 3: not allowed on this target."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    type: str  # hex, decimal, address, register, bytes, choice
    field: str  # the Command field it fills: mem, address, length, data
    hint: str
    values: dict[str, int] | None = None  # choice: name -> number sent
    optional: bool = False
    mask_when: str | None = None  # after this choice, a REGISTER.FIELD is the field's bit mask
    implied_mask_when: str | None = None  # after this choice, a register name also sends mask_when


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    id: int | None  # None for a local command
    description: str
    params: tuple[Param, ...] = ()
    local: bool = False  # handled on the PC, never sent (EXIT, HELP, CLEAR)

    @property
    def usage(self) -> str:
        return " ".join(
            [self.name, *(f"[{p.hint}]" if p.optional else p.hint for p in self.params)]
        )


def load_specs(path: Path = COMMANDS_YAML) -> dict[str, CommandSpec]:
    """Every command of commands.yaml, by name, in file order."""
    commands = yaml.safe_load(path.read_text())["commands"]
    return {
        name: CommandSpec(
            name=name,
            id=entry.get("id"),
            description=entry.get("description", ""),
            params=tuple(Param(**param) for param in entry.get("params", [])),
            local=entry.get("local", False),
        )
        for name, entry in commands.items()
    }


def parse(
    line: str, specs: dict[str, CommandSpec], target: target_model.Target
) -> wire_protocol.Command | None:
    """The Command for *line*, None for a blank line; raise CommandError if it can't be parsed."""
    tokens = line.split()
    if not tokens:
        return None
    name, args = tokens[0].upper(), tokens[1:]
    spec = specs.get(name)
    if spec is None:
        raise CommandError(f"Unknown command: {name}", code=3)

    required = sum(not p.optional for p in spec.params)
    if not required <= len(args) <= len(spec.params):
        expected = (
            len(spec.params)
            if required == len(spec.params)
            else f"{required} to {len(spec.params)}"
        )
        raise CommandError(f"{name} expects {expected} parameter(s), got {len(args)}", code=2)

    fields, choices, implied_mask = {}, set(), None
    for param, text in zip(
        spec.params, args, strict=False
    ):  # optional parameters left out are absent
        value = _READERS[param.type](text, param, target)
        if param.type == "choice":
            choices.add(text.upper())
        if param.mask_when in choices:
            value = _mask(text, value, target)
        elif param.implied_mask_when in choices:
            implied_mask = _implied_mask(text, target)
        # every number goes into a 32-bit packet field (a slot, an address, a length, a word)
        if isinstance(value, int) and not 0 <= value <= 0xFFFFFFFF:
            raise CommandError(f"Invalid value '{text}' for {param.name}", code=2)
        fields[param.field] = value
    data = fields.get("data")
    if isinstance(data, int):
        data = data.to_bytes(wire_protocol.WORD_SIZE, "little")
    command = wire_protocol.Command(
        name=name,
        id=spec.id,
        mem=fields.get("mem"),
        address=fields.get("address", 0),
        length=fields.get("length"),
        data=data,
    )
    if implied_mask is not None:
        mask_param = next(p for p in spec.params if p.implied_mask_when)
        control = next(
            p.values for p in spec.params if p.values and mask_param.mask_when in p.values
        )
        command.then = wire_protocol.Command(
            name=name,
            id=spec.id,
            mem=control[mask_param.mask_when],
            address=command.address,
            data=implied_mask.to_bytes(wire_protocol.WORD_SIZE, "little"),
        )
    return command


def _mask(text: str, value: int, target: target_model.Target) -> int:
    """A mask: a REGISTER.FIELD gives the field's bits, a hex number is itself. Any other name is
    refused: the reader turned it into an address (USART1_SR -> 0x40013800), and that is no mask."""
    bitfield = target.registers.field_by_name(text)
    if bitfield:
        return bitfield[1].mask
    try:
        if int(text, 16) == value:
            return value
    except ValueError:
        pass
    raise CommandError(f"MASK takes a hex number or REGISTER.FIELD, not the name '{text}'", code=2)


def _implied_mask(text: str, target: target_model.Target) -> int | None:
    """The bits a register name stands for in a 4-byte watch: a field's, or the bytes of a register
    narrower than 4 (an AVR PINB would else also watch DDRB and PORTB). None: all 4 bytes."""
    if text in target.symbols:
        return None
    bitfield = target.registers.field_by_name(text)
    if bitfield:
        return bitfield[1].mask
    register = target.registers.by_name(text)
    if register is not None and register.size < wire_protocol.WORD_SIZE:
        return (1 << 8 * register.size) - 1
    return None


def _hex(text: str, param: Param, target: target_model.Target) -> int:
    try:
        return int(text, 16)
    except ValueError:
        raise CommandError(f"Invalid value '{text}' for {param.name}", code=2) from None


def _decimal(text: str, param: Param, target: target_model.Target) -> int:
    try:
        return int(text, 16 if text.lower().startswith("0x") else 10)
    except ValueError:
        raise CommandError(f"Invalid value '{text}' for {param.name}", code=2) from None


def _address(text: str, param: Param, target: target_model.Target) -> int:
    """A RAM symbol (a local static `name` matches its mangled `name.N`), a register (REGISTER, or
    REGISTER.FIELD for the register it is in), else a hex address. A name wins over hex: a
    variable `cafe` or the AVR register ADC is not an address."""
    if text not in target.symbols:
        register = _named_register(text, target)
        if register is not None:
            return register.address
    symbol = target.symbols.get(text) or _local_static(text, target)
    if symbol is not None:
        hint = elf_symbols.narrow_symbol_hint(symbol)
        if hint:
            log.warning(hint)
        return symbol.address
    try:
        return int(text, 16)
    except ValueError:
        pass
    register_name, _, field_name = text.rpartition(".")
    if target.registers.by_name(register_name):
        raise CommandError(f"Register {register_name} has no field '{field_name}'", code=2)
    if not target.symbols:
        raise CommandError(
            f"Cannot resolve symbol '{text}': no ELF loaded. "
            f"Add 'elf: path/to/firmware.elf' to build_info.yaml.",
            code=2,
        )
    raise CommandError(
        f"Symbol '{text}' not found in ELF symbol table. "
        f"Tip: only static/global variables are watchable. "
        f"Local variables live on the stack and have no fixed address.",
        code=2,
    )


def _local_static(text: str, target: target_model.Target) -> elf_symbols.Symbol | None:
    statics = [s for name, s in target.symbols.items() if name.startswith(text + ".")]
    if len(statics) > 1:
        raise CommandError(
            f"Ambiguous symbol '{text}': multiple local statics found: "
            f"{', '.join(s.name for s in statics)}. Use the full mangled name.",
            code=2,
        )
    if statics:
        log.info("Resolved '%s' -> '%s' (local static)", text, statics[0].name)
        return statics[0]
    return None


def _named_register(text: str, target: target_model.Target):
    bitfield = target.registers.field_by_name(text)
    return bitfield[0] if bitfield else target.registers.by_name(text)


def _register(text: str, param: Param, target: target_model.Target) -> int:
    """A register name, else a hex address. The name wins: the AVR register ADC is not 0xADC."""
    register = target.registers.by_name(text)
    if register is not None:
        return register.address
    try:
        return int(text, 16)
    except ValueError:
        raise CommandError(f"Unknown register name '{text}'", code=2) from None


def _bytes(text: str, param: Param, target: target_model.Target) -> bytes:
    digits = text[2:] if text.lower().startswith("0x") else text
    try:
        return bytes.fromhex(digits)
    except ValueError:
        raise CommandError(f"Invalid hex data for {param.name}: '{text}'", code=2) from None


def _choice(text: str, param: Param, target: target_model.Target) -> int:
    # Each command has its own names: BREAKPOINT 0 MASK must not send NEXT just because both are 3.
    value = next((v for name, v in param.values.items() if name.lower() == text.lower()), None)
    if value is None:
        raise CommandError(
            f"Invalid control value '{text}'. Expected one of: {', '.join(param.values)}", code=2
        )
    return value


_READERS: dict[str, Callable[[str, Param, target_model.Target], object]] = {
    "hex": _hex,
    "decimal": _decimal,
    "address": _address,
    "register": _register,
    "bytes": _bytes,
    "choice": _choice,
}
