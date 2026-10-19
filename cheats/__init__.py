"""
A cheat menu for Pikmin 3 Deluxe, in the pause menu.

Builds the mod from the files of your own copy of the game: its RomFS, for the menu's layouts, and
its ExeFS, for the game's program, whose own words the menu's switches run. Nothing of the game is
kept in this repository.

It writes two mod folders:

* `Cheat Menu`: the menu (a Cheats tab in Other Settings, and Purple and White columns in the Onion
  menu), and a cheat file of the cheats that must be set before the game starts.
* `Debug Patches`: a cheat file of the game's debug menus and test maps, nothing else.
"""

from __future__ import annotations

import logging

from pathlib import Path

from cheats import compiler, layout, program
from cheats.errors import BuildError
from cheats.formats import atmosphere
from cheats.game import BASE, BUILD_ID, Game
from cheats.romfs import Mod, RomFs
from cheats.rows import ROWS

logger = logging.getLogger(__name__)

ENTRIES = Path(__file__).parent / "entries"
MOD_NAME, DEBUG_NAME = "Cheat Menu", "Debug Patches"


def cheat_file(name: str, patch: dict[int, int]) -> str:
    """
    One of the cheat files to copy into a mod folder.

    Returns:
        Its text, its lines ending as a loader expects.

    Raises:
        BuildError: If it is not a cheat file, or one of its entries writes a word the patch writes.
    """
    text = (ENTRIES / name).read_text(encoding="utf-8")
    for entry, words in atmosphere.entries(text, BASE).items():
        clash = sorted(set(words) & set(patch))
        if clash:
            raise BuildError(f"[{entry}] of {name} writes words the patch writes, from {clash[0]:#x}")
    return "\n".join(text.splitlines()) + "\n"


def build(romfs: str | Path, exefs: str | Path, out: str | Path) -> None:
    """
    Build both mod folders.

    Args:
        romfs: Pikmin 3 Deluxe's extracted RomFS.
        exefs: Its extracted ExeFS, or the program file `main` in it.
        out: The folder to write the two mod folders into.
    """
    romfs, game = RomFs(romfs), Game(exefs)
    compiler.llvm()  # (found before anything is built, or the build stops at once saying where it looked)
    out = Path(out)
    mod, debug = Mod(out / MOD_NAME), Mod(out / DEBUG_NAME)
    entries = atmosphere.entries((ENTRIES / "rows.txt").read_text(encoding="utf-8"), BASE)
    logger.info("the layouts: the Cheats tab, and the Onion menu's two more columns")
    layout.build(romfs, mod)
    logger.info("the code: the menu, and a switch for each word the rows' cheats change")
    patch = program.build(ROWS, entries, game, layout.scroll_bar(romfs), mod)
    logger.info("the cheat files")
    mod.write_cheats(BUILD_ID, cheat_file("menu.txt", patch))
    debug.write_cheats(BUILD_ID, cheat_file("debug.txt", patch))
    logger.info("done: the mod folders are in %s", out)
