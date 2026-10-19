"""
IPS patches of the game's program, which a loader applies before the game starts.

A patch is "PATCH", then records, then "EOF". A record is where its bytes go (three bytes, big
endian), how many there are (two bytes) and the bytes. A patch with anything 16 MB or more into the
program is written as IPS32 instead, whose records count in four bytes ("IPS32" ... "EEOF").
Records count from the start of the program file as a loader sees it, which is 0x100 bytes before
the start of its code.
"""

from __future__ import annotations

import struct

from cheats.errors import BuildError

HEADER = 0x100  # the program file's header, which records count from


def write(words: dict[int, int], base: int) -> bytes:
    """
    A patch holding `words`, by address, each run of them one record.

    Args:
        words: The words to write, by their address.
        base: The address the program's code starts at.

    Returns:
        The patch file's bytes.

    Raises:
        BuildError: If a run cannot be held in a record.
    """
    runs: list[tuple[int, bytes]] = []
    run: list[int] = []
    for address in [*sorted(words), None]:
        if run and address != run[-1] + 4:
            runs.append((run[0], b"".join(struct.pack("<I", words[a]) for a in run)))
            run = []
        if address is not None:
            run.append(address)
    wide = any(start - base + HEADER >= 1 << 24 for start, _ in runs)
    patch = bytearray(b"IPS32" if wide else b"PATCH")
    end = b"EEOF" if wide else b"EOF"
    for start, data in runs:
        offset = start - base + HEADER
        place = offset.to_bytes(4 if wide else 3, "big") if HEADER <= offset < 1 << 32 else end
        if place == end or len(data) > 0xFFFF:  # (a record may not begin with the bytes that end the patch)
            raise BuildError(f"the run of words at {start:#x} does not fit the patch format")
        patch += place + len(data).to_bytes(2, "big") + data
    return bytes(patch + end)
