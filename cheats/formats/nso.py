"""
Program files (NSO): the game's own, read for its words, and one of the mod's own, written.

A Switch game is several program files that its loader lays out one after another: this game's
`rtld`, `main`, `subsdk0` and `sdk`. A mod folder's `exefs` may add one more, `subsdk1` to
`subsdk9`, and the loader lays it out with the rest. Its code can then be as long as it needs to
be, and the game's own code reaches it with an ordinary branch.

A program file is a header of 0x100 bytes and three parts, each at the start of a page of memory:
code, constants and variables, followed in memory by zeroed memory. The header gives each part's
place in the file and in memory, its size, whether it is packed (LZ4) and its SHA-256, and the
program's build ID.

What a program file of a mod's own must hold is what the game's own `rtld` asks of each one it
finds:

* At the start of its code, the place of the module's header (`MOD0`), which `rtld` stops for good
  without. The game's own files have the header 8 bytes in; so has this.
* Writable memory where the header says, for what `rtld` keeps of the module (0x68 bytes): here,
  the zeroed memory after the module's variables, which `rtld` clears where the header says.
* A table of linking with a table of symbols by their hash, which `rtld`'s search divides by the
  number of rows: so this has one row, empty, and nothing is found in it. Nothing in it is to be
  moved or joined, and there is no function to start, so `rtld` passes it over.

And what a loader asks: each part at the start of a page of memory, the code first, and the
constants beginning with the module's name. Nothing is packed.
"""

from __future__ import annotations

import hashlib
import struct

PAGE = 0x1000
HEADER = 0x100  # the header; the module's name field follows it (one 0 byte, as in the game's), then the parts
MOD0_AT = 8  # where the module's header is, as in the game's own files
RECORD = 0x68  # what rtld keeps of a module, in the zeroed memory the header names
VARIABLES = 0x10  # a module without variables still has a few zero bytes of them, so that no part is empty
DT_NULL, DT_HASH, DT_STRTAB, DT_SYMTAB, DT_STRSZ, DT_SYMENT = 0, 4, 5, 6, 10, 11


def align(n: int, to: int = PAGE) -> int:
    """`n` rounded up to a multiple of `to`."""
    return (n + to - 1) // to * to


def unpack(data: bytes) -> tuple[str, bytes]:
    """
    Read one of the game's program files.

    Returns:
        Its build ID (40 hexadecimal digits), and its memory as the loader lays it out from the start
        of its code, its zeroed memory left out.

    Raises:
        ValueError: If it is not a program file, or a part does not unpack to its size.
    """
    if data[:4] != b"NSO0":
        raise ValueError("not a program file")
    flags = struct.unpack_from("<I", data, 0xC)[0]
    parts = []
    for k in range(3):
        offset, at, size = struct.unpack_from("<III", data, 0x10 + 0x10 * k)
        stored = data[offset : offset + struct.unpack_from("<I", data, 0x60 + 4 * k)[0]]
        part = _lz4(stored, size) if flags >> k & 1 else stored[:size]
        parts.append((at, part))
    image = bytearray(max(at + len(part) for at, part in parts))
    for at, part in parts:
        image[at : at + len(part)] = part
    return data[0x40:0x54].hex().upper(), bytes(image)


def _lz4(src: bytes, size: int) -> bytes:
    """
    Unpack one LZ4 block: runs of plain bytes, each followed by a copy of earlier output.

    Returns:
        The bytes unpacked.

    Raises:
        ValueError: If it does not unpack to `size` bytes.
    """
    out = bytearray()
    p, n = 0, len(src)
    while p < n:
        token = src[p]
        p += 1
        run = token >> 4
        if run == 15:
            while src[p] == 255:
                run += 255
                p += 1
            run += src[p]
            p += 1
        out += src[p : p + run]
        p += run
        if p >= n:
            break
        back = src[p] | src[p + 1] << 8
        p += 2
        length = (token & 15) + 4
        if token & 15 == 15:
            while src[p] == 255:
                length += 255
                p += 1
            length += src[p]
            p += 1
        start = len(out) - back
        if back >= length:
            out += out[start : start + length]
        else:  # the copy overlaps what it writes: the bytes repeat every `back`
            repeat = out[start:]
            whole, rest = divmod(length, back)
            out += repeat * whole + repeat[:rest]
    if len(out) != size:
        raise ValueError(f"a part of the program unpacked to {len(out)} bytes, not {size}")
    return bytes(out)


def data_place(name: str, code_size: int, at: int) -> int:
    """Where `build` puts the variables of a module named `name` whose code is `code_size` bytes `at` bytes in."""
    return align(align(at + code_size) + len(_constants(name, 0)[0]))


def _constants(name: str, ro_at: int) -> tuple[bytearray, dict[str, int]]:
    """
    The constants part: the module's name, its table of linking, an empty table of symbols by hash,
    one empty symbol, an empty name, and an empty table of what unwinds a call.

    Returns:
        The part's bytes, and where in memory each table is.
    """
    label = name.encode("ascii")
    ro = bytearray(struct.pack("<II", 0, len(label)) + label)
    ro += bytes(-len(ro) % 8)
    dynamic = ro_at + len(ro)
    ro += bytes(8 * 6)
    hashes = ro_at + len(ro)
    ro += struct.pack("<4I", 1, 1, 0, 0)  # one row, one chain, both empty
    symbols = ro_at + len(ro)
    ro += bytes(16)  # symbol 0, the one every table begins with
    strings = ro_at + len(ro)
    ro += b"\0"
    ro += bytes(-len(ro) % 4)
    unwind = ro_at + len(ro)
    frames = unwind + 12
    # version 1; where the frames are, as a signed 4-byte distance from that field; the count; the table's kind
    ro += bytes([1, 0x1B, 0x03, 0x3B]) + struct.pack("<iI", frames - (unwind + 4), 0)
    unwind_end = ro_at + len(ro)  # (the module header names that table alone, as the game's do)
    ro += bytes(4)  # the frames: none, and the word that ends them
    entries = (DT_HASH, hashes, DT_STRTAB, strings, DT_SYMTAB, symbols, DT_STRSZ, 1, DT_SYMENT, 16, DT_NULL, 0)
    struct.pack_into("<12i", ro, dynamic - ro_at, *entries)
    return ro, {"dynamic": dynamic, "symbols": symbols, "strings": strings, "unwind": unwind, "unwind_end": unwind_end}


def build(name: str, code: bytes, at: int, data: bytes = b"", zeroed: int = 0) -> bytes:
    """
    A program file of the mod's own.

    Args:
        name: The module's name, which a loader prints as it loads it.
        code: Its code and constants, placed `at` bytes from the module's start (past its header).
        at: Where the code goes, a multiple of 4.
        data: Its variables, which go at `data_place(name, len(code), at)`.
        zeroed: How many bytes of zeroed memory its variables go on into.

    Returns:
        The file's bytes.

    Raises:
        ValueError: If the code does not fit after the header.
    """
    if at % 4 or at < MOD0_AT + 0x1C or len(code) % 4 or not code:
        raise ValueError(f"code of {len(code)} bytes at {at:#x} does not fit after the header")
    text_size = at + len(code)
    ro_at = align(text_size)
    ro, places = _constants(name, ro_at)
    data_at = align(ro_at + len(ro))
    variables = bytes(data) + bytes(-len(data) % 4)
    variables += bytes(max(0, VARIABLES - len(variables)))
    zeroed_at = data_at + len(variables)
    record = align(max(zeroed_at, data_at + len(data) + zeroed), 8)  # rtld's record, after the zeroed variables
    zeroed_end = align(record + RECORD)
    # the code, its first two words "0, and the header 8 bytes in", then the header
    text = bytearray(text_size)
    struct.pack_into("<II", text, 0, 0, MOD0_AT)
    text[MOD0_AT : MOD0_AT + 4] = b"MOD0"
    struct.pack_into(
        "<6i",
        text,
        MOD0_AT + 4,
        places["dynamic"] - MOD0_AT,
        zeroed_at - MOD0_AT,
        zeroed_end - MOD0_AT,
        places["unwind"] - MOD0_AT,
        places["unwind_end"] - MOD0_AT,
        record - MOD0_AT,
    )
    text[at:] = code
    parts = [bytes(text), bytes(ro), variables]
    head = bytearray(HEADER)
    head[0:4] = b"NSO0"
    offset = HEADER + 1
    for k, (part, part_at) in enumerate(zip(parts, (0, ro_at, data_at), strict=True)):
        struct.pack_into("<III", head, 0x10 + 0x10 * k, offset, part_at, len(part))
        struct.pack_into("<I", head, 0x60 + 4 * k, len(part))
        head[0xA0 + 0x20 * k : 0xC0 + 0x20 * k] = hashlib.sha256(part).digest()
        offset += len(part)
    struct.pack_into("<I", head, 0x1C, HEADER)  # the module's name field: one 0 byte
    struct.pack_into("<I", head, 0x2C, 1)
    struct.pack_into("<I", head, 0x3C, zeroed_end - zeroed_at)
    head[0x40:0x54] = hashlib.sha256(b"".join(parts)).digest()[:20]  # its build ID: 20 bytes and 12 of 0, as the game's
    struct.pack_into("<6I", head, 0x88, 0, 0, places["strings"] - ro_at, 1, places["symbols"] - ro_at, 16)
    return bytes(head) + b"\0" + b"".join(parts)
