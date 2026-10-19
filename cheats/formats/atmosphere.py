"""
Cheat files, in the format of Atmosphère's cheat engine.

A cheat file is a list of entries, each a name in square brackets followed by lines of eight-digit
hexadecimal words. The entries here use one kind of line only, a write of a constant into the
game's program::

    04000000 AAAAAAAA VVVVVVVV             the word V written at A
    08000000 AAAAAAAA HHHHHHHH LLLLLLLL    two words: L at A, and H at A + 4

A counts from the start of the program's code. A loader lists the entries for the player to tick.
"""

from __future__ import annotations

import re

from cheats.errors import BuildError

WORD = re.compile(r"[0-9A-Fa-f]{8}")


def entries(text: str, base: int) -> dict[str, dict[int, int]]:
    """
    Read the entries of a cheat file.

    Args:
        text: The file's text.
        base: What the returned addresses count from: the address the program's code starts at.

    Returns:
        For each entry, by name, the words it writes by address, in the order it writes them.

    Raises:
        BuildError: For a line that is not a write of a constant, or one a loader would not read.
    """
    out: dict[str, dict[int, int]] = {}
    name = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("["):
            if not line.endswith("]") or len(line) < 3:
                raise BuildError(f"line {number} of a cheat file is not a whole entry name: {line}")
            name = line[1:-1]
            if name in out:
                raise BuildError(f"the cheat file has two entries named [{name}]")
            out[name] = {}
            continue
        words = line.split()
        if name is None or not all(WORD.fullmatch(word) for word in words):
            raise BuildError(f"line {number} of a cheat file is not a line of an entry: {line}")
        width = {"04000000": 4, "08000000": 8}.get(words[0])
        if width is None or len(words) != (3 if width == 4 else 4):
            raise BuildError(f"line {number} of a cheat file is not a write of a constant: {line}")
        address = base + int(words[1], 16)
        if width == 4:
            out[name][address] = int(words[2], 16)
        else:
            out[name][address] = int(words[3], 16)
            out[name][address + 4] = int(words[2], 16)
    return out
