"""
SARC, the archive inside most of the game's `.szs` files.

Pikmin 3 Deluxe keeps almost everything in `.szs` files: a Yaz0 stream (`cheats.formats.yaz0`)
around a little-endian SARC archive. An archive may hold archives: each layout archive
(`lyt/common.szs`, `lyt/parts.szs`) is an archive of one file, itself an archive of the layouts,
their animations and their textures.

An archive is three tables and then the files' bytes::

    SARC  0x14 bytes: its own length (u16 at 4), the byte order mark (FF FE for little-endian, at 6),
          the size of the archive (u32 at 8) and where the files' bytes start (u32 at 0xC)
    SFAT  12 bytes holding the count of files (u16 at 6) and the multiplier of the name hash (u32
          at 8), then a 16-byte node for each file: the hash of its name, its attributes, and the
          start and end of its bytes
    SFNT  8 bytes, then the names, each ending in a zero byte and starting on a multiple of four

A node's start and end count from where the files' bytes start. Attributes with the top byte set
mean the file has a name, found in the name table at four times the low 24 bits. A file without
one is known only by its hash and is listed here as `#` and the hash in hex.

`Sarc` reads a decompressed archive. `replace` and `rebuild_aligned` give a copy of one with files
changed; `rebuild_aligned` also gives the edits that make the copy from the stock archive, which
`yaz0.splice` packs without compressing the whole archive again.
"""

from __future__ import annotations

import struct

from cheats.formats.yaz0 import Edit, apply_edits, same_length_edits

NODE = 16  # the size of one file's entry in the SFAT table
LARGEST = 0x2000  # the largest boundary a file of the game's archives starts on
PAGE = 0x1000  # the boundary a texture file starts on


class Sarc:
    """
    An archive read from its decompressed bytes.

    Attributes:
        data: The archive's bytes.
        entries: (name, start, end) for each file, its start and end in `data`.
        endian: The `struct` prefix for its numbers.
        data_start: Where the files' bytes start.
        nodes: Where the first file's SFAT node is.
    """

    def __init__(self, data: bytes) -> None:
        """
        Read the archive's tables.

        Raises:
            ValueError: If `data` is not an archive.
        """
        self.data = plain = bytes(data)
        if plain[:4] != b"SARC":
            raise ValueError("not a SARC archive")
        self.endian = endian = "<" if plain[6:8] == b"\xff\xfe" else ">"
        sfat, _, _, self.data_start = struct.unpack_from(f"{endian}HHII", plain, 4)
        if plain[sfat : sfat + 4] != b"SFAT":
            raise ValueError("no SFAT")
        count = struct.unpack_from(f"{endian}H", plain, sfat + 6)[0]
        self.nodes = sfat + 12
        sfnt = self.nodes + NODE * count
        if plain[sfnt : sfnt + 4] != b"SFNT":
            raise ValueError("no SFNT")
        names = sfnt + 8
        self.entries: list[tuple[str, int, int]] = []
        for index in range(count):
            name_hash, attributes, start, end = struct.unpack_from(f"{endian}IIII", plain, self.nodes + NODE * index)
            if attributes >> 24:
                at = names + (attributes & 0xFFFFFF) * 4
                entry = plain[at : plain.index(b"\0", at)].decode("utf-8", errors="replace")
            else:
                entry = f"#{name_hash:08x}"
            self.entries.append((entry, self.data_start + start, self.data_start + end))

    def files(self) -> dict[str, bytes]:
        """The bytes of every file, by name."""
        return {name: self.data[start:end] for name, start, end in self.entries}

    def span(self, name: str) -> tuple[int, int]:
        """
        Find one file inside the archive, for editing it where it lies.

        Returns:
            Its (start, end) in `data`.

        Raises:
            KeyError: If the archive has no file of that name.
        """
        for entry, start, end in self.entries:
            if entry == name:
                return start, end
        raise KeyError(name)


def replace(plain: bytes, name: str, new: bytes) -> bytes:
    """
    Replace one file of an archive.

    The file may change size only when nothing follows it in the archive, as is the case for the
    one file of a layout archive and for the table of the buttons' sounds; its end and the
    archive's size are then updated.

    Returns:
        The new archive.

    Raises:
        ValueError: If the file changes size and other files follow it.
    """
    arc = Sarc(plain)
    start, end = arc.span(name)
    out = bytearray(plain[:start]) + bytearray(new) + bytearray(plain[end:])
    if len(new) != end - start:
        if end != len(plain):
            raise ValueError(f"{name} cannot change size: other files follow it")
        for index, (entry, _, _) in enumerate(arc.entries):
            if entry == name:
                node = arc.nodes + NODE * index
                struct.pack_into(f"{arc.endian}I", out, node + 12, start + len(new) - arc.data_start)
        struct.pack_into(f"{arc.endian}I", out, 8, len(out))
    return bytes(out)


def rebuild_aligned(plain: bytes, changes: dict[str, bytes]) -> tuple[bytes, list[Edit]]:
    """
    Replace some files of an archive with others of any length, every file keeping its boundary.

    The table of files and their names is kept, and the files' bytes are laid out again in the
    order they were in. Each file starts on the boundary it starts on in the stock archive: the
    smallest of 0x10, 0x20 ... 0x2000 that puts it where it is after the file before it (most files
    are on 0x10, a texture file on 0x1000). Unchanged, the stock archive comes back byte for byte,
    since the game's archives are laid out so.

    Returns:
        The new archive, and the edits that make it from the stock one, in order and apart (each
        moved file only the zeros before it, each changed file its new bytes).

    Raises:
        KeyError: If `changes` names a file the archive does not have.
        ValueError: If a file does not start on any such boundary, or the edits come out wrong.
    """
    arc = Sarc(plain)
    names = {name for name, _, _ in arc.entries}
    missing = [name for name in changes if name not in names]
    if missing:
        raise KeyError(f"archive has no file named {', '.join(missing)}")
    head = bytearray(plain[: arc.data_start])
    body = bytearray()
    edits: list[Edit] = []
    stock_end = arc.data_start  # where the file before this one ends in the stock archive
    for index in sorted(range(len(arc.entries)), key=lambda index: arc.entries[index][1]):
        name, start, end = arc.entries[index]
        gap = start - stock_end
        boundary = 0x10
        while boundary <= LARGEST and (-(stock_end - arc.data_start) % boundary) != gap:
            boundary <<= 1
        if boundary > LARGEST:
            raise ValueError(f"{name} does not start on a boundary after the file before it")
        if name.endswith(".bntx") and not (start - arc.data_start) % PAGE:
            boundary = max(boundary, PAGE)  # a texture file on its page, whatever came before it
        new = changes.get(name, plain[start:end])
        pad = -len(body) % boundary
        at = len(body) + pad
        if pad != gap:
            edits.append((stock_end, start, bytes(pad)))  # only the zeros before it: a file moved is not a file changed
        if name in changes:
            edits.append((start, end, bytes(new)))
        body += bytes(pad) + bytes(new)
        struct.pack_into(f"{arc.endian}II", head, arc.nodes + NODE * index + 8, at, at + len(new))
        stock_end = end
    if stock_end != len(plain):
        edits.append((stock_end, len(plain), b""))
    struct.pack_into(f"{arc.endian}I", head, 8, len(head) + len(body))
    out = bytes(head) + bytes(body)
    edits = same_length_edits(plain[: arc.data_start], head) + [
        (lo, hi, made) for lo, hi, made in edits if plain[lo:hi] != made
    ]
    if apply_edits(plain, edits) != out:
        raise ValueError("the edits do not make the archive")
    return out, edits
