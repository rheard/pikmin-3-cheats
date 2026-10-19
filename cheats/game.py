"""
The game's program (`main`), read from your own copy of the game.

The mod's switches run the game's own words from elsewhere, and its patch changes some of them, so
the build has to know what they are. They are read here from the program file in the ExeFS of your
own copy rather than kept in this repository. The mod fits one build of the program only, that of
version 1.2.0 (`BUILD_ID`), and the build stops on any other.

Addresses count from `BASE`, as the game's code is numbered when it is read on its own: the
program's code starts there, and its constants at `TEXT_END`.
"""

from __future__ import annotations

import struct

from pathlib import Path

from cheats import arm
from cheats.errors import BuildError
from cheats.formats import nso

BUILD_ID = "D467F5AD367BBEE88C51F8C468143CF23486A44B"  # the program of Pikmin 3 Deluxe 1.2.0
BASE = 0x60000000
TEXT_END = 0x61100000
REACH = 0x1008  # a load of a constant counts up to 4 KB from the pc, which is 8 bytes past the load


class Game:
    """The game's program, as the loader lays it out in memory."""

    def __init__(self, path: str | Path):
        """
        Read the program from the ExeFS at `path`: the folder itself, or its file `main`.

        Raises:
            BuildError: If there is no program there, or it is not the build the mod is for.
        """
        path = Path(path)
        file = path / "main" if path.is_dir() else path
        if not file.is_file():
            raise BuildError(f"{path} does not look like Pikmin 3 Deluxe's ExeFS: there is no main in it")
        try:
            build, self.image = nso.unpack(file.read_bytes())
        except (ValueError, IndexError) as error:
            raise BuildError(f"{file} is not a program file the build can read: {error}") from error
        if build != BUILD_ID:
            raise BuildError(f"{file} is the program of another version: the mod is for version 1.2.0 ({BUILD_ID})")
        self._targets: set[int] | None = None
        self._made: dict[int, list[tuple[int, int]]] | None = None

    def word(self, address: int) -> int:
        """
        Read a word of the program, as it is before any patch.

        Returns:
            The word at `address`.

        Raises:
            BuildError: If the program has nothing there.
        """
        if address % 4 or not BASE <= address < BASE + len(self.image):
            raise BuildError(f"the game's program has no word at {address:#x}")
        return struct.unpack_from("<I", self.image, address - BASE)[0]

    def code(self) -> memoryview:
        """The program's code, as words."""
        return memoryview(self.image)[: TEXT_END - BASE].cast("I")

    def branch_targets(self) -> set[int]:
        """Every place one of the program's `b` or `bl` goes to (what is reached through a register is not here)."""
        if self._targets is None:
            self._targets = set()
            for k, word in enumerate(self.code()):
                if word >> 25 & 7 == 0b101 and word >> 28 != 0xF:
                    offset = word & 0xFFFFFF
                    if offset & 0x800000:
                        offset -= 1 << 24
                    self._targets.add(BASE + 4 * k + 8 + 4 * offset)
        return self._targets

    def addresses_made(self) -> dict[int, list[tuple[int, int]]]:
        """
        Every place the program makes an address the position-independent way.

        That is an `ldr rb, [pc, #k]` of a constant, then `add rb, pc, rb`: the constant is the address
        less the `add`'s own place, plus 8.

        Returns:
            For each address made, the places of the `ldr` and the `add` that make it.
        """
        if self._made is None:
            self._made = {}
            code = self.code()
            for k, add in enumerate(code):
                if (add & 0xFFFF0FF0) != 0xE08F0000 or k == 0:  # add rd, pc, rm (always)
                    continue
                ldr, rb = code[k - 1], add & 15
                if add >> 12 & 15 != rb or arm.pair_first(ldr) != rb:
                    continue
                at = BASE + 4 * k
                imm = ldr & 0xFFF
                pool = at + 4 + (imm if ldr >> 23 & 1 else -imm)
                made = (self.word(pool) + at + 8) & 0xFFFFFFFF
                self._made.setdefault(made, []).append((at - 4, at))
        return self._made

    def readers(self, address: int) -> list[int]:
        """The program's loads of the word at `address` as a constant beside the code (both ways from it)."""
        out = []
        for at in range(max(BASE, address - REACH), min(TEXT_END, address + REACH), 4):
            try:
                found = arm.literal(at, self.word(at))
            except BuildError:
                continue  # a load of the pc: no reader of a constant
            if found and found[0] <= address < found[0] + 4 * found[1]:
                out.append(at)
        return out
