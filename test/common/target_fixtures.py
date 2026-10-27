"""Small Targets for tests, built in a line instead of loaded from a build."""

from pc_tool import target_model
from pc_tool.device_description import Peripheral, Register, Segment


def ram(start: int = 0x20000000, size: int = 0x5000) -> Segment:
    return Segment("IRAM", "ram", start, size)


def flash(start: int = 0x08000000, size: int = 0x10000, page: int | None = 0x400) -> Segment:
    return Segment("FLASH", "flash", start, size, page)


def eeprom(start: int = 0x810000, size: int = 0x400) -> Segment:
    return Segment("EEPROM", "eeprom", start, size)


def peripheral(name: str, *registers: tuple[str, int, int, bool]) -> Peripheral:
    """A peripheral from (register name, address, size in bytes, writable)."""
    regs = tuple(Register(name, reg, address, size, writable) for reg, address, size, writable in registers)
    return Peripheral(name, min(r.address for r in regs), "", regs)


def usart1(base: int = 0x40013800, writable: bool = True) -> Peripheral:
    """An STM32-style USART: SR, DR, BRR, 32 bits each."""
    return peripheral("USART1", ("SR", base, 4, writable), ("DR", base + 4, 4, writable), ("BRR", base + 8, 4, writable))


# AVR-like: register addresses are data-space addresses, 16-bit registers are 2 bytes (ATmega48 values)
AVR_PERIPHERALS = (
    peripheral("USART", ("UCSR0A", 0xC0, 1, True), ("UCSR0B", 0xC1, 1, True), ("UCSR0C", 0xC2, 1, True),
               ("UBRR0", 0xC4, 2, True), ("UDR0", 0xC6, 1, True)),
    peripheral("TWI", ("TWBR", 0xB8, 1, True), ("TWSR", 0xB9, 1, True), ("TWDR", 0xBB, 1, True),
               ("TWCR", 0xBC, 1, True)),
)


def make_target(segments=(), peripherals=(), firmware: Segment | None = None, symbols: dict | None = None,
                breakpoints: int = 4, watchpoints: int = 4) -> target_model.Target:
    return target_model.Target(
        mcu="test", platform="STM32", port="loop://", baudrate=19200, uart_idle=False,
        segments=tuple(segments), peripherals=tuple(peripherals), registers=target_model.Registers(tuple(peripherals)),
        symbols=symbols or {}, breakpoints=breakpoints, watchpoints=watchpoints, firmware=firmware, build_info={},
    )


def firmware(start: int = 0x08000000, size: int = 0x3000, page: int = 0x400) -> Segment:
    """A running image in the first *size* bytes of flash: pages below start + size are protected."""
    return Segment("firmware", "flash", start, size, page)
