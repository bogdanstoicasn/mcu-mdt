"""Minimal ELF32 files built in memory, so ELF handling is tested without a toolchain."""

import struct


def elf_with_segments(segments: list[tuple[int, int, int, int]]) -> bytes:
    """Little-endian ARM ELF32 with only program headers: [(vaddr, paddr, filesz, memsz)]."""
    ehsize, phentsize = 52, 32
    header = struct.pack("<4sBBBBB7sHHIIIIIHHHHHH", b"\x7fELF", 1, 1, 1, 0, 0, b"\0" * 7,
                         2, 40, 1, 0, ehsize, 0, 0x05000000, ehsize, phentsize, len(segments), 40, 0, 0)
    data_offset = ehsize + phentsize * len(segments)
    phdrs, payload = b"", b""
    for vaddr, paddr, filesz, memsz in segments:
        phdrs += struct.pack("<IIIIIIII", 1, data_offset + len(payload), vaddr, paddr, filesz, memsz, 5, 4)
        payload += b"\xAA" * filesz
    return header + phdrs + payload


def elf_with_symbols(symbols: list[tuple[str, int, int]]) -> bytes:
    """ELF32 with only a symbol table: [(name, value, size)] as global data objects."""
    shstrtab = b"\0.shstrtab\0.strtab\0.symtab\0"
    strtab, entries = b"\0", struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    for name, value, size in symbols:
        entries += struct.pack("<IIIBBH", len(strtab), value, size, 0x11, 0, 0xFFF1)   # GLOBAL OBJECT, ABS
        strtab += name.encode() + b"\0"
    blobs, offset, layout = [shstrtab, strtab, entries], 52, []
    for blob in blobs:
        layout.append(offset)
        offset += len(blob)
    sections = [
        (0, 0, 0, 0, 0, 0, 0),
        (1, 3, layout[0], len(shstrtab), 0, 0, 0),           # .shstrtab
        (11, 3, layout[1], len(strtab), 0, 0, 0),            # .strtab
        (19, 2, layout[2], len(entries), 2, 1, 16),          # .symtab -> .strtab
    ]
    header = struct.pack("<4sBBBBB7sHHIIIIIHHHHHH", b"\x7fELF", 1, 1, 1, 0, 0, b"\0" * 7,
                         2, 40, 1, 0, 0, offset, 0, 52, 0, 0, 40, len(sections), 1)
    shdrs = b"".join(struct.pack("<IIIIIIIIII", name, kind, 0, 0, off, size, link, info, 1, entsize)
                     for name, kind, off, size, link, info, entsize in sections)
    return header + b"".join(blobs) + shdrs
