"""
The code the mod adds to the game: the menu, and the switches that turn its rows' cheats on and off.

Both go in the mod's own program file (`exefs/subsdk1`), which the loader lays out after the game's
own. The patch of the game's program (`exefs/<build id>.ips`) points the game at them: the first
word of each function of the game's the menu hooks (`HOOKS`) becomes a branch to the menu's code,
and each word a switch stands in for a branch to its switch (`switches.py`).

The menu is C (`menu/menu.c`), compiled by LLVM. The hooks' few words and the switches are assembly
the build writes, since they hold the game's own words, read from your copy of it.
"""

from __future__ import annotations

import logging
import tempfile

from pathlib import Path
from typing import TYPE_CHECKING

from cheats import arm, compiler, rows
from cheats.errors import BuildError
from cheats.formats import ips, nso
from cheats.game import BASE, BUILD_ID
from cheats.switches import CODE_MOST, FAR, PROGRAM, PROGRAM_CODE, Switches

if TYPE_CHECKING:
    from cheats.game import Game
    from cheats.romfs import Mod
    from cheats.rows import Action, Row

logger = logging.getLogger(__name__)

MENU = Path(__file__).parent / "menu"
PROGRAM_FILE = "subsdk1"  # its name in the mod's exefs folder: the first the game does not have
PROGRAM_NAME = "CheatMenu"  # the module's name, which a loader prints as it loads it

# The game's functions the menu's code goes in front of, after or instead of: `after` runs the game's,
# then the menu's; `before` runs the menu's first, and the game's only if the menu's says it was not
# its button; `instead` runs the menu's, which calls the game's itself (`orig_<name>`).
HOOKS = (
    (0x60BE47FC, "setup", "after"),  # the pause window made: the tab's buttons found by name
    (0x60BE657C, "press", "before"),  # a button pressed (the window, its name)
    (0x60BE7E44, "redraw", "after"),  # the page drawn again for its tab
    (0x60BE9408, "frame", "instead"),  # each frame of the settings page
    (0x60BE9158, "back", "before"),  # B pressed
    (0x60BE57BC, "links", "instead"),  # the cursor's links between buttons
    (0x60E0909C, "save", "after"),  # the settings written (the save is committed next)
    (0x60E08F88, "load", "after"),  # the settings read
    (0x60DFF938, "spray_add", "instead"),  # the spray count changed (state, by how much, player)
    (0x60DFFBE0, "spray_get", "instead"),  # the spray count read (state, player)
    (0x60BBFBB4, "onion_setup", "after"),  # the Onion menu made: its columns found by number
    (0x60BC08A0, "onion_places", "after"),  # its boxes made places of the cursor
    (0x60BC0A18, "onion_links", "after"),  # the cursor's links, as it opens
    (0x60BC0B30, "onion_reset", "after"),  # the menu put back
    (0x60BC2D10, "onion_list", "after"),  # the types listed, a column each
    (0x60BC0E6C, "onion_frame", "instead"),  # each frame
    (0x60BC14EC, "onion_arrows", "instead"),  # its arrows' loops started and stopped, in step
    (0x60BC4C0C, "onion_press", "before"),  # a button pressed (the menu, its name, quiet)
    (0x60BC1ADC, "onion_change", "instead"),  # a column's count changed (the menu, the column, by, quiet)
    (0x60BC26C0, "onion_left", "instead"),  # Pikmin left in the Onion
    (0x60BC29EC, "onion_out", "instead"),  # Pikmin in the squad
    (0x60BC39B0, "onion_numbers", "after"),  # the columns' numbers written
    (0x60BC20F4, "onion_all", "instead"),  # Select All on or off
    (0x60BC4A1C, "onion_close", "after"),  # OK or Back pressed
    (0x60C7F404, "carry_speed", "after"),  # a carried thing's speed worked out
    (0x609F27B0, "carried", "before"),  # a carried thing's carriers' strength looked at, as one joins or lets go
)


def hook_source(game: Game) -> str:
    """
    The assembly of the hooks: for each hooked function, the words that run the menu's code with it,
    and `orig_<name>`, the function's own first word followed by a branch to the rest of it.

    Returns:
        The assembly.

    Raises:
        BuildError: If a hooked function is out of reach, or its first word cannot run elsewhere.
    """
    out = ["    .syntax unified", "    .arm", '    .section .text.hooks, "ax"', "    .balign 4"]
    for address, name, how in HOOKS:
        first = game.word(address)
        if address < FAR:
            raise BuildError(f"{address:#x}: a hooked function out of a branch's reach of the program file")
        # its first word runs in the program file: a push, or any word that neither branches nor reads the pc
        if first & 0xFFFF0000 != 0xE92D0000 and (arm.branch_target(address, first) is not None or arm.reads_pc(first)):
            raise BuildError(f"{address:#x} begins with a word that cannot simply be run elsewhere")
        if how == "after":
            out += [
                "",
                f"    .global hook_{name}",
                f"    .type   hook_{name}, %function",
                f"hook_{name}:                    @ the game's, then menu_{name}",
                "    push    {r4, lr}",
                "    mov     r4, r0",
                f"    bl      orig_{name}",
                "    mov     r0, r4",
                "    pop     {r4, lr}",
                f"    b       menu_{name}",
            ]
        elif how == "before":
            out += [
                "",
                f"    .global hook_{name}",
                f"    .type   hook_{name}, %function",
                f"hook_{name}:                    @ menu_{name} first; the game's unless it was the menu's",
                "    push    {r0-r3, r12, lr}",
                "    vpush   {d0-d7}",
                f"    bl      menu_{name}",
                "    vpop    {d0-d7}",
                "    cmp     r0, #0",
                "    pop     {r0-r3, r12, lr}",
                "    bxne    lr",
                f"    b       orig_{name}",
            ]
        out += [
            f"    .global orig_{name}",
            f"    .type   orig_{name}, %function",
            f"orig_{name}:                    @ its own first word, then the rest of it",
            f"    .word   0x{first:08X}",
            f"    b       LAB_{address + 4:08x}",
        ]
    return "\n".join(out) + "\n"


def entry_point(name: str, how: str) -> str:
    """What the patch branches to from a hooked function: the menu's own function, or the hook's words."""
    return f"menu_{name}" if how == "instead" else f"hook_{name}"


def compile_menu(header: str, hooks: str, assembly: str, veneers: dict[int, str | int]) -> compiler.Built:
    """
    Compile the menu, the hooks and the switches, and link them to run where the loader puts them.

    The variables go a page past the constants of the program file, which depends on the size of the
    code: so the code is linked once to know its size, and again if its variables are not where the
    first link put them.

    Returns:
        The code built.

    Raises:
        BuildError: If it does not build, or does not fit.
    """
    logger.info("  with %s", compiler.version())
    names = {f"VEN_{target:08x}": at for at, target in veneers.items() if isinstance(target, int)}
    script = (MENU / "game.ld").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as work:
        folder = Path(work)
        (folder / "rows.h").write_text(header, encoding="utf-8")
        (folder / "hooks.S").write_text(hooks, encoding="utf-8")
        (folder / "switches.S").write_text(assembly, encoding="utf-8")
        sources = [MENU / "menu.c", folder / "hooks.S", folder / "switches.S"]
        guess = PROGRAM + 0x10000
        built = compiler.build(sources, PROGRAM_CODE, guess, include=[folder], script=script, names=names)
        place = PROGRAM + nso.data_place(PROGRAM_NAME, len(built.code), PROGRAM_CODE - PROGRAM)
        if place != guess:
            again = compiler.build(sources, PROGRAM_CODE, place, include=[folder], script=script, names=names)
            if len(again.code) != len(built.code):
                raise BuildError("the code changed size when its variables moved")
            built = again
    if built.data_at != place and (built.data or built.zeroed):
        raise BuildError("the variables are not where the program file puts them")
    if PROGRAM_CODE + len(built.code) > PROGRAM + CODE_MOST:
        raise BuildError("the code is too long: switches far into it would be out of reach of the game's code")
    return built


def build(
    menu_rows: tuple[Row | Action, ...],
    entries: dict[str, dict[int, int]],
    game: Game,
    bar: dict[str, float],
    mod: Mod,
) -> dict[int, int]:
    """
    Write the patch and the program file into the mod folder.

    Args:
        menu_rows: The rows of the tab.
        entries: The rows' entries, by name: the words each writes, by address.
        game: The game's program.
        bar: The scroll bar's sizes and places (`layout.scroll_bar`).
        mod: The mod folder.

    Returns:
        The words the patch writes, by address.

    Raises:
        BuildError: If a switch cannot be made, or the code does not build or fit.
    """
    switches = Switches(menu_rows, entries, game)
    assembly = switches.source()
    veneers = switches.veneers()
    built = compile_menu(rows.header(menu_rows, entries, game, bar), hook_source(game), assembly, veneers)
    symbols = built.symbols
    words = {address: arm.branch(address, symbols[entry_point(name, how)]) for address, name, how in HOOKS}
    into = {target: at for at, target in veneers.items() if isinstance(target, str)}
    for address in switches.addresses():
        if address in words:
            raise BuildError(f"{address:#x} is both a hooked function and a switch")
        label = f"sw_{address:08x}"
        words[address] = arm.branch(address, into[label] if address < FAR else symbols[label])
    for at, target in veneers.items():
        if at in words:
            raise BuildError(f"the veneer at {at:#x} is a word of the patch already")
        words[at] = arm.branch(at, symbols[target] if isinstance(target, str) else target)
    mod.write_patch(BUILD_ID, ips.write(words, BASE))
    mod.write_program(
        PROGRAM_FILE,
        nso.build(PROGRAM_NAME, built.code, PROGRAM_CODE - PROGRAM, built.data, built.zeroed),
    )
    logger.info(
        "  %d switches (%d of them for words of two rows), %d hooks and %d veneers; %d bytes of code",
        len(switches.addresses()),
        len(switches.shared),
        len(HOOKS),
        len(veneers),
        len(built.code),
    )
    return words
